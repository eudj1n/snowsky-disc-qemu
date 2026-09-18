"""Observed disagreement is not gold; reports never rerun or dispatch requests."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.disc_assistant import launcher
from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.interpreter import InterpretationContext, interpret_request
from research.disc_assistant.assistant.interpretation_sources import LiteralSource, SlotSource
from research.disc_assistant.assistant.journal import Trace, history_command
from research.disc_assistant.experiments.nlu import dataset, shadow_report as reports


def source(name='literal', intent=None, status='recognized', **extra):
    intent = {'action': 'pause'} if intent is None and status == 'recognized' else intent
    label = ('play' if 'query' in intent else 'language' if 'locale' in intent else intent['action']) if intent else 'reject'
    return {'source': name, 'version': 'v1', 'status': status, 'intent': intent, 'label': label,
            'reason': 'fixture', 'spans': [], 'scores': {}, 'provenance': {'rules_sha256': 'a'*64},
            'elapsed_ms': 2, **extra}


def record(identity='one', text='Pause', locale='en', sources=None, primary=None, speech=False):
    primary = primary or {'status': 'recognized', 'intent': {'action': 'pause'}}
    events = [{'phase': 'interpretation_started', 'payload': {'provider': {'name': 'rules', 'version': 'v1'}}},
              {'phase': 'single_action_policy', 'payload': {'supported': True, 'grammar_sha256': 'c'*64}},
              {'phase': 'interpretation_shadow', 'payload': {
                  'primary': primary, 'context': {'locale': locale, 'playback': 'unknown'},
                  'sources': sources if sources is not None else [source(), source('slots', {'action': 'stop'})],
                  'execution_source': 'primary_only'}}]
    if speech:
        events += [{'phase': 'audio_validated', 'payload': {'sha256': 'd'*64, 'path': '/private/secret.wav'}},
                   {'phase': 'speech_model', 'payload': {'model_sha256': 'e'*64}},
                   {'phase': 'speech_command_text', 'payload': {'text': text}}]
    return {'id': identity, 'command': 'ask', 'input': '[audio]' if speech else text, 'input_truncated': False,
            'context': {'locale': locale, 'language_rules_sha256': 'f'*64}, 'events': events,
            'device': 'PRIVATE_DEVICE', 'outcome': {'secret': 'PRIVATE_SECRET'}}


class ShadowReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, rows):
        path = self.root / name
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        return path

    def report(self, rows, name='report', **kwargs):
        return reports.build(self.write(name + '.jsonl', rows), self.root / name, **kwargs)

    def test_pending_queue_and_allowlisted_evidence_never_infer_gold(self):
        row = record()
        row['events'][2]['payload']['sources'][0]['provenance']['sdk_body'] = 'PRIVATE_SECRET'
        result = self.report([row])
        self.assertEqual(result['pending_rows'], 1)
        self.assertFalse(result['labels_inferred'])
        self.assertTrue(all(r['quality'] is None for r in result['sources']))
        pending = list(dataset.read_jsonl(self.root / 'report/pending.jsonl'))[0]
        dataset.validate_row(pending, pending=True)
        self.assertIsNone(pending['intent'])
        self.assertNotIn('sources', pending['origin'])
        evidence = (self.root / 'report/evidence.jsonl').read_text()
        self.assertNotIn('PRIVATE', evidence)
        self.assertIn('intent_disagreement', evidence)
        for file in (self.root / 'report').iterdir():
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / 'report').stat().st_mode & 0o777, 0o700)

    def test_availability_is_not_disagreement_and_all_scope_includes_agreements(self):
        row = record(sources=[source(), source('model', status='unavailable', reason='source_timeout')])
        report = self.report([row])
        self.assertEqual(report['pending_rows'], 0)
        self.assertEqual(report['disagreements'], {})
        model = next(r for r in report['sources'] if r['source'] == 'model')
        self.assertEqual(model['statuses'], {'unavailable': 1})
        self.assertEqual(model['available_latency']['samples'], 0)
        self.assertIsNone(model['available_latency']['p50_ms'])
        self.assertEqual(self.report([row], 'all', scope='all')['pending_rows'], 1)

    def test_language_modality_stt_and_source_revisions_are_not_merged(self):
        a = record(sources=[source()])
        b = record('two', speech=True, sources=[source()])
        c = record('three', speech=True, sources=[source(provenance={'rules_sha256': 'b'*64})])
        d = record('four', text='Пауза', locale='ru', sources=[source()])
        e = deepcopy(b); e['id'] = 'five'; e['events'][-2]['payload']['model_sha256'] = '9'*64
        result = self.report([a, b, c, d, e], scope='all')
        rows = [r for r in result['sources'] if r['role'] == 'shadow']
        self.assertEqual(len(rows), 5)
        self.assertEqual(result['pending_rows'], 2)  # Same exact input, distinct observations.
        evidence = list(dataset.read_jsonl(self.root / 'report/evidence.jsonl'))
        self.assertEqual(evidence[1]['text'], 'Pause')
        self.assertEqual(evidence[1]['modality'], 'speech')
        self.assertNotIn('secret.wav', json.dumps(evidence))

    def test_duplicate_requests_count_once_and_conflicting_duplicates_fail(self):
        row = record()
        result = self.report([row, row])
        self.assertEqual(result['coverage']['duplicate_request'], 1)
        self.assertEqual(result['coverage']['eligible_requests'], 1)
        other = deepcopy(row); other['input'] = 'Stop'
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.report([row, other], 'conflict')
        self.assertFalse((self.root / 'conflict').exists())

    def test_partial_missing_malformed_and_locale_mismatched_evidence_is_counted(self):
        no = record('no'); no['events'] = []
        truncated = record('truncated'); truncated['input_truncated'] = True
        broken = record('broken'); broken['events'][2]['payload']['sources'][0]['intent'] = {'truncated': True}
        locale = record('locale'); locale['events'][2]['payload']['context']['locale'] = 'ru'
        failure = record('failure'); failure['events'][2]['payload'] = {'status': 'unavailable', 'error_type': 'ValueError'}
        ambiguous = record('ambiguous'); ambiguous['events'].append(ambiguous['events'][2])
        result = self.report([no, truncated, broken, locale, failure, ambiguous, record('valid')])
        self.assertEqual(result['coverage'], {'input_records': 7, 'no_shadow': 1, 'unusable_input': 1,
                         'invalid_shadow': 2, 'collector_unavailable': 1, 'ambiguous_shadow': 1, 'eligible_requests': 1})

    def test_exact_text_spans_retained_while_normalized_and_audio_variants_share_groups(self):
        rows = [record('one', text='Pause', speech=True), record('two', text='pause'),
                record('three', text='Put playback on pause', speech=True)]
        self.report(rows)
        pending = list(dataset.read_jsonl(self.root / 'report/pending.jsonl'))
        self.assertEqual({r['text'] for r in pending}, {'Pause', 'pause', 'Put playback on pause'})
        self.assertEqual(len({r['group'] for r in pending}), 1)

    def test_explicit_review_adds_quality_without_treating_outcomes_as_labels(self):
        rows = [record(), record('two', text='Do not pause', primary={'status': 'unrecognized', 'intent': None},
                                 sources=[source(), source('slots', status='rejected')])]
        history = self.write('history.jsonl', rows)
        reports.build(history, self.root / 'initial')
        pending = list(dataset.read_jsonl(self.root / 'initial/pending.jsonl'))
        annotations = []
        for row in pending:
            negative = row['text'] == 'Do not pause'
            annotations.append({'id': row['id'], 'group': row['group'], 'split': 'regression',
                                'review': {'status': 'reviewed', 'by': 'fixture-human', 'note': 'Explicit fixture annotation'},
                                'label': 'reject' if negative else 'pause',
                                'intent': None if negative else {'action': 'pause'}, 'slots': []})
        reviewed = self.root / 'reviewed.jsonl'
        dataset.review(self.root / 'initial/pending.jsonl', self.write('annotations.jsonl', annotations), reviewed)
        report = reports.build(history, self.root / 'scored', reviewed=reviewed)
        source_rows = {r['source']: r for r in report['sources']}
        self.assertEqual(source_rows['literal']['quality']['false_activations'], 1)
        self.assertEqual(source_rows['literal']['quality']['exact_intent_correct'], 1)
        self.assertEqual(source_rows['slots']['quality']['wrong_action'], 1)
        self.assertEqual(source_rows['rules']['quality']['false_activations'], 0)
        self.assertIn('Reviewed observations', (self.root / 'scored/report.md').read_text())
        self.assertEqual(report['reviewed_unique_inputs'], 2)

    def test_argument_mismatch_is_separate_from_wrong_action_and_missing_arguments(self):
        expected = {'query': 'Blur', 'kind': 'artist', 'artist': None, 'title': None}
        wrong = {**expected, 'kind': 'auto'}
        row = record(text='Play artist Blur', sources=[source(intent=wrong), source('slots', intent=expected)],
                     primary={'status': 'recognized', 'intent': expected})
        self.report([row])
        pending = list(dataset.read_jsonl(self.root / 'report/pending.jsonl'))[0]
        pending.update(split='regression', review={'status': 'reviewed', 'by': 'fixture', 'note': 'Explicit artist'},
                       label='play', intent=expected, slots=[{'field': 'query', 'start': 12, 'end': 16, 'text': 'Blur'}])
        report = self.report([row], 'scored', reviewed=self.write('gold.jsonl', [pending]))
        literal = next(r for r in report['sources'] if r['source'] == 'literal')
        self.assertEqual(literal['quality']['wrong_arguments'], 1)
        self.assertEqual(literal['quality']['wrong_action'], 0)
        self.assertEqual(report['disagreements']['argument_disagreement'], 1)

    def test_review_must_match_input_and_cannot_supply_duplicate_or_unknown_ids(self):
        self.report([record()])
        pending = list(dataset.read_jsonl(self.root / 'report/pending.jsonl'))[0]
        for name, rows in [('duplicate', [pending, pending]), ('foreign', [{**pending, 'id': 'foreign'}]),
                           ('changed', [{**pending, 'text': 'Changed'}])]:
            with self.assertRaises(ValueError):
                self.report([record()], name, reviewed=self.write(name+'-gold.jsonl', rows))
            self.assertFalse((self.root / name).exists())

    def test_output_refuses_overwrite_repo_and_symlink_into_repo(self):
        self.report([record()])
        with self.assertRaises(FileExistsError): self.report([record()])
        forbidden = self.root / 'repo'; forbidden.mkdir()
        alias = self.root / 'alias'; alias.symlink_to(forbidden, target_is_directory=True)
        with patch.object(dataset, 'REPOSITORY', forbidden.resolve()):
            with self.assertRaises(ValueError):
                reports.build(self.root / 'report.jsonl', alias / 'report')

    def test_real_journal_export_is_consumed_without_provider_or_device_access(self):
        config_path = self.root / 'config.toml'
        config_path.write_text(f'[device]\nkey="fixture"\nhost="127.0.0.1"\n[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="en"\n')
        config = replace(load(config_path), shadow=True)
        with Trace(config, 'rank', '/rank Answer in Russian', source='interactive') as trace:
            with self.assertRaises(ValueError):
                asyncio.run(interpret_request('Answer in Russian', InterpretationContext('en'), trace=trace,
                                              shadow=(LiteralSource(), SlotSource())))
            trace.finish({'status': 'error'})
        history = self.root / 'real-export.jsonl'
        history_command(config, ['export', str(history)])
        with patch.object(LiteralSource, 'evaluate', side_effect=AssertionError('must not rerun')):
            report = reports.build(history, self.root / 'real-report')
        self.assertEqual(report['coverage']['eligible_requests'], 1)
        self.assertEqual(report['pending_rows'], 1)
        self.assertTrue(all(r['quality'] is None for r in report['sources']))

    def test_launcher_runs_without_config_and_resolves_caller_paths(self):
        with patch.dict(os.environ, {'DISC_ASSISTANT_CALLER_DIR': str(self.root)}), \
                patch.object(reports, 'main', return_value=0) as main, \
                patch.object(launcher, 'load', side_effect=AssertionError('no runtime config')):
            self.assertEqual(launcher.main(['--config', 'missing.toml', 'shadow-report', '--history=history.jsonl',
                                           '--output', 'report', '--reviewed', 'gold.jsonl']), 0)
            self.assertEqual(main.call_args.args[0], ['--history='+str(self.root/'history.jsonl'),
                              '--output', str(self.root/'report'), '--reviewed', str(self.root/'gold.jsonl')])

    def test_latency_unknowns_denominators_and_empty_export(self):
        self.assertEqual(reports.latency([None]), {'samples': 0, 'p50_ms': None, 'p95_ms': None})
        self.assertEqual(reports.latency(range(1, 21)), {'samples': 20, 'p50_ms': 10, 'p95_ms': 19})
        result = self.report([])
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['pending_rows'], 0)


if __name__ == '__main__':
    unittest.main()
