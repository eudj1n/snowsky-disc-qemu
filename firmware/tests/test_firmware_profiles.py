import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from firmware.profile import PROFILES, available_versions, apply_key_patch, identify_player, load_profile, patch_state, validate
from firmware.tools.firmware_extract import extract
from firmware.tools.firmware_inventory import plaintext_digest


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = bytearray(512)
        self.data[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<H', self.data, 18, 8)
        struct.pack_into('<I', self.data, 28, 52)
        struct.pack_into('<HH', self.data, 42, 32, 1)
        struct.pack_into('<8I', self.data, 52, 1, 128, 0x500000, 0, 384, 384, 5, 4)
        self.data[256:260] = bytes.fromhex('41004292')
        self.profile = {'product': 'SNOWSKY_DISC', 'main_os_version': 257, 'recovery_os_version': 18,
                        'binaries': {'usr/bin/mq_player': hashlib.sha256(self.data).hexdigest()},
                        'key_patch': {'offset': '0x100', 'address': '0x500080',
                                      'before': '41004292', 'after': '01000224'}}
        self.binary = self.root / 'usr/bin/mq_player'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(self.data)
        meta = self.root / 'etc/product_version/version.in'
        meta.parent.mkdir(parents=True)
        meta.write_text('PRODUCT=SNOWSKY_DISC\nMAIN_OS_VER=257\nRECOVERY_OS_VER=18\n')

    def test_exact_build_patch_and_idempotency(self):
        validate(self.root, self.profile)
        self.assertTrue(apply_key_patch(self.binary, self.profile))
        validate(self.root, self.profile)
        self.assertFalse(apply_key_patch(self.binary, self.profile))
        self.assertEqual(self.binary.read_bytes()[:256], self.data[:256])
        self.assertEqual(self.binary.read_bytes()[260:], self.data[260:])

    def test_diagnostic_detection_accepts_only_full_stock_or_permitted_patch(self):
        self.profile.update(version='2.57', diagnostics={})
        other = {**self.profile, 'binaries': {'usr/bin/mq_player': '0' * 64}}
        with patch('firmware.profile.load_profile', side_effect=lambda v: self.profile if v == '2.57' else other):
            self.assertEqual(identify_player(self.data)['version'], '2.57')
            apply_key_patch(self.binary, self.profile)
            self.assertEqual(identify_player(self.binary.read_bytes())['version'], '2.57')
            with self.assertRaises(ValueError):
                identify_player(self.data, '2.40')
            self.data[400] ^= 1
            with self.assertRaises(ValueError):
                identify_player(self.data)

    def test_matching_short_anchor_is_not_enough(self):
        self.data[400] ^= 1
        self.binary.write_bytes(self.data)
        with self.assertRaises(ValueError):
            apply_key_patch(self.binary, self.profile)
        self.assertEqual(self.binary.read_bytes(), self.data)

    def test_modified_already_patched_binary_rejected(self):
        apply_key_patch(self.binary, self.profile)
        data = bytearray(self.binary.read_bytes())
        data[400] ^= 1
        with self.assertRaises(ValueError):
            patch_state(data, self.profile)

    def test_wrong_virtual_address_rejected(self):
        self.profile['key_patch']['address'] = '0x400100'
        with self.assertRaises(ValueError):
            patch_state(self.data, self.profile)

    def test_wrong_rootfs_version_rejected(self):
        self.profile['main_os_version'] = 240
        with self.assertRaises(ValueError):
            validate(self.root, self.profile)

    def test_unknown_profile_rejected(self):
        with patch('firmware.profile.PROFILES', self.root):
            for version in ('../../other', '2.99', '257'):
                with self.assertRaises(ValueError):
                    load_profile(version)

    def test_profiles_match_inventory(self):
        for version in available_versions():
            profile = load_profile(version)
            inventory = json.loads((PROFILES / f'inventory/v{version}.json').read_text())
            self.assertEqual(profile['rootfs_sha256'], inventory['rootfs']['sha256'])
            self.assertEqual(profile['rootfs_size'], inventory['rootfs']['size'])
            self.assertEqual(profile['rootfs_chunks'], inventory['rootfs_chunks'])
            for sha in profile['binaries'].values():
                self.assertRegex(sha, r'^[a-f0-9]{64}$')

    def test_extraction_never_overwrites_existing_directory(self):
        with self.assertRaises(ValueError):
            extract(self.root / 'missing', self.root, load_profile('2.57'))
        self.assertEqual(self.binary.read_bytes(), self.data)

    def test_invalid_chunks_never_reach_unsquashfs(self):
        with patch('firmware.tools.firmware_extract.subprocess.run') as run:
            with self.assertRaises(ValueError):
                extract(self.root, self.root / 'new', load_profile('2.57'))
            run.assert_not_called()

    def test_bad_plaintext_never_reaches_unsquashfs(self):
        (self.root / ('rootfs.squashfs.0000.' + 'a' * 64 + '.enc')).write_bytes(b'bad')
        profile = {**load_profile('2.57'), 'rootfs_chunks': 1}
        with patch('firmware.tools.firmware_extract.plaintext_digest', return_value={'sha256': 'bad', 'size': 0}), \
             patch('firmware.tools.firmware_extract.subprocess.run') as run:
            with self.assertRaises(ValueError):
                extract(self.root, self.root / 'new', profile)
            run.assert_not_called()
        self.assertFalse((self.root / 'new').exists())

    def test_successful_stream_decryption_matches_output(self):
        import subprocess
        source = b'hsqs' + bytes(range(256)) * 20
        chunks = []
        for index, block in enumerate((source[:3000], source[3000:])):
            result = subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-iter', '10000',
                                     '-k', 'fo123'], input=block, capture_output=True, check=True)
            path = self.root / f'chunk-{index}'
            path.write_bytes(result.stdout)
            chunks.append(path)
        output = io.BytesIO()
        self.assertEqual(plaintext_digest(chunks, output),
                         {'sha256': hashlib.sha256(source).hexdigest(), 'size': len(source)})
        self.assertEqual(output.getvalue(), source)

    def test_readme_keeps_decryption_details_in_internal_guide(self):
        readme = (PROFILES.parent / 'README.md').read_text()
        self.assertNotIn('fo' + '123', readme)
        self.assertIn('firmware/README.md', readme)
