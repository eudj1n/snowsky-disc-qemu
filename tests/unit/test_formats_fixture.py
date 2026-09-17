"""Generated format layouts and preservation of ambiguous stock identities."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

from tests.fixtures.formats_fixture import dsf, dff, generate, FILES, FOLDER, RATE, SECONDS
from controller.fiio_link import library_page, playback_snapshot


class FormatsFixtureTests(unittest.TestCase):
    def test_dsf_header_and_metadata_offset(self):
        data = dsf()
        self.assertEqual(data[:4], b'DSD ')
        size, total, metadata = struct.unpack_from('<QQQ', data, 4)
        self.assertEqual((size, total), (28, len(data)))
        self.assertEqual(data[28:32], b'fmt ')
        self.assertEqual(struct.unpack_from('<Q6IQ2I', data, 32),
                         (52, 1, 0, 2, 2, 2822400, 1, 22579200, 4096, 0))
        self.assertEqual(data[80:84], b'data')
        self.assertEqual(80 + struct.unpack_from('<Q', data, 84)[0], metadata)
        self.assertEqual(data[metadata:metadata + 3], b'ID3')
        remainder = (RATE * SECONDS // 8) % 4096
        tail = b'\x69' * remainder + b'\0' * (4096 - remainder)
        self.assertEqual(data[metadata - 8192:metadata], tail * 2)

    def test_id3_v23_size_and_unicode(self):
        data = dsf()
        offset, = struct.unpack_from('<Q', data, 20)
        tag = data[offset:]
        self.assertEqual(tag[:6], b'ID3\x03\0\0')
        self.assertTrue(all(b < 128 for b in tag[6:10]))
        size = sum(b << shift for b, shift in zip(tag[6:10], (21, 14, 7, 0)))
        self.assertEqual(size, len(tag) - 10)
        self.assertIn('DSF Title Ё'.encode('utf-16-le'), tag)

    def test_dff_sizes_channels_and_duration(self):
        data = dff()
        self.assertEqual(data[:4], b'FRM8')
        self.assertEqual(struct.unpack_from('>Q', data, 4)[0], len(data) - 12)
        self.assertEqual(data[12:16], b'DSD ')
        offset = 16
        chunks = {}
        while offset < len(data):
            tag = data[offset:offset + 4]
            size, = struct.unpack_from('>Q', data, offset + 4)
            chunks[tag] = data[offset + 12:offset + 12 + size]
            offset += 12 + size + size % 2
        self.assertEqual(offset, len(data))
        self.assertEqual(set(chunks), {b'FVER', b'PROP', b'DIIN', b'DSD '})
        self.assertIn(b'\0\x02SLFTSRGT', chunks[b'PROP'])
        self.assertIn(struct.pack('>I', RATE), chunks[b'PROP'])
        self.assertEqual(len(chunks[b'DSD ']) * 8 // (RATE * 2), SECONDS)

    def test_fixture_has_two_six_second_cue_tracks(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = generate(temporary)
            self.assertEqual(folder.name, FOLDER)
            self.assertEqual({p.name for p in folder.iterdir()}, set(FILES))
            cue = (folder / 'Image.cue').read_text()
            self.assertIn('FILE "Image.wav" WAVE', cue)
            self.assertIn('TITLE "Cue First Ё"', cue)
            self.assertIn('TITLE "Cue Second й"', cue)
            self.assertEqual(cue.count('TRACK '), 2)
            self.assertIn('INDEX 01 00:06:00', cue)
            with wave.open(str(folder / 'Image.wav')) as audio:
                self.assertEqual(audio.getnframes(), 12 * 44100)
                self.assertEqual((audio.getnchannels(), audio.getsampwidth()), (2, 2))

    def test_generator_refuses_existing_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / FOLDER
            folder.mkdir()
            sentinel = folder / 'keep'
            sentinel.write_bytes(b'user data')
            with self.assertRaises(FileExistsError):
                generate(temporary)
            self.assertEqual(sentinel.read_bytes(), b'user data')

    def test_dsd_patterns_are_deterministic(self):
        self.assertEqual(dsf(), dsf())
        self.assertEqual(dff(), dff())

    def test_wire_queue_preserves_duplicate_ids_and_order(self):
        payload = b'0002[{"songId":6,"flag":6,"itemName":"DFF Pattern"},' \
                  b'{"songId":6,"flag":6,"itemName":"Cue First"}]'
        value = library_page(payload)
        self.assertEqual(value['total'], 2)
        self.assertEqual([item['songId'] for item in value['items']], [6, 6])
        self.assertEqual([item['itemName'] for item in value['items']], ['DFF Pattern', 'Cue First'])

    def test_snapshot_preserves_zero_track_and_cue_flag(self):
        value = playback_snapshot(b'{"song":"{\\"is_cue\\":true,\\"song_track\\":0,\\"pos_id\\":6}"}')
        self.assertEqual(value['song'], {'is_cue': True, 'song_track': 0, 'pos_id': 6})
