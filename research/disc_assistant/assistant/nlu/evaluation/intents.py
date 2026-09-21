"""Train-only nearest exemplars, development-only thresholds, untouched test scoring."""
from research.disc_assistant.assistant.nlu.intents import AlbumIntent, music_from_dict

from dataclasses import asdict
import json
from pathlib import Path

from research.disc_assistant.assistant.nlu.interpreter import RuleInterpreter, InterpretationContext
from research.disc_assistant.assistant.nlu.intents import Intent, ControlIntent, LanguageIntent
from research.disc_assistant.assistant.nlu.evaluation.encoder import digest

LABELS = ('pause', 'resume', 'stop', 'next', 'previous', 'play', 'language', 'reject')
THRESHOLDS = (.35, .45, .55, .65, .75, .85, .95, 1.01)
MARGINS = (0, .05, .10, .15)


def load_corpus(path):
    data = json.loads(Path(path).read_text())
    if data.get('version') != 1 or not isinstance(data.get('cases'), list):
        raise ValueError('invalid intent corpus')
    seen, texts = set(), set()
    for row in data['cases']:
        if (row['id'] in seen or row['label'] not in LABELS or row['locale'] not in ('ru', 'en')
                or row['split'] not in ('train', 'development', 'test') or not row['text'].strip()):
            raise ValueError('invalid or duplicate intent case')
        key = (row['locale'], ' '.join(row['text'].casefold().split()))
        if key in texts:
            raise ValueError('duplicate text would leak across splits')
        seen.add(row['id']); texts.add(key)
        if 'reference_span' in row:
            start, end = row['reference_span']
            if row['text'][start:end] != row['intent']['query']:
                raise ValueError('invalid reference span')
    for locale in ('ru', 'en'):
        for split in ('train', 'development', 'test'):
            if {r['label'] for r in data['cases'] if r['locale'] == locale and r['split'] == split} != set(LABELS):
                raise ValueError('each locale/split needs every label')
    return data


def nearest(similarities, training):
    scores = {label: max(float(score) for score, row in zip(similarities, training) if row['label'] == label)
              for label in LABELS}
    ordered = sorted(scores, key=lambda label: (-scores[label], label))
    first, second = ordered[:2]
    return {'label': first, 'score': scores[first], 'runner_up': second,
            'margin': scores[first] - scores[second]}


def accepted(evidence, threshold, margin):
    return evidence['label'] if evidence['score'] >= threshold and evidence['margin'] >= margin else 'reject'


def metrics(rows, predictions):
    confusion = {truth: {guess: 0 for guess in LABELS} for truth in LABELS}
    for row, pred in zip(rows, predictions):
        confusion[row['label']][pred] += 1
    f1 = {}
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[t][label] for t in LABELS if t != label)
        fn = sum(confusion[label][p] for p in LABELS if p != label)
        f1[label] = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0
    negative = sum(row['label'] == 'reject' for row in rows)
    false = sum(row['label'] == 'reject' and p != 'reject' for row, p in zip(rows, predictions))
    positives = len(rows)-negative
    return {'total': len(rows), 'correct': sum(row['label'] == p for row, p in zip(rows, predictions)),
            'macro_f1': sum(f1.values()) / len(f1), 'per_label_f1': f1, 'confusion': confusion,
            'negative_count': negative, 'false_activations': false,
            'command_count': positives,
            'correct_commands': sum(row['label'] == p and p != 'reject' for row, p in zip(rows, predictions)),
            'rejected_commands': sum(row['label'] != 'reject' and p == 'reject' for row, p in zip(rows, predictions))}


def calibrate(rows, evidence, rules=None):
    best = None
    trials = []
    for threshold in THRESHOLDS:
        for margin in MARGINS:
            predictions = [accepted(item, threshold, margin) for item in evidence]
            if rules is not None:
                predictions = [rule if rule != 'reject' else guess for rule, guess in zip(rules, predictions)]
            score = metrics(rows, predictions)
            trials.append({'threshold': threshold, 'margin': margin,
                           **{k: score[k] for k in ('correct', 'macro_f1', 'false_activations', 'correct_commands', 'rejected_commands')}})
            # Minimize false activation first, then macro-F1. Deterministic conservative ties.
            key = (-score['false_activations'], score['macro_f1'], score['correct'], threshold, margin)
            if best is None or key > best[0]:
                best = (key, {'threshold': threshold, 'margin': margin, 'development': score})
    return {**best[1], 'trials': trials}


