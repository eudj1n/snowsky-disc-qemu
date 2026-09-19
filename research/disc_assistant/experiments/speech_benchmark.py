"""Fixed-audio STT comparison in temporary or existing servers; no DISC access."""
import argparse
import asyncio
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import statistics
import subprocess
import time
import urllib.error
import urllib.request

from research.disc_assistant.assistant.interpreter import interpret_request, InterpretationContext
from research.disc_assistant.assistant.languages import normalized, load_languages
from research.disc_assistant.assistant.responses import locale_code
from research.disc_assistant.assistant.local_service import endpoint
from research.disc_assistant.assistant.speech import SpeechContext
from research.disc_assistant.assistant.voice.backends import model_digest
from research.disc_assistant.assistant.voice.files import audio_details, command_text, load_audio, resolve_path
from research.disc_assistant.assistant.voice.resident import WhisperServer
from research.disc_assistant.assistant.voice.samples import read_json, comparable

IMAGE = 'disc-assistant-whisper:1.9.4'
DECODERS = (('beam5', 5, 5), ('greedy', 1, 1))


def private_json(path, value):
    with open(path, 'x', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def cases_from_inputs(samples, audio_paths, locale):
    cases = []
    if samples:
        root = resolve_path(samples)
        manifests = [root / 'manifest.json'] if (root / 'manifest.json').is_file() else sorted(root.glob('*/manifest.json'))
        if not manifests:
            raise ValueError('samples must contain a manifest.json (or locale subdirectories with manifests)')
        for path in manifests:
            data = read_json(path)
            if (not isinstance(data, dict) or data.get('version') != 1 or data.get('status') != 'complete'
                    or not isinstance(data.get('cases'), list) or not 1 <= len(data['cases']) <= 100):
                raise ValueError('samples require a complete version-1 manifest')
            for case in data['cases']:
                if not isinstance(case, dict) or not isinstance(case.get('file'), str) or 'id' not in case:
                    raise ValueError('sample requires an id and file')
                file = (path.parent / case['file']).resolve()
                if not file.is_relative_to(path.parent.resolve()):
                    raise ValueError('sample file must remain inside its manifest directory')
                audio = load_audio(file)
                details = audio_details(audio)
                if details['sha256'] != case.get('sha256'):
                    raise ValueError('sample checksum changed')
                cases.append({'id': case['id'], 'locale': locale_code(case.get('locale', data.get('locale'))),
                              'text': case.get('text'), 'expected': case.get('expected'),
                              'audio': audio, **details})
    else:
        for i, path in enumerate(audio_paths):
            audio = load_audio(resolve_path(path))
            cases.append({'id': f'audio-{i+1:03}', 'locale': locale_code(locale), 'text': None,
                          'expected': None, 'audio': audio, **audio_details(audio)})
    if not 1 <= len(cases) <= 100:
        raise ValueError('benchmark requires 1..100 recordings')
    keys = set()
    for case in cases:
        if not isinstance(case['id'], str) or not 1 <= len(case['id']) <= 64:
            raise ValueError('invalid sample id')
        key = (case['locale'], case['id'])
        if key in keys:
            raise ValueError('duplicate sample id within locale')
        keys.add(key)
        if case['text'] is not None and (not isinstance(case['text'], str) or len(case['text']) > 1000):
            raise ValueError('invalid reference text')
        if case['expected'] is not None and not isinstance(case['expected'], dict):
            raise ValueError('invalid reference interpretation')
    return cases


@contextmanager
def server(model, threads, image=IMAGE):
    """Only owns its random container; no managed-service restart or shared volume."""
    name = 'disc-stt-bench-' + secrets.token_hex(8)
    started = time.perf_counter()
    try:
        subprocess.run(['docker', 'run', '--pull=never', '-d', '--name', name,
                        '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                        '--tmpfs', '/tmp:size=64m,mode=1777', '-p', '127.0.0.1::18119',
                        '--mount', f'type=bind,src={model},dst=/models/whisper.bin,readonly', image,
                        '-m', '/models/whisper.bin', '--host', '0.0.0.0', '--port', '18119',
                        '-t', str(threads), '-ng', '-nf', '-nlp'], check=True, capture_output=True, timeout=30)
        address = subprocess.check_output(['docker', 'port', name, '18119/tcp'], text=True, timeout=10).strip()
        if not address.startswith('127.0.0.1:') or not address[10:].isdigit():
            raise RuntimeError('unexpected benchmark port binding')
        url = 'http://' + address
        deadline = time.monotonic() + 120
        while True:
            try:
                with urllib.request.urlopen(url + '/health', timeout=2) as reply:
                    if reply.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('benchmark Whisper startup timed out')
            time.sleep(.25)
        yield url + '/inference', round((time.perf_counter() - started) * 1000, 3)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


async def measure(provider, case, identity):
    started = time.perf_counter()
    row = {**identity, 'case': case['id'], 'locale': case['locale'], 'audio_sha256': case['sha256'],
           'duration_ms': case['duration_ms']}
    try:
        result = await provider.transcribe(case['audio'], SpeechContext(case['locale'], 'benchmark'))
        # STT-only timer excludes interpretation, journal, search, device and TTS.
        elapsed = (time.perf_counter() - started) * 1000
        try:
            intent = await interpret_request(command_text(result.text), InterpretationContext(case['locale']))
            actual = {'status': 'recognized', 'intent': asdict(intent)}
        except ValueError:
            actual = {'status': 'unrecognized'}
        row.update(status='ok', text=result.text, actual=actual,
                   text_correct=(normalized(command_text(result.text)) == normalized(command_text(case['text'])))
                   if case['text'] is not None else None,
                   interpretation_correct=(comparable(actual) == comparable(case['expected']))
                   if case['expected'] is not None else None)
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        row.update(status='error', error_type=type(exc).__name__,
                   text_correct=False if case['text'] is not None else None,
                   interpretation_correct=False if case['expected'] is not None else None)
    row.update(stt_ms=round(elapsed, 3), rtf=round(elapsed / case['duration_ms'], 4))
    return row


def summarize(rows):
    summaries = []
    keys = sorted({(r['profile'], r['locale']) for r in rows if not r['warmup']})
    for profile, locale in keys:
        measured = [r for r in rows if (r['profile'], r['locale']) == (profile, locale) and not r['warmup']]
        warm = [r for r in measured if r['status'] == 'ok' and not r['first_request']]
        times = sorted(r['stt_ms'] for r in warm)
        summary = {'profile': profile, 'locale': locale, 'attempts': len(measured),
                   'errors': sum(r['status'] == 'error' for r in measured), 'warm_successes': len(warm),
                   'warm_median_ms': round(statistics.median(times), 3) if times else None,
                   'warm_p95_ms': times[math.ceil(.95 * len(times)) - 1] if times else None,
                   'warm_median_rtf': statistics.median(r['rtf'] for r in warm) if warm else None}
        for metric in ('text_correct', 'interpretation_correct'):
            labeled = [r for r in measured if r.get(metric) is not None]
            summary[metric] = {'correct': sum(r[metric] for r in labeled), 'total': len(labeled)} if labeled else None
        summaries.append(summary)
    return summaries


async def benchmark(args, config):
    external = args.server is not None
    if external:
        endpoint(args.server, '/inference')
        if args.threads is not None:
            raise ValueError('--threads starts Docker profiles; for --server use --server-threads as a declaration only')
        if len(args.model or []) > 1:
            raise ValueError('--server uses one already loaded model; specify at most one --model')
    elif args.server_threads is not None or args.server_label is not None:
        raise ValueError('--server-threads/--server-label require --server')
    thread_counts = [args.server_threads] if external else (args.threads or [2, 4])
    cases = cases_from_inputs(args.samples, args.audio, args.locale or config.locale)
    models = [resolve_path(p) for p in (args.model or [config.speech.get('model', '')])]
    if any(not p.is_file() or (not external and ',' in str(p)) for p in models) or len(set(models)) != len(models):
        raise ValueError('select unique existing model files (Docker mount paths cannot contain commas)')
    fingerprints = []
    for path in models:
        stat = path.stat()
        fingerprints.append({'model': path.name, 'sha256': model_digest(str(path), stat.st_size, stat.st_mtime_ns)})
    image = {'Id': None, 'Architecture': None}
    if not external:
        try:
            image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', IMAGE], text=True,
                                                      stderr=subprocess.DEVNULL, timeout=15))[0]
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError('benchmark requires Docker and the installed Whisper image; run setup --all first') from exc
    output = resolve_path(args.output)
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents:
        raise ValueError('benchmark audio/reports must live outside the repository')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    # Freeze bytes once so every profile gets the identical recording.
    frozen = []
    for i, case in enumerate(cases):
        filename = f'{i:03}.wav'
        with open(output / filename, 'xb', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
            stream.write(case['audio'].data)
        frozen.append({k: case[k] for k in ('id', 'locale', 'text', 'expected', 'sha256')} | {'file': filename})
    private_json(output / 'manifest.json', {'version': 1, 'status': 'complete', 'cases': frozen})
    records, profiles, failures = [], [], []
    report = {'version': 1, 'scope': 'STT and interpreter only; no search, device execution, journal or TTS',
              'status': 'running', 'image_id': image['Id'], 'image_architecture': image['Architecture'],
              'execution': 'external_server' if external else 'managed_docker',
              'server_url': args.server, 'server_label': args.server_label,
              'first_request_scope': 'benchmark_run' if external else 'fresh_server',
              'runner_system': platform.system(), 'runner_machine': platform.machine(),
              'grammar_sha256': {locale: hashlib.sha256(json.dumps(asdict(load_languages((locale,))),
                                    sort_keys=True).encode()).hexdigest() for locale in {c['locale'] for c in cases}},
              'catalog_hints': False, 'repeats': args.repeats, 'warmup_per_decoder': args.warmup,
              'model_binding': ('checksum of operator reference file only; server model is not attested or loaded by benchmark'
                                if external else 'checksum of read-only mounted operator file; endpoint does not attest weights'),
              'models': fingerprints, 'profiles': profiles, 'failures': failures}
    private_json(output / 'run.json', report)
    try:
        with open(output / 'rows.jsonl', 'x', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
            for model_index, (model, fingerprint) in enumerate(zip(models, fingerprints)):
                for threads in thread_counts:
                    group = 'external' if external else f'm{model_index}-t{threads}'
                    if external:
                        print(f'Using existing server: {args.server}; threads={threads} (operator-declared, not changed)', flush=True)
                    else:
                        print(f'Starting {group}: {model.name}, {threads} threads', flush=True)
                    try:
                        context = nullcontext((args.server, None)) if external else server(model, threads)
                        with context as (url, startup_ms):
                            providers = []
                            for label, beam, best in DECODERS:
                                provider = WhisperServer({'model': str(model), 'server_url': url,
                                                          'timeout': args.timeout}, beam_size=beam, best_of=best)
                                evidence = provider.evidence() # Hashing is outside the STT timer.
                                if evidence['model_sha256'] != fingerprint['sha256']:
                                    raise ValueError('model changed before comparison')
                                profile = group + '-' + label
                                profiles.append({'id': profile, 'threads': threads, 'model_sha256': fingerprint['sha256'],
                                                 'threads_binding': 'operator_declared_not_server_attested' if external else 'launch_arguments',
                                                 'decoder': evidence['decoder'], 'startup_ms': startup_ms})
                                providers.append((profile, provider))
                            first_request = True
                            rounds = [(True, n, cases[:1]) for n in range(args.warmup)] + [
                                (False, n, cases) for n in range(args.repeats)]
                            for warmup, repeat, cohort in rounds:
                                for case_index, case in enumerate(cohort):
                                    order = providers if (repeat + case_index) % 2 == 0 else providers[::-1]
                                    for profile, provider in order:
                                        row = await measure(provider, case, {'profile': profile, 'warmup': warmup,
                                            'repeat': repeat, 'first_request': first_request})
                                        first_request = False
                                        records.append(row)
                                        stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush()
                                        print(f'{profile} {case["locale"]}/{case["id"]}: {row["stt_ms"]} ms ({row["status"]})', flush=True)
                            # Detect an externally replaced model; do not report a valid paired comparison.
                            with model.open('rb') as model_file:
                                if hashlib.file_digest(model_file, 'sha256').hexdigest() != fingerprint['sha256']:
                                    raise ValueError('model changed during comparison')
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                        failures.append({'group': group, 'error_type': type(exc).__name__})
                        print(f'{group}: failed ({type(exc).__name__}); see report', flush=True)
        report['status'] = 'complete' if not failures and all(r['status'] == 'ok' for r in records) else 'partial'
    finally:
        if report['status'] == 'running':
            report['status'] = 'interrupted'
        failed_groups = {failure['group'] for failure in failures}
        valid = [row for row in records if row['profile'].rsplit('-', 1)[0] not in failed_groups]
        report.update(summary=summarize(valid), rows=records, excluded_group_rows=len(records) - len(valid))
        private_json(output / 'report.json', report)
        print(f'Report: {output / "report.json"}', flush=True)
    return 0 if report['status'] == 'complete' else 1


def main(argv, config):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--samples', help='existing manifest directory, or parent of locale directories')
    source.add_argument('--audio', action='append', default=[], help='unlabelled PCM WAV; repeat for more files')
    parser.add_argument('--locale', help='locale for unlabelled audio; defaults to config')
    parser.add_argument('--output', required=True, help='new private directory outside the checkout')
    parser.add_argument('--model', action='append', help='existing model file; repeat to compare quantization/models')
    parser.add_argument('--threads', type=int, nargs='+', help='Docker thread profiles; default 2 4')
    parser.add_argument('--server', help='existing loopback /inference URL; no Docker or process lifecycle calls')
    parser.add_argument('--server-threads', type=int, help='declare existing server threads for the report; does not change them')
    parser.add_argument('--server-label', help='operator-provided server build/backend label (not attested)')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args(argv)
    if (not 1 <= args.repeats <= 20 or not 0 <= args.warmup <= 5 or not 1 <= args.timeout <= 600
            or (args.threads is not None and (not 1 <= len(args.threads) <= 8
                or any(not 1 <= n <= 64 for n in args.threads) or len(set(args.threads)) != len(args.threads)))
            or (args.server_threads is not None and not 1 <= args.server_threads <= 64)
            or (args.server_label is not None and (not 1 <= len(args.server_label) <= 120
                or any(ord(c) < 32 for c in args.server_label))) or len(args.model or []) > 4):
        raise ValueError('invalid benchmark bounds (see speech-benchmark --help)')
    return asyncio.run(benchmark(args, config))
