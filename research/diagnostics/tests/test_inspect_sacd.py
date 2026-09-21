import struct
import tempfile
import unittest
from pathlib import Path

from research.diagnostics.inspect_sacd import inspect


class SacdStructureTests(unittest.TestCase):
    def fixture(self):
        # Original header-only test data; not a playable SACD or copied media.
        data = bytearray(550 * 2048)
        master, area = 510 * 2048, 544 * 2048
        data[master:master + 10] = b'SACDMTOC\x01\x14'
        struct.pack_into('>I', data, master + 64, 544)
        data[area:area + 10] = b'TWOCHTOC\x01\x14'
        struct.pack_into('>H', data, area + 10, 2)
        data[area + 20:area + 22] = bytes((4, 2))
        data[area + 32], data[area + 69] = 2, 2
        struct.pack_into('>II', data, area + 72, 546, 549)
        times = area + 2048
        data[times:times + 8] = b'SACDTRL2'
        data[times + 1028:times + 1036] = bytes((0, 6, 0, 0, 1, 2, 37, 0))
        return data

    def read(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original-headers.iso'
            path.write_bytes(data)
            return inspect(path)

    def test_structural_units_and_no_private_metadata(self):
        facts = self.read(self.fixture())
        self.assertEqual(facts, {'size': 550 * 2048, 'areas': [dict(
            kind='TWOCHTOC', channels=2, frame_format=2, tracks=2,
            duration_frames=[450, 4687], sample_rate=2822400)]})

    def test_invalid_extents_and_tables(self):
        for offset, value in ((510 * 2048, b'INVALID!'),
                              (510 * 2048 + 64, struct.pack('>I', 550)),
                              (544 * 2048 + 10, struct.pack('>H', 97)),
                              (544 * 2048 + 72, struct.pack('>II', 549, 551)),
                              (545 * 2048, b'NO_TABLE'),
                              (545 * 2048 + 1029, bytes((60,)))):
            data = self.fixture()
            data[offset:offset + len(value)] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.read(data)

    def test_dst_is_reported_separately_and_partial_sectors_rejected(self):
        data = self.fixture()
        data[544 * 2048 + 21] = 0
        self.assertEqual(self.read(data)['areas'][0]['frame_format'], 0)
        with self.assertRaises(ValueError):
            self.read(data[:-1])