def label_of(intent):
    if type(intent) is ControlIntent:
        return intent.action
    if type(intent) in (Intent, AlbumIntent):
        return 'play'
    if type(intent) is LanguageIntent:
        return 'language'
    return 'reject'


async def evaluate(corpus, encoder):
    from sklearn.feature_extraction.text import TfidfVectorizer
    report = {'corpus_sha256': digest(corpus), 'selection': 'development only: minimize false activations, then macro-F1',
              'candidate_thresholds': THRESHOLDS, 'candidate_margins': MARGINS, 'locales': {}}
    for locale in ('ru', 'en'):
        rows = [row for row in corpus['cases'] if row['locale'] == locale]
        training = [r for r in rows if r['split'] == 'train']
        indices = {split: [i for i, row in enumerate(rows) if row['split'] == split] for split in ('development', 'test')}
        vectors = encoder.encode([r['text'] for r in rows])
        train_vectors = vectors[[i for i, row in enumerate(rows) if row['split'] == 'train']]
        embedding = [nearest(v @ train_vectors.T, training) for v in vectors]
        vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), lowercase=True)
        train_sparse = vectorizer.fit_transform([r['text'] for r in training])
        char = [nearest(s, training) for s in (vectorizer.transform([r['text'] for r in rows]) @ train_sparse.T).toarray()]
        rule_intents = []
        for row in rows:
            rule = await RuleInterpreter().interpret(row['text'], InterpretationContext(locale))
            rule_intents.append(rule.intent)
        rule_labels = [label_of(intent) for intent in rule_intents]
        variants = {}
        for name, source in [('rules', None), ('character_ngrams', char), ('embeddings', embedding), ('rules_then_embeddings', embedding)]:
            dev_indices, test_indices = indices['development'], indices['test']
            threshold = None if source is None else calibrate(
                [rows[i] for i in dev_indices], [source[i] for i in dev_indices],
                [rule_labels[i] for i in dev_indices] if name == 'rules_then_embeddings' else None)
            details, predicted = [], []
            for i in test_indices:
                row = rows[i]
                label = rule_labels[i] if source is None else accepted(source[i], threshold['threshold'], threshold['margin'])
                if name == 'rules_then_embeddings' and rule_labels[i] != 'reject':
                    label = rule_labels[i]
                # Learned labels alone do not fabricate music/language slots.
                complete = (asdict(ControlIntent(label)) if label in LABELS[:5] else
                            asdict(rule_intents[i]) if label != 'reject' and label == rule_labels[i] else None)
                predicted.append(label)
                details.append({'id': row['id'], 'text': row['text'], 'expected': row['label'], 'predicted': label,
                                'evidence': source[i] if source is not None else None,
                                'complete_intent': complete,
                                'complete_intent_matches': complete == row.get('intent') if 'intent' in row else None})
            raw_predictions = [rule_labels[i] if source is None or (name == 'rules_then_embeddings' and rule_labels[i] != 'reject')
                               else source[i]['label'] for i in test_indices]
            variants[name] = {'calibration': threshold, 'test': metrics([rows[i] for i in test_indices], predicted),
                              'unthresholded_test': metrics([rows[i] for i in test_indices], raw_predictions),
                              'complete_positive_correct': sum(d['complete_intent_matches'] is True and d['expected'] != 'reject' for d in details),
                              'complete_positive_total': sum('intent' in rows[i] and rows[i]['label'] != 'reject' for i in test_indices),
                              'cases': details}
        report['locales'][locale] = {'sizes': {s: sum(r['split'] == s for r in rows) for s in ('train','development','test')}, 'variants': variants}
    return report
