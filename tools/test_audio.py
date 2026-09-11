"""Capture integrity checks: python3 -m unittest discover -s tools -p 'test_*.py'."""
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from audio import capture_info, export_wav, read_chunk


class AudioCaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def capture(self, data, channels=2, width=4, rate=44100):
        (self.root / 'audio.fmt').write_bytes(struct.pack('<III', channels, width, rate))
        (self.root / 'audio.pcm').write_bytes(data)
        return capture_info(self.root)

    def test_wav_preserves_signed_stereo_and_drops_partial_frame(self):
        pcm = struct.pack('<iiii', -2147483648, 2147483647, 12345, -67890)
        self.capture(pcm + b'bad')
        output = self.root / 'capture.wav'
        export_wav(self.root, output)
        with wave.open(str(output)) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (2, 4, 44100))
            self.assertEqual(wav.readframes(100), pcm)

    def test_wav_unsigned_8bit_conversion(self):
        self.capture(bytes([128, 255, 0, 127]), channels=1, width=1)
        output = self.root / 'capture.wav'
        export_wav(self.root, output)
        with wave.open(str(output)) as wav:
            self.assertEqual(wav.readframes(100), bytes([0, 127, 128, 255]))

    def test_live_growth_reads_only_complete_frames(self):
        info = self.capture(b'\x00' * 8)
        with (self.root / 'audio.pcm').open('ab') as f:
            f.write(b'\x01' * 11)
        self.assertEqual(read_chunk(self.root, info['generation'], 8), b'\x01' * 8)

    def test_old_generation_and_unaligned_offsets_rejected(self):
        info = self.capture(b'\x00' * 16)
        for generation, offset in [('old', 0), (info['generation'], -8), (info['generation'], 1)]:
            with self.assertRaises(ValueError):
                read_chunk(self.root, generation, offset)

    def test_invalid_format_rejected(self):
        for width, rate in [(0, 44100), (5, 44100), (4, 0)]:
            with self.assertRaises(ValueError):
                self.capture(b'', width=width, rate=rate)


if __name__ == '__main__':
    unittest.main()
