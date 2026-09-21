"""Offline shadow observations and explicit review; never reruns or trains providers."""
from research.disc_assistant.assistant.nlu.intents import AlbumIntent, music_from_dict

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
import hashlib
import math
from pathlib import Path
import re
from types import SimpleNamespace

from research.disc_assistant.assistant.nlu.command_catalog import digest
from research.disc_assistant.assistant.nlu.intents import Intent, ControlIntent, LanguageIntent, intent_from_dict
from research.disc_assistant.assistant.nlu.interpretation_sources import Evidence, validate
from research.disc_assistant.assistant.nlu.evaluation.dataset import (
    history_example, normalized, private_output, private_path, read_jsonl, validate_row)

TOKEN = re.compile(r'[a-zA-Z0-9_.:+-]{1,120}')
HASH = re.compile(r'[0-9a-f]{64}')


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def provenance(raw):
    """Allowlisted model/rule identity, not arbitrary SDK data or device paths."""
    result = {}
    for key in ('snapshot', 'source_hash', 'model_sha256', 'rules_sha256', 'grammar_sha256', 'prompt_sha256', 'schema_sha256'):
        value = raw.get(key)
        if value is not None:
            if not isinstance(value, str) or not HASH.fullmatch(value):
                raise ValueError('invalid source fingerprint')
            result[key] = value
    for key in ('threshold', 'minimum_margin'):
        if key in raw:
            if not number(raw[key]):
                raise ValueError('invalid source threshold')
            result[key] = raw[key]
    # A fixed reason is useful diagnostically; never retain raw exception bodies.
    if isinstance(raw.get('error_type'), str) and TOKEN.fullmatch(raw['error_type']):
        result['error_type'] = raw['error_type']
    return result


def source_result(raw, text, *, primary=False):
    if not isinstance(raw, dict):
        raise ValueError('invalid source row')
    name, version = raw.get('source'), raw.get('version')
    if any(not isinstance(v, str) or not TOKEN.fullmatch(v) for v in (name, version)):
        raise ValueError('invalid source identity')
    value, chosen = raw.get('intent'), raw.get('label', 'reject')
    if value is not None:
        value = intent_from_dict(value)
    evidence = Evidence(name, version, raw.get('status'), chosen, value, raw.get('reason', ''),
                        raw.get('spans', []), raw.get('scores', {}), raw.get('provenance', {}))
    validate(evidence, SimpleNamespace(name=name, version=version), text)
    elapsed = raw.get('elapsed_ms')
    if elapsed is not None and not number(elapsed):
        raise ValueError('invalid source duration')
    result = asdict(evidence)
    result['provenance'] = provenance(evidence.provenance)
    # Error type is not a new model revision. Scores/latency do not define identity.
    identity = {k: v for k, v in result['provenance'].items() if k != 'error_type'}
    result.update(role='primary' if primary else 'shadow', elapsed_ms=elapsed,
                  revision=digest([name, version, identity]))
    return result


def primary_result(record, payload, text):
    primary = payload['primary']
    raw_intent = primary.get('intent')
    chosen = ('play' if 'query' in raw_intent else 'language' if 'locale' in raw_intent
              else raw_intent.get('action')) if isinstance(raw_intent, dict) else 'reject'
    starts = [e['payload'] for e in record['events'] if e.get('phase') == 'interpretation_started']
    info = starts[0].get('provider', {}) if len(starts) == 1 else {}
    policy = [e['payload'] for e in record['events'] if e.get('phase') == 'single_action_policy']
    identity = {'grammar_sha256': policy[0].get('grammar_sha256')} if len(policy) == 1 else {}
    # Local rule hashes describe this provider only, not a future remote interpreter.
    if info.get('name') == 'rules':
        identity['rules_sha256'] = record.get('context', {}).get('language_rules_sha256')
    return source_result({'source': info.get('name', 'unknown-primary'), 'version': info.get('version', 'unknown'),
                          'status': 'rejected' if primary.get('status') == 'unrecognized' else primary.get('status'),
                          'label': chosen, 'intent': raw_intent, 'provenance': identity}, text, primary=True)


