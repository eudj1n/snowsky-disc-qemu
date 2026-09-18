"""Installer preserves device settings and verifies all downloaded bytes."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.disc_assistant import launcher, speech_setup
from research.disc_assistant.assistant.config import load


class SpeechSetupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / 'config.toml'
        self.path.write_text(f'# custom settings\n[device]\nkey="fixture"\nhost="127.0.0.1"\ntcp_port=12345\n'
                             f'[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="en"\n')

    def test_download_is_verified_repeatable_and_does_not_replace_unknown_bytes(self):
        entry = {'file': 'model.bin', 'url': 'https://fixture.invalid/model', 'sha256': hashlib.sha256(b'fixture').hexdigest()}
        with patch.object(speech_setup.urllib.request, 'urlopen', return_value=io.BytesIO(b'fixture')) as fetch:
            speech_setup.download(entry, self.root)
            speech_setup.download(entry, self.root)
            fetch.assert_called_once()
        (self.root / 'model.bin').write_bytes(b'unknown')
        with self.assertRaises(ValueError):
            speech_setup.download(entry, self.root)
        self.assertEqual((self.root / 'model.bin').read_bytes(), b'unknown')
        (self.root / 'model.bin').unlink()
        with patch.object(speech_setup.urllib.request, 'urlopen', return_value=io.BytesIO(b'corrupt')):
            with self.assertRaises(ValueError):
                speech_setup.download(entry, self.root)
        self.assertFalse((self.root / 'model.bin').exists())
        self.assertFalse(list(self.root.glob('*.part-*')))

    def test_install_preserves_config_and_comments_with_private_backup(self):
        try:
            import tomlkit
        except ImportError:
            self.skipTest('optional setup --all config editor')
        original = self.path.read_bytes()
        (self.root / 'data/speech/piper').mkdir(parents=True)
        with patch.object(speech_setup, 'download') as download, patch.object(speech_setup.subprocess, 'run') as run, \
                patch.object(launcher, 'environment', return_value={}), redirect_stdout(io.StringIO()):
            speech_setup.install(self.path, model='base')
            first = self.path.read_bytes()
            speech_setup.install(self.path, model='base')
        self.assertEqual(self.path.read_bytes(), first)
        backups = list(self.root.glob('config.toml.before-speech-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertIn('# custom settings', self.path.read_text())
        config = load(self.path)
        self.assertEqual((config.device_key, config.tcp_port, config.locale), ('fixture', 12345, 'en'))
        self.assertEqual(config.speech['backend'], 'server')
        self.assertTrue(config.services['speech'])
        self.assertEqual(set(config.tts['models']), {'ru', 'en'})
        self.assertFalse(any('up' in call.args[0] for call in run.call_args_list))
        self.assertFalse(any(call.args[0]['file'] == 'ggml-small.bin' for call in download.call_args_list))

    def test_external_service_is_not_silently_managed(self):
        with self.assertRaises(ValueError):
            speech_setup.manage(load(self.path), 'up')

    def test_all_setup_installs_optional_dependencies_then_speech(self):
        with patch.object(launcher.subprocess, 'run') as run, patch.object(launcher, 'initialize'), \
                patch.object(speech_setup, 'install') as install:
            self.assertEqual(launcher.main(['--config', str(self.path), 'setup', '--all', '--whisper-model', 'small']), 0)
        install.assert_called_once_with(self.path.resolve(), model='small')
        self.assertEqual(run.call_count, 2)
        self.assertTrue(run.call_args.args[0][-1].endswith('requirements-speech.txt'))
