import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from firmware.tools.firmware_inventory import inventory, verified_chunks, versions, plaintext_digest


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / 'package'
        self.ota = self.package / 'main_os/ota_v257'
        self.ota.mkdir(parents=True)
        (self.package / 'ota_config.in').write_text('current_version=257\nrecovery_version=18\n')
        self.chunks = []
        records = []
        for index in range(2):
            path = self.ota / f'rootfs.squashfs.{index:04d}.{"a" * 64}.enc'
            data = bytes([index]) * 32
            path.write_bytes(data)
            records.append(f'SHA256(ota/{path.name})= {hashlib.sha256(data).hexdigest()}')
            self.chunks.append(path)
        (self.ota / 'manifest.sha256').write_text('\n'.join(records))

    def archive(self, altered=False):
        archive = Path(self.temp.name) / 'package.zip'
        with zipfile.ZipFile(archive, 'w') as result:
            for path in self.package.rglob('*'):
                if path.is_file():
                    data = b'changed' if altered and path == self.chunks[0] else path.read_bytes()
                    result.writestr('vendor/' + path.relative_to(self.package).as_posix(), data)
        return archive

    def test_read_only_inventory_matches_zip(self):
        before = {p: p.read_bytes() for p in self.package.rglob('*') if p.is_file()}
        result = inventory(self.package, self.archive())
        self.assertEqual(result['version'], '2.57')
        self.assertEqual(result['recovery_os_version'], 18)
        self.assertEqual(result['rootfs_chunks'], 2)
        self.assertTrue(result['archive']['matches_unpacked_rootfs'])
        self.assertFalse(result['firmware_executed'])
        self.assertFalse(result['manifest_signature_verified'])
        self.assertNotIn('rootfs', result)
        self.assertNotIn(str(self.package), json.dumps(result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.package.rglob('*') if p.is_file()})

    def test_changed_archive_is_not_mislabeled_as_matching(self):
        with self.assertRaises(ValueError):
            inventory(self.package, self.archive(altered=True))

    def test_missing_chunk_is_rejected(self):
        self.chunks[0].unlink()
        with self.assertRaises(ValueError):
            verified_chunks(self.ota)

    def test_changed_encrypted_payload_is_rejected(self):
        self.chunks[0].write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            verified_chunks(self.ota)

    def test_duplicate_manifest_entry_is_rejected(self):
        path = self.ota / 'manifest.sha256'
        path.write_text(path.read_text() + '\n' + path.read_text().splitlines()[0])
        with self.assertRaises(ValueError):
            verified_chunks(self.ota)

    def test_invalid_version_is_not_used_as_a_path(self):
        (self.package / 'ota_config.in').write_text('current_version=../../other\nrecovery_version=18\n')
        with self.assertRaises(ValueError):
            versions(self.package)

    def test_bad_ciphertext_does_not_produce_a_plaintext_digest(self):
        with self.assertRaises(ValueError):
            plaintext_digest(self.chunks)
