import json
from pathlib import Path
import socket
import socketserver
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from controller.fiio_link import Frames, frame
from research.disc_assistant.assistant.config import Config
from research.disc_assistant.assistant.console import Application, run
from research.disc_assistant.assistant.device import device_lock
from research.disc_assistant.assistant.live import DeviceSession


from controller.tests.session_fixture import Server, until


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server = Server()
        self.addCleanup(self.server.close)
        self.config = Config('synthetic', '127.0.0.1', self.server.server_address[1], 1,
                             Path(self.tmp.name), '127.0.0.1', 1, 'http', 'UNSET_SEARCH_KEY', {}, timeout=.3, locale='en')

    def session(self):
        session = DeviceSession(self.config, backoff=.02, health_interval=.1)
        session.__enter__()
        self.addCleanup(session.__exit__, None, None, None)
        session.connect()
        self.assertTrue(session.wait_ready(2), session.status())
        return session

    def test_multiple_operations_use_one_connection_and_one_handshake(self):
        session = self.session()
        for _ in range(3):
            with session.operation() as client:
                self.assertEqual(client.handshake(), '0306')
                self.assertEqual(client.now_playing()['state'], 0)
        self.assertEqual(self.server.accepts, 1)
        self.assertEqual(self.server.tags.count('0599'), 1)
        self.assertEqual(self.server.writes, 0)

    def test_events_continue_while_idle_and_during_slow_non_tcp_work(self):
        session = self.session()
        self.server.push('a202', '{"state":1}')
        until(lambda: session.status()['observation']['playback'] == 'paused')
        with session.operation() as client:
            self.server.push('a103', '00002EE0')
            until(lambda: session.status()['observation']['position_ms'] == 12000)
            self.server.push('a60a', '000F')
            until(lambda: session.status()['observation']['scan_active'])
            with self.assertRaisesRegex(ValueError, 'scan'):
                client.scan_guard()
        self.server.push('a60a', '0005')
        until(lambda: not session.status()['observation']['scan_active'])

    def test_natural_eof_and_silent_read_do_not_mean_disconnected(self):
        session = self.session()
        self.server.push('a103', '00000000')
        self.server.push('a202', '{"state":2}')
        until(lambda: session.status()['observation']['playback'] == 'stopped')
        self.server.silent_now = True
        with session.operation() as client:
            with self.assertRaises(TimeoutError):
                client.now_playing()
            self.assertEqual(client.play_mode(), 0)
        self.assertEqual(session.status()['connection'], 'ready')
        self.assertEqual(self.server.accepts, 1)

    def test_reconnect_recovers_observation_without_mutation_replay(self):
        session = self.session()
        self.server.drop_write = True
        with session.operation() as client:
            client.play_pause()
            until(client.closed.is_set)
            self.assertTrue(client.mutation_attempted)
        until(lambda: self.server.accepts >= 2 and session.status()['connection'] == 'ready')
        self.assertEqual(self.server.writes, 1)
        self.assertEqual(session.status()['observation']['playback'], 'playing')

    def test_explicit_disconnect_stays_disconnected_then_connects_again(self):
        session = self.session()
        session.disconnect()
        count = self.server.accepts
        time.sleep(.15)
        self.assertEqual(self.server.accepts, count)
        self.assertEqual(session.status()['connection'], 'disconnected')
        self.assertEqual(session.status()['observation']['playback'], 'unknown')
        with self.assertRaises(ConnectionError):
            with session.operation():
                self.fail('disconnected commands must not wait for reconnect')
        session.connect()
        self.assertTrue(session.wait_ready(2))
        self.assertEqual(self.server.accepts, count + 1)

    def test_late_tagged_reply_retires_connection_without_reusing_it(self):
        session = self.session()
        self.server.delay_tag = '0501'
        with session.operation() as client:
            with self.assertRaises(TimeoutError):
                client.settings()
            self.assertTrue(client.closed.is_set())
        self.server.delay_tag = None
        self.server.release_reply.set()
        until(lambda: self.server.accepts >= 2 and session.status()['connection'] == 'ready')
        self.assertEqual(self.server.writes, 0)

    def test_active_service_excludes_one_shot_device_owner(self):
        self.session()
        with self.assertRaisesRegex(ValueError, 'another assistant'):
            with device_lock(self.config.data_dir):
                pass

    def test_work_waiting_for_an_old_generation_is_cancelled(self):
        session = self.session()
        attempted = threading.Event()
        errors = []
        session.operations.acquire()
        def queued():
            attempted.set()
            try:
                with session.operation() as client:
                    client.play_pause()
            except ConnectionError as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=queued)
        worker.start()
        attempted.wait(1)
        session.disconnect()
        session.operations.release()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.server.writes, 0)

    def test_idle_scan_observation_blocks_later_mutation_preflight(self):
        session = self.session()
        self.server.push('a60a', '000F')
        until(lambda: session.status()['observation']['scan_active'])
        with session.operation() as client:
            with self.assertRaisesRegex(ValueError, 'scan'):
                client.scan_guard()
        self.assertEqual(self.server.writes, 0)

    def test_not_ready_command_does_not_wait_for_connection_initialization(self):
        session = self.session()
        errors = []
        finished = threading.Event()
        # Model the connector owning operations while initialization is pending.
        with session.guard:
            session.connection = 'connecting'
        def command():
            try:
                with session.operation():
                    errors.append('unexpected execution')
            except ConnectionError:
                pass
            finally:
                finished.set()
        with session.operations:
            worker = threading.Thread(target=command)
            worker.start()
            rejected_immediately = finished.wait(.5)
        worker.join(2)
        self.assertTrue(rejected_immediately)
        self.assertFalse(errors)
        self.assertEqual(self.server.writes, 0)

    def test_missing_search_key_does_not_disable_controls(self):
        with patch.dict('os.environ', {}, clear=True), Application(self.config) as app:
            self.assertTrue(app.session.wait_ready(2))
            with self.assertRaisesRegex(ValueError, 'search is unavailable'):
                app.request('Play Artist')
            self.assertEqual(app.request('/status')['session']['connection'], 'ready')
            self.assertEqual(app.request('Pause')['status'], 'confirmed')

    def test_blank_and_invalid_console_commands_do_not_write(self):
        with Application(self.config) as app:
            self.assertTrue(app.session.wait_ready(2))
            self.assertIsNone(app.request('   '))
            for line in ('/unknown', '/disconnect extra', '/device other', '/search', '/rank'):
                with self.assertRaises(ValueError):
                    app.request(line)
            self.assertEqual(self.server.writes, 0)

    def test_graceful_shutdown_stops_reader_and_session_threads(self):
        with DeviceSession(self.config) as session:
            session.connect()
            self.assertTrue(session.wait_ready(2))
            client = session.client
        self.assertFalse(session.worker.is_alive())
        self.assertFalse(client.reader.is_alive())
        self.assertEqual(self.server.writes, 0)

    def test_console_controls_without_search_and_disconnect_commands(self):
        with Application(self.config) as app:
            self.assertTrue(app.session.wait_ready(2))
            device = app.request('/device')
            self.assertEqual(device['device'], {'key': 'synthetic', 'host': '127.0.0.1',
                'tcp_port': self.config.tcp_port, 'http_port': 1})
            self.assertEqual(device['session']['connection'], 'ready')
            self.assertEqual(app.request('/rank Pause')['action'], 'pause')
            self.assertEqual(app.request('Pause')['status'], 'confirmed')
            self.assertEqual(app.request('Pause')['status'], 'already_satisfied')
            self.assertEqual(self.server.writes, 1)
            self.assertEqual(self.server.accepts, 1)
            self.assertEqual(app.request('/disconnect')['connection'], 'disconnected')
            disconnected = app.request('/device')
            self.assertEqual(disconnected['device'], device['device'])
            self.assertEqual(disconnected['session']['connection'], 'disconnected')
            self.assertFalse(disconnected['session']['enabled'])
            self.assertEqual(app.request('Resume')['status'], 'not_sent')
            app.request('/connect')
            self.assertTrue(app.session.wait_ready(2))
            self.assertEqual(app.request('/status')['session']['observation']['playback'], 'paused')

    def test_eof_exits_console_once_and_releases_socket_and_lock(self):
        output = []
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(run(self.config, input_fn=lambda prompt: (_ for _ in ()).throw(EOFError()), output=output.append), 0)
        self.assertTrue(any('Console closed' in line for line in output))
        until(lambda: not self.server.connections)
        with device_lock(self.config.data_dir):
            pass
        self.assertEqual(self.server.writes, 0)
