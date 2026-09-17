#!/usr/bin/env python3
"""Read a fingerprinted V2.40/V2.57 active HTTP route table (no firmware writes, no Ghidra required)."""
import argparse
import json
import struct
from pathlib import Path
from firmware.profile import identify_player
from research.diagnostics.player_memory import load_segments


def routes(data, version=None):
    profile = identify_player(data, version)
    return parse_routes(data, profile['diagnostics']['http'])


def parse_routes(data, layout):
    """Parse an already verified build; separate for firmware-free malformed-ELF tests."""
    segments = load_segments(data)

    def offset(address, size=1):
        for kind, off, va, _, filesz, *_ in segments:
            if kind == 1 and va <= address and address + size <= va + filesz:
                return off + address - va
        raise ValueError(f'address {address:08x} not in file-backed PT_LOAD')

    def string(address):
        start = offset(address)
        end = data.index(b'\0', start, start + 256)
        offset(address, end - start + 1)
        return data[start:end].decode('ascii')

    result = []
    for i in range(32):
        method, path, handler, event = struct.unpack_from('<4I', data, offset(int(layout['table'], 16) + i * 16, 16))
        if not method:
            if len(result) != layout['count'] or not result or result[0]['path'] != '/dir/':
                raise ValueError('not the expected route table')
            return result
        if event not in (0, 1) or not any(flags & 1 and va <= handler < va + filesz
                                         for _, _, va, _, filesz, _, flags, _ in segments):
            raise ValueError('Invalid route event or non-executable handler')
        method, path = string(method), string(path)
        if method not in ('GET', 'POST', 'DELETE', 'PUT', 'HEAD', 'OPTIONS') or not path.startswith('/'):
            raise ValueError('Invalid route method/path')
        result.append(dict(method=method, path=path,
                           handler=f'0x{handler:08x}', event='HTTP_CHUNK' if event else 'HTTP_MSG'))
    raise ValueError('unterminated route table; unsupported firmware')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', nargs='?', default='/work/rootfs/usr/bin/mq_player')
    parser.add_argument('--version', help='Require version (default: fingerprint detection)')
    args = parser.parse_args()
    print(json.dumps(routes(Path(args.binary).read_bytes(), args.version), indent=2))
