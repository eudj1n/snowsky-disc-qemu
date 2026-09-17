#!/usr/bin/env python3
"""Exact-build runtime validation; unknown/modified builds fail closed."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

DEFAULT_VERSION = '2.57'

PROFILES = Path(__file__).resolve().parent


def load_profile(version=DEFAULT_VERSION):
    if not re.fullmatch(r'\d+\.\d{2}', version):
        raise ValueError('Invalid firmware version')
    path = PROFILES / f'v{version}.json'
    if not path.is_file():
        raise ValueError('Unknown firmware version; add a reviewed profile first')
    return json.loads(path.read_text())


def patch_state(data, profile):
    patch = profile['key_patch']
    offset, address = int(patch['offset'], 16), int(patch['address'], 16)
    before, after = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
    if not before or len(before) != len(after) or offset < 0 or offset + len(before) > len(data):
        raise ValueError('Invalid patch range')
    normalized = bytearray(data)
    current = bytes(normalized[offset:offset + len(before)])
    if current not in (before, after):
        raise ValueError('Unexpected key guard bytes')
    normalized[offset:offset + len(before)] = before
    if hashlib.sha256(normalized).hexdigest() != profile['binaries']['usr/bin/mq_player']:
        raise ValueError('Unknown mq_player build; refusing patch/probe')
    if data[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 8:
        raise ValueError('Expected ELF32 little-endian MIPS')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 42)
    segments = [struct.unpack_from('<8I', data, phoff + i * phsize) for i in range(phnum)]
    if not any(kind == 1 and flags & 1 and off <= offset and
               offset + len(before) <= off + size and va + offset - off == address
               for kind, off, va, _, size, _, flags, _ in segments):
        raise ValueError('Patch address/offset is not in an executable PT_LOAD')
    return current == after


def validate(rootfs, profile):
    rootfs = Path(rootfs)
    metadata = dict(line.split('=', 1) for line in
                    (rootfs / 'etc/product_version/version.in').read_text().splitlines() if '=' in line)
    for key, expected in [('PRODUCT', profile['product']), ('MAIN_OS_VER', profile['main_os_version']),
                          ('RECOVERY_OS_VER', profile['recovery_os_version'])]:
        if metadata.get(key) != str(expected):
            raise ValueError(f'Firmware metadata mismatch: {key}; select the correct isolated volume')
    for name, expected in profile['binaries'].items():
        path = rootfs / name
        if path.is_symlink():
            raise ValueError(f'Expected a regular pinned binary: {name}')
        data = path.read_bytes()
        if name == 'usr/bin/mq_player':
            patch_state(data, profile)
        elif hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Firmware binary mismatch: {name}')


def apply_key_patch(binary, profile):
    path = Path(binary)
    data = path.read_bytes()
    if patch_state(data, profile):
        return False
    patch = profile['key_patch']
    offset, after = int(patch['offset'], 16), bytes.fromhex(patch['after'])
    with path.open('r+b') as target:
        target.seek(offset)
        target.write(after)
    return True


def require_v240_player(binary):
    """Old address-based diagnostics must never interpret V2.57 memory as V2.40."""
    patch_state(Path(binary).read_bytes(), load_profile('2.40'))


def identify_player(data, version=None):
    """Select reviewed diagnostic addresses by full stock/patched fingerprint."""
    for candidate in ([version] if version is not None else ['2.40', '2.57']):
        profile = load_profile(candidate)
        try:
            patch_state(data, profile)
        except ValueError:
            continue
        if 'diagnostics' not in profile:
            raise ValueError('No reviewed diagnostics for this build')
        return profile
    raise ValueError('Unknown or mismatched mq_player build; refusing diagnostic probe')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['validate', 'patch-keys'])
    parser.add_argument('rootfs', type=Path)
    parser.add_argument('--version', default=DEFAULT_VERSION)
    args = parser.parse_args()
    profile = load_profile(args.version)
    validate(args.rootfs, profile)
    if args.operation == 'patch-keys':
        changed = apply_key_patch(args.rootfs / 'usr/bin/mq_player', profile)
        print(f'V{args.version}: keys enabled ({"patched" if changed else "already patched"})')
    else:
        print(f'V{args.version}: product and six binary fingerprints verified')
