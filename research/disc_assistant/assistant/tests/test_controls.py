from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from controller.fiio_link import frame
from research.disc_assistant.assistant import controls
from research.disc_assistant.assistant.__main__ import main
from research.disc_assistant.assistant.config import Config
from research.disc_assistant.assistant.device import ObservedSocket, PlaybackClient
from research.disc_assistant.assistant.intents import ControlIntent, Intent, parse
from research.disc_assistant.assistant.tests.test_playback import FakeClient


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.config = Config('test', 'localhost', 1, 2, self.directory / 'data', 'localhost', 3, 'http', 'KEY', {})
        self.client = FakeClient()
        self.client.play_pause = lambda: self.send('toggle')
        self.client.next_track = lambda: self.send('next')
        self.client.previous_track = lambda: self.send('previous')

    def send(self, action):
        self.client.mutation_attempted = True
        self.client.calls += 1
        if self.client.error:
            raise self.client.error
        if action == 'toggle':
            self.client.snapshot = dict(self.client.snapshot, state=1-self.client.snapshot['state'])
        else:
            self.client.snapshot = dict(self.client.snapshot, song={**self.client.snapshot['song'], 'pos_id': 2})

    def execute(self, action):
        with patch.object(controls, 'PlaybackClient', return_value=self.client), patch.object(controls.time, 'sleep'):
            return controls.execute(self.config, ControlIntent(action))

    def test_control_grammar_and_music_title_collision(self):
        for phrase, action in [('Пауза', 'pause'), ('Pause', 'pause'), ('Продолжи', 'resume'),
                               ('Resume', 'resume'), ('Стоп', 'stop'), ('Stop', 'stop'),
                               ('Следующий трек', 'next'), ('Next track', 'next'),
                               ('Предыдущий трек', 'previous'), ('Previous track', 'previous')]:
            self.assertEqual(parse(phrase), ControlIntent(action))
        self.assertEqual(parse('Play Stop'), Intent('Stop'))
        self.assertEqual(parse('Включи трек Пауза'), Intent('Пауза', 'track'))
        with self.assertRaises(ValueError):
            parse('Stop Numb')

    def test_initial_connection_wait_sends_no_handshake_or_mutation(self):
        raw = Mock()
        with patch('controller.fiio_link.socket.create_connection', side_effect=[ConnectionRefusedError(), raw]) as connect, \
                patch.object(controls.time, 'sleep'):
            with PlaybackClient(timeout=1) as client:
                self.assertFalse(client.mutation_attempted)
        self.assertEqual(connect.call_count, 2)
        raw.sendall.assert_not_called()

    def test_initial_connection_wait_is_bounded(self):
        with patch('controller.fiio_link.socket.create_connection', side_effect=ConnectionRefusedError), \
                patch.object(controls.time, 'monotonic', side_effect=[0, 0, 2]):
            with self.assertRaises(ConnectionRefusedError):
                PlaybackClient(timeout=1)

    def test_pause_resume_and_already_satisfied_do_not_toggle_twice(self):
        for action, state in [('pause', 1), ('resume', 0), ('stop', 1)]:
            first = self.execute(action)
            self.assertEqual(first['status'], 'confirmed', first)
            self.assertEqual(first['state']['state'], state)
            calls = self.client.calls
            self.assertEqual(self.execute(action)['status'], 'already_satisfied')
            self.assertEqual(self.client.calls, calls)
        self.assertEqual(first['device_stop_semantics'], 'pause_preserving_position_and_queue')

    def test_empty_loading_and_silent_snapshots_do_not_dispatch(self):
        for snapshot in ({}, {'state': 0}, dict(self.client.snapshot, state=2)):
            self.client.snapshot = snapshot
            self.assertEqual(self.execute('pause')['status'], 'not_sent')
        self.client.now_playing = Mock(side_effect=TimeoutError('silent'))
        self.assertEqual(self.execute('pause')['status'], 'not_sent')
        self.assertEqual(self.client.calls, 0)

    def test_lost_write_is_uncertain_and_never_replayed(self):
        self.client.error = OSError('lost write')
        result = self.execute('pause')
        self.assertEqual(result['status'], 'uncertain')
        self.assertTrue(result['mutation_attempted'])
        self.assertEqual(self.client.calls, 1)

    def test_navigation_uses_observed_identity_not_position_arithmetic(self):
        for action in ('next', 'previous'):
            self.client.snapshot['song']['pos_id'] = 8
            self.assertEqual(self.execute(action)['outcome'], 'track_changed')
            self.assertEqual(self.client.snapshot['song']['pos_id'], 2)

    def test_restart_requires_progress_evidence(self):
        before = self.client.snapshot
        with patch.object(controls, 'observe', return_value=(before, 1000)):
            self.assertEqual(controls.verify(self.client, before, 12000, 'previous', 1)[1], 'restarted')
        with patch.object(controls, 'observe', return_value=(before, None)), \
                patch.object(controls.time, 'monotonic', side_effect=[0, 0, 0, 2]), \
                patch.object(controls.time, 'sleep'):
            self.assertEqual(controls.verify(self.client, before, None, 'previous', 1), (None, None))

    def test_old_events_cannot_confirm_a_blank_fresh_reply(self):
        self.client.observed = [('a202', json.dumps(self.client.snapshot).encode())]
        self.client.snapshot = {}
        self.assertEqual(self.execute('pause')['status'], 'not_sent')
        self.assertEqual(self.client.calls, 0)

    def test_external_track_change_does_not_confirm_toggle(self):
        before = self.client.snapshot
        after = dict(before, state=1, song={**before['song'], 'song_name': 'Other'})
        with patch.object(controls, 'observe', return_value=(after, None)), \
                patch.object(controls.time, 'monotonic', side_effect=[0, 0, 0, 2]), \
                patch.object(controls.time, 'sleep'):
            self.assertEqual(controls.verify(self.client, before, None, 'pause', 1), (None, None))

    def test_all_control_writes_are_marked_before_failure(self):
        for tag, payload in [('0201', '0000'), ('0201', '0001'), ('0201', '0002'), ('0102', '0003')]:
            raw = Mock()
            raw.sendall.side_effect = OSError('lost')
            session = Mock(mutation_attempted=False, mutation_phase='selection', attempted_phases=set())
            if tag == '0102':
                session.mutation_phase = 'mode'
            socket = ObservedSocket(raw, session)
            with self.assertRaises(OSError):
                socket.sendall(frame(tag, payload))
            self.assertTrue(session.mutation_attempted)
            with self.assertRaises(RuntimeError):
                socket.sendall(frame(tag, payload))
            self.assertEqual(raw.sendall.call_count, 1)

    def test_cli_controls_and_dry_run_need_no_search_or_database(self):
        path = self.directory / 'config.toml'
        path.write_text(f'[device]\nkey="test"\nhost="localhost"\n[storage]\ndata_dir="{self.config.data_dir}"')
        with patch('research.disc_assistant.assistant.__main__.Store') as store, \
                patch('research.disc_assistant.assistant.__main__.create_client') as search, \
                patch('research.disc_assistant.assistant.__main__.control', return_value={'status': 'confirmed'}) as control, \
                patch.dict('os.environ', {}, clear=True), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--config', str(path), 'rank', 'Pause']), 0)
            self.assertEqual(json.loads(out.getvalue())['status'], 'planned')
            control.assert_not_called()
            self.assertEqual(main(['--config', str(path), 'ask', 'Пауза']), 0)
            control.assert_called_once()
            store.assert_not_called()
            search.assert_not_called()
        self.assertFalse(self.config.data_dir.exists())
