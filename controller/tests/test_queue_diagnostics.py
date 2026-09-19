"""Failed queue guards expose their evidence without weakening confirmation."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from controller.catalog import CatalogChanged
from controller.models import CommandResult
from controller.queue import snapshot


class QueueDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(page_size=200, max_tracks=100, max_requests=10)
        self.rows = [dict(pos=0, name='First', author='Artist'), dict(pos=1, name='Second', author='Artist')]
        self.page = {'items': self.rows, 'total': 2, 'mark': 0}
        self.http = Mock()
        self.http.catalog.side_effect = lambda *args, **kw: deepcopy(self.page)
        self.client = Mock()
        self.client.play_mode.return_value = 0
        self.state = {'state': 0, 'playerflag': 7, 'song': {
            'pos_id': 1, 'song_name': 'First', 'song_artist_name': 'Artist',
            'song_file_path': '/private/media/never-export.flac'}}
        self.client.now_playing.side_effect = lambda: deepcopy(self.state)

    def observe(self):
        return snapshot(self.config, self.client, self.http, expected=self.rows,
                        selected={'kind': 'artist', 'artist': 'Artist'})

    def failure(self, code):
        with self.assertRaises(CatalogChanged) as caught:
            self.observe()
        evidence = caught.exception.diagnostics
        self.assertEqual(evidence['code'], code)
        self.assertNotIn('/private/media', str(evidence))
        return evidence

    def test_fresh_empty_or_wrong_state_reports_exact_failed_fields(self):
        self.state = {}
        evidence = self.failure('state_mismatch')
        self.assertEqual(set(evidence['failed_checks']), {'playing', 'source', 'position', 'title', 'artist'})
        self.assertEqual(evidence['expected']['pos_id'], 1)
        self.assertIsNone(evidence['observed']['pos_id'])

    def test_stale_mark_and_changed_title_remain_failures(self):
        self.page['mark'] = 1
        self.assertEqual(set(self.failure('state_mismatch')['failed_checks']), {'position', 'title'})
        self.page['mark'] = 0
        self.state['song']['song_name'] = 'Other'
        self.assertEqual(self.failure('state_mismatch')['failed_checks'], ['title'])

    def test_queue_membership_and_races_have_separate_codes(self):
        self.page['items'] = [dict(pos=0, name='Other', author='Artist')]
        self.page['total'] = 1
        evidence = self.failure('membership_mismatch')
        self.assertEqual((evidence['missing_count'], evidence['unexpected_count']), (2, 1))
        self.page.update(items=self.rows, total=2)
        self.client.play_mode.side_effect = [0, 1]
        self.failure('mode_changed')
        self.client.play_mode.side_effect = None
        self.http.catalog.side_effect = [deepcopy(self.page), {**deepcopy(self.page), 'mark': 1}]
        self.failure('unstable_queue')

    def test_good_queue_and_typed_result_keep_diagnostics(self):
        self.assertEqual(self.observe()['mark'], 0)
        evidence = {'queue': {'code': 'state_mismatch'}}
        result = CommandResult.from_result({'operation_id': 'test', 'status': 'uncertain',
                                            'mutation_attempted': True, 'confirmation': evidence}, 'play_artist')
        self.assertEqual(result.to_dict()['confirmation'], evidence)
