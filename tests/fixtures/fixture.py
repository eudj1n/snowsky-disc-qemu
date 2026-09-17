"""Three deterministic 30-second tracks (WAV + tagged FLAC), two albums; no copyrighted test media."""
from pathlib import Path
import struct
import sys
import subprocess
import wave


NAMES = ('CI Tone — Проверка.wav', 'Second — Ё.flac', 'Third — й.flac')


def generate(directory):
    # Exercise UTF-8 FAT directory and file names on every clean integration run.
    path = Path(directory) / 'Кириллица Ё й' / NAMES[0]
    path.parent.mkdir(exist_ok=True)
    # Integer square wave: no host floating-point or random dithering differences.
    period = b''.join(struct.pack('<hh', value, value)
                      for value in ([4096] * 50 + [-4096] * 50))
    with path.open('xb') as output:
        with wave.open(output, 'wb') as wav:
            wav.setparams((2, 2, 44100, 0, 'NONE', 'NONE'))
            wav.writeframes(period * (44100 * 30 // 100))
    # Stock ignores WAV INFO tags. FLAC Vorbis comments exercise album grouping.
    for name in NAMES[1:]:
        target = path.with_name(name)
        if target.exists():
            raise FileExistsError(target)
        subprocess.run(['sox', str(path), '--add-comment', 'ARTIST=CI Artist',
                        '--add-comment', 'ALBUM=CI Album', str(target)], check=True)
    return path


if __name__ == '__main__':
    generate(sys.argv[1])
