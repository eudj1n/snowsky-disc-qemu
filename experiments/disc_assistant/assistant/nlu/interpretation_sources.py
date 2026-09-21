"""Independent interpretation evidence, comparison and bounded shadow collection.

A source never receives application state, Controller or a search client. Scores
remain source-local; no learned arbitration or action dispatch lives here.
"""
from experiments.disc_assistant.assistant.nlu import RULES_VERSION
from experiments.disc_assistant.assistant.nlu.intents import AlbumIntent, music_from_dict

import asyncio
from dataclasses import asdict, dataclass, field
import json
import math
import sqlite3
import time
from typing import Protocol

from experiments.disc_assistant.assistant.nlu.command_catalog import digest, source as catalog_source, validate_classifier
from experiments.disc_assistant.assistant.nlu.command_features import classify
from experiments.disc_assistant.assistant.nlu.interpreter import InterpretationContext, validate_intent
from experiments.disc_assistant.assistant.nlu.intents import parse, Intent, ControlIntent, LanguageIntent, VolumeIntent
from experiments.disc_assistant.assistant.nlu.languages import load_languages
from experiments.disc_assistant.assistant.nlu.understanding import extract, single_action


@dataclass(frozen=True)
class Evidence:
    source: str
    version: str
    status: str
    label: str = 'reject'
    intent: object = None
    reason: str = ''
    spans: tuple = ()
    scores: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)


class Source(Protocol):
    name: str
    version: str

    async def evaluate(self, text: str, context: InterpretationContext) -> Evidence: ...


def label(intent):
    return ('play' if type(intent) in (Intent, AlbumIntent) else 'language' if type(intent) is LanguageIntent
            else intent.action if type(intent) in (ControlIntent, VolumeIntent) else 'reject')


def validate(value, provider, text):
    if (type(value) is not Evidence or value.source != provider.name or value.version != provider.version
            or value.status not in ('recognized', 'rejected', 'unsupported', 'incomplete', 'unavailable')
            or value.label not in ('play', 'language', 'pause', 'resume', 'stop', 'next', 'previous', 'like', 'dislike', 'now_playing', 'volume', 'reject')
            or not isinstance(value.reason, str) or type(value.scores) is not dict
            or type(value.provenance) is not dict or not isinstance(value.spans, (list, tuple))):
        raise ValueError('invalid source evidence')
    if value.status == 'recognized':
        validate_intent(value.intent)
        if label(value.intent) != value.label:
            raise ValueError('source label disagrees with intent')
    elif value.intent is not None:
        raise ValueError('nonrecognized source cannot carry an intent')
    if len(value.spans) > 4:
        raise ValueError('too many source spans')
    for span in value.spans:
        if (set(span) != {'name', 'start', 'end', 'text'} or type(span['start']) is not int or type(span['end']) is not int
                or not 0 <= span['start'] < span['end'] <= len(text) or text[span['start']:span['end']] != span['text']):
            raise ValueError('invalid source span')
    if value.scores:
        if (set(value.scores) != {'value', 'margin', 'kind', 'calibrated'} or value.scores['calibrated'] is not False
                or not isinstance(value.scores['kind'], str) or not value.scores['kind']
                or any(type(value.scores[k]) not in (float, int) or not math.isfinite(value.scores[k]) or not 0 <= value.scores[k] <= 1 for k in ('value', 'margin'))):
            raise ValueError('invalid or unsupported calibrated scores')
    # Invalid diagnostic metadata must not fail later journal serialization.
    json.dumps(asdict(value), allow_nan=False)
    return value


class LiteralSource:
    name, version = 'literal', RULES_VERSION

    async def evaluate(self, text, context):
        rules = load_languages((context.locale,))
        provenance = {'rules_sha256': digest(asdict(rules))}
        try:
            intent = parse(text, rules)
        except ValueError:
            return Evidence(self.name, self.version, 'rejected', reason='no_literal_match', provenance=provenance)
        return Evidence(self.name, self.version, 'recognized', label(intent), intent, 'literal_rule', provenance=provenance)


class SlotSource:
    name, version = 'slots', 'single-action-v2'

    async def evaluate(self, text, context):
        result = extract(text, context.locale)
        raw = result['intent']
        intent = (music_from_dict(raw) if result['label'] == 'play' else LanguageIntent(**raw) if result['label'] == 'language'
                  else ControlIntent(**raw)) if raw is not None else None
        return Evidence(self.name, self.version, result['status'], result['label'], intent, result['reason'],
                        tuple(result['spans']), provenance=result['evidence'])