def differences(results):
    """Availability is operational evidence, not a disagreement about meaning."""
    available = [r for r in results if r['status'] != 'unavailable']
    reasons = []
    executable = [r for r in available if r['intent'] is not None]
    if executable and len(executable) < len(available):
        reasons.append('recognition_disagreement')
    if len({r['label'] for r in available if r['label'] != 'reject'}) > 1:
        reasons.append('label_disagreement')
    if len({digest(r['intent']) for r in executable}) > 1:
        reasons.append('intent_disagreement')
    if any(a['label'] == b['label'] and a['intent'] != b['intent']
           for i, a in enumerate(executable) for b in executable[i+1:]):
        reasons.append('argument_disagreement')
    return reasons


def observations(history):
    cases, counters, seen = [], Counter(), {}
    for record in read_jsonl(history):
        counters['input_records'] += 1
        if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id']:
            counters['invalid_record'] += 1
            continue
        signature = digest(record)
        if record['id'] in seen:
            if seen[record['id']] != signature:
                raise ValueError('conflicting duplicate request IDs in export')
            counters['duplicate_request'] += 1
            continue
        seen[record['id']] = signature
        events = record.get('events', [])
        if not isinstance(events, list) or any(not isinstance(e, dict) or not isinstance(e.get('payload'), dict) for e in events):
            counters['invalid_events'] += 1
            continue
        shadows = [e['payload'] for e in events if e.get('phase') == 'interpretation_shadow']
        if not shadows:
            counters['no_shadow'] += 1
            continue
        if len(shadows) != 1:
            counters['ambiguous_shadow'] += 1
            continue
        payload = shadows[0]
        if payload.get('status') == 'unavailable' and 'sources' not in payload:
            counters['collector_unavailable'] += 1
            continue
        try:
            row = history_example(record)
            if row is None:
                counters['unusable_input'] += 1
                continue
            validate_row(row, pending=True)
            context = payload['context']
            if (context['locale'] != row['locale'] or context.get('playback') not in ('playing', 'paused', 'stopped', 'unknown')
                    or payload.get('execution_source') != 'primary_only'):
                raise ValueError('inconsistent shadow context')
            raw = payload['sources']
            if not isinstance(raw, list) or not 1 <= len(raw) <= 8:
                raise ValueError('invalid source count')
            results = [source_result(r, row['text']) for r in raw]
            if len({r['source'] for r in results}) != len(results):
                raise ValueError('duplicate sources')
            results.insert(0, primary_result(record, payload, row['text']))
        except (ValueError, TypeError, KeyError, AttributeError):
            counters['invalid_shadow'] += 1
            continue
        key = 'shadow-' + digest([row['locale'], row['text']])[:24]
        cases.append({'id': key, 'request_reference': digest(record['id'])[:24], 'locale': row['locale'],
                      'text': row['text'], 'modality': 'speech' if row['origin']['kind'] == 'history_stt' else 'text',
                      'origin': row['origin'], 'context': {'playback': context['playback']},
                      'sources': results, 'disagreements': differences(results)})
        counters['eligible_requests'] += 1
    return cases, dict(sorted(counters.items()))


def queue_rows(cases, scope):
    # Keep exact text for trustworthy spans; normalized variants and repeated audio
    # form connected groups, so reviewers cannot split them across fit/evaluation.
    parents = {}
    def root(key):
        parents.setdefault(key, key)
        cursor = key
        while parents[cursor] != cursor:
            cursor = parents[cursor]
        while parents[key] != key:
            previous = parents[key]
            parents[key] = cursor
            key = previous
        return cursor
    for case in cases:
        text_key = digest([case['locale'], normalized(case['text'])])
        audio = case['origin'].get('audio_sha256')
        root(text_key)
        if audio:
            parents[root(text_key)] = root('audio-' + audio)
    grouped = defaultdict(list)
    for case in cases:
        grouped[case['id']].append(case)
    rows = []
    for identity, records in sorted(grouped.items()):
        if scope == 'disagreements' and not any(r['disagreements'] for r in records):
            continue
        case = records[0]
        rows.append({'id': identity, 'locale': case['locale'], 'text': case['text'],
                     'group': 'shadow-group-' + digest(root(digest([case['locale'], normalized(case['text'])])))[:24],
                     'split': None, 'origin': {'kind': 'shadow_review', 'reference': identity,
                                              'modalities': sorted({r['modality'] for r in records})},
                     'review': {'status': 'pending'}, 'label': None, 'intent': None, 'slots': []})
    return rows


