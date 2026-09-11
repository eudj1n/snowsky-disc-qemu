"""Lossless frame deduplication, buffer selection and real multipart transport."""
import http.client
import struct
import tempfile
import threading
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import stream


def pixels(blue, green=20, red=40, unused=0):
    return bytes((blue, green, red, unused)) * (stream.W * stream.H)


def decode_png(png):
    """Check exact pixel bytes independently of the encoder (RGB, filter 0)."""
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    compressed = b''
    offset = 8
    while offset < len(png):
        size = struct.unpack('>I', png[offset:offset + 4])[0]
        if png[offset + 4:offset + 8] == b'IDAT':
            compressed += png[offset + 8:offset + 8 + size]
        offset += size + 12
    data = zlib.decompress(compressed)
    stride = stream.W * 3 + 1
    assert all(data[y * stride] == 0 for y in range(stream.H))
    return b''.join(data[y * stride + 1:(y + 1) * stride] for y in range(stream.H))


class FrameStateTests(unittest.TestCase):
    def setUp(self):
        self.state = stream.State()
        self.a, self.b = pixels(10), pixels(80)

    def test_duplicate_and_unused_byte_changes_do_not_encode_or_publish(self):
        self.assertTrue(self.state.update_frame(self.a + self.b, 0, True))
        revision = self.state.frame_revision
        with patch.object(stream, '_png', side_effect=AssertionError('Redundant encoding')):
            self.assertFalse(self.state.update_frame(self.a + self.b, 0, True))
            self.assertFalse(self.state.update_frame(pixels(10, unused=255) + self.b, 0, True))
            self.assertFalse(self.state.update_frame(self.a + self.a, 1, True))
        self.assertEqual(self.state.frame_revision, revision)

    def test_active_buffer_and_same_buffer_writes_are_lossless(self):
        self.state.update_frame(self.a + self.b, 1, True)
        self.assertEqual(decode_png(self.state.png), bytes((40, 20, 80)) * (stream.W * stream.H))
        # Marker does not change, but pixels do. Also verify rotation with one
        # distinguishable pixel at the beginning of the raw framebuffer.
        changed = bytes((1, 2, 3, 0)) + self.b[4:]
        self.assertTrue(self.state.update_frame(self.a + changed, 1, True))
        expected = bytes((40, 20, 80)) * (stream.W * stream.H - 1) + bytes((3, 2, 1))
        self.assertEqual(decode_png(self.state.png), expected)

    def test_sleep_wake_and_reconnect_keep_complete_current_frame(self):
        self.state.update_frame(self.a + self.b, 0, True)
        awake = self.state.png
        self.assertTrue(self.state.update_frame(self.a + self.b, 0, False))
        self.assertEqual(decode_png(self.state.png), stream.BLACK_RGB)
        self.assertFalse(self.state.update_frame(self.b + self.a, 1, False))
        self.assertTrue(self.state.update_frame(self.a + self.b, 0, True))
        self.assertEqual(self.state.png, awake)
        self.assertEqual(self.state.wait_frame(None, 0)[1], awake)

    def test_fallback_and_short_read(self):
        self.state.update_frame(self.a + self.b, None, True)
        self.state.update_frame(self.a + pixels(90), None, True)
        self.assertEqual(self.state.live, 1)
        previous = self.state.png
        self.assertFalse(self.state.update_frame(b'short', 0, True))
        self.assertEqual(self.state.png, previous)

    def test_marker_switch_during_read_retries_and_unstable_sample_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fb0'
            path.write_bytes(self.a + self.b + pixels(200))
            with patch.object(stream, 'FB', str(path)):
                with patch.object(stream, '_active_buffer', side_effect=[0, 1, 1, 1]):
                    raw, active = stream._read_frame()
                self.assertEqual(raw, self.a + self.b)
                self.assertEqual(active, 1)
                with patch.object(stream, '_active_buffer', side_effect=[0, 1, 1, 0]):
                    self.assertIsNone(stream._read_frame())

    def test_slow_consumer_gets_latest_complete_frame(self):
        revision, _ = self.state.wait_frame(None, 0)
        for blue in range(10, 15):
            self.state.update_frame(pixels(blue) + self.b, 0, True)
        latest, png = self.state.wait_frame(revision, 0)
        self.assertGreater(latest, revision)
        self.assertEqual(decode_png(png), bytes((40, 20, 14)) * (stream.W * stream.H))


class FrameTransportTests(unittest.TestCase):
    def setUp(self):
        self.state = stream.State()
        self.finished = threading.Event()
        finished = self.finished

        class Handler(stream.Handler):
            def _frame_stream(self):
                try:
                    super()._frame_stream()
                finally:
                    finished.set()

        self.patches = [patch.object(stream, 'state', self.state),
                        patch.object(stream, 'FRAME_HEARTBEAT', .1)]
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
        connection.request('GET', '/stream')
        response = connection.getresponse()
        self.clients.append((connection, response))
        self.assertEqual(response.status, 200)
        self.assertIn('boundary=FRAME', response.getheader('Content-Type'))
        return response

    def frame(self, response):
        self.assertEqual(response.readline(), b'--FRAME\r\n')
        self.assertEqual(response.readline(), b'Content-Type: image/png\r\n')
        header = response.readline()
        self.assertTrue(header.startswith(b'Content-Length: '))
        size = int(header.split(b':')[1])
        self.assertEqual(response.readline(), b'\r\n')
        png = response.read(size)
        self.assertEqual(len(png), size)
        # All PNG bytes are available without waiting for the next changed frame.
        self.assertEqual(response.readline(), b'\r\n')
        return png

    def test_initial_idle_refresh_change_and_new_viewer(self):
        response = self.connect()
        self.assertEqual(self.frame(response), self.state.png)
        self.assertEqual(self.frame(response), self.state.png)  # Idle refresh.
        self.state.update_frame(pixels(42) * 2, 1, True)
        expected = bytes((40, 20, 42)) * (stream.W * stream.H)
        self.assertEqual(decode_png(self.frame(response)), expected)
        self.assertEqual(decode_png(self.frame(self.connect())), expected)

    def test_disconnect_releases_handler(self):
        response = self.connect()
        self.frame(response)
        connection, _ = self.clients.pop()
        response.close()
        connection.close()
        self.assertTrue(self.finished.wait(2), 'Disconnected frame handler leaked')

    def test_new_frame_wakes_client_without_waiting_for_idle_refresh(self):
        with patch.object(stream, 'FRAME_HEARTBEAT', 10):
            response = self.connect()
            self.frame(response)
            self.state.update_frame(pixels(77) * 2, 0, True)
            # HTTP timeout is 2s, much shorter than the idle refresh interval.
            self.assertEqual(decode_png(self.frame(response)),
                             bytes((40, 20, 77)) * (stream.W * stream.H))
            response.close()
        # Wake the old long waiter after restoring the short test heartbeat, so
        # a disconnected handler cannot outlive this test's patched state.
        self.state.update_frame(pixels(78) * 2, 0, True)
        self.assertTrue(self.finished.wait(2))
