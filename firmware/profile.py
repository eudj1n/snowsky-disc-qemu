#!/usr/bin/env python3
"""Exact-build runtime validation; unknown/modified builds fail closed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct

PROFILES = Path(__file__).resolve().parent
DEFAULT_VERSION = (PROFILES / 'active-version').read_text().strip()
# Extra full-suite dispatch implemented by ci/integration.sh. New scenarios need code.
FULL_SCENARIOS = frozenset({'library', 'formats', 'track-end', 'scan-cancel',
                            'library-reset', 'storage', 'preferences'})


def load_profile(version=DEFAULT_VERSION):
    if not re.fullmatch(r'\d+\.\d{2}', version):
        raise ValueError('Invalid firmware version')
    path = PROFILES / f'v{version}.json'
    if not path.is_file():
        raise ValueError('Unknown firmware version; add a reviewed profile first')
    profile = json.loads(path.read_text())
    if profile.get('version') != version:
        raise ValueError('Firmware profile identity mismatch')
    for key in ('capabilities', 'acceptance', 'full_scenarios'):
        if not isinstance(profile.get(key), list) or any(type(x) is not str for x in profile[key]):
            raise ValueError(f'Missing or invalid reviewed {key}')
    if not set(profile['full_scenarios']) <= FULL_SCENARIOS:
        raise ValueError('Full suite contains a scenario without a runner')
    if not set(profile['full_scenarios']) <= set(profile['acceptance']):
        raise ValueError('Full suite includes an unreviewed scenario')
    return profile


def available_versions():
    # Only explicit runtime profiles, never inventory or vendor announcements.
    return sorted(p.stem[1:] for p in PROFILES.glob('v*.json')
                  if re.fullmatch(r'v\d+\.\d{2}', p.stem))


def selected_version():
    return os.environ.get('FW_VERSION') or DEFAULT_VERSION


def selected_profile():
    return load_profile(selected_version())


def value(profile, key):
    result = profile
    for part in key.split('.'):
        result = result[part]
    return result


def supports(profile, feature):
    return feature in profile.get('capabilities', [])


def require_scenario(profile, scenario):
    if scenario not in profile.get('acceptance', []):
        raise ValueError(f"Unreviewed acceptance scenario {scenario!r} for V{profile['version']}")


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
    for candidate in ([version] if version is not None else available_versions()):
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
    parser.add_argument('operation', choices=['validate', 'patch-keys', 'get', 'supports', 'require-scenario'])
    parser.add_argument('target')
    parser.add_argument('--version', default=selected_version())
    args = parser.parse_args()
    profile = load_profile(args.version)
    if args.operation == 'get':
        result = value(profile, args.target)
        print(json.dumps(result) if isinstance(result, (dict, list, bool)) else result)
        raise SystemExit(0)
    if args.operation == 'supports':
        raise SystemExit(0 if supports(profile, args.target) else 1)
    if args.operation == 'require-scenario':
        require_scenario(profile, args.target)
        raise SystemExit(0)
    validate(args.target, profile)
    if args.operation == 'patch-keys':
        changed = apply_key_patch(Path(args.target) / 'usr/bin/mq_player', profile)
        print(f'V{args.version}: keys enabled ({"patched" if changed else "already patched"})')
    else:
        print(f'V{args.version}: product and six binary fingerprints verified')
