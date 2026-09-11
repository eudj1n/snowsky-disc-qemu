#!/usr/bin/env python3
"""Assemble a known runtime profile into a new rootfs. Never replace existing data."""
import argparse
from pathlib import Path
import subprocess
import tempfile

from firmware_inventory import CHUNK, plaintext_digest
from firmware_profile import load_profile


def extract(ota, destination, profile):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Rootfs already exists; use a new isolated work volume')
    selected = {}
    for path in Path(ota).glob('rootfs.squashfs.*.enc'):
        match = CHUNK.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file() or int(match[1]) in selected:
            raise ValueError('Invalid or duplicate rootfs chunk')
        selected[int(match[1])] = path
    if set(selected) != set(range(profile['rootfs_chunks'])):
        raise ValueError('Chunk indices/count do not match selected firmware')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=destination.parent) as squash:
        actual = plaintext_digest([selected[i] for i in sorted(selected)], output=squash)
        if actual != {'sha256': profile['rootfs_sha256'], 'size': profile['rootfs_size']}:
            raise ValueError('Plaintext rootfs does not match selected firmware')
        squash.flush()
        subprocess.run(['unsquashfs', '-no-progress', '-no-xattrs', '-d', str(destination),
                        f'/proc/self/fd/{squash.fileno()}'], pass_fds=(squash.fileno(),), check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ota', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--version', default='2.40')
    args = parser.parse_args()
    extract(args.ota, args.destination, load_profile(args.version))
