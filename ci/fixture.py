"""One deterministic, generated 30-second stereo WAV. No copyrighted test media."""
from pathlib import Path
import struct
import sys
import wave


def generate(directory):
    path = Path(directory) / 'CI Tone.wav'
    # Integer square wave: no host floating-point or random dithering differences.
    period = b''.join(struct.pack('<hh', value, value)
                      for value in ([4096] * 50 + [-4096] * 50))
    with path.open('xb') as output:
        with wave.open(output, 'wb') as wav:
            wav.setparams((2, 2, 44100, 0, 'NONE', 'NONE'))
            wav.writeframes(period * (44100 * 30 // 100))
    return path


if __name__ == '__main__':
    generate(sys.argv[1])
