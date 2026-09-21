"""Frozen-dataset command comparison. No user config, player, or implicit model download."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

from experiments.disc_assistant.assistant.nlu.command_catalog import CommandCatalog, digest, source
from experiments.disc_assistant.assistant.nlu.command_features import classify
from experiments.disc_assistant.assistant.nlu.explain import decide
from experiments.disc_assistant.assistant.nlu.evaluation.dataset import audit, load
from experiments.disc_assistant.assistant.nlu.evaluation.encoder import Encoder
from experiments.disc_assistant.assistant.nlu.evaluation.intents import accepted, metrics
from experiments.disc_assistant.assistant.nlu.evaluation.train_commands import fit_features, matrix, export_model, evidence, scored

ROOT = Path(__file__).parent
DATA = ROOT.parent / 'data'
THRESHOLDS = (.15, .25, .35, .45, .55, .65, .75, .85, .95, 1.01)
MARGINS = (0., .05, .10, .15)
CS = (.1, 1., 10.)


def score_key(score):
    return -score['false_activations'], score['macro_f1'], score['correct']


def calibrate(rows, predictions):
    best, trials = None, []
    for threshold in THRESHOLDS:
        for margin in MARGINS:
            result = metrics(rows, [accepted(p, threshold, margin) for p in predictions])
            trials.append({'threshold': threshold, 'margin': margin,
                           **{k: result[k] for k in ('false_activations', 'correct_commands', 'rejected_commands', 'macro_f1', 'correct')}})
            key = (*score_key(result), threshold, margin)
            if best is None or key > best[0]:
                best = key, {'threshold': threshold, 'margin': margin, 'development': result}
    return {**best[1], 'trials': trials}


def measurements(rows, predictions, calibration):
    labels = [accepted(p, calibration['threshold'], calibration['margin']) for p in predictions]
    result = metrics(rows, labels)
    result['wrong_action_commands'] = sum(r['label'] != 'reject' and p not in ('reject', r['label'])
                                          for r, p in zip(rows, labels))
    n, failures = result['negative_count'], result['false_activations']
    # Exact one-sided 95% upper bound for zero observed failures, not a quality guarantee.
    result['zero_failure_upper_bound_95'] = 1 - .05 ** (1/n) if n and failures == 0 else None
    return {'accepted': result, 'raw': metrics(rows, [p['label'] for p in predictions]),
            'cases': [{'id': r['id'], 'expected': r['label'], 'accepted_label': label, **p}
                      for r, label, p in zip(rows, labels, predictions)]}


def pipeline_score(rows, authored, portable=None):
    outputs = [decide(r['text'], authored, portable) for r in rows]
    result = scored(rows, outputs)
    result['complete_positive_correct'] = sum(r['label'] != 'reject' and r['intent'] is not None
        and r['intent'] == o['candidate']['intent'] for r, o in zip(rows, outputs))
    result['complete_positive_total'] = sum(r['label'] != 'reject' and r['intent'] is not None for r in rows)
    result['incomplete_requests_completed'] = sum(r['label'] != 'reject' and r['intent'] is None
                                                and o['candidate']['intent'] is not None for r, o in zip(rows, outputs))
    result['wrong_action_commands'] = sum(r['label'] != 'reject' and o['candidate']['label'] not in ('reject', r['label'])
        for r, o in zip(rows, outputs))
    result['by_origin'] = {}
    for kind in sorted({r['origin']['kind'] for r in rows}):
        pairs = [(r, o) for r, o in zip(rows, outputs) if r['origin']['kind'] == kind]
        result['by_origin'][kind] = {**metrics([r for r, _ in pairs], [o['candidate']['label'] for _, o in pairs]),
            'complete_positive_correct': sum(r['intent'] is not None and r['intent'] == o['candidate']['intent'] for r, o in pairs),
            'complete_positive_total': sum(r['label'] != 'reject' and r['intent'] is not None for r, _ in pairs)}
    for case, row in zip(result['cases'], rows):
        case.update(origin=row['origin'], group=row['group'])
    result['slot_accuracy'] = {}
    for label in ('play', 'language'):
        selected = [(r, o) for r, o in zip(rows, outputs) if r['label'] == label and r['intent'] is not None]
        result['slot_accuracy'][label] = {'total': len(selected), 'exact_intent': sum(
            r['intent'] == o['candidate']['intent'] for r, o in selected)}
    return result


def resource_probe(rows, portable):
    durations = []
    for _ in range(3):
        for row in rows:
            start = time.perf_counter()
            classify(row['text'], portable)
            durations.append((time.perf_counter() - start) * 1000)
    durations.sort()
    return {'probes': len(durations), 'p50_ms': durations[len(durations)//2],
            'p95_ms': durations[int(len(durations)*.95)],
            'scope': 'warm standard-library text scoring only; excludes loading, DB, slots and speech; not Pi'}


def evaluate(locale, all_rows, manifest, encoder, output):
    from sklearn.linear_model import LogisticRegression
    authored = source(locale)
    training = [r for r in all_rows if r['locale'] == locale and r['split'] == 'train']
    development = [r for r in all_rows if r['locale'] == locale and r['split'] == 'development']
    evaluation = {split: [r for r in all_rows if r['locale'] == locale and r['split'] == split]
                  for split in ('test', 'regression')}
    references = {(r['text'], r['label']) for r in training}
    if not all((r['text'], r['label']) in references for r in authored['examples']):
        raise ValueError('dataset must include current locale references in training; version the dataset again')
    # Only train/development is consulted until every estimator and threshold is selected.
    fit_rows = training + development
    vocabulary, idf = fit_features(training)
    text_values = matrix(fit_rows, vocabulary, idf)
    embedding_values = encoder.encode([r['text'] for r in fit_rows])
    n = len(training)
    fitted, results = {}, {}
    for feature, values in (('text', text_values), ('embeddings', embedding_values)):
        for weighting in (None, 'balanced'):
            name = feature + ('_balanced' if weighting else '_ordinary')
            best, trials = None, []
            for c in CS:
                start = time.perf_counter()
                estimator = LogisticRegression(C=c, class_weight=weighting, max_iter=2000, random_state=0)
                estimator.fit(values[:n], [r['label'] for r in training])
                calibration = calibrate(development, evidence(estimator.predict_proba(values[n:]), estimator.classes_))
                trials.append({'C': c, 'fit_and_calibration_ms': (time.perf_counter()-start)*1000, **calibration})
                key = (*score_key(calibration['development']), -c)
                if best is None or key > best[0]:
                    best = key, estimator, calibration, c
            _, estimator, calibration, c = best
            fitted[name] = estimator, calibration
            results[name] = {'C': c, 'class_weight': weighting, 'calibration': calibration, 'trials': trials, 'evaluation': {}}
    # Candidate publication is selected by development before looking at test/regression.
    text_name = max(('text_ordinary', 'text_balanced'), key=lambda name: (
        *score_key(fitted[name][1]['development']), -results[name]['C'], name == 'text_ordinary'))
    source_vectors = encoder.encode([r['text'] for r in authored['examples']])
    portable_models = {}
    for name in ('text_ordinary', 'text_balanced'):
        estimator, calibration = fitted[name]
        portable = export_model(estimator, vocabulary, idf)
        portable.update(threshold=calibration['threshold'], margin=calibration['margin'], training={
            'dataset_sha256': manifest['sha256'], 'train_hash': digest(training), 'development_hash': digest(development),
            'algorithm': 'multinomial logistic regression', 'C': results[name]['C'], 'class_weight': results[name]['class_weight'],
            'selection': 'development false activations, macro-F1, correctness; no test selection'})
        portable_models[name] = portable
        bundle = {'version': 1, 'locale': locale, 'source_hash': digest(authored), 'classifier': portable,
                  'embedding': {'pipeline': encoder.info, 'signature': encoder.signature, 'dimensions': encoder.info['dimensions']},
                  'vectors': {r['id']: v.tolist() for r, v in zip(authored['examples'], source_vectors)}}
        data = json.dumps(bundle, ensure_ascii=False, indent=2) + '\n'
        (output / f'{locale}-{name}-commands.json').write_text(data)
        if name == text_name:
            (output / f'{locale}-commands.json').write_text(data)
            catalog = CommandCatalog(output / 'import-check')
            try:
                snapshot = catalog.publish(locale, bundle)
            finally:
                catalog.close()
    report = {'source_hash': digest(authored), 'training': len(training), 'development': len(development),
              'selected_text_variant': text_name, 'snapshot': snapshot['id'], 'models': results, 'pipeline': {}}
    # The estimator and acceptance decisions above are now frozen.
    parity_cases = 0
    for split, rows in {'development': development, **evaluation}.items():
        if not rows:
            continue
        values = {'text': matrix(rows, vocabulary, idf), 'embeddings': encoder.encode([r['text'] for r in rows])}
        for name, (estimator, calibration) in fitted.items():
            prediction = evidence(estimator.predict_proba(values[name.split('_')[0]]), estimator.classes_)
            if name.startswith('text_'):
                for row, expected in zip(rows, prediction):
                    actual = classify(row['text'], portable_models[name])
                    if actual['label'] != expected['label'] or abs(actual['score'] - expected['score']) > 1e-10:
                        raise AssertionError('portable scorer differs from estimator')
                    parity_cases += 1
            if split != 'development':
                results[name]['evaluation'][split] = measurements(rows, prediction, calibration)
        if split != 'development':
            report['pipeline'][split] = {
                'rules': metrics(rows, [decide(r['text'], authored)['rules']['label'] for r in rows]),
                'guarded_rules': pipeline_score(rows, authored),
                'preview_selected_text': pipeline_score(rows, authored, portable_models[text_name])}
    report['portable_runtime'] = {'parity_cases': parity_cases,
        'bundle_bytes': (output / f'{locale}-commands.json').stat().st_size,
        **resource_probe(evaluation['test'], portable_models[text_name])}
    report['promotion'] = {'eligible': False, 'reasons': [
        'authored examples are not independent human/STT acceptance',
        'current interpreter remains rules; model and slot quality require review',
        'Pi memory, latency and speech resource measurements outstanding']}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DATA / 'datasets/commands-v2')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work, output = args.work.expanduser().resolve(), args.output.expanduser().resolve()
    repository = ROOT.parents[4]
    if any(path == repository or repository in path.parents for path in (work, output)):
        parser.error('work/output must be outside the repository')
    manifest, rows = load(args.dataset)
    summary = audit(rows)
    if summary['near_duplicates_to_review']:
        raise ValueError('review cross-split near duplicates and version the dataset before training')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    encoder = Encoder(work / 'model', work / 'embeddings.sqlite3')
    try:
        report = {'version': 2, 'dataset': manifest, 'audit': summary, 'model': encoder.info,
                  'platform': platform.platform(), 'protocol': {'C': CS, 'thresholds': THRESHOLDS, 'margins': MARGINS,
                  'class_weights': [None, 'balanced'], 'random_state': 0, 'encoder': 'frozen; no fine-tuning'},
                  'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                  for name in ('dataset.py', 'study_commands.py', 'train_commands.py', 'encoder.py', 'intents.py',
                                               '../command_features.py', '../explain.py',
                                               '../intents.py', '../languages.py')}, 'locales': {}}
        for locale in summary['locales']:
            report['locales'][locale] = evaluate(locale, rows, manifest, encoder, output)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'output': str(output), 'dataset': manifest['sha256'], 'locales': {
            locale: {'selected': value['selected_text_variant'], 'runtime': value['portable_runtime']}
            for locale, value in report['locales'].items()}}, indent=2))
    finally:
        encoder.close()


if __name__ == '__main__':
    main()
