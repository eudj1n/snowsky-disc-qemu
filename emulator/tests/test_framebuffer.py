import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from emulator.runtime import framebuffer
from tests.fixtures.framebuffer import pixels, decode_png

class FrameStateTests(unittest.TestCase):
    def setUp(self):
        self.state = framebuffer.FrameState()
        self.a, self.b = pixels(10), pixels(80)

    def test_duplicate_and_unused_byte_changes_do_not_encode_or_publish(self):
        self.assertTrue(self.state.update_frame(self.a + self.b, 0, True))
        revision = self.state.frame_revision
        with patch.object(framebuffer, 'png', side_effect=AssertionError('Redundant encoding')):
            self.assertFalse(self.state.update_frame(self.a + self.b, 0, True))
            self.assertFalse(self.state.update_frame(pixels(10, unused=255) + self.b, 0, True))
            self.assertFalse(self.state.update_frame(self.a + self.a, 1, True))
        self.assertEqual(self.state.frame_revision, revision)

    def test_active_buffer_and_same_buffer_writes_are_lossless(self):
        self.state.update_frame(self.a + self.b, 1, True)
        self.assertEqual(decode_png(self.state.png), bytes((40, 20, 80)) * (framebuffer.W * framebuffer.H))
        # Marker does not change, but pixels do. Also verify rotation with one
        # distinguishable pixel at the beginning of the raw framebuffer.
        changed = bytes((1, 2, 3, 0)) + self.b[4:]
        self.assertTrue(self.state.update_frame(self.a + changed, 1, True))
        expected = bytes((40, 20, 80)) * (framebuffer.W * framebuffer.H - 1) + bytes((3, 2, 1))
        self.assertEqual(decode_png(self.state.png), expected)

    def test_sleep_wake_and_reconnect_keep_complete_current_frame(self):
        self.state.update_frame(self.a + self.b, 0, True)
        awake = self.state.png
        self.assertTrue(self.state.update_frame(self.a + self.b, 0, False))
        self.assertEqual(decode_png(self.state.png), framebuffer.BLACK_RGB)
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
            reader = framebuffer.Framebuffer(directory)
            reader.path = path
            with patch.object(reader, 'active_buffer', side_effect=[0, 1, 1, 1]):
                raw, active = reader.read()
            self.assertEqual(raw, self.a + self.b)
            self.assertEqual(active, 1)
            with patch.object(reader, 'active_buffer', side_effect=[0, 1, 1, 0]):
                self.assertIsNone(reader.read())

    def test_slow_consumer_gets_latest_complete_frame(self):
        revision, _ = self.state.wait_frame(None, 0)
        for blue in range(10, 15):
            self.state.update_frame(pixels(blue) + self.b, 0, True)
        latest, png = self.state.wait_frame(revision, 0)
        self.assertGreater(latest, revision)
        self.assertEqual(decode_png(png), bytes((40, 20, 14)) * (framebuffer.W * framebuffer.H))