def annotations(path, cases):
    if path is None:
        return {}
    known = {c['id']: (c['locale'], c['text']) for c in cases}
    result, seen = {}, set()
    for row in read_jsonl(path):
        validate_row(row, pending=True)
        key = row['id']
        if key in seen or known.get(key) != (row['locale'], row['text']):
            raise ValueError('review IDs/text/locale must match this export exactly')
        seen.add(key)
        if row['review']['status'] == 'reviewed':
            result[key] = row
    return result


def latency(values):
    values = sorted(v for v in values if v is not None)
    return {'samples': len(values), 'p50_ms': values[math.ceil(.5*len(values))-1] if values else None,
            'p95_ms': values[math.ceil(.95*len(values))-1] if values else None}


def quality(rows):
    labeled = [(case, source, gold) for case, source, gold in rows if gold is not None]
    if not labeled:
        return None
    counts = Counter({k: 0 for k in ('reviewed_occurrences', 'nonexecutable_total', 'false_activations',
                        'positive_total', 'exact_intent_correct', 'abstained_positive', 'wrong_action',
                        'argument_total', 'argument_exact', 'wrong_arguments', 'unavailable')})
    for case, source, gold in labeled:
        actual, expected = source['intent'], gold['intent']
        counts['reviewed_occurrences'] += 1
        counts['unavailable'] += source['status'] == 'unavailable'
        if expected is None:
            counts['nonexecutable_total'] += 1
            counts['false_activations'] += actual is not None
        else:
            counts['positive_total'] += 1
            counts['exact_intent_correct'] += actual == expected
            counts['abstained_positive'] += actual is None
            counts['wrong_action'] += actual is not None and source['label'] != gold['label']
            if gold['label'] in ('play', 'language'):
                counts['argument_total'] += 1
                counts['argument_exact'] += actual == expected
                counts['wrong_arguments'] += actual is not None and source['label'] == gold['label'] and actual != expected
    return {'reviewed_unique_inputs': len({c['id'] for c, _, _ in labeled}), **dict(counts)}


def summarize(cases, gold):
    groups = defaultdict(list)
    for case in cases:
        for source in case['sources']:
            key = (case['locale'], case['modality'], case['origin'].get('stt_model_sha256', 'unknown') if case['modality'] == 'speech' else 'not_applicable',
                   source['role'], source['source'], source['version'], source['revision'])
            groups[key].append((case, source, gold.get(case['id'])))
    rows = []
    for key, items in sorted(groups.items()):
        counts = Counter(s['status'] for _, s, _ in items)
        pairs = [(s, c['sources'][0]) for c, s, _ in items if s['role'] == 'shadow'
                 and s['status'] != 'unavailable' and c['sources'][0]['status'] != 'unavailable']
        rows.append({**dict(zip(('locale', 'modality', 'stt_model_sha256', 'role', 'source', 'version', 'revision'), key)),
                     'provenance': items[0][1]['provenance'], 'observations': len(items),
                     'unique_inputs': len({c['id'] for c, _, _ in items}), 'statuses': dict(counts),
                     'reasons': dict(Counter(s['reason'] for _, s, _ in items)),
                     'latency': latency(s['elapsed_ms'] for _, s, _ in items),
                     'available_latency': latency(s['elapsed_ms'] for _, s, _ in items if s['status'] != 'unavailable'),
                     'primary_comparison': {'comparable': len(pairs),
                         'disagreements': sum(bool(differences([a, b])) for a, b in pairs)},
                     'quality': quality(items)})
    return rows


def input_label(row):
    text = f"{row['locale']}/{row['modality']}"
    return text + '/' + row['stt_model_sha256'][:8] if row['modality'] == 'speech' else text