class CommandModelSource:
    name, version = 'command_model', 'portable-text-v1'

    def __init__(self, directory):
        self.path = directory / 'assistant.sqlite3'

    async def evaluate(self, text, context):
        # Shadow must not migrate, seed a catalog or wait behind an application writer.
        if not self.path.exists():
            return Evidence(self.name, self.version, 'unavailable', reason='no_command_snapshot')
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0)
        try:
            row = db.execute('SELECT s.id,s.payload_json FROM command_snapshots s JOIN command_heads h ON h.snapshot_id=s.id WHERE h.locale=?', (context.locale,)).fetchone()
        finally:
            db.close()
        if row is None:
            return Evidence(self.name, self.version, 'unavailable', reason='no_command_snapshot')
        provenance = {'snapshot': row[0]}
        if len(row[1]) > 16*1024*1024:
            raise ValueError('command snapshot exceeds limit')
        snapshot = json.loads(row[1])
        provenance['source_hash'] = snapshot['source_hash']
        if snapshot['source_hash'] != digest(catalog_source(context.locale)):
            return Evidence(self.name, self.version, 'unavailable', reason='stale_command_snapshot', provenance=provenance)
        model = snapshot.get('classifier')
        if model is None:
            return Evidence(self.name, self.version, 'unavailable', reason='no_trained_snapshot', provenance=provenance)
        validate_classifier(model)
        prediction = classify(text, model)
        scores = {'value': prediction['score'], 'margin': prediction['margin'], 'kind': prediction['score_kind'], 'calibrated': False}
        provenance['model_sha256'] = digest(model)
        provenance['threshold'] = model['threshold']
        provenance['minimum_margin'] = model['margin']
        chosen = prediction['label']
        if not prediction['accepted'] or chosen == 'reject':
            return Evidence(self.name, self.version, 'rejected', reason='model_abstained', scores=scores, provenance=provenance)
        if chosen in ('play', 'language'):
            return Evidence(self.name, self.version, 'incomplete', chosen, reason='model_has_no_arguments', scores=scores, provenance=provenance)
        return Evidence(self.name, self.version, 'recognized', chosen, ControlIntent(chosen), 'classified_control', scores=scores, provenance=provenance)


def default_sources(config):
    sources = (LiteralSource(), SlotSource(), CommandModelSource(config.data_dir))
    if config.structured.get('enabled', False):
        from experiments.disc_assistant.assistant.nlu.structured_source import StructuredSource
        sources += (StructuredSource(config.structured),)
    return sources


async def measured(provider, text, context):
    start = time.perf_counter()
    try:
        evidence = validate(await provider.evaluate(text, context), provider, text)
    except Exception as exc:
        evidence = Evidence(provider.name, provider.version, 'unavailable', reason='source_failed',
                            provenance={'error_type': type(exc).__name__})
    return {**asdict(evidence), 'spans': list(evidence.spans), 'elapsed_ms': round((time.perf_counter()-start)*1000, 3)}


async def collect(text, context, sources, *, timeout_ms=100):
    if not 1 <= len(sources) <= 8 or len({s.name for s in sources}) != len(sources):
        raise ValueError('sources need 1..8 unique identities')
    started = time.perf_counter()
    tasks = [asyncio.create_task(measured(s, text, context)) for s in sources]
    try:
        done, pending = await asyncio.wait(tasks, timeout=timeout_ms/1000)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return [task.result() if task in done else {
            **asdict(Evidence(source.name, source.version, 'unavailable', reason='source_timeout')),
            'elapsed_ms': round((time.perf_counter()-started)*1000, 3)} for source, task in zip(sources, tasks)]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def diagnostic_choice(text, context, results):
    """Versioned preview policy, not weights and never the execution selector."""
    policy = single_action(text, context.locale)
    by_name = {r['source']: r for r in results}
    slots = by_name.get('slots')
    if slots and slots['status'] == 'incomplete' and policy['supported']:
        return {k: slots[k] for k in ('status', 'label', 'intent', 'source', 'reason', 'spans')}
    reason = None if policy['supported'] else policy['reason']
    if slots and (slots['status'] in ('unsupported', 'incomplete') or slots['reason'] in ('non_command_context', 'negated_command', 'quoted_command')):
        reason = slots['reason']
    if reason:
        return {'status': 'unsupported' if not policy['supported'] or (slots and slots['status'] == 'unsupported') else 'rejected',
                'label': 'reject', 'intent': None, 'source': 'single_action_context', 'reason': reason, 'spans': []}
    for name in ('slots', 'literal', 'command_model'):
        candidate = by_name.get(name)
        if candidate and candidate['status'] == 'recognized':
            return {k: candidate[k] for k in ('status', 'label', 'intent', 'source', 'reason', 'spans')}
    incomplete = next((r for r in results if r['status'] == 'incomplete'), None)
    return {'status': 'incomplete' if incomplete else 'rejected', 'label': incomplete['label'] if incomplete else 'reject',
            'intent': None, 'source': 'diagnostic-priority-v1', 'reason': 'no_complete_intent', 'spans': []}


def comparison(primary, results):
    return [{'source': r['source'], 'status_agrees': r['status'] == ('rejected' if primary['status'] == 'unrecognized' else primary['status']),
             'intent_agrees': r['intent'] == primary['intent'] if primary['status'] == r['status'] == 'recognized' else None}
            for r in results]


async def explain_sources(config, text, context=None):
    context = context or InterpretationContext(config.locale)
    results = await collect(text, context, default_sources(config), timeout_ms=config.shadow_timeout_ms)
    return {'sources': results, 'candidate': diagnostic_choice(text, context, results),
            'diagnostic_policy': 'priority-v1; source scores are not combined; never executes',
            'policy': single_action(text, context.locale), 'context': asdict(context)}
