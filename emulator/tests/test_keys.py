from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from emulator.runtime.keys import Buttons, CODES, Device, BRIGHTNESS


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'dev/input').mkdir(parents=True)
        (self.root / 'emu').mkdir()
        (self.root / 'dev/input/event0').touch()
        (self.root / 'emu/volume-buttons').write_bytes(b'11')
        self.device = Mock(transition=None)
        self.device.running.return_value = True
        self.now = 0
        self.buttons = Buttons(self.root, self.device, sleep=lambda _: None, clock=lambda: self.now)

    def events(self):
        raw = (self.root / 'dev/input/event0').read_bytes()
        return [(c, v) for _, _, t, c, v in struct.iter_unpack('<iiHHi', raw) if t == 1]

    def test_single_and_double_codes_preserve_firmware_assignment(self):
        for name in ('volume_up', 'volume_down', 'play_pause'):
            for gesture in ('single', 'double'):
                self.buttons.gesture(name, gesture)
                self.assertEqual(self.events()[-2:], [(CODES[name][gesture], 1), (CODES[name][gesture], 0)])

    def test_hold_repeat_release_gpio(self):
        self.buttons.gesture('volume_up', 'hold')
        self.assertEqual((self.root / 'emu/volume-buttons').read_bytes(), b'01')
        self.buttons.gesture('volume_up', 'hold')
        self.buttons.gesture('volume_up', 'end')
        self.assertEqual(self.events(), [(0x107, 1), (0x107, 2), (0x107, 0)])
        self.assertEqual((self.root / 'emu/volume-buttons').read_bytes(), b'11')

    def test_lost_release_expires_and_two_keys_are_independent(self):
        self.buttons.gesture('volume_up', 'hold')
        self.now = 1
        self.buttons.gesture('volume_down', 'hold')
        self.now = 1.6
        self.buttons.expire()
        self.assertEqual((self.root / 'emu/volume-buttons').read_bytes(), b'10')
        self.buttons.cancel()
        self.assertEqual((self.root / 'emu/volume-buttons').read_bytes(), b'11')

    def test_restart_clears_stale_gpio_state(self):
        (self.root / 'emu/volume-buttons').write_bytes(b'00')
        self.buttons.reset()
        self.assertEqual((self.root / 'emu/volume-buttons').read_bytes(), b'11')

    def test_power_uses_lifecycle_not_shutdown_code(self):
        self.buttons.gesture('power', 'single')
        self.assertEqual(self.events(), [(0x103, 1), (0x103, 0)])
        self.buttons.gesture('power', 'hold')
        self.device.toggle_power.assert_called_once()
        self.assertNotIn(0x108, [c for c, _ in self.events()])

    def test_off_power_starts_but_media_does_not(self):
        self.device.running.return_value = False
        with self.assertRaises(ValueError):
            self.buttons.gesture('play_pause', 'single')
        self.buttons.gesture('power', 'single')
        self.device.toggle_power.assert_called_once()
        self.assertEqual(self.events(), [])

    def test_unsafe_unknown_and_transition_rejected(self):
        for code in (0x108, 0xffff, None):
            with self.assertRaises(ValueError):
                self.buttons.pulse(code)
        with self.assertRaises(ValueError):
            self.buttons.gesture('menu_up', 'single')
        self.device.transition = 'starting'
        with self.assertRaises(ValueError):
            self.buttons.gesture('power', 'single')
        self.assertEqual(self.events(), [])

    def test_brightness_nul_padded_firmware_write(self):
        path = self.root / BRIGHTNESS
        path.parent.mkdir(parents=True)
        device = Device(self.root)
        path.write_bytes(b'0\0\0\0')
        self.assertFalse(device.screen_on())
        path.write_bytes(b'20\0\0')
        self.assertTrue(device.screen_on())

    def test_dac_volume_gain_and_mute(self):
        (self.root / 'emu/dac-left').write_bytes(bytes([20]))
        (self.root / 'emu/dac-right').write_bytes(bytes([255]))
        self.assertAlmostEqual(Device(self.root).gains()[0], 10 ** (-10 / 20))
        self.assertEqual(Device(self.root).gains()[1], 0)

    def test_guest_shutdown_request_never_toggles_power_on(self):
        path = self.root / 'emu/power-request'
        path.write_bytes(b'1')
        device = Device(self.root)
        with patch.object(device, 'processes', return_value=[]):
            device.service_requests()
        self.assertIsNone(device.transition)
        self.assertEqual(path.read_bytes(), b'0')

    def test_guest_shutdown_request_is_scoped_stop_and_waits_for_boot(self):
        path = self.root / 'emu/power-request'
        path.write_bytes(b'1')
        device = Device(self.root)
        device.transition = 'starting'
        device.service_requests()
        self.assertEqual(path.read_bytes(), b'1')
        device.transition = None
        with patch.object(device, 'processes', return_value=[123]), patch('emulator.runtime.keys.threading.Thread') as thread:
            device.service_requests()
            thread.return_value.start.assert_called_once()
        self.assertEqual(device.transition, 'stopping')
        self.assertEqual(path.read_bytes(), b'0')


if __name__ == '__main__':
    unittest.main()
