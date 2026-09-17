from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

from research.disc_assistant import launcher
from research.disc_assistant.assistant.config import load


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.env_file = self.directory / '.env'
        self.config = self.directory / 'config.toml'
        p = patch.object(launcher, 'ENV_FILE', self.env_file)
        p.start()
        self.addCleanup(p.stop)

    def initialize(self):
        with redirect_stdout(io.StringIO()):
            launcher.initialize(self.config)

    def test_setup_is_repeatable_and_preserves_settings_and_key(self):
        self.initialize()
        self.config.write_text(self.config.read_text().replace('local-disc-emulator', 'physical'))
        before = (self.config.read_bytes(), self.env_file.read_bytes())
        self.initialize()
        self.assertEqual(before, (self.config.read_bytes(), self.env_file.read_bytes()))
        self.assertEqual(len(launcher.read_env(self.env_file)['TYPESENSE_API_KEY']), 64)
        self.assertEqual(self.env_file.stat().st_mode & 0o777, 0o600)

    def test_empty_template_gets_key_without_losing_other_settings(self):
        self.env_file.write_text('# keep me\nTYPESENSE_API_KEY=\nTYPESENSE_PORT=8109\n')
        self.initialize()
        values = launcher.read_env(self.env_file)
        self.assertEqual(values['TYPESENSE_PORT'], '8109')
        self.assertTrue(values['TYPESENSE_API_KEY'])
        self.assertIn('# keep me', self.env_file.read_text())

    def test_env_is_data_and_never_shell_code(self):
        target = self.directory / 'executed'
        self.env_file.write_text(f'TYPESENSE_API_KEY="$(touch {target})"\n')
        self.assertEqual(launcher.read_env(self.env_file)['TYPESENSE_API_KEY'], f'$(touch {target})')
        self.assertFalse(target.exists())
        for text in ('UNKNOWN=secret', 'TYPESENSE_API_KEY=one\nTYPESENSE_API_KEY=two', 'TYPESENSE_API_KEY="bad'):
            self.env_file.write_text(text)
            with self.assertRaises(ValueError):
                launcher.read_env(self.env_file)

    def test_toml_port_and_file_key_have_consistent_precedence(self):
        self.initialize()
        self.env_file.write_text('TYPESENSE_API_KEY=local\nTYPESENSE_PORT=8109\n')
        with patch.dict(os.environ, {'TYPESENSE_API_KEY': 'stale', 'TYPESENSE_PORT': '8111'}):
            env = launcher.environment(load(self.config))
        self.assertEqual(env['TYPESENSE_API_KEY'], 'local')
        self.assertEqual(env['TYPESENSE_PORT'], '8108')

    def test_search_forwards_cyrillic_as_one_argument_and_relative_config(self):
        self.initialize()
        with patch.dict(os.environ, {'DISC_ASSISTANT_CALLER_DIR': str(self.directory)}), \
                patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(launcher.main(['--config', 'config.toml', 'search', 'линкин парк намб', '--limit', '2']), 0)
        args = run.call_args.args[0]
        self.assertEqual(args[-4:], ['search', 'линкин парк намб', '--limit', '2'])
        self.assertEqual(Path(args[args.index('--config') + 1]), self.config.resolve())
        self.assertEqual(args[0], launcher.sys.executable)

    def test_up_uses_config_port_and_waits_only_after_compose_success(self):
        self.initialize()
        self.config.write_text(self.config.read_text().replace('port = 8108', 'port = 8123'))
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                patch.object(launcher, 'wait_ready') as ready:
            self.assertEqual(launcher.main(['--config', str(self.config), 'up']), 0)
            self.assertEqual(run.call_args.kwargs['env']['TYPESENSE_PORT'], '8123')
            self.assertEqual(run.call_args.args[0][-2:], ['up', '-d'])
            ready.assert_called_once()
            self.assertEqual(ready.call_args.args[0].search_port, 8123)

    def test_down_needs_no_config_and_keeps_volumes(self):
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(launcher.main(['--config', str(self.config), 'down']), 0)
        args = run.call_args.args[0]
        self.assertIn('disc-assistant', args)
        self.assertEqual(args[-1], 'down')
        self.assertNotIn('--volumes', args)

    def test_shell_help_works_from_outside_repository(self):
        script = launcher.PACKAGE / 'run.sh'
        result = subprocess.run(['bash', str(script), '--help'], cwd=self.directory, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('setup', result.stdout)
        self.assertIn('search QUERY', result.stdout)
