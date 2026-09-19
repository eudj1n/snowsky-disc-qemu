"""Read structural SACD ISO facts without exposing disc or track text.

Original narrow reader of 2048-byte-sector images. Layout reference:
https://github.com/sacd-ripper/sacd-ripper/blob/master/libs/libsacd/scarletbook.h
This is not an audio decoder or a general ISO/filesystem validator.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


SECTOR = 2048


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def inspect(path):
    size = Path(path).stat().st_size
    if size % SECTOR:
        raise ValueError('requires 2048-byte sectors')
    with Path(path).open('rb') as source:
        def read(lsn, count=1):
            if not 0 <= lsn < size // SECTOR or not 1 <= count <= 96:
                raise ValueError('invalid TOC extent')
            source.seek(lsn * SECTOR)
            data = source.read(count * SECTOR)
            if len(data) != count * SECTOR:
                raise ValueError('truncated TOC')
            return data

        master = read(510)
        if master[:10] != b'SACDMTOC\x01\x14':
            raise ValueError('unsupported Master TOC')
        areas = []
        # Primary stereo/multichannel areas only; the other addresses are backups.
        for offset in (64, 72):
            lsn = struct.unpack_from('>I', master, offset)[0]
            if not lsn:
                continue
            header = read(lsn)
            signature = b'TWOCHTOC' if offset == 64 else b'MULCHTOC'
            if header[:10] != signature + b'\x01\x14':
                raise ValueError('unsupported Area TOC')
            data = read(lsn, struct.unpack_from('>H', header, 10)[0])
            count, channels, encoding = header[69], header[32], header[21] & 15
            start, end = struct.unpack_from('>II', header, 72)
            if not count or header[20] != 4 or channels not in (2, 5, 6):
                raise ValueError('unsupported area parameters')
            if encoding not in (0, 2, 3) or not 0 < start <= end < size // SECTOR:
                raise ValueError('invalid audio extent/encoding')
            times = [data[i:i + SECTOR] for i in range(0, len(data), SECTOR)
                     if data[i:i + 8] == b'SACDTRL2']
            if len(times) != 1:
                raise ValueError('expected one track time table')
            durations = []
            for track in range(count):
                minute, second, frame = times[0][1028 + 4 * track:1031 + 4 * track]
                if second >= 60 or frame >= 75:
                    raise ValueError('invalid track time')
                durations.append((minute * 60 + second) * 75 + frame)
            areas.append(dict(kind=signature.decode(), channels=channels,
                              frame_format=encoding, tracks=count,
                              duration_frames=durations, sample_rate=2822400))
    if not areas:
        raise ValueError('no primary audio areas')
    return dict(size=size, areas=areas)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iso', type=Path)
    args = parser.parse_args()
    print(json.dumps(dict(sha256=digest(args.iso), **inspect(args.iso)), indent=2))
