import struct
import unittest
from unittest.mock import patch

from inspect_link_commands import commands, parse_allowlist


class LinkCommandTests(unittest.TestCase):
    def fixture(self):
        data = bytearray(2048)
        data[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 1)
        # A deliberately nonstandard VA/file-offset mapping.
        struct.pack_into('<8I', data, 52, 1, 512, 0x123000, 0, 1024, 1024, 4, 4)
        struct.pack_into('<3I', data, 512, 0x123040, 0x123048, 0)
        data[576:581] = b'0501\x00'
        data[584:589] = b'0713\x00'
        return data, {'table': '0x123000', 'count': 2}

    def test_maps_segments_and_reads_terminated_allowlist(self):
        data, layout = self.fixture()
        self.assertEqual(parse_allowlist(data, layout), ['0501', '0713'])

    def test_requires_full_fingerprint_not_plausible_table(self):
        with self.assertRaises(ValueError):
            commands(self.fixture()[0])

    def test_rejects_profile_without_reviewed_layout(self):
        with patch('inspect_link_commands.identify_player', return_value={'diagnostics': {'network': {}}}):
            with self.assertRaisesRegex(ValueError, 'No reviewed TCP allowlist'):
                commands(b'')

    def test_rejects_bad_pointers_count_termination(self):
        for index, value in ((0, 0), (0, 1), (1, 0x1233fd), (2, 0x123040)):
            data, layout = self.fixture()
            struct.pack_into('<I', data, 512 + 4 * index, value)
            with self.assertRaises(ValueError):
                parse_allowlist(data, layout)
        for count in (0, 1, 3, 513, True):
            data, layout = self.fixture()
            with self.assertRaises(ValueError):
                parse_allowlist(data, dict(layout, count=count))

    def test_rejects_malformed_tags_and_duplicates(self):
        for raw in (b'0501x', b'xx01\0', b'0713\0'):
            data, layout = self.fixture()
            data[576:581] = raw
            with self.assertRaises(ValueError):
                parse_allowlist(data, layout)

    def test_rejects_truncated_segments(self):
        data, layout = self.fixture()
        for size in (10, 80, 600):
            with self.assertRaises(ValueError):
                parse_allowlist(data[:size], layout)
