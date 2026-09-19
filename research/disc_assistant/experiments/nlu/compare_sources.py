"""Repeatable offline source comparison. Examined data is regression, not holdout."""
import argparse
import asyncio
import json
from pathlib import Path
import statistics

from research.disc_assistant.assistant.command_catalog import CommandCatalog, digest
from research.disc_assistant.assistant.interpreter import InterpretationContext
from research.disc_assistant.assistant.interpretation_sources import (
    LiteralSource, SlotSource, CommandModelSource, collect, diagnostic_choice)
from research.disc_assistant.assistant.understanding import single_action
from research.disc_assistant.experiments.nlu.dataset import load

ROOT = Path(__file__).parent


def metrics(rows):
    positives = [r for r in rows if r['expected'] is not None]
    negatives = [r for r in rows if r['expected'] is None]
    return {
        'positive_count': len(positives),
        'exact_complete_intents': sum(r['actual'] == r['expected'] for r in positives),
        'negative_count': len(negatives),
        'false_activations': sum(r['actual'] is not None for r in negatives),
        'language': {'correct': sum(r['actual'] == r['expected'] for r in positives if 'locale' in r['expected']),
                     'total': sum('locale' in r['expected'] for r in positives)},
        'music': {'correct': sum(r['actual'] == r['expected'] for r in positives if 'query' in r['expected']),
                  'total': sum('query' in r['expected'] for r in positives)},
        'median_ms': round(statistics.median(r['elapsed_ms'] for r in rows), 3),
    }


async def evaluate(cases, directory):
    sources = (LiteralSource(), SlotSource(), CommandModelSource(directory))
    records = []
    for case in cases:
        text, context = case['text'], InterpretationContext(case['locale'])
        results = await collect(text, context, sources, timeout_ms=100)
        policy = single_action(text, context.locale)
        primary = {**results[0], 'source': 'live_rules_with_policy'}
        if not policy['supported']:
            primary.update(status='unsupported', intent=None, reason=policy['reason'])
        candidate = {**diagnostic_choice(text, context, results), 'source': 'diagnostic_priority',
                     'elapsed_ms': sum(r['elapsed_ms'] for r in results)}
        records.append({'id': case['id'], 'locale': case['locale'], 'set': case['set'],
                        'text': text, 'expected': case['intent'], 'policy': policy,
                        'results': [*results, primary, candidate]})
    summaries = {}
    for subset in sorted({r['set'] for r in records}):
        summaries[subset] = {}
        for locale in sorted({r['locale'] for r in records}):
            group = [r for r in records if r['set'] == subset and r['locale'] == locale]
            summaries[subset][locale] = {
                name: metrics([{'expected': r['expected'], 'actual': value['intent'], 'elapsed_ms': value['elapsed_ms']}
                               for r in group for value in r['results'] if value['source'] == name])
                for name in ('literal', 'slots', 'command_model', 'live_rules_with_policy', 'diagnostic_priority')}
    return {'summary': summaries, 'cases': records}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, help='Optional directory containing ru/en-commands.json; no training')
    parser.add_argument('--output', type=Path, required=True, help='New directory; never user runtime storage')
    args = parser.parse_args(argv)
    manifest, rows = load(ROOT / 'datasets/commands-v2')
    acceptance = json.loads((ROOT / 'slot_acceptance.json').read_text())
    cases = [{**r, 'set': 'acceptance'} for r in acceptance['cases']]
    cases += [{**r, 'set': 'examined_v2_test_regression'} for r in rows if r['split'] == 'test']
    args.output.mkdir(parents=True, exist_ok=False)
    catalog = CommandCatalog(args.output / 'catalog')
    try:
        snapshots = {locale: catalog.publish(locale, json.loads((args.models / f'{locale}-commands.json').read_text())
                                             if args.models else None)['id'] for locale in ('ru', 'en')}
    finally:
        catalog.close()
    report = asyncio.run(evaluate(cases, args.output / 'catalog'))
    report.update(version=1, scope=acceptance['scope'], dataset_sha256=manifest['sha256'],
                  acceptance_sha256=digest(acceptance), snapshots=snapshots,
                  model_selection='none; imported previously frozen snapshots; no retraining')
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
