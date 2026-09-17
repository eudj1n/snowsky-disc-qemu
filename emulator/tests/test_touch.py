"""Moving touch out of the viewer preserves event bytes, guest isolation and timing."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from emulator.runtime.touch import Touch


class TouchTests(unittest.TestCase):
    def test_tap_flips_coordinates_and_separates_release(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Touch(Path(directory) / 'one'), Touch(Path(directory) / 'two')
            for touch in (first, second):
                touch.path.parent.mkdir(parents=True)
                touch.path.touch()
            def during_hold(duration):
                self.assertEqual(duration, .30)
                events = list(struct.iter_unpack('<iiHHi', first.path.read_bytes()))
                self.assertEqual([(e[2], e[3], e[4]) for e in events],
                                 [(3, 0x39, 0), (3, 0x35, 329), (3, 0x36, 279),
                                  (3, 0, 329), (3, 1, 279), (1, 0x14a, 1), (0, 0, 0)])
            with patch('emulator.runtime.touch.time.sleep', side_effect=during_hold) as sleep:
                first.tap(30, 80)
            sleep.assert_called_once_with(.30)
            events = list(struct.iter_unpack('<iiHHi', first.path.read_bytes()))
            self.assertEqual([(e[2], e[3], e[4]) for e in events[-3:]],
                             [(3, 0x39, -1), (1, 0x14a, 0), (0, 0, 0)])
            self.assertEqual(second.path.read_bytes(), b'')
