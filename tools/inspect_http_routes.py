#!/usr/bin/env python3
"""Read stock V2.40's active HTTP route table (no firmware writes, no Ghidra required)."""
import argparse
import json
import struct
from pathlib import Path


def routes(data):
    if data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('expected ELF32 little-endian')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 42)
    segments = [struct.unpack_from('<8I', data, phoff + i * phsize) for i in range(phnum)]

    def offset(address, size=1):
        for kind, off, va, _, filesz, *_ in segments:
            if kind == 1 and va <= address and address + size <= va + filesz:
                return off + address - va
        raise ValueError(f'address {address:08x} not in file-backed PT_LOAD')

    def string(address):
        start = offset(address)
        return data[start:data.index(b'\0', start, start + 256)].decode('ascii')

    result = []
    for i in range(32):
        method, path, handler, event = struct.unpack_from('<4I', data, offset(0x6c7a50 + i * 16, 16))
        if not method:
            if not result or result[0]['path'] != '/dir/':
                raise ValueError('not the expected V2.40 route table')
            return result
        result.append(dict(method=string(method), path=string(path),
                           handler=f'0x{handler:08x}', event='HTTP_CHUNK' if event else 'HTTP_MSG'))
    raise ValueError('unterminated route table; unsupported firmware')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', nargs='?', default='/work/rootfs/usr/bin/mq_player')
    args = parser.parse_args()
    print(json.dumps(routes(Path(args.binary).read_bytes()), indent=2))
