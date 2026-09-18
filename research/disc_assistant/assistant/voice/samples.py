"""Reproducible synthetic corpora and interpretation checks. Never controls a player."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re

from research.disc_assistant.assistant.interpreter import InterpretationContext, interpret_request
from research.disc_assistant.assistant.providers import ProviderUnavailable, InvalidProviderResult
from research.disc_assistant.assistant.speech import InvalidSpeech, NoSpeech, SpeechUnavailable
from research.disc_assistant.assistant.voice.backends import transcribe_file, synthesize_text
from research.disc_assistant.assistant.voice.files import audio_details, load_audio, resolve_path, stt_audio
from research.disc_assistant.assistant.languages import normalized
from research.disc_assistant.assistant.voice.catalog_evaluation import CatalogEvaluation, music_case, validate_targets

CORPORA = Path(__file__).parent / 'samples'


def read_json(path):
    with Path(path).open('rb') as stream:
        data = stream.read(256 * 1024 + 1)
    if len(data) > 256 * 1024:
        raise ValueError('sample manifest is too large')
    return json.loads(data)


def validate_cases(data, locale):
    if not isinstance(data, dict) or data.get('version') != 1 or data.get('locale') != locale:
        raise ValueError('corpus must be version 1 and match the active locale')
    cases = data.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError('corpus must contain 1..100 cases')
    ids = set()
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get('id'), str)
                or not re.fullmatch(r'[a-z0-9_-]{1,64}', case['id']) or case['id'] in ids
                or not isinstance(case.get('text'), str) or not 1 <= len(case['text']) <= 1000
                or any(ord(c) < 32 for c in case['text'])
                or not isinstance(case.get('expected'), dict)):
            raise ValueError('invalid or duplicate corpus case')
        expected = case['expected']
        if (expected.get('status') not in ('recognized', 'unrecognized')
                or (expected['status'] == 'recognized' and not isinstance(expected.get('intent'), dict))):
            raise ValueError('expected must declare recognized intent or unrecognized status')
        ids.add(case['id'])
    return cases


async def interpretation(text, config, trace, interpreter):
    try:
        intent = await interpret_request(text, InterpretationContext(config.locale), interpreter=interpreter, trace=trace)
        return {'status': 'recognized', 'intent': asdict(intent)}
    except (InvalidProviderResult, ProviderUnavailable):
        raise
    except ValueError:
        return {'status': 'unrecognized'}


def comparable(value):
    if isinstance(value, str):
        return normalized(value)
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items()}
    return value


async def write_sample(config, text, path, trace, *, provider=None):
    path = resolve_path(path)
    sidecar = path.with_suffix(path.suffix + '.json')
    if path.suffix.lower() != '.wav':
        raise ValueError('synthesis output must have a .wav extension')
    if path.exists() or sidecar.exists():
        raise FileExistsError('synthesis output or metadata already exists; choose a new path')
    audio, metadata = await synthesize_text(config, text, trace, provider=provider)
    if audio.sample_rate != 16000:
        original = audio_details(audio)
        audio = stt_audio(audio, max_seconds=config.speech.get('max_seconds', 30))
        metadata.update(audio_details(audio), source_audio=original, resampler='soxr-HQ')
    metadata = {'version': 1, 'text': text, **metadata}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation; never overwrite an existing recording or sidecar.
    with open(path, 'xb', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        stream.write(audio.data)
    with open(sidecar, 'x', encoding='utf-8', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
    return {'status': 'synthesized', 'output': str(path), 'metadata': str(sidecar), 'synthesis': metadata}


async def speech_command(config, args, trace, *, transcriber=None, synthesizer=None, interpreter=None):
    if args.command == 'synthesize':
        return await write_sample(config, args.text, args.output, trace, provider=synthesizer)
    directory = resolve_path(args.directory)
    if args.command == 'speech-samples':
        corpus_path = resolve_path(args.corpus) if args.corpus else CORPORA / f'{config.locale}.json'
        corpus = read_json(corpus_path)
        cases = validate_cases(corpus, config.locale)
        # Check authored expectations before generating audio or creating output.
        for case in cases:
            actual = await interpretation(case['text'], config, trace, interpreter)
            if comparable(actual) != comparable(case['expected']):
                raise ValueError(f'corpus expectation disagrees with interpreter: {case["id"]}')
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        manifest = {'version': 1, 'locale': config.locale, 'status': 'generating', 'cases': []}
        manifest_path = directory / 'manifest.json'
        try:
            for case in cases:
                trace.event('sample', {'id': case['id']})
                result = await write_sample(config, case['text'], directory / (case['id'] + '.wav'),
                                            trace, provider=synthesizer)
                manifest['cases'].append({**case, 'file': case['id'] + '.wav',
                                          'sha256': result['synthesis']['sha256']})
            manifest['status'] = 'complete'
        finally:
            with manifest_path.open('x', encoding='utf-8') as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
        return {'status': 'generated', 'directory': str(directory), 'sample_count': len(cases)}
    manifest = read_json(directory / 'manifest.json')
    cases = validate_cases(manifest, config.locale)
    if manifest.get('status') != 'complete':
        raise ValueError('sample generation is incomplete; generate into a new directory')
    if getattr(args, 'catalog', False):
        overlay = read_json(resolve_path(args.expectations)) if args.expectations else None
        targets = validate_targets(cases, overlay, config.locale)
        async with CatalogEvaluation(config, targets, trace) as catalog:
            result = await evaluate(config, directory, cases, trace, transcriber, interpreter, catalog)
            catalog.verify()
            result['catalog'] = {key: catalog.head[key] for key in
                                 ('generation', 'index_generation', 'index_signature', 'track_count')}
            result['scope'] = 'catalog selection preview; no device access or command execution'
            return result
    if getattr(args, 'expectations', None):
        raise ValueError('--expectations requires --catalog')
    return await evaluate(config, directory, cases, trace, transcriber, interpreter)


async def evaluate(config, directory, cases, trace, transcriber, interpreter, catalog=None):
    results = []
    for case in cases:
        if catalog is not None:
            catalog.verify()
        if case.get('file') != case['id'] + '.wav':
            raise ValueError('invalid sample filename')
        audio = load_audio(directory / case['file'], max_seconds=config.speech.get('max_seconds', 30))
        if audio_details(audio)['sha256'] != case.get('sha256'):
            raise ValueError('sample checksum changed; generate a new corpus')
        trace.event('sample', {'id': case['id']})
        try:
            transcript = await transcribe_file(config, directory / case['file'], trace, provider=transcriber)
            actual = await interpretation(transcript['command_text'], config, trace, interpreter)
            matched = comparable(actual) == comparable(case['expected'])
            row = {'id': case['id'], 'passed': matched, 'interpretation_match': matched,
                            'transcription_match': comparable(transcript['command_text']) == comparable(case['text']),
                            'text': transcript['text'], 'expected': case['expected'], 'actual': actual,
                            'transcription_ms': transcript['transcription_ms'],
                            'failed_stage': None if matched else 'interpretation'}
            if catalog is not None and music_case(case):
                row.update(await catalog.evaluate(case, actual))
            results.append(row)
        except (NoSpeech, InvalidSpeech, SpeechUnavailable) as exc:
            results.append({'id': case['id'], 'passed': False, 'failed_stage': 'transcription',
                            'error_type': type(exc).__name__})
        trace.event('sample_result', results[-1])
    passed = sum(row['passed'] for row in results)
    music_ids = {case['id'] for case in cases if music_case(case)}
    return {'status': 'evaluated' if passed == len(results) else 'evaluation_failed',
            'passed': passed, 'total': len(results), 'cases': results,
            'interpretation_passed': sum(row.get('interpretation_match', False) for row in results),
            'selection_passed': sum(row['passed'] for row in results if row['id'] in music_ids) if catalog else None,
            'selection_total': len(music_ids) if catalog else None,
            'scope': 'interpretation only; no catalog lookup, settings changes or device access'}
