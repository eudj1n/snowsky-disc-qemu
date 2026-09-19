from contextlib import redirect_stdout, redirect_stderr
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

    def test_launcher_forwards_commands_when_search_credentials_are_unavailable(self):
        self.initialize()
        self.env_file.write_text('invalid secret file')
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)), \
                patch.object(launcher, 'environment', side_effect=ValueError('search key missing')):
            for command in ('ask', 'rank', 'explain'):
                self.assertEqual(launcher.main(['--config', str(self.config), command, 'Пауза']), 0)

    def test_start_runs_up_then_one_console_process_and_listen_skips_docker(self):
        self.initialize()
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                patch.object(launcher, 'wait_ready') as ready:
            self.assertEqual(launcher.main(['--config', str(self.config), 'start']), 0)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0][-2:], ['up', '-d'])
            self.assertEqual(run.call_args_list[1].args[0][-1], 'start')
            ready.assert_called_once()
            run.reset_mock()
            ready.reset_mock()
            self.assertEqual(launcher.main(['--config', str(self.config), 'listen']), 0)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-1], 'listen')
            ready.assert_not_called()

    def test_web_defaults_to_existing_services_and_bootstrap_prepares_search(self):
        self.initialize()
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                patch.object(launcher, 'wait_ready') as ready:
            self.assertEqual(launcher.main(['--config', str(self.config), 'web', '--port', '8092']), 0)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-3:], ['web', '--port', '8092'])
            ready.assert_not_called()
            run.reset_mock()
            self.assertEqual(launcher.main(['--config', str(self.config), 'web', '--bootstrap']), 0)
            self.assertEqual(run.call_count, 2)
            ready.assert_called_once()

    def test_failed_search_startup_still_launches_console(self):
        self.initialize()
        with patch.object(launcher.subprocess, 'run', side_effect=[OSError('docker unavailable'), Mock(returncode=0)]) as run:
            self.assertEqual(launcher.main(['--config', str(self.config), 'start']), 0)
            self.assertEqual(run.call_args.args[0][-1], 'start')

    def test_io_compat_selects_wrapper_only_when_explicit_and_preserves_project(self):
        self.initialize()
        config = load(self.config)
        stock = launcher.compose_command('up', '-d', config=config)
        self.assertNotIn(str(launcher.PACKAGE / 'assistant/compose.io-compat.yaml'), stock)
        self.config.write_text(self.config.read_text().replace('io_accounting_compat = false',
                                                              'io_accounting_compat = true'))
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                patch.object(launcher, 'wait_ready'):
            self.assertEqual(launcher.main(['--config', str(self.config), 'web', '--bootstrap']), 0)
            command = run.call_args_list[0].args[0]
            self.assertIn(str(launcher.PACKAGE / 'assistant/compose.io-compat.yaml'), command)
            self.assertEqual(command[command.index('-p') + 1], 'disc-assistant')
            self.assertEqual(run.call_count, 2)
        for value in ('"yes"', '1'):
            self.config.write_text(self.config.read_text().replace('io_accounting_compat = true',
                                                                  f'io_accounting_compat = {value}'))
            with self.assertRaisesRegex(ValueError, 'must be a boolean'):
                load(self.config)
            self.config.write_text(self.config.read_text().replace(f'io_accounting_compat = {value}',
                                                                  'io_accounting_compat = true'))
        self.config.write_text(self.config.read_text().replace('protocol = "http"', 'protocol = "https"'))
        with self.assertRaisesRegex(ValueError, 'managed local'):
            load(self.config)

    def test_search_timeout_explains_compatibility_without_preventing_controls(self):
        self.initialize()
        with patch.object(launcher.urllib.request, 'urlopen', side_effect=OSError('unavailable')):
            with self.assertRaises(launcher.SearchReadinessError) as failure:
                launcher.wait_ready(load(self.config), timeout=0)
        self.assertIn('/proc/self/io', str(failure.exception))
        output = io.StringIO()
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                patch.object(launcher, 'wait_ready', side_effect=failure.exception), redirect_stderr(output):
            self.assertEqual(launcher.main(['--config', str(self.config), 'web', '--bootstrap']), 0)
        self.assertIn('typesense.io_accounting_compat', output.getvalue())
        self.assertEqual(run.call_count, 2)
        self.assertNotIn('TYPESENSE_API_KEY', run.call_args.kwargs['env'])

    def test_console_interrupt_exits_without_launcher_traceback(self):
        self.initialize()
        with patch.object(launcher.subprocess, 'run', side_effect=KeyboardInterrupt):
            self.assertEqual(launcher.main(['--config', str(self.config), 'listen']), 130)

    def test_rejected_input_and_missing_search_key_reach_application_journal(self):
        self.initialize()
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=1)) as run, \
                patch.object(launcher, 'environment', side_effect=ValueError('missing key')):
            self.assertEqual(launcher.main(['--config', str(self.config), 'ask', 'unrecognized input']), 1)
            self.assertEqual(run.call_args.args[0][-2:], ['ask', 'unrecognized input'])
            self.assertEqual(launcher.main(['--config', str(self.config), '--source', 'scheduled', 'ask', 'Play Numb']), 1)
            self.assertEqual(run.call_args.args[0][-4:], ['--source', 'scheduled', 'ask', 'Play Numb'])
            self.assertNotIn('TYPESENSE_API_KEY', run.call_args.kwargs['env'])

    def test_down_needs_no_config_and_keeps_volumes(self):
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(launcher.main(['--config', str(self.config), 'down']), 0)
        args = run.call_args.args[0]
        self.assertIn('disc-assistant', args)
        self.assertEqual(args[-1], 'down')
        self.assertNotIn('--volumes', args)

    def test_benchmark_bypasses_application_search_and_device(self):
        self.initialize()
        with patch('research.disc_assistant.experiments.speech_benchmark.main', return_value=0) as benchmark, \
                patch.object(launcher, 'environment', side_effect=AssertionError('no search credentials')), \
                patch.object(launcher.subprocess, 'run', side_effect=AssertionError('no app or compose startup')):
            self.assertEqual(launcher.main(['--config', str(self.config), 'speech-benchmark',
                                           '--audio', 'sample.wav', '--output', 'report']), 0)
        self.assertEqual(benchmark.call_args.args[0], ['--audio', 'sample.wav', '--output', 'report'])

    def test_shell_help_works_from_outside_repository(self):
        script = launcher.PACKAGE / 'run.sh'
        result = subprocess.run(['bash', str(script), '--help'], cwd=self.directory, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('setup', result.stdout)
        self.assertIn('search QUERY', result.stdout)

    def test_debug_is_forwarded_before_application_command(self):
        self.initialize()
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(launcher.main(['--config', str(self.config), '--debug', 'rank', 'Pause']), 0)
        self.assertEqual(run.call_args.args[0][-3:], ['--debug', 'rank', 'Pause'])
