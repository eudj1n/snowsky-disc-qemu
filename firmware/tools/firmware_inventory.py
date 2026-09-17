#!/usr/bin/env python3
"""Read-only inventory of an unpacked SNOWSKY DISC OTA package (no guest execution).

Optionally verify the matching ZIP and stream-decrypt rootfs chunks into a digest,
without writing decrypted firmware. Run with the pinned Docker image for OpenSSL.
Manifest hashes detect corruption; this tool does NOT authenticate its signature.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

CHUNK = re.compile(r'rootfs\.squashfs\.(\d{4})\.([a-f0-9]{64})\.enc')
MANIFEST = re.compile(r'SHA256\(ota/(rootfs\.squashfs\.\d{4}\.[a-f0-9]{64}\.enc)\)= ([a-f0-9]{64})')


def digest_stream(stream):
    digest, size = hashlib.sha256(), 0
    while block := stream.read(1024 * 1024):
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def digest_file(path):
    with path.open('rb') as stream:
        return digest_stream(stream)


def versions(package):
    values = {}
    for line in (package / 'ota_config.in').read_text().splitlines():
        key, separator, value = line.strip().partition('=')
        if separator and key in ('current_version', 'recovery_version'):
            if key in values or not re.fullmatch(r'[1-9]\d{0,5}', value):
                raise ValueError('Invalid or duplicate OTA version')
            values[key] = int(value)
    if set(values) != {'current_version', 'recovery_version'}:
        raise ValueError('OTA version metadata missing')
    return values['current_version'], values['recovery_version']


def verified_chunks(directory):
    chunks, expected = {}, {}
    for path in directory.glob('rootfs.squashfs.*.enc'):
        match = CHUNK.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            raise ValueError('Invalid rootfs chunk')
        index = int(match[1])
        if index in chunks:
            raise ValueError('Duplicate rootfs chunk index')
        chunks[index] = path
    if not chunks or set(chunks) != set(range(len(chunks))):
        raise ValueError('Rootfs chunk indices must be contiguous from zero')
    for line in (directory / 'manifest.sha256').read_text().splitlines():
        match = MANIFEST.fullmatch(line)
        if match:
            if match[1] in expected:
                raise ValueError('Duplicate rootfs manifest entry')
            expected[match[1]] = match[2]
    if set(expected) != {path.name for path in chunks.values()}:
        raise ValueError('Rootfs manifest entries do not match package files')
    for path in chunks.values():
        if digest_file(path)[0] != expected[path.name]:
            raise ValueError(f'Encrypted chunk checksum mismatch: index {CHUNK.fullmatch(path.name)[1]}')
    return [chunks[index] for index in range(len(chunks))], expected


def verify_archive(archive, package, main, expected):
    found, configs = set(), []
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            path = Path(entry.filename)
            if path.name == 'ota_config.in':
                if entry.file_size > 65536:
                    raise ValueError('Oversized archive configuration')
                configs.append(source.read(entry))
            if len(path.parts) < 3 or path.parts[-3:-1] != ('main_os', f'ota_v{main}'):
                continue
            if not CHUNK.fullmatch(path.name):
                continue
            if path.name in found or path.name not in expected or entry.file_size > 4 * 1024 * 1024:
                raise ValueError('Invalid, duplicate or oversized archive chunk')
            with source.open(entry) as chunk:
                if digest_stream(chunk)[0] != expected[path.name]:
                    raise ValueError('Archive and unpacked rootfs chunks differ')
            found.add(path.name)
    if found != set(expected) or configs != [(package / 'ota_config.in').read_bytes()]:
        raise ValueError('Archive and unpacked package differ')


def plaintext_digest(chunks, output=None):
    digest, size, magic = hashlib.sha256(), 0, b''
    for path in chunks:
        command = ['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-iter', '10000',
                   '-k', 'fo123', '-in', str(path)]
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            while block := process.stdout.read(1024 * 1024):
                if not magic:
                    magic = block[:4]
                digest.update(block)
                size += len(block)
                if output is not None:
                    output.write(block)
            if process.wait():
                raise ValueError('OpenSSL could not decrypt a rootfs chunk')
    if magic != b'hsqs':
        raise ValueError('Decrypted payload is not a little-endian SquashFS image')
    return {'sha256': digest.hexdigest(), 'size': size}


def inventory(package, archive=None, decrypt_rootfs=False):
    package = Path(package)
    main, recovery = versions(package)
    chunks, expected = verified_chunks(package / 'main_os' / f'ota_v{main}')
    result = {
        'schema_version': 1,
        'version': f'{main // 100}.{main % 100:02d}',
        'main_os_version': main,
        'recovery_os_version': recovery,
        'rootfs_chunks': len(chunks),
        'encrypted_rootfs_manifest_checked': True,
        'manifest_signature_verified': False,
        'firmware_executed': False,
    }
    if archive:
        archive = Path(archive)
        verify_archive(archive, package, main, expected)
        sha, size = digest_file(archive)
        result['archive'] = {'sha256': sha, 'size': size, 'matches_unpacked_rootfs': True}
    if decrypt_rootfs:
        result['rootfs'] = plaintext_digest(chunks)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path, help='unpacked package containing ota_config.in')
    parser.add_argument('--archive', type=Path, help='also verify/hash the original ZIP')
    parser.add_argument('--decrypt-rootfs', action='store_true', help='hash plaintext in memory; never execute it')
    args = parser.parse_args()
    print(json.dumps(inventory(args.package, args.archive, args.decrypt_rootfs), indent=2))
