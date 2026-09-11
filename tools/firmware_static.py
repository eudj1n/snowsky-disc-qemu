#!/usr/bin/env python3
"""Extract a pinned OTA for static analysis only; never execute guest code.

Destination must not exist. Use an isolated Docker volume, not the runtime volume.
Native unsquashfs runs only after the streamed plaintext matches a committed inventory.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from firmware_inventory import plaintext_digest, verified_chunks, versions


def extract(package, record, destination):
    package, destination = Path(package), Path(destination)
    main, recovery = versions(package)
    if (main, recovery) != (record['main_os_version'], record['recovery_os_version']):
        raise ValueError('Package version does not match inventory')
    chunks, _ = verified_chunks(package / 'main_os' / f'ota_v{main}')
    if len(chunks) != record['rootfs_chunks']:
        raise ValueError('Chunk count does not match inventory')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Static destination must not exist; existing data is never removed')
    with tempfile.TemporaryFile() as squash:
        actual = plaintext_digest(chunks, output=squash)
        if actual != record['rootfs']:
            raise ValueError('Plaintext does not match inventory')
        squash.flush()
        # /proc/self/fd is inherited by the native extractor, not a firmware process.
        subprocess.run(['unsquashfs', '-no-progress', '-no-xattrs', '-d', str(destination),
                        f'/proc/self/fd/{squash.fileno()}'], pass_fds=(squash.fileno(),), check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    extract(args.package, json.loads(args.inventory.read_text()), args.destination)
