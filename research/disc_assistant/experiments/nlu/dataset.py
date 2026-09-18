"""Auditable command annotations and explicit private history collection. No ML imports."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata

from research.disc_assistant.assistant.command_catalog import LABELS, digest
from research.disc_assistant.assistant.intents import ControlIntent, Intent, LanguageIntent
from research.disc_assistant.assistant.interpreter import validate_intent
from research.disc_assistant.assistant.responses import locale_code

REPOSITORY = Path(__file__).resolve().parents[4]
SPLITS = ('train', 'development', 'test', 'regression')


def normalized(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def valid_text(text):
    return (isinstance(text, str) and 1 <= len(text) <= 1000 and bool(text.strip())
            and not any(ord(c) < 32 or ord(c) == 127 for c in text))


def validate_row(row, *, pending=False):
    if not isinstance(row, dict):
        raise ValueError('annotation must be an object')
    required = {'id', 'locale', 'text', 'group', 'split', 'origin', 'review', 'label', 'intent', 'slots'}
    if set(row) != required:
        raise ValueError('annotation fields must match schema 1')
    if any(not isinstance(row[k], str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,160}', row[k]) for k in ('id', 'group')):
        raise ValueError('invalid annotation identity/group')
    locale_code(row['locale'])
    if not valid_text(row['text']) or not isinstance(row['origin'], dict) or not row['origin'].get('kind'):
        raise ValueError('invalid annotation text/origin')
    review = row['review']
    if not isinstance(review, dict) or review.get('status') not in ('pending', 'reviewed'):
        raise ValueError('invalid review status')
    if review['status'] == 'pending':
        if not pending or any(row[k] is not None for k in ('split', 'label', 'intent')) or row['slots'] != []:
            raise ValueError('pending rows cannot train or carry inferred gold labels')
        return row
    if not valid_text(review.get('by')) or not valid_text(review.get('note')):
        raise ValueError('reviewer and annotation rationale are required')
    if row['split'] not in SPLITS or row['label'] not in LABELS:
        raise ValueError('invalid split/label')
    label, value = row['label'], row['intent']
    if label == 'reject':
        if value is not None or row['slots'] != []:
            raise ValueError('rejection cannot have an executable intent')
        return row
    if value is None and label in ('play', 'language') and row['slots'] == []:
        return row  # Known action without the required argument; never executable.
    try:
        intent = (Intent(**value) if label == 'play' else LanguageIntent(**value) if label == 'language'
                  else ControlIntent(**value))
        validate_intent(intent)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise ValueError('invalid gold intent') from exc
    if value != asdict(intent):
        raise ValueError('gold intent must include all canonical fields, including null artist/title')
    if label in LABELS[:5] and intent.action != label:
        raise ValueError('intent action disagrees with label')
    slots = row['slots']
    if not isinstance(slots, list):
        raise ValueError('slots must be a list')
    seen = set()
    for slot in slots:
        if (not isinstance(slot, dict) or set(slot) != {'field', 'start', 'end', 'text'}
                or slot['field'] not in ('query', 'language') or slot['field'] in seen
                or type(slot['start']) is not int or type(slot['end']) is not int
                or not 0 <= slot['start'] < slot['end'] <= len(row['text'])
                or row['text'][slot['start']:slot['end']] != slot['text']):
            raise ValueError('invalid original-text slot span')
        seen.add(slot['field'])
    if label == 'play' and (seen != {'query'} or slots[0]['text'] != intent.query):
        raise ValueError('play needs its exact query span, not a repaired catalog name')
    if label == 'language' and seen != {'language'}:
        raise ValueError('language needs a target span')
    if label in LABELS[:5] and slots:
        raise ValueError('controls have no slots')
    return row


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except ValueError as exc:
                raise ValueError(f'invalid JSON at line {number}') from exc


def validate_rows(rows):
    ids, texts, groups = set(), {}, {}
    for row in rows:
        validate_row(row)
        if row['id'] in ids:
            raise ValueError('duplicate annotation ID')
        ids.add(row['id'])
        previous = groups.setdefault(row['group'], row['split'])
        if previous != row['split'] and {previous, row['split']} != {'train', 'regression'}:
            raise ValueError('related phrase/audio group crosses splits')
        # Reused earlier/STT cases are explicitly regression, never a holdout.
        if row['split'] == 'regression':
            continue
        key = (row['locale'], normalized(row['text']))
        if key in texts:
            raise ValueError(f'duplicate normalized text: {row["id"]} / {texts[key]}')
        texts[key] = row['id']
    locales = sorted({r['locale'] for r in rows})
    for locale in locales:
        for split in ('train', 'development', 'test'):
            if {r['label'] for r in rows if r['locale'] == locale and r['split'] == split} != set(LABELS):
                raise ValueError('each locale train/development/test needs every label including reject')
    if not locales:
        raise ValueError('empty dataset')
    return rows


def audit(rows):
    counts = Counter((r['locale'], r['split'], r['label']) for r in rows)
    near = []
    active = [r for r in rows if r['split'] != 'regression']
    for i, a in enumerate(active):
        left = set(re.findall(r'[^\W_]+', normalized(a['text'])))
        for b in active[i+1:]:
            if a['locale'] != b['locale'] or a['split'] == b['split']:
                continue
            right = set(re.findall(r'[^\W_]+', normalized(b['text'])))
            score = len(left & right) / len(left | right) if left | right else 0
            if score >= .8:
                near.append({'a': a['id'], 'b': b['id'], 'token_jaccard': round(score, 3)})
    training = {(r['locale'], normalized(r['text'])) for r in rows if r['split'] == 'train'}
    return {'rows': len(rows), 'locales': sorted({r['locale'] for r in rows}),
            'counts': {':'.join(k): v for k, v in sorted(counts.items())},
            'near_duplicates_to_review': near,
            'regression_training_overlap': sum(r['split'] == 'regression' and
                (r['locale'], normalized(r['text'])) in training for r in rows)}


def load(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    raw = (directory / 'cases.jsonl').read_bytes()
    if manifest.get('version') != 1 or manifest.get('sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('dataset bytes do not match frozen manifest')
    rows = validate_rows(list(read_jsonl(directory / 'cases.jsonl')))
    return manifest, rows


def private_path(path):
    path = Path(path).expanduser().resolve()
    if path == REPOSITORY or REPOSITORY in path.parents:
        raise ValueError('write personal annotation files outside the repository')
    return path


def private_output(path, text):
    path = private_path(path)
    with open(path, 'x', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        stream.write(text)


def collect(history, output):
    """Copy only input text/locale and a hashed provenance ID; never predicted labels."""
    rows, seen = [], set()
    for record in read_jsonl(history):
        if record.get('command') not in ('ask', 'rank', 'explain') or record.get('input_truncated'):
            continue
        locale = record.get('context', {}).get('locale')
        try:
            locale_code(locale)
        except ValueError:
            continue
        text = record.get('input')
        speech = [e['payload'].get('text') for e in record.get('events', [])
                  if e.get('phase') == 'speech_command_text' and isinstance(e.get('payload'), dict)]
        if speech:
            text = speech[-1]
        elif isinstance(text, str) and text.startswith(('/explain ', '/rank ')):
            text = text.partition(' ')[2]
        if not valid_text(text) or text == '[audio]' or text.startswith('/'):
            continue
        key = (locale, normalized(text))
        if key in seen:
            continue
        seen.add(key)
        identity = digest([record.get('id'), locale, text])[:24]
        origin = {'kind': 'history_stt' if speech else 'history_text', 'reference': identity}
        group = 'history-' + identity
        if speech:
            for event in record.get('events', []):
                phase, payload = event.get('phase'), event.get('payload', {})
                if not isinstance(payload, dict):
                    continue
                field = 'sha256' if phase == 'audio_validated' else 'model_sha256' if phase == 'speech_model' else None
                value = payload.get(field) if field else None
                if isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value):
                    origin['audio_sha256' if phase == 'audio_validated' else 'stt_model_sha256'] = value
                    if phase == 'audio_validated':
                        group = 'audio-' + value
        rows.append({'id': 'history-' + identity, 'locale': locale, 'text': text,
                     'group': group, 'split': None, 'origin': origin,
                     'review': {'status': 'pending'}, 'label': None, 'intent': None, 'slots': []})
    private_output(output, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    return {'pending': len(rows), 'output': str(output), 'labels_inferred': False}


def review(queue, annotation_file, output):
    rows = list(read_jsonl(queue))
    annotations = list(read_jsonl(annotation_file))
    patches = {r['id']: r for r in annotations}
    ids = {r['id'] for r in rows}
    if len(ids) != len(rows) or len(patches) != len(annotations) or not set(patches) <= ids:
        raise ValueError('duplicate or unknown review IDs')
    result = []
    for row in rows:
        validate_row(row, pending=True)
        if row['id'] in patches:
            patch = patches[row['id']]
            if set(patch) != {'id', 'group', 'split', 'review', 'label', 'intent', 'slots'}:
                raise ValueError('review must specify group/split/reviewer/label/intent/slots')
            row = {**row, **patch}
            validate_row(row)
        result.append(row)
    private_output(output, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in result))
    return {'reviewed': sum(r['review']['status'] == 'reviewed' for r in result),
            'pending': sum(r['review']['status'] == 'pending' for r in result)}


def freeze(input_path, output, name):
    rows = validate_rows(list(read_jsonl(input_path)))
    summary = audit(rows)
    if summary['near_duplicates_to_review']:
        raise ValueError('review cross-split near duplicates before freezing')
    if not valid_text(name):
        raise ValueError('dataset name is required')
    output = private_path(output)
    raw = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    manifest = {'version': 1, 'name': name, 'sha256': hashlib.sha256(raw.encode()).hexdigest(),
                'description': 'Explicit reviewed dataset; review identities and origins are in each row.'}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    private_output(output / 'cases.jsonl', raw)
    private_output(output / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return {'manifest': manifest, **summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate')
    validate.add_argument('directory', type=Path)
    gather = sub.add_parser('collect')
    gather.add_argument('--history', type=Path, required=True)
    gather.add_argument('--output', type=Path, required=True)
    annotate = sub.add_parser('review')
    annotate.add_argument('--queue', type=Path, required=True)
    annotate.add_argument('--annotations', type=Path, required=True)
    annotate.add_argument('--output', type=Path, required=True)
    snapshot = sub.add_parser('freeze')
    snapshot.add_argument('--input', type=Path, required=True)
    snapshot.add_argument('--output', type=Path, required=True)
    snapshot.add_argument('--name', required=True)
    args = parser.parse_args()
    if args.command == 'validate':
        manifest, rows = load(args.directory)
        result = {'manifest': manifest, **audit(rows)}
    elif args.command == 'collect':
        result = collect(args.history, args.output)
    elif args.command == 'review':
        result = review(args.queue, args.annotations, args.output)
    else:
        result = freeze(args.input, args.output, args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
