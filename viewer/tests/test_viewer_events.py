"""Real HTTP checks for viewer SSE, without a guest or firmware."""
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from viewer import server as stream


class DeviceEventsTests(unittest.TestCase):
    def setUp(self):
        self.state = stream.State()
        self.finished = threading.Event()
        finished = self.finished

        class Handler(stream.Handler):
            def _device_events(self):
                try:
                    super()._device_events()
                finally:
                    finished.set()

        self.patches = [patch.object(stream, 'state', self.state),
                        patch.object(stream, 'EVENT_HEARTBEAT', .05)]
        for p in self.patches:
            p.start()
        self.server = stream.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.clients = []

    def tearDown(self):
        for connection, response in self.clients:
            response.close()
            connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        for p in reversed(self.patches):
            p.stop()

    def connect(self):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        connection.request('GET', '/events')
        response = connection.getresponse()
        self.clients.append((connection, response))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'text/event-stream; charset=utf-8')
        self.assertIsNone(response.getheader('Content-Length'))
        self.assertIn('no-cache', response.getheader('Cache-Control'))
        self.assertEqual(self.block(response), b'retry: 1000\n')
        return response

    def block(self, response):
        lines = []
        while True:
            line = response.readline()
            self.assertTrue(line, 'SSE closed unexpectedly')
            if line == b'\n':
                return b''.join(lines)
            lines.append(line)

    def snapshot(self, response):
        while True:
            block = self.block(response)
            if block.startswith(b':'):
                continue
            self.assertTrue(block.startswith(b'event: device\ndata: '), block)
            return json.loads(block.split(b'data: ', 1)[1])

    def test_initial_change_idle_and_reconnect_snapshot(self):
        response = self.connect()
        self.assertEqual(self.snapshot(response), self.state.device)
        self.state.publish_device(dict(self.state.device))
        self.assertEqual(self.block(response), b': heartbeat\n')
        updated = dict(running=True, screen_on=False, transition=None, error='Тест\nошибки')
        self.state.publish_device(updated)
        self.assertEqual(self.snapshot(response), updated)
        self.assertEqual(self.block(response), b': heartbeat\n')
        # A reconnect immediately receives the current snapshot, even when no
        # state has changed since the previous connection.
        self.assertEqual(self.snapshot(self.connect()), updated)

    def test_multiple_viewers_receive_updates_and_json_still_works(self):
        first, second = self.connect(), self.connect()
        self.snapshot(first)
        self.snapshot(second)
        updated = dict(running=True, screen_on=True, transition='starting', error=None)
        self.state.publish_device(updated)
        self.assertEqual(self.snapshot(first), updated)
        self.assertEqual(self.snapshot(second), updated)
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request('GET', '/device.json')
            response = connection.getresponse()
            self.assertEqual(json.loads(response.read()), updated)
        finally:
            connection.close()

    def test_disconnected_viewer_handler_exits(self):
        response = self.connect()
        self.snapshot(response)
        connection, _ = self.clients.pop()
        response.close()
        connection.close()
        self.assertTrue(self.finished.wait(2), 'Disconnected SSE handler leaked')

    def test_slow_consumers_coalesce_to_latest_snapshot(self):
        revision, _ = self.state.wait_device(None, 0)
        for transition in ('starting', None, 'stopping'):
            self.state.publish_device({**self.state.device, 'transition': transition})
        latest, snapshot = self.state.wait_device(revision, 0)
        self.assertGreater(latest, revision)
        self.assertEqual(snapshot['transition'], 'stopping')
