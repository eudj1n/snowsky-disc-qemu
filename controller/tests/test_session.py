from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import ast
import time
import unittest
from unittest.mock import Mock, patch

from controller.models import DeviceConfig, ConnectionState, PlaybackState, OperationStatus, PlayMode
from controller.session import DiscSession
from controller.tests.session_fixture import Server, until


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.server = Server()
        self.addCleanup(self.server.close)
        self.config = DeviceConfig('127.0.0.1', self.server.server_address[1], 1, timeout=.3)

    def session(self):
        session = DiscSession(self.config, backoff=.02, health_interval=.1)
        session.__enter__()
        self.addCleanup(session.__exit__, None, None, None)
        session.connect()
        self.assertTrue(session.wait_ready(2))
        return session

    def test_typed_snapshot_and_idempotent_controls_share_one_connection(self):
        session = self.session()
        state = session.snapshot()
        self.assertEqual(state.connection, ConnectionState.READY)
        self.assertEqual(state.playback.state, PlaybackState.PLAYING)
        self.assertEqual(state.playback.track.title, 'Track')
        self.assertEqual(state.playback.track.queue_position, 0)
        self.assertEqual(state.playback.mode, PlayMode.LIST_ONCE)
        result = session.pause()
        self.assertEqual(result.status, OperationStatus.CONFIRMED)
        self.assertEqual(result.playback.state, PlaybackState.PAUSED)
        self.assertTrue(result.mutation_attempted)
        self.assertEqual(session.pause().status, OperationStatus.ALREADY_SATISFIED)
        self.assertEqual(session.resume().status, OperationStatus.CONFIRMED)
        self.assertEqual(self.server.writes, 2)
        self.assertEqual(self.server.accepts, 1)
        self.assertEqual(self.server.tags.count('0599'), 1)
        serialized = json.loads(json.dumps(result.to_dict()))
        self.assertEqual(serialized['playback']['state'], 'paused')
        self.assertNotIn('playerflag', json.dumps(serialized))

    def test_cached_snapshots_are_detached_and_receive_idle_pushes(self):
        session = self.session()
        old = session.snapshot()
        self.server.push('a202', '{"state":1}')
        until(lambda: session.snapshot().playback.state == PlaybackState.PAUSED)
        self.assertEqual(old.playback.state, PlaybackState.PLAYING)
        with self.assertRaises(FrozenInstanceError):
            old.playback.track.title = 'changed'
        tags = len(self.server.tags)
        for _ in range(10):
            session.snapshot()
        self.assertLessEqual(len(self.server.tags) - tags, 1)  # A health read may run independently.

    def test_reconnect_does_not_replay_uncertain_control(self):
        session = self.session()
        original = session.snapshot().generation
        self.server.drop_write = True
        result = session.pause()
        self.assertEqual(result.status, OperationStatus.UNCERTAIN)
        self.assertTrue(result.mutation_attempted)
        until(lambda: session.snapshot().generation > original and session.snapshot().connection == ConnectionState.READY)
        self.assertEqual(self.server.writes, 1)
        session.disconnect()
        self.assertEqual(session.resume().status, OperationStatus.NOT_SENT)
        accepts = self.server.accepts
        time.sleep(.15)
        self.assertEqual(self.server.accepts, accepts)

    def test_final_stop_and_silent_read_leave_transport_ready(self):
        session = self.session()
        self.server.push('a103', '00000000')
        self.server.push('a202', '{"state":2}')
        until(lambda: session.snapshot().playback.state == PlaybackState.STOPPED)
        self.server.silent_now = True
        self.assertEqual(session.resume().status, OperationStatus.NOT_SENT)
        self.assertEqual(session.snapshot().connection, ConnectionState.READY)
        self.assertEqual(self.server.accepts, 1)
        self.assertEqual(self.server.writes, 0)

    def test_normalized_queue_and_invalid_selection_never_write(self):
        session = self.session()
        http = Mock()
        http.catalog.return_value = {'total': 1, 'mark': 0,
                                     'items': [{'pos': 0, 'name': 'Track', 'author': 'Artist'}]}
        with patch('controller.fiio_http.HTTPClient', return_value=http):
            result = session.queue()
            self.assertEqual(result.status, OperationStatus.OBSERVED)
            self.assertEqual(result.queue.items[0].title, 'Track')
            self.assertEqual(result.queue.selected_position, 0)
            self.assertEqual(result.queue.mode, PlayMode.LIST_ONCE)
            self.assertEqual(session.play_artist('Artist', index=0).status, OperationStatus.NOT_SENT)
            self.assertEqual(session.play_artist('Artist', album='Album', index=5).status, OperationStatus.NOT_SENT)
        self.assertEqual(self.server.writes, 0)

    def test_queue_observation_rejects_changes_across_pages(self):
        session = self.session()
        http = Mock()
        http.catalog.side_effect = [
            {'total': 1, 'mark': 0, 'items': [{'pos': 0, 'name': 'First', 'author': 'Artist'}]},
            {'total': 1, 'mark': 0, 'items': [{'pos': 0, 'name': 'Other', 'author': 'Artist'}]}]
        with patch('controller.fiio_http.HTTPClient', return_value=http):
            self.assertEqual(session.queue().status, OperationStatus.NOT_SENT)
        self.assertEqual(self.server.writes, 0)

    def test_no_native_stop_and_invalid_configuration_are_explicit(self):
        session = self.session()
        with self.assertRaises(ValueError):
            session.control('stop')
        with session.operation() as client:
            with self.assertRaisesRegex(ValueError, 'outside the reviewed'):
                client.set_volume(10)
        for fields in ({'tcp_port': 0}, {'timeout': True}, {'host': ' '}, {'page_size': 201}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                replace(self.config, **fields)
        self.assertEqual(self.server.writes, 0)

    def test_explicit_named_mode_is_verified_without_implicit_restore(self):
        session = self.session()
        result = session.set_play_mode(PlayMode.REPEAT_LIST)
        self.assertEqual(result.status, OperationStatus.CONFIRMED)
        self.assertEqual(result.requested_mode, PlayMode.REPEAT_LIST)
        self.assertEqual(result.previous_mode, PlayMode.LIST_ONCE)
        self.assertEqual(session.set_play_mode('repeat_list').status, OperationStatus.ALREADY_SATISFIED)
        self.assertEqual(self.server.writes, 1)
        session.disconnect()
        self.assertEqual(self.server.mode, 3)


class ControllerBoundaryTests(unittest.TestCase):
    def test_production_controller_imports_no_application_or_runtime_components(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = {'research', 'emulator', 'viewer', 'firmware', 'tests'}
        for path in root.rglob('*.py'):
            if 'tests' in path.relative_to(root).parts:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                    [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    self.assertNotIn(name.split('.')[0], forbidden, f'{path}:{node.lineno} imports {name}')
