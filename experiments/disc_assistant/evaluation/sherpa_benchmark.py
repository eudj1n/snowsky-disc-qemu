"""Evaluate pinned Russian Zipformer on fixed WAVs without loading Assistant config."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import time

from experiments.disc_assistant.evaluation.sherpa_setup import (
    MODEL_ID, REVISION, FILES, outside_repo, verify_models,
)
from experiments.disc_assistant.evaluation.speech_benchmark import (
    cases_from_inputs, measure, private_json, summarize,
)


from experiments.disc_assistant.assistant.voice.sherpa_model import SherpaRussian


async def benchmark(args):
    import sherpa_onnx
    root = outside_repo(args.root)
    directory = root / MODEL_ID
    verify_models(directory)
    cases = cases_from_inputs(args.samples, args.audio, 'ru')
    if any(case['locale'] != 'ru' for case in cases):
        raise ValueError('select a Russian-only corpus for this monolingual model')
    output = outside_repo(args.output)
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    frozen = []
    for i, case in enumerate(cases):
        filename = f'{i:03}.wav'
        (output / filename).write_bytes(case['audio'].data)
        frozen.append({key: case[key] for key in ('id', 'locale', 'text', 'expected', 'sha256')}
                      | {'file': filename})
    private_json(output / 'manifest.json', {'version': 1, 'status': 'complete', 'cases': frozen})
    records, profiles = [], []
    report = {
        'version': 1, 'status': 'running', 'scope': 'file STT and interpreter; no device/search/config access',
        'execution': 'native_cpu', 'engine': sherpa_onnx.__version__,
        'model': MODEL_ID, 'revision': REVISION, 'files_sha256': FILES,
        'runner_system': platform.system(), 'runner_machine': platform.machine(),
        'python': platform.python_version(), 'threads': args.threads,
        'repeats': args.repeats, 'warmup': args.warmup,
        'decoder': 'greedy_search', 'catalog_hints': False, 'tail_padding_ms': 300,
        'timing': 'file throughput, not microphone streaming latency; load separate; first request excluded from warm summaries',
        'profiles': profiles,
    }
    private_json(output / 'run.json', report)
    try:
        with (output / 'rows.jsonl').open('x') as stream:
            for threads in args.threads:
                started = time.perf_counter()
                provider = SherpaRussian(directory, threads)
                profile = f'sherpa-ru-int8-t{threads}'
                profiles.append({'id': profile, 'load_ms': round((time.perf_counter() - started) * 1000, 3)})
                first = True
                for repeat in range(-args.warmup, args.repeats):
                    for case in cases:
                        row = await measure(provider, case, {
                            'profile': profile, 'repeat': repeat, 'warmup': repeat < 0, 'first_request': first,
                        })
                        first = False
                        records.append(row)
                        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                        stream.flush()
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                del provider
        verify_models(directory)
        report['status'] = 'complete' if all(r['status'] == 'ok' for r in records) else 'completed_with_errors'
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                      error_type=type(exc).__name__)
        raise
    finally:
        valid = report['status'] in ('complete', 'completed_with_errors')
        report.update(rows=records, summary=summarize(records) if valid else [],
                      summaries_valid=valid)
        private_json(output / 'report.json', report)
    return 0 if report['status'] == 'complete' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='~/disc-speech/sherpa-onnx')
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--audio', action='append', type=Path)
    inputs.add_argument('--samples', type=Path)
    parser.add_argument('--output', required=True)
    parser.add_argument('--threads', type=int, nargs='+', default=[2, 4])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--warmup', type=int, default=1)
    args = parser.parse_args()
    if (not 1 <= args.repeats <= 20 or not 0 <= args.warmup <= 5
            or not 1 <= len(args.threads) <= 4 or len(set(args.threads)) != len(args.threads)
            or any(not 1 <= n <= 16 for n in args.threads)):
        parser.error('use 1..20 repeats, 0..5 warmups, and 1..4 unique thread counts in 1..16')
    raise SystemExit(asyncio.run(benchmark(args)))


if __name__ == '__main__':
    main()
