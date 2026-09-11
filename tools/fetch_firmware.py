#!/usr/bin/env python3
"""Fetch a private HTTPS URL without printing it; extract only V2.40 rootfs chunks.

The assembled/decrypted payload is authenticated by 00_extract_rootfs.sh before
unsquashfs or execution. ZIP wrapper/recovery/kernel contents are not trusted/used.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile

MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_CHUNK = 4 * 1024 * 1024
CHUNKS = 85
CHUNK = re.compile(r'(?:[^/]+/)*main_os/ota_v240/(rootfs\.squashfs\.(\d{4})\.[0-9a-fA-F]{64}\.enc)')


def https_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('An HTTPS URL without embedded credentials is required')
    return url


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, https_url(newurl))


def extract_chunks(archive, destination):
    destination = Path(destination)
    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError('Destination must be an existing empty directory')
    with zipfile.ZipFile(archive) as package:
        selected = {}
        for entry in package.infolist():
            match = CHUNK.fullmatch(entry.filename)
            if not match:
                continue
            index = int(match[2])
            if index in selected or entry.file_size > MAX_CHUNK:
                raise ValueError('Duplicate or oversized rootfs chunk')
            selected[index] = (entry, match[1])
        if set(selected) != set(range(CHUNKS)):
            raise ValueError('Expected exactly 85 V2.40 rootfs chunks')
        for entry, name in selected.values():
            # Flatten to a regex-validated basename; never extract archive paths/symlinks.
            with package.open(entry) as source, (destination / name).open('xb') as target:
                shutil.copyfileobj(source, target)


def fetch(url, destination):
    request = urllib.request.Request(https_url(url), headers={'User-Agent': 'diskos-qemu-ci'})
    opener = urllib.request.build_opener(HTTPSRedirect())
    with tempfile.TemporaryFile() as archive:
        with opener.open(request, timeout=60) as response:
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > MAX_DOWNLOAD:
                    raise ValueError('Download exceeds limit')
                archive.write(block)
        archive.seek(0)
        extract_chunks(archive, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    # Pop so any later subprocess cannot inherit the URL. Never render an exception
    # originating in urllib: even its message/traceback can contain a signed URL.
    url = os.environ.pop('FIRMWARE_V240_URL', '')
    if not url:
        parser.exit(1, 'FIRMWARE_V240_URL secret is missing\n')
    try:
        fetch(url, args.destination)
    except Exception:
        parser.exit(1, 'Firmware download/extraction failed (details suppressed to protect the URL)\n')
    print('Extracted 85 rootfs chunks; payload SHA-256 verification follows before unpacking.')


if __name__ == '__main__':
    main()