def markdown(report):
    lines = ['# Shadow observations', '',
             'Observed disagreements are not errors. Accuracy requires explicit reviewed labels.', '',
             'This is occurrence-weighted, observational evidence, not independent model acceptance.', '',
             f"Eligible requests: {report['coverage'].get('eligible_requests', 0)}; review queue: {report['pending_rows']}.", '',
             '| Locale/input/STT | Source/version/revision | Observed | Recognized | Unavailable | Disagree with primary | p50/p95 ms |',
             '| --- | --- | ---: | ---: | ---: | ---: | --- |']
    for row in report['sources']:
        timings, comparison = row['latency'], row['primary_comparison']
        disagreement = f"{comparison['disagreements']}/{comparison['comparable']}" if comparison['comparable'] else '—'
        duration = f"{timings['p50_ms']}/{timings['p95_ms']}" if timings['samples'] else '—'
        lines.append(f"| {input_label(row)} | {row['role']}:{row['source']}/{row['version']}/{row['revision'][:8]} | "
                     f"{row['observations']} | {row['statuses'].get('recognized', 0)} | {row['statuses'].get('unavailable', 0)} | "
                     f"{disagreement} | {duration} |")
    if report['reviewed_unique_inputs']:
        lines += ['', '## Reviewed observations', '',
                  '| Locale/input/STT | Source/revision | Reviewed occurrences | Exact positive intent | False activation/nonexecutable | Exact arguments |',
                  '| --- | --- | ---: | ---: | ---: | ---: |']
        for row in report['sources']:
            q = row['quality']
            if q:
                lines.append(f"| {input_label(row)} | {row['role']}:{row['source']}/{row['revision'][:8]} | "
                             f"{q['reviewed_occurrences']} | {q['exact_intent_correct']}/{q['positive_total']} | "
                             f"{q['false_activations']}/{q['nonexecutable_total']} | {q['argument_exact']}/{q['argument_total']} |")
    lines += ['', 'Missing duration is unknown, not zero; primary duration is not reconstructed.', '',
              'Coverage/exclusions, reason counts, quality denominators and full revisions are in report.json.',
              'Individual evidence is in evidence.jsonl; pending.jsonl contains no predictions or inferred labels.', '']
    return '\n'.join(lines)


def build(history, output, *, reviewed=None, scope='disagreements'):
    if scope not in ('disagreements', 'all'):
        raise ValueError('invalid review scope')
    output = private_path(output)
    if output.exists():
        raise FileExistsError('report output directory must be new')
    cases, coverage = observations(history)
    pending = queue_rows(cases, scope)
    gold = annotations(reviewed, cases)
    report = {'version': 1, 'scope': 'observational, occurrence-weighted; no rerun, training or model selection',
              'history_sha256': hashlib.sha256(Path(history).read_bytes()).hexdigest(),
              'coverage': coverage, 'review_scope': scope, 'pending_rows': len(pending),
              'reviewed_unique_inputs': len(gold), 'labels_inferred': False,
              'disagreements': dict(Counter(reason for case in cases for reason in case['disagreements'])),
              'sources': summarize(cases, gold)}
    if reviewed:
        report['reviewed_sha256'] = hashlib.sha256(Path(reviewed).read_bytes()).hexdigest()
    output.mkdir(mode=0o700)  # Caller chooses an existing parent; no partial parent tree.
    files = {'report.json': json.dumps(report, ensure_ascii=False, indent=2) + '\n',
             'report.md': markdown(report),
             'pending.jsonl': ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in pending),
             'evidence.jsonl': ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in cases)}
    for name, content in files.items():
        private_output(output / name, content)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=Path, required=True, help='Explicit history export; never opens runtime storage')
    parser.add_argument('--output', type=Path, required=True, help='New private directory outside repository')
    parser.add_argument('--reviewed', type=Path, help='Optional dataset.review output for gold metrics')
    parser.add_argument('--review-scope', choices=('disagreements', 'all'), default='disagreements')
    args = parser.parse_args(argv)
    try:
        report = build(args.history, args.output, reviewed=args.reviewed, scope=args.review_scope)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f'Shadow report failed ({type(exc).__name__}): {exc}\n')
    print(json.dumps({'output': str(args.output), 'coverage': report['coverage'],
                      'pending': report['pending_rows'], 'reviewed': report['reviewed_unique_inputs'], 'labels_inferred': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
