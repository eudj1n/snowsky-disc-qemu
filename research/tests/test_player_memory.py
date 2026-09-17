import io
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from research.diagnostics.player_memory import guest_base, parse_maps, read_memory, unique_player_pid


class MemoryTests(unittest.TestCase):
    def test_transient_duplicate_pid_is_rechecked_without_choosing_one(self):
        with patch('research.diagnostics.player_memory.player_pids', side_effect=[[12, 13], [12]]) as scan, \
                patch('research.diagnostics.player_memory.time.sleep') as sleep:
            self.assertEqual(unique_player_pid(SimpleNamespace(root='/guest')), 12)
            self.assertEqual(scan.call_count, 2)
            sleep.assert_called_once_with(.05)

    def test_persistent_duplicate_pids_still_fail_closed(self):
        with patch('research.diagnostics.player_memory.player_pids', return_value=[12, 13]) as scan, \
                patch('research.diagnostics.player_memory.time.sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'found PIDs'):
                unique_player_pid(SimpleNamespace(root='/guest'))
            self.assertEqual(scan.call_count, 11)
            self.assertEqual(sleep.call_count, 10)

    def test_missing_pid_fails_without_waiting(self):
        with patch('research.diagnostics.player_memory.player_pids', return_value=[]), \
                patch('research.diagnostics.player_memory.time.sleep') as sleep:
            with self.assertRaises(ValueError):
                unique_player_pid(SimpleNamespace(root='/guest'))
            sleep.assert_not_called()

    def setUp(self):
        self.maps = parse_maps('1000-2000 r--p 00000000 00:01 42 /guest/usr/bin/mq_player\n'
                               '3000-4000 rw-p 00001000 00:01 42 /guest/usr/bin/mq_player\n'
                               '4000-5000 rw-p 00000000 00:00 0\n')
        self.stat = SimpleNamespace(st_dev=os.makedev(0, 1), st_ino=42)
        self.segments = [(1, 0, 0x400000, 0, 4096, 4096, 5, 4096),
                         (1, 4096, 0x402000, 0, 4096, 8192, 6, 4096)]

    def test_base_uses_both_elf_segments_and_file_identity(self):
        self.assertEqual(guest_base(self.maps, self.segments, self.stat), 0x1000 - 0x400000)
        self.stat.st_ino = 43
        with self.assertRaises(ValueError):
            guest_base(self.maps, self.segments, self.stat)

    def test_conflicting_mappings_rejected(self):
        self.maps[1]['start'] += 4096
        with self.assertRaises(ValueError):
            guest_base(self.maps, self.segments, self.stat)

    def test_shared_file_page_at_distinct_guest_addresses(self):
        # V2.40 has a PT_LOAD boundary inside a page, with a 64K VA gap.
        segments = [(1, 0, 0x400000, 0, 0x1720, 0x1720, 5, 65536),
                    (1, 0x1720, 0x411720, 0, 0x8e0, 0x18e0, 6, 65536)]
        maps = parse_maps('1000-3000 r--p 00000000 00:01 42 /guest/usr/bin/mq_player\n'
                          '12000-13000 rw-p 00001000 00:01 42 /guest/usr/bin/mq_player\n')
        self.assertEqual(guest_base(maps, segments, self.stat), 0x1000 - 0x400000)

    def test_exact_read_can_cross_adjacent_readable_mappings(self):
        memory = io.BytesIO(bytes(range(256)) * 80)
        self.assertEqual(read_memory(memory, self.maps, 0, 0x3ffe, 4), b'\xfe\xff\x00\x01')

    def test_null_overflow_gap_unreadable_and_short_reads_rejected(self):
        memory = io.BytesIO(b'\0' * 0x1800)
        for address, size in ((0, 4), (2**32 - 1, 4), (0x1fff, 2), (0x1000, 0), (0x1800, 4)):
            with self.assertRaises(ValueError):
                read_memory(memory, self.maps, 0, address, size)
        self.maps[0]['perms'] = '---p'
        with self.assertRaises(ValueError):
            read_memory(memory, self.maps, 0, 0x1000, 4)
