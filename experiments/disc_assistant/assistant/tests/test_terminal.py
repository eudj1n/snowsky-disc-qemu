from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from experiments.disc_assistant.assistant.config import Config
from experiments.disc_assistant.assistant.journal import Trace, Journal, console_history, history_command
from experiments.disc_assistant.assistant.nlu.languages import load_languages
from experiments.disc_assistant.assistant.terminal import Terminal, CommandCompleter
from experiments.disc_assistant.assistant import console


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Config('fixture', 'localhost', 1, 1, Path(self.tmp.name),
                             'localhost', 1, 'http', 'UNUSED', {})

    def record(self, text, *, config=None, source='interactive'):
        command = text.split()[0][1:] if text.startswith('/') else 'ask'
        with Trace(config or self.config, command, text, source=source) as trace:
            trace.finish({'status': 'completed'})

    def terminal(self, pipe, *, config=None):
        return Terminal(config or self.config, load_languages,
                        input=pipe, output=DummyOutput())

    def test_recall_is_device_scoped_bounded_and_respects_retention(self):
        self.record('Play Old')
        with Journal(self.config) as journal, journal.db:
            journal.db.execute("UPDATE requests SET started_at='2000-01-01T00:00:00+00:00'")
        self.record('Play Other', config=replace(self.config, device_key='other'))
        self.record('Play Scheduled', source='scheduled')
        self.record('Play CLI', source='cli')
        self.record('Play ' + 'X' * 4000)
        self.record('Play First')
        self.record('Play Second')
        self.assertEqual(console_history(self.config), ['Play First', 'Play Second'])
        self.assertEqual(console_history(replace(self.config, journal_max_requests=1)), ['Play Second'])
        self.assertEqual(console_history(replace(self.config, journal_enabled=False)), [])

    def test_history_excludes_screen_commands_and_control_characters(self):
        for text in ('/clear', '/exit', '/history', 'Play\nPause', 'Play\x1b[2J'):
            self.record(text)
        self.assertEqual(console_history(self.config), [])

    def test_up_recalls_previous_session_and_clear_removes_recall(self):
        self.record('Включи Fixture')
        with create_pipe_input() as pipe:
            terminal = self.terminal(pipe)
            pipe.send_text('\x1b[A\r')
            self.assertEqual(terminal.read(), 'Включи Fixture')
            result = history_command(self.config, ['clear', '--yes'])
            terminal.after_command('/history clear --yes', result)
            pipe.send_text('\x1b[A/status\r')
            self.assertEqual(terminal.read(), '/status')

    def test_disabled_journal_keeps_only_session_history(self):
        config = replace(self.config, journal_enabled=False)
        with create_pipe_input() as pipe:
            terminal = self.terminal(pipe, config=config)
            pipe.send_text('Pause\r')
            self.assertEqual(terminal.read(), 'Pause')
            pipe.send_text('\x1b[A\r')
            self.assertEqual(terminal.read(), 'Pause')
        self.assertFalse((self.config.data_dir / 'assistant.sqlite3').exists())

    def test_completion_tracks_language_changes_and_nested_arguments(self):
        rules = load_languages(['en'])
        completer = CommandCompleter(lambda: rules)
        def options(text):
            return [c.text for c in completer.get_completions(Document(text), CompleteEvent())]
        self.assertEqual(options('/sta'), ['/status'])
        self.assertEqual(options('/dev'), ['/device'])
        self.assertEqual(options('/deb'), ['/debug'])
        self.assertEqual(options('/debug o'), ['off', 'on'])
        self.assertIn('ru', options('/language '))
        self.assertNotIn('ru', options('/language ru '))
        self.assertEqual(options('/history pr'), ['prune'])
        self.assertEqual(options('па'), [])
        rules = load_languages(['ru'])
        self.assertIn('пауза', options('па'))
        self.assertEqual(options('play'), [])

    def test_ctrl_r_tab_ctrl_l_cancel_and_eof_use_real_key_processing(self):
        self.record('Play Fixture')
        with create_pipe_input() as pipe:
            terminal = self.terminal(pipe)
            pipe.send_text('\x12Fixture\r\r')
            self.assertEqual(terminal.read(), 'Play Fixture')
            # Completion runs asynchronously; Enter follows completion, as when typing.
            def enter_after_completion():
                deadline = time.monotonic() + 2
                while terminal.session.default_buffer.text != '/status' and time.monotonic() < deadline:
                    time.sleep(.01)
                pipe.send_text('\r')
            worker = threading.Thread(target=enter_after_completion)
            worker.start()
            pipe.send_text('/sta\t')
            self.assertEqual(terminal.read(), '/status')
            worker.join(3)
            pipe.send_text('Pause\x0c\r')
            self.assertEqual(terminal.read(), 'Pause')
            pipe.send_text('Discard this\x03')
            with self.assertRaises(KeyboardInterrupt):
                terminal.read()
            pipe.send_text('\x04')
            with self.assertRaises(EOFError):
                terminal.read()

    def test_screen_clear_preserves_history(self):
        self.record('Play Fixture')
        with create_pipe_input() as pipe, patch('experiments.disc_assistant.assistant.terminal.clear') as clear:
            terminal = self.terminal(pipe)
            self.assertTrue(terminal.after_command('/clear', {'status': 'clear_screen'}))
            clear.assert_called_once()
        self.assertEqual(console_history(self.config), ['Play Fixture'])

    def test_console_cancels_input_but_interrupt_during_execution_exits(self):
        app = Mock(config=self.config)
        app.status.return_value = {}
        app.request.side_effect = [{'status': 'clear_screen'}, {'status': 'exit'}]
        terminal = Mock()
        terminal.read.side_effect = [KeyboardInterrupt, '/clear', '/exit']
        with patch.object(console, 'Application') as factory, \
                patch('experiments.disc_assistant.assistant.terminal.Terminal', return_value=terminal), \
                patch.object(console.sys.stdin, 'isatty', return_value=True), \
                patch.object(console.sys.stdout, 'isatty', return_value=True), \
                patch.dict('os.environ', {'TERM': 'xterm'}):
            factory.return_value.__enter__.return_value = app
            console.run(self.config, output=Mock())
            self.assertEqual([c.args[0] for c in app.request.call_args_list], ['/clear', '/exit'])
            terminal.read.side_effect = ['Pause']
            app.request.side_effect = KeyboardInterrupt
            console.run(self.config, output=Mock())
            self.assertEqual(terminal.read.call_count, 4)

    def test_redirected_console_emits_no_terminal_escape_and_creates_no_editor(self):
        app = Mock(config=self.config)
        app.status.return_value = {}
        app.request.side_effect = [{'status': 'clear_screen'}, {'status': 'exit'}]
        output = []
        with patch.object(console, 'Application') as factory, \
                patch('experiments.disc_assistant.assistant.terminal.Terminal') as editor, \
                patch.object(console.sys.stdin, 'isatty', return_value=False), \
                patch('builtins.input', side_effect=['/clear', '/exit']):
            factory.return_value.__enter__.return_value = app
            console.run(self.config, output=output.append)
        editor.assert_not_called()
        self.assertNotIn('\x1b', ''.join(output))
        self.assertIn('clear_screen', ''.join(output))

    def test_help_is_multiline_in_terminal_and_json_in_pipe(self):
        for tty in (True, False):
            with self.subTest(tty=tty):
                app = Mock(config=self.config)
                app.status.return_value = {}
                app.request.side_effect = [{'help': 'First line\nSecond line', 'request_id': 'fixture'},
                                           {'status': 'exit'}]
                output = []
                with patch.object(console, 'Application') as factory, \
                        patch.object(console.sys.stdin, 'isatty', return_value=tty), \
                        patch.object(console.sys.stdout, 'isatty', return_value=tty):
                    factory.return_value.__enter__.return_value = app
                    console.run(self.config, input_fn=Mock(side_effect=['/help', '/exit']), output=output.append)
                if tty:
                    self.assertIn('First line\nSecond line', output)
                else:
                    self.assertIn('First line\\nSecond line', ''.join(output))
