"""Installer preserves device settings and verifies all downloaded bytes."""
from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
import tempfile
import urllib.error
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
            context = fetch.call_args.kwargs['context']
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
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

    def test_public_roots_work_without_python_default_ca_store(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(empty.cert_store_stats()['x509_ca'], 0)
        with patch.object(speech_setup.ssl, 'create_default_context', return_value=empty), \
                patch.dict(os.environ, {'DISC_ASSISTANT_CA_BUNDLE': ''}):
            context = speech_setup.download_context()
        self.assertGreater(context.cert_store_stats()['x509_ca'], 0)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_custom_ca_bundle_is_loaded_and_invalid_paths_fail_closed(self):
        import certifi
        bundle = self.root / 'trusted-ca.pem'
        bundle.write_bytes(Path(certifi.where()).read_bytes())
        with patch.dict(os.environ, {'DISC_ASSISTANT_CA_BUNDLE': str(bundle)}):
            context = speech_setup.download_context()
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            bundle.write_text('invalid certificate')
            with self.assertRaisesRegex(ValueError, 'trusted PEM CA bundle'):
                speech_setup.download_context()

    def test_tls_failure_has_actionable_error_without_insecure_retry(self):
        entry = {'file': 'model.bin', 'url': 'https://fixture.invalid/model', 'sha256': 'unused'}
        failure = urllib.error.URLError(ssl.SSLCertVerificationError(1, 'untrusted test certificate'))
        with patch.object(speech_setup.urllib.request, 'urlopen', side_effect=failure) as fetch:
            with self.assertRaisesRegex(RuntimeError, 'DISC_ASSISTANT_CA_BUNDLE'):
                speech_setup.download(entry, self.root)
        fetch.assert_called_once()
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
        self.assertTrue(config.tts['models']['ru'].endswith('ru_RU-irina-medium.onnx'))
        voices = json.loads((self.root / 'data/speech/piper/voices.json').read_text())
        self.assertEqual(voices['ru'], '/models/ru_RU-irina-medium.onnx')
        self.assertFalse(any('up' in call.args[0] for call in run.call_args_list))
        self.assertFalse(any(call.args[0]['file'] == 'ggml-small.bin' for call in download.call_args_list))

    def test_voice_upgrade_preserves_installed_whisper_and_recreates_only_changed_mapping(self):
        try:
            import tomlkit
        except ImportError:
            self.skipTest('optional setup --all config editor')
        model = self.root / 'ggml-small.bin'
        model.write_bytes(b'operator installed STT model')
        with self.path.open('a') as stream:
            stream.write(f'[speech]\nmodel="{model}"\n')
        directory = self.root / 'data/speech/piper'
        directory.mkdir(parents=True)
        (directory / 'voices.json').write_text('{"ru":"/models/ru_RU-denis-medium.onnx"}')
        before = speech_setup.environment(load(self.path))
        with patch.object(speech_setup, 'download') as download, patch.object(speech_setup.subprocess, 'run'), \
                patch.object(launcher, 'environment', return_value={}), redirect_stdout(io.StringIO()):
            speech_setup.install(self.path)
            first = speech_setup.environment(load(self.path))
            speech_setup.install(self.path)
        config = load(self.path)
        self.assertEqual(config.speech['model'], str(model))
        self.assertEqual(model.read_bytes(), b'operator installed STT model')
        self.assertTrue(all(c.args[0]['file'].startswith('piper/') for c in download.call_args_list))
        self.assertNotEqual(before['DISC_PIPER_VOICES_SHA256'], first['DISC_PIPER_VOICES_SHA256'])
        self.assertEqual(first, speech_setup.environment(config))

    def test_whisper_selection_preserves_custom_models_and_requires_explicit_replacement(self):
        config = load(self.path)
        custom = self.root / 'custom.bin'
        custom.write_bytes(b'custom model')
        config = replace(config, speech={'model': str(custom)})
        self.assertEqual(speech_setup.selected_whisper(config, None), (custom, None))
        self.assertEqual(speech_setup.selected_whisper(config, 'small')[1], 'ggml-small.bin')
        custom.unlink()
        with self.assertRaisesRegex(ValueError, 'Configured Whisper model is missing'):
            speech_setup.selected_whisper(config, None)
        config = replace(config, speech={'model': str(self.root / 'ggml-small.bin')})
        self.assertEqual(speech_setup.selected_whisper(config, None)[1], 'ggml-small.bin')

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

    def test_launcher_does_not_implicitly_select_base(self):
        with patch.object(launcher.subprocess, 'run'), patch.object(launcher, 'initialize'), \
                patch.object(speech_setup, 'install') as install:
            self.assertEqual(launcher.main(['--config', str(self.path), 'setup', '--all']), 0)
        install.assert_called_once_with(self.path.resolve(), model=None)
