#!/usr/bin/env python3
"""Read the fingerprinted stock TCP command allowlist; never sends commands.

Admission is necessary, not sufficient: an admitted tag can have a NULL handler.
Local UI dispatch tables do not establish TCP reachability. No guest patches.
"""
import argparse
import json
from pathlib import Path
import re
import struct

from firmware.profile import identify_player
from research.diagnostics.player_memory import load_segments


def parse_allowlist(data, layout):
    """Parse a reviewed layout separately for malformed-ELF unit tests."""
    segments = load_segments(data)

    def offset(address, size):
        for _, start, va, _, filesz, *_ in segments:
            if va <= address and address + size <= va + filesz:
                return start + address - va
        raise ValueError('TCP allowlist address outside file-backed PT_LOAD')

    table = int(layout['table'], 16)
    count = layout['count']
    if type(count) is not int or not 1 <= count <= 512 or table % 4:
        raise ValueError('Invalid TCP allowlist layout')
    tags = []
    for index in range(count + 1):
        pointer, = struct.unpack_from('<I', data, offset(table + 4 * index, 4))
        if index == count:
            if pointer:
                raise ValueError('Unterminated TCP allowlist')
            return tags
        if not pointer:
            raise ValueError('Unexpected TCP allowlist count')
        start = offset(pointer, 5)
        raw = data[start:start + 5]
        if not re.fullmatch(b'[0-9a-f]{4}\x00', raw):
            raise ValueError('Invalid TCP allowlist command string')
        tag = raw[:4].decode('ascii')
        if tag in tags:
            raise ValueError('Duplicate TCP allowlist command')
        tags.append(tag)


def commands(data, version=None):
    profile = identify_player(data, version)
    layout = profile['diagnostics']['network'].get('tcp_allowlist')
    if layout is None:
        raise ValueError('No reviewed TCP allowlist for this firmware')
    return {'version': profile['version'], 'table': layout['table'],
            'admitted': parse_allowlist(data, layout)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', nargs='?', default='/work/rootfs/usr/bin/mq_player')
    parser.add_argument('--version', help='Require an exact reviewed version')
    args = parser.parse_args()
    print(json.dumps(commands(Path(args.binary).read_bytes(), args.version), indent=2))
