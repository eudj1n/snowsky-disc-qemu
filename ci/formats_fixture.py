"""Small original CUE/DSF/DSDIFF fixtures; no downloaded music or firmware data.

DSF/DSDIFF layout references: FFmpeg libavformat/dsfdec.c and iff.c.
These produce deterministic one-bit test patterns, not a listening-quality
DSD encoder. Never interpret metadata acceptance as native DSD output support.
"""
from pathlib import Path
import struct
import wave

FOLDER = 'Formats CI Ё'
FILES = ('Image.wav', 'Image.cue', 'Pattern.dsf', 'Pattern.dff')
RATE = 2822400
SECONDS = 8


def id3():
    body = b''
    for tag, value in ((b'TIT2', 'DSF Title Ё'), (b'TPE1', 'Formats Artist'),
                       (b'TALB', 'DSF Album'), (b'TRCK', '7')):
        text = b'\x01\xff\xfe' + value.encode('utf-16-le')
        body += tag + struct.pack('>I', len(text)) + b'\0\0' + text
    size = len(body)
    return b'ID3\x03\0\0' + bytes((size >> 21, (size >> 14) & 127,
                                      (size >> 7) & 127, size & 127)) + body


def dsf():
    samples = RATE * SECONDS
    blocks, remainder = divmod(samples // 8, 4096)
    data = b'\x69' * (blocks * 4096 * 2)
    if remainder:
        data += (b'\x69' * remainder + b'\0' * (4096 - remainder)) * 2
    fmt = b'fmt ' + struct.pack('<Q6IQ2I', 52, 1, 0, 2, 2, RATE, 1, samples, 4096, 0)
    offset = 28 + len(fmt) + 12 + len(data)
    tags = id3()
    return (b'DSD ' + struct.pack('<QQQ', 28, offset + len(tags), offset) + fmt +
            b'data' + struct.pack('<Q', len(data) + 12) + data + tags)


def chunk(tag, data):
    return tag + struct.pack('>Q', len(data)) + data + b'\0' * (len(data) % 2)


def dff():
    properties = (b'SND ' + chunk(b'FS  ', struct.pack('>I', RATE)) +
                  chunk(b'CHNL', struct.pack('>H', 2) + b'SLFTSRGT') +
                  chunk(b'CMPR', b'DSD \x0enot compressed'))
    title = b'DFF Pattern'
    info = chunk(b'DITI', struct.pack('>I', len(title)) + title)
    body = (b'DSD ' + chunk(b'FVER', struct.pack('>I', 0x01050000)) +
            chunk(b'PROP', properties) + chunk(b'DIIN', info) +
            chunk(b'DSD ', b'\x96' * (RATE * SECONDS // 8 * 2)))
    return b'FRM8' + struct.pack('>Q', len(body)) + body


def generate(sd):
    folder = Path(sd) / FOLDER
    folder.mkdir()
    with (folder / FILES[0]).open('xb') as output:
        with wave.open(output, 'wb') as audio:
            audio.setparams((2, 2, 44100, 0, 'NONE', 'NONE'))
            period = b''.join(struct.pack('<hh', v, v) for v in [1024] * 50 + [-1024] * 50)
            audio.writeframes(period * (44100 * 12 // 100))
    cue = ('PERFORMER "Cue Artist"\nTITLE "Cue Album Ё"\nFILE "Image.wav" WAVE\n'
           '  TRACK 01 AUDIO\n    TITLE "Cue First Ё"\n    INDEX 01 00:00:00\n'
           '  TRACK 02 AUDIO\n    TITLE "Cue Second й"\n    INDEX 01 00:06:00\n')
    for name, data in ((FILES[1], cue.encode('utf-8')), (FILES[2], dsf()), (FILES[3], dff())):
        with (folder / name).open('xb') as output:
            output.write(data)
    return folder


if __name__ == '__main__':
    import sys
    generate(sys.argv[1])
