"""Host setup must preserve explicit profiles when changing the firmware path."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class HostSetupTests(unittest.TestCase):
    def test_up_preserves_other_env_entries(self):
        for initial in ('# custom settings\nFW_VERSION=2.40\nWORK_VOLUME=legacy-work\nOTA_DIR=/old\nSTREAM_FPS=18', ''):
            with self.subTest(initial=bool(initial)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copyfile(Path(__file__).resolve().parents[2] / 'run.sh', root / 'run.sh')
                (root / '.env').write_text(initial)
                ota = root / 'firmware chunks'
                ota.mkdir()
                (ota / 'rootfs.squashfs.0000.test.enc').touch()
                commands = root / 'commands'
                commands.mkdir()
                docker = commands / 'docker'
                docker.write_text('#!/bin/sh\nexit 0\n')
                docker.chmod(0o755)
                subprocess.run(['bash', str(root / 'run.sh'), 'up', str(ota)], check=True,
                               env={**os.environ, 'PATH': str(commands) + ':' + os.environ['PATH']},
                               capture_output=True, text=True)
                rows = (root / '.env').read_text().splitlines()
                self.assertEqual([r for r in rows if r.startswith('OTA_DIR=')], ['OTA_DIR=' + str(ota)])
                if initial:
                    for expected in ('# custom settings', 'FW_VERSION=2.40', 'WORK_VOLUME=legacy-work', 'STREAM_FPS=18'):
                        self.assertIn(expected, rows)
