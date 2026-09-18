"""Terminal editing only; all commands still pass through Application.request."""
import os
import shlex
import sqlite3

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import SimpleLexer
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import clear
from prompt_toolkit.styles import Style

from research.disc_assistant.assistant.journal import console_history, recallable
from research.disc_assistant.assistant.responses import MODES, available_reply_languages

COMMANDS = ('/connect', '/disconnect', '/device', '/status', '/queue', '/sync', '/index',
            '/search', '/rank', '/explain', '/commands', '/ask', '/transcribe', '/language', '/response', '/locales', '/help', '/history', '/debug', '/clear', '/exit')

DEFAULT_STYLES = {
    'prompt': 'ansicyan bold',
    'input': 'ansiyellow',
    'result': 'ansigreen',
    'error': 'ansired bold',
    'warning': 'ansiyellow bold',
    'debug': 'ansibrightblack',
    'suggestion': 'ansibrightblack italic',
}


class CommandCompleter(Completer):
    def __init__(self, rules):
        self.rules = rules

    def get_completions(self, document, complete_event):
        if document.text_after_cursor:
            return
        text = document.text_before_cursor.lstrip()
        prefix = text
        if text.startswith('/debug '):
            prefix = text[len('/debug '):]
            options = ('on', 'off')
        elif text.startswith('/language '):
            prefix = text[len('/language '):]
            options = available_reply_languages() + ['reset']
        elif text.startswith('/response '):
            parts = text[len('/response '):].split(' ')
            prefix = parts[-1]
            if len(parts) == 1:
                options = ('mode', 'reset')
            elif len(parts) == 2 and parts[0] == 'mode':
                options = MODES
            else:
                options = ()
        elif text.startswith('/history '):
            prefix = text[len('/history '):]
            options = ('show', 'export', 'prune', 'clear')
        elif text.startswith('/'):
            options = COMMANDS
        else:
            options = [phrase for phrase, _ in self.rules().commands]
        for option in sorted(set(options)):
            if option.casefold().startswith(prefix.casefold()):
                yield Completion(option, start_position=-len(prefix))


class RecallHistory(InMemoryHistory):
    def append_string(self, string):
        if recallable(string):
            super().append_string(string)


class Terminal:
    def __init__(self, config, rules, **session_options):
        self.config = config
        self.history_error_reported = False
        self.history = RecallHistory()
        colors = config.terminal.get('color', True) and not os.environ.get('NO_COLOR')
        styles = {key: config.terminal.get(key, value) for key, value in DEFAULT_STYLES.items()}
        styles['auto-suggestion'] = styles.pop('suggestion')
        self.style = Style.from_dict(styles if colors else {})
        self.color_depth = None if colors else ColorDepth.DEPTH_1_BIT
        self.session = PromptSession(history=self.history, completer=CommandCompleter(rules),
            auto_suggest=AutoSuggestFromHistory(), complete_while_typing=False,
            style=self.style, color_depth=self.color_depth, lexer=SimpleLexer('class:input'),
            **session_options)

    def write(self, text, role='result'):
        # Plain text fragments, never HTML/ANSI interpretation of device metadata.
        print_formatted_text(FormattedText([(f'class:{role}', text)]), style=self.style,
                             color_depth=self.color_depth, output=self.session.app.output)

    def read(self):
        # Refresh after every completed command, including journal clear/prune.
        # The journal already stores submitted input and applies its retention.
        strings = self.history.get_strings()[-1000:]
        if self.config.journal_enabled:
            try:
                strings = console_history(self.config)
            except (OSError, ValueError, sqlite3.Error):
                if not self.history_error_reported:
                    self.write('Saved input history unavailable; using session history.', 'warning')
                    self.history_error_reported = True
        self.history = RecallHistory(strings)
        self.session.history = self.history
        self.session.default_buffer.history = self.history
        with patch_stdout():
            return self.session.prompt([('class:prompt', f'{self.config.device_key}> ')])

    def after_command(self, line, result):
        if result and result.get('status') == 'clear_screen':
            clear()
            return True
        if result and 'removed' in result and shlex.split(line.strip()) == ['/history', 'clear', '--yes']:
            self.history = RecallHistory()
        return False
