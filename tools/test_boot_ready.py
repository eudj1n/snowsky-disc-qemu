from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from boot_ready import ready, wait_ready


class BootReadyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = self.base / 'rootfs'
        (self.root / 'emu').mkdir(parents=True)
        (self.root / 'dev/input').mkdir(parents=True)
        self.marker = self.root / 'emu/fb-live'
        self.marker.write_bytes(b'\x01')
        self.proc = self.base / 'proc'
        for pid, program, event in ((1, 'mq_ui', 'event1'), (2, 'mq_player', 'event0')):
            entry = self.proc / str(pid)
            (entry / 'fd').mkdir(parents=True)
            (entry / 'cmdline').write_bytes(f'qemu\0/usr/bin/{program}\0'.encode())
            (self.root / 'dev/input' / event).touch()
            (entry / 'fd/3').symlink_to('anon_inode:[eventpoll]')
            (entry / 'fd/4').symlink_to(self.root / 'dev/input' / event)
        self.device = Mock(root=self.root)
        self.device.processes.return_value = [1, 2]

    def test_requires_both_input_consumers_and_current_boot_frame(self):
        self.assertTrue(ready(self.device, self.proc))
        for marker in (b'', b'\xff', b'0', b'\x00\x01'):
            self.marker.write_bytes(marker)
            self.assertFalse(ready(self.device, self.proc))
        self.marker.write_bytes(b'\x00')
        self.device.processes.return_value = [1]
        self.assertFalse(ready(self.device, self.proc))
        self.device.processes.return_value = [1, 2]
        (self.proc / '2/fd/4').unlink()
        self.assertFalse(ready(self.device, self.proc))

    def test_other_root_and_similar_command_do_not_count(self):
        (self.proc / '2/fd/4').unlink()
        (self.proc / '2/fd/4').symlink_to(self.base / 'other/dev/input/event0')
        self.assertFalse(ready(self.device, self.proc))
        (self.proc / '2/fd/4').unlink()
        (self.proc / '2/fd/4').symlink_to(self.root / 'dev/input/event0')
        (self.proc / '1/cmdline').write_bytes(b'qemu\0/usr/bin/mq_ui_old\0')
        self.assertFalse(ready(self.device, self.proc))

    def test_exit_or_missing_marker_is_not_ready(self):
        self.device.processes.return_value = [1, 999]
        self.assertFalse(ready(self.device, self.proc))
        self.marker.unlink()
        self.assertFalse(ready(self.device, self.proc))

    def test_ready_has_no_minimum_wait_and_failure_is_bounded(self):
        sleep = Mock()
        with patch('boot_ready.ready', return_value=True):
            wait_ready(self.device, sleep=sleep)
        sleep.assert_not_called()
        with patch('boot_ready.ready', return_value=False):
            with self.assertRaisesRegex(TimeoutError, 'not ready'):
                wait_ready(self.device, timeout=1, clock=Mock(side_effect=[0, 0, 1]), sleep=sleep)
        sleep.assert_called_once_with(.2)
