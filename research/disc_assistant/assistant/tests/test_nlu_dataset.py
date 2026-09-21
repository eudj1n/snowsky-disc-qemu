"""Annotation isolation, frozen splits and comparison accounting; no ML dependencies."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.disc_assistant.assistant.nlu.evaluation import dataset
from research.disc_assistant.assistant.nlu.evaluation.study_commands import calibrate, measurements, pipeline_score
from research.disc_assistant.assistant.nlu.command_catalog import source

CORPUS = Path(__file__).parents[2] / 'assistant/nlu/data/datasets/commands-v2'


def pending(text='pause', identity='sample'):
    return {'id': identity, 'locale': 'en', 'text': text, 'group': identity, 'split': None,
            'origin': {'kind': 'history_text'}, 'review': {'status': 'pending'},
            'label': None, 'intent': None, 'slots': []}


def annotated(text='pause', label='pause', identity='sample'):
    row = pending(text, identity)
    row.update(split='train', label=label, intent={'action': label},
               review={'status': 'reviewed', 'by': 'fixture-reviewer', 'note': 'fixture gold action'})
    if label == 'reject':
        row['intent'] = None
    return row


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest, self.rows = dataset.load(CORPUS)

    def write(self, name, rows):
        path = self.root / name
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return path

    def test_frozen_corpus_and_all_labels_per_language_split(self):
        self.assertEqual(len(self.rows), 609)
        self.assertEqual(dataset.audit(self.rows)['near_duplicates_to_review'], [])
        self.assertEqual({r['origin']['kind'] for r in self.rows if r['split'] == 'test'}, {'authored'})
        self.assertTrue(all(r['split'] == 'regression' for r in self.rows if r['origin']['kind'] == 'synthetic_stt'))
        with self.assertRaisesRegex(ValueError, 'pending'):
            dataset.validate_rows([pending()])

    def test_every_legacy_evaluation_case_is_retained_as_regression(self):
        root = CORPUS.parents[1]
        originals = json.loads((root / 'intents.json').read_text())['cases']
        originals += json.loads((root / 'command_challenge.json').read_text())['cases']
        expected = {r['id'] for r in originals if r.get('split') != 'train'}
        retained = {r['origin']['reference'] for r in self.rows if r['origin']['kind'] == 'prior_evaluation'
                    and r['split'] == 'regression'}
        self.assertEqual(retained, expected)

    def test_changed_frozen_bytes_are_rejected(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.root / 'cases.jsonl').write_bytes((CORPUS / 'cases.jsonl').read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'frozen manifest'):
            dataset.load(self.root)

    def test_duplicate_text_ids_and_audio_families_cannot_cross_splits(self):
        for kind in ('id', 'text', 'group'):
            rows = deepcopy(self.rows)
            train = next(r for r in rows if r['locale'] == 'en' and r['split'] == 'train' and r['label'] == 'pause')
            test = next(r for r in rows if r['locale'] == 'en' and r['split'] == 'test' and r['label'] == 'pause')
            test[kind] = train[kind]
            with self.assertRaises(ValueError): dataset.validate_rows(rows)
        rows = deepcopy(self.rows)
        regression = next(r for r in rows if r['split'] == 'regression')
        next(r for r in rows if r['split'] == 'test')['group'] = regression['group']
        with self.assertRaisesRegex(ValueError, 'group crosses'):
            dataset.validate_rows(rows)

    def test_spans_labels_and_canonical_slots_are_validated(self):
        music = deepcopy(next(r for r in self.rows if r['label'] == 'play'))
        invalid = []
        wrong = deepcopy(music); wrong['slots'][0]['end'] -= 1; invalid.append(wrong)
        wrong = deepcopy(music); wrong['intent']['query'] = 'Invented canonical artist'; invalid.append(wrong)
        wrong = deepcopy(music); wrong['intent'].pop('artist'); invalid.append(wrong)
        wrong = annotated(); wrong['label'] = 'resume'; invalid.append(wrong)
        wrong = annotated(); wrong['review'].pop('by'); invalid.append(wrong)
        wrong = annotated(); wrong['intent'] = {'action': 'delete'}; invalid.append(wrong)
        for row in invalid:
            with self.assertRaises(ValueError): dataset.validate_row(row)
        missing = annotated(label='language')
        missing['intent'] = None
        dataset.validate_row(missing)

    def test_collection_ignores_predictions_and_keeps_failures_and_quote_distinctions(self):
        records = []
        for i, text in enumerate(('Pause', 'pause', '"Pause"', 'Pause?', '/explain nonsense', '[audio]', '/status')):
            records.append({'id': str(i), 'command': 'ask' if i != 4 else 'explain', 'input': text,
                            'context': {'locale': 'en'}, 'status': 'error',
                            'outcome': {'action': 'stop'}, 'device': 'PRIVATE_HOST',
                            'events': [{'phase': 'parsed', 'payload': {'action': 'stop'}}]})
        records[5]['events'].append({'phase': 'speech_command_text', 'payload': {'text': 'Unknown speech text'}})
        output = self.root / 'pending.jsonl'
        dataset.collect(self.write('history.jsonl', records), output)
        rows = list(dataset.read_jsonl(output))
        self.assertEqual([r['text'] for r in rows], ['Pause', '"Pause"', 'Pause?', 'nonsense', 'Unknown speech text'])
        self.assertEqual(rows[-1]['origin']['kind'], 'history_stt')
        self.assertNotIn('PRIVATE_HOST', output.read_text())
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        for row in rows:
            dataset.validate_row(row, pending=True)
            self.assertIsNone(row['label'])
        with self.assertRaises(FileExistsError):
            dataset.collect(self.root / 'history.jsonl', output)

    def test_transcript_variants_share_recording_group_without_copying_paths(self):
        records = [{'id': str(i), 'command': 'ask', 'input': '[audio]', 'context': {'locale': 'en'},
            'events': [{'phase': 'audio_validated', 'payload': {'sha256': 'a'*64, 'path': '/private/example.wav'}},
                       {'phase': 'speech_model', 'payload': {'model_sha256': str(i)*64, 'model': 'private-model-name'}},
                       {'phase': 'speech_command_text', 'payload': {'text': text}}]}
                   for i, text in enumerate(('Play Lincoln Park', 'Play Linkin Park'))]
        output = self.root / 'speech.jsonl'
        dataset.collect(self.write('speech-history.jsonl', records), output)
        rows = list(dataset.read_jsonl(output))
        self.assertEqual(rows[0]['group'], rows[1]['group'])
        self.assertEqual(rows[0]['origin']['audio_sha256'], 'a'*64)
        self.assertNotEqual(rows[0]['origin']['stt_model_sha256'], rows[1]['origin']['stt_model_sha256'])
        self.assertNotIn('/private/', output.read_text())
        self.assertNotIn('private-model-name', output.read_text())

    def test_truncated_unknown_locale_and_audio_without_transcript_are_skipped(self):
        rows = [{'command': 'ask', 'input': 'Pause', 'input_truncated': True, 'context': {'locale': 'en'}},
                {'command': 'rank', 'input': '[audio]', 'context': {'locale': 'en'}},
                {'command': 'ask', 'input': 'Pause', 'context': {}},
                {'command': 'status', 'input': 'Pause', 'context': {'locale': 'en'}}]
        result = dataset.collect(self.write('history.jsonl', rows), self.root / 'out.jsonl')
        self.assertEqual(result['pending'], 0)

    def test_review_changes_only_explicit_annotations_and_preserves_original_text(self):
        queue = self.write('queue.jsonl', [pending(), pending('unknown', 'other')])
        gold = annotated()
        fields = {'id', 'group', 'split', 'review', 'label', 'intent', 'slots'}
        patch_row = {k: gold[k] for k in fields}
        labels = self.write('labels.jsonl', [patch_row])
        output = self.root / 'reviewed.jsonl'
        self.assertEqual(dataset.review(queue, labels, output), {'reviewed': 1, 'pending': 1})
        reviewed = list(dataset.read_jsonl(output))
        self.assertEqual(reviewed[0]['text'], 'pause')
        self.assertIsNone(reviewed[1]['label'])
        with self.assertRaises(ValueError): dataset.validate_rows(reviewed)
        patch_row['text'] = 'silently changed'
        with self.assertRaisesRegex(ValueError, 'review must specify'):
            dataset.review(queue, self.write('bad.jsonl', [patch_row]), self.root / 'bad-out.jsonl')

    def test_freeze_is_explicit_private_and_never_overwrites(self):
        output = self.root / 'versioned'
        dataset.freeze(CORPUS / 'cases.jsonl', output, 'fixture-v1')
        manifest, rows = dataset.load(output)
        self.assertEqual(rows, self.rows)
        self.assertEqual(manifest['name'], 'fixture-v1')
        self.assertEqual((output / 'cases.jsonl').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): dataset.freeze(CORPUS / 'cases.jsonl', output, 'fixture-v1')
        with patch.object(dataset, 'REPOSITORY', self.root.resolve()):
            with self.assertRaisesRegex(ValueError, 'outside'):
                dataset.private_output(self.root / 'private.jsonl', 'secret')

    def test_calibration_and_metrics_expose_abstentions_wrong_actions_and_false_activations(self):
        rows = [annotated(), annotated('do not pause', 'reject', 'negative')]
        predictions = [{'label': 'pause', 'score': .8, 'margin': .3},
                       {'label': 'pause', 'score': .4, 'margin': .1}]
        selected = calibrate(rows, predictions)
        self.assertEqual(selected['development']['false_activations'], 0)
        self.assertEqual(selected['development']['correct_commands'], 1)
        predictions[0]['label'] = 'stop'
        measured = measurements(rows, predictions, selected)
        self.assertEqual(measured['accepted']['wrong_action_commands'], 1)
        self.assertAlmostEqual(measured['accepted']['zero_failure_upper_bound_95'], .95)

    def test_missing_arguments_are_not_counted_as_complete_intent_success(self):
        row = annotated('Change the interface language', 'language')
        row['intent'] = None
        score = pipeline_score([row], source('en'))
        self.assertEqual(score['complete_positive_total'], 0)
        self.assertEqual(score['complete_positive_correct'], 0)


if __name__ == '__main__':
    unittest.main()
