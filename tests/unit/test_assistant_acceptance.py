"""The acceptance oracle must not mistake a confident reply for device success."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from tests.fixtures.assistant_fixture import MANIFEST
from tests.integration.assistant_check import judge, screenshot, write_json


class AssistantAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads(MANIFEST.read_text())
        self.tracks = {t['key']: t for t in self.suite['tracks']}
        items = [dict(pos=i, name=self.tracks[k]['title'], author='Test Atlas', count=0)
                 for i, k in enumerate(('alpha', 'beta', 'gamma'))]
        self.before = {'state': {'state': 0, 'song': {
            'song_name': 'Signal Beta', 'song_artist_name': 'Test Atlas',
            'song_file_path': '/tmp/sdcard/beta.flac', 'pos_id': 2}},
            'position_ms': 10000, 'monotonic': 10, 'generation': 1,
            'queue': {'items': items, 'mark': 1, 'total': 3, 'mode': 0}}
        self.after = deepcopy(self.before)
        self.after.update(position_ms=15000, monotonic=15)

    def case(self, name):
        return next(c for c in self.suite['cases'] if c['id'] == 'en-' + name)

    def reply(self, status='confirmed'):
        return {'status': status, 'response': {'language': 'en'}}

    def test_confirmed_restart_does_not_pass_previous(self):
        self.after['position_ms'] = 1000
        result = dict(self.reply(), outcome='restarted')
        checks = judge(self.case('previous'), self.tracks, self.before, result, self.after, [{'tag': '0201'}])
        self.assertTrue(checks['response_status'])
        self.assertFalse(checks['expected_neighbor'])

    def test_album_requires_all_artists_in_fixture_queue(self):
        target = self.tracks['comp-a']
        self.after['state']['song'].update(song_name=target['title'], song_artist_name=target['artist'],
                                          song_file_path='/tmp/sdcard/comp-a.flac', pos_id=1)
        self.after['queue'].update(mark=0, items=[dict(pos=0, name=target['title'], author=target['artist'])])
        checks = judge(self.case('album-compilation'), self.tracks, self.before, self.reply('playing'), self.after, [{}])
        self.assertTrue(checks['target'])
        self.assertFalse(checks['queue_membership'])

    def test_wrong_track_cannot_become_gold_from_selected(self):
        result = dict(self.reply('playing'), selected={'title': 'Signal Beta', 'artist': 'Test Atlas'})
        checks = judge(self.case('track'), self.tracks, self.before, result, self.after, [{}])
        self.assertFalse(checks['target'])

    def test_successful_readback_does_not_hide_uncertain_reply(self):
        self.after['state']['state'] = 1
        checks = judge(self.case('pause'), self.tracks, self.before, self.reply('uncertain'), self.after, [{}])
        self.assertTrue(checks['playback_state'])
        self.assertFalse(checks['response_status'])

    def test_noop_with_hidden_write_fails_even_if_state_unchanged(self):
        checks = judge(self.case('missing'), self.tracks, self.before,
                       self.reply('not_found'), self.after, [{'tag': '0201'}])
        self.assertFalse(checks['mutation_contract'])

    def test_noop_requires_position_and_same_session(self):
        self.after.update(position_ms=None, generation=2)
        checks = judge(self.case('missing'), self.tracks, self.before, self.reply('not_found'), self.after, [])
        self.assertFalse(checks['position_retained'])
        self.assertFalse(checks['same_connection'])

    def test_negation_rejection_with_continued_playback_passes(self):
        reply = self.reply('error');reply['response']['code'] = 'command.unrecognized'
        checks = judge(self.case('negation'), self.tracks, self.before, reply, self.after, [])
        self.assertTrue(all(checks.values()), checks)

    def test_reports_cannot_overwrite_previous_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'case.json'
            write_json(path, {'original': True})
            with self.assertRaises(FileExistsError):
                write_json(path, {'original': False})
            self.assertEqual(json.loads(path.read_text()), {'original': True})

    def test_screenshot_requires_active_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);(root / 'emu').mkdir()
            (root / 'emu/fb-live').write_bytes(b'2')
            with self.assertRaisesRegex(RuntimeError, 'marker'):
                screenshot(root, root / 'screen.png')

    def test_screenshot_uses_binary_live_marker_and_is_exclusive(self):
        from emulator.runtime.framebuffer import BUF, png, to_rgb
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);(root / 'emu').mkdir();(root / 'dev').mkdir()
            (root / 'emu/fb-live').write_bytes(b'\x01')
            second = b'\x10\x20\x30\0' * (BUF // 4)
            (root / 'dev/fb0').write_bytes(bytes(BUF) + second)
            output = root / 'screen.png'
            evidence = screenshot(root, output)
            self.assertEqual(evidence['buffer'], 1)
            self.assertFalse(evidence['visually_reviewed'])
            self.assertEqual(output.read_bytes(), png(to_rgb(second)))
            with self.assertRaises(FileExistsError):
                screenshot(root, output)


if __name__ == '__main__':
    unittest.main()
