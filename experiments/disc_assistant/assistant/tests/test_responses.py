"""Response contracts, contributed locales and application/journal parity."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from prompt_toolkit.document import Document

from experiments.disc_assistant.assistant import __main__ as cli
from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.console import Application
from experiments.disc_assistant.assistant.nlu.intents import parse
from experiments.disc_assistant.assistant.journal import Trace, JournalWriteError, history_command
from experiments.disc_assistant.assistant.nlu.languages import LOCALES, load_languages
from experiments.disc_assistant.assistant.preferences import effective_config, language_command, response_command, Preferences
from experiments.disc_assistant.assistant.responses import (
    REPLIES, Responses, exception_result, load_reply_locale, validate_locales,
)
from experiments.disc_assistant.assistant.terminal import CommandCompleter


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'config.toml'
        self.path.write_text(f'[device]\nkey="test"\nhost="127.0.0.1"\n'
                             f'[storage]\ndata_dir="{self.root}/data"\n')
        self.config = load(self.path)

    def invoke(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            status = cli.main(['--config', str(self.path), *arguments])
        return status, json.loads(output.getvalue()) if output.getvalue() else None

    def reply(self, result, mode='errors', language='en', **kwargs):
        return Responses(language, mode).attach(result, command=kwargs.pop('command', 'ask'),
            source=kwargs.pop('source', 'interactive'), **kwargs)['response']

    def test_confirmed_and_already_satisfied_controls_have_precise_silent_replies(self):
        for action, status, expected in (
                ('pause', 'confirmed', 'playback.paused'),
                ('pause', 'already_satisfied', 'playback.already_paused'),
                ('resume', 'confirmed', 'playback.resumed'),
                ('resume', 'already_satisfied', 'playback.already_playing'),
                ('stop', 'confirmed', 'playback.stopped')):
            with self.subTest(action=action, status=status):
                reply = self.reply({'status': status, 'action': action})
                self.assertEqual(reply['code'], expected)
                self.assertIsInstance(reply['text'], str)
                self.assertFalse(reply['speak'])
                self.assertFalse(reply['interactive'])
        self.assertIn('queue and position', self.reply({'status': 'confirmed', 'action': 'stop'})['text'])

    def test_navigation_restart_is_not_announced_as_another_track(self):
        reply = self.reply({'status': 'confirmed', 'action': 'previous', 'outcome': 'restarted'})
        self.assertEqual(reply['code'], 'playback.restarted')

    def test_playing_uses_observed_metadata_and_sanitizes_controls(self):
        reply = self.reply({'status': 'playing', 'selected': {'title': 'Selected', 'artist': 'Wrong'},
            'state': {'song': {'song_name': 'Numb\x1b', 'song_artist_name': 'Linkin Park\n'}}})
        self.assertEqual(reply['text'], 'Playing Numb — Linkin Park.')
        self.assertEqual(self.reply({'status': 'playing'})['code'], 'command.completed')
        self.assertEqual(self.reply({'status': 'confirmed', 'action': 'next',
            'state': {'song': {'song_name': 'Numb', 'song_artist_name': 'Linkin Park'}}})['code'],
            'playback.track_changed')

    def test_uncertain_is_never_localized_as_success_even_with_selected_track(self):
        for language in ('ru', 'en'):
            reply = self.reply({'status': 'uncertain', 'action': 'pause',
                'selected': {'title': 'Numb', 'artist': 'Linkin Park'}}, language=language)
            self.assertEqual(reply['code'], 'command.uncertain')
            self.assertTrue(reply['speak'])
            self.assertNotIn('Numb', reply['text'])

    def test_policy_is_separate_from_text_and_scheduled_work_is_silent(self):
        for mode in ('none', 'errors', 'all'):
            for status in ('confirmed', 'uncertain', 'not_sent', 'not_found', 'interrupted', 'error'):
                for source in ('interactive', 'cli', 'scheduled', 'startup'):
                    reply = self.reply({'status': status, 'action': 'pause'}, mode, source=source)
                    expected = source in ('cli', 'interactive') and (mode == 'all' or
                        (mode == 'errors' and status != 'confirmed'))
                    self.assertEqual(reply['speak'], expected, (mode, status, source))
                    self.assertTrue(reply['text'])
                    self.assertFalse(reply['interactive'])
        reply = self.reply({'status': 'planned'}, 'all', command='rank')
        self.assertEqual(reply['code'], 'system.no_message')
        self.assertIsNone(reply['text'])
        self.assertFalse(reply['speak'])

    def test_error_categories_have_distinct_localized_messages(self):
        for category, code in (('unrecognized_or_invalid_command', 'command.unrecognized'),
                ('invalid_preference', 'preferences.invalid'),
                ('search_unavailable_or_invalid', 'search.unavailable'),
                ('stale_index_or_catalog', 'catalog.stale'), ('execution_error', 'command.error')):
            self.assertEqual(self.reply({'status': 'error'}, failure=category)['code'], code)

    def test_locale_and_speech_policy_survive_restart_and_reset_independently(self):
        self.assertEqual(response_command(self.config)['source'], 'saved')
        self.assertTrue(self.config.data_dir.exists())
        original = self.path.read_bytes()
        language_command(self.config, ['ru'])
        language_command(self.config, ['en'])
        response_command(self.config, ['mode', 'all'])
        config = effective_config(load(self.path))
        self.assertEqual((config.locale, config.response_mode), ('en', 'all'))
        self.assertEqual(self.path.read_bytes(), original)
        response_command(self.config, ['reset'])
        self.assertEqual(effective_config(self.config).response_mode, 'errors')
        self.assertEqual(effective_config(self.config).locale, 'en')

    def test_invalid_preferences_do_not_replace_saved_values_and_corruption_is_resettable(self):
        language_command(self.config, ['en'])
        for args in (['mode', 'yes'], ['language', '../en'], ['language', 'xx'], ['unknown']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                response_command(self.config, args)
            self.assertEqual(language_command(self.config)['locale'], 'en')
        with Preferences(self.config.data_dir) as preferences:
            with preferences.db:
                preferences.db.execute("UPDATE settings SET value_json='broken' WHERE key='response.mode'")
        with self.assertRaisesRegex(ValueError, 'response reset'):
            effective_config(self.config)
        status, result = self.invoke('response', 'reset')
        self.assertEqual(status, 0)
        self.assertEqual(result['locale'], 'en')

    def test_cli_preference_commands_use_saved_reply_language_even_for_invalid_settings(self):
        self.invoke('language', 'en')
        self.assertEqual(self.invoke('language')[1]['response']['language'], 'en')
        code, result = self.invoke('response', 'mode', 'invalid')
        self.assertEqual(code, 1)
        self.assertEqual(result['response']['language'], 'en')
        self.assertEqual(result['response']['code'], 'preferences.invalid')

    def test_config_validates_reply_language_policy_and_reserved_dialogue(self):
        base = self.path.read_text()
        for section in ('[response]\nlanguage="missing"', '[response]\nmode="yes"',
                        '[response]\nunknown=true', '[dialogue]\nenabled=true', '[dialogue]\nenabled=0'):
            self.path.write_text(base + section)
            with self.subTest(section=section), self.assertRaises(ValueError):
                load(self.path)
        self.path.write_text(base + '[response]\nlanguage="en"\nmode="none"\n[dialogue]\nenabled=false\n')
        self.assertEqual(load(self.path).locale, 'en')
        self.assertFalse(load(self.path).dialogue_enabled)

    def test_console_and_cli_share_reply_and_journal_template_provenance(self):
        app = Application(self.config)
        app.request('/language en')
        app.request('/response mode all')
        control = {'status': 'confirmed', 'action': 'pause', 'mutation_attempted': True}
        app.device_call = Mock(return_value=dict(control))
        console_result = app.request('Pause')
        with patch.object(cli, 'control', return_value=dict(control)) as device:
            code, cli_result = self.invoke('ask', 'Pause')
        self.assertEqual(code, 0)
        device.assert_called_once()
        self.assertEqual(console_result['response'], cli_result['response'])
        self.assertTrue(console_result['response']['speak'])
        for result in (console_result, cli_result):
            record = history_command(self.config, ['show', result['request_id']])
            self.assertEqual(record['outcome']['response'], result['response'])
            self.assertEqual(record['context']['response'], Responses('en', 'all').context())
        reopened = Application(self.config)
        self.assertEqual(reopened.config.locale, 'en')
        self.assertEqual(reopened.request('/language reset')['response']['language'], 'ru')

    def test_errors_are_localized_and_journaled_without_raw_exception_text(self):
        language_command(self.config, ['en'])
        app = Application(self.config)
        with self.assertRaises(ValueError) as caught:
            app.request('unrecognized-private-marker')
        reply = exception_result(app.config, caught.exception)
        self.assertEqual(reply['response']['code'], 'command.unrecognized')
        code, result = self.invoke('ask', 'unrecognized-private-marker')
        self.assertEqual(code, 1)
        self.assertEqual(reply['response'], result['response'])
        with self.assertRaises(RuntimeError) as caught:
            with Trace(app.config, 'ask', 'Pause') as trace:
                trace.event('execution_started', {})
                raise RuntimeError('secret-server-body')
        result = exception_result(app.config, caught.exception)
        record = history_command(self.config, ['show', result['request_id']])
        self.assertNotIn('secret-server-body', json.dumps(record))
        self.assertEqual(result['response']['code'], 'command.error')

    def test_disabled_journal_still_generates_replies_and_interruption(self):
        config = replace(self.config, journal_enabled=False)
        with Trace(config, 'ask', 'Pause') as trace:
            result = trace.finish({'status': 'confirmed', 'action': 'pause'})
        self.assertEqual(result['response']['code'], 'playback.paused')
        self.assertEqual(result['request_id'], trace.id)
        with self.assertRaises(KeyboardInterrupt) as caught:
            with Trace(config, 'ask', 'Pause') as trace:
                trace.event('execution_started', {})
                raise KeyboardInterrupt()
        self.assertEqual(exception_result(config, caught.exception)['response']['code'], 'command.interrupted')
        self.assertFalse(config.data_dir.exists())

    def test_journal_failure_is_uncertain_and_does_not_request_replay(self):
        with self.assertRaises(JournalWriteError) as caught:
            with Trace(self.config, 'ask', 'Pause') as trace:
                trace.event('execution_started', {})
                trace.journal.db.execute('PRAGMA query_only=ON')
                trace.finish({'status': 'confirmed', 'action': 'pause'})
        result = exception_result(self.config, caught.exception)
        self.assertEqual(result['response']['code'], 'command.uncertain')
        self.assertFalse(result['response']['interactive'])

    def test_builtin_locales_are_complete_and_have_distinct_hashes(self):
        self.assertTrue({'en', 'ru'} <= {locale['code'] for locale in validate_locales()['locales']})
        self.assertNotEqual(Responses('en', 'all').context()['templates_sha256'],
                            Responses('ru', 'all').context()['templates_sha256'])

    def contributed(self):
        directory = self.root / 'locales'
        (directory / 'replies').mkdir(parents=True)
        (directory / 'fr.toml').write_text((LOCALES / 'en.toml').read_text().replace('play = ["play"]', 'play = ["mets"]'))
        (directory / 'replies/fr.toml').write_text((REPLIES / 'en.toml').read_text()
            .replace('code = "en"', 'code = "fr"').replace('Playback paused.', 'Lecture en pause.'))
        return directory

    def test_added_locale_is_discovered_validated_parsed_and_rendered_without_registry_edits(self):
        directory = self.contributed()
        self.assertEqual(validate_locales(directory=directory)['locales'][0]['code'], 'fr')
        self.assertEqual(parse('mets Numb', load_languages(('fr',), directory=directory)).query, 'Numb')
        reply = Responses('fr', 'all', directory=directory / 'replies').attach(
            {'status': 'confirmed', 'action': 'pause'}, command='ask', source='cli')['response']
        self.assertEqual(reply['text'], 'Lecture en pause.')
        with patch('experiments.disc_assistant.assistant.terminal.available_reply_languages', return_value=['fr']):
            completions = CommandCompleter(lambda: load_languages()).get_completions(Document('/language '), None)
            self.assertEqual([item.text for item in completions], ['fr', 'reset'])

    def test_expanded_text_is_bounded_to_journal_retention(self):
        directory = self.contributed()
        path = directory / 'replies/fr.toml'
        path.write_text(path.read_text().replace('Playing {title} — {artist}.', '{title}' * 30 + '{artist}'))
        response = Responses('fr', 'all', directory=path.parent).attach(
            {'status': 'playing', 'selected': {'title': 't' * 200, 'artist': 'a' * 200}},
            command='ask', source='cli')['response']
        self.assertEqual(len(response['text']), 2000)
        self.assertTrue(response['text'].endswith('…'))

    def test_invalid_templates_and_incomplete_locales_fail_before_execution(self):
        directory = self.contributed()
        path = directory / 'replies/fr.toml'
        valid = path.read_text()
        for replacement in ('{title.__class__}', '{title[0]}', '{title!r}', '{title:>20}', '{other}', '{title', ''):
            path.write_text(valid.replace('{title}', replacement))
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                load_reply_locale('fr', directory=path.parent)
        for text in (valid.replace('"command.completed"', '"unknown.code"'),
                     valid.replace('code = "fr"', 'code = "en"'),
                     valid + '\n[extra]\nx=1\n'):
            path.write_text(text)
            with self.assertRaises(ValueError):
                validate_locales(directory=directory)
        path.write_text(valid)
        (directory / 'fr.toml').write_text('[commands]\nplay=["mets"]\n')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            validate_locales(directory=directory)
        for code in ('../en', '', 'EN', 'ru/en'):
            with self.assertRaises(ValueError):
                load_reply_locale(code)
        path.unlink()
        with self.assertRaises(ValueError):
            load_reply_locale('fr', directory=path.parent)

    def test_response_completion_offers_only_valid_policy_values(self):
        completer = CommandCompleter(lambda: load_languages())
        options = [c.text for c in completer.get_completions(Document('/response mode '), None)]
        self.assertEqual(options, ['all', 'errors', 'none'])


if __name__ == '__main__':
    unittest.main()
