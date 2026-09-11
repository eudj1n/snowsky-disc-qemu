import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fetch_firmware import CHUNKS, extract_chunks, https_url, main


def archive(indices=range(CHUNKS), extra=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as package:
        for index in indices:
            package.writestr(f'update/main_os/ota_v240/rootfs.squashfs.{index:04d}.{"a" * 64}.enc', b'test')
        if extra:
            package.writestr(*extra)
    data.seek(0)
    return data


class FirmwareCITests(unittest.TestCase):
    def test_only_expected_chunks_are_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            extract_chunks(archive(extra=('../../outside', b'bad')), directory)
            self.assertEqual(len(list(Path(directory).iterdir())), 85)
            self.assertTrue(all(p.name.startswith('rootfs.squashfs.') for p in Path(directory).iterdir()))

    def test_incomplete_archive_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                extract_chunks(archive(range(84)), directory)
            self.assertFalse(list(Path(directory).iterdir()))

    def test_duplicate_index_rejected(self):
        extra = ('other/main_os/ota_v240/rootfs.squashfs.0000.' + 'b' * 64 + '.enc', b'bad')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                extract_chunks(archive(extra=extra), directory)

    def test_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / 'keep'
            existing.write_bytes(b'user data')
            with self.assertRaises(ValueError):
                extract_chunks(archive(), directory)
            self.assertEqual(existing.read_bytes(), b'user data')

    def test_https_only_without_credentials(self):
        for url in ('http://example.com/file', 'file:///tmp/file', 'https://a:b@example.com/file'):
            with self.assertRaises(ValueError):
                https_url(url)
        self.assertEqual(https_url('https://example.com/?token=test'), 'https://example.com/?token=test')

    def test_download_errors_do_not_print_secret(self):
        output = io.StringIO()
        with patch('sys.argv', ['fetch', '/tmp/unused']), patch('sys.stderr', output), \
             patch.dict('os.environ', {'FIRMWARE_V240_URL': 'https://private.invalid/secret'}), \
             patch('fetch_firmware.fetch', side_effect=ValueError('https://private.invalid/secret')):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 1)
        self.assertNotIn('private.invalid', output.getvalue())
        self.assertNotIn('/secret', output.getvalue())

    def test_manifest_matches_extractor(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'firmware/v2.40.json').read_text())
        sha = re.search(r'ROOTFS_SHA256="([a-f0-9]+)"', (root / 'scripts/lib.sh').read_text())[1]
        self.assertEqual(manifest['rootfs_sha256'], sha)
        self.assertEqual(manifest['rootfs_chunks'], CHUNKS)
