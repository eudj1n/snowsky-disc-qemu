from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.disc_assistant import launcher
from research.disc_assistant.assistant.__main__ import main
from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.console import Application
from research.disc_assistant.assistant.preferences import Preferences, effective_config, language_command, response_command


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'config.toml'
        self.path.write_text(f'[device]\nkey="test"\nhost="127.0.0.1"\n'
                             f'[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="en"\n')
        self.config = load(self.path)

    def invoke(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = main(['--config', str(self.path), *arguments])
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def legacy(self, **settings):
        with Preferences(self.config.data_dir) as preferences, preferences.db:
            for key, value in settings.items():
                preferences.write(key, value)

    def test_startup_persists_default_without_changing_config_or_catalog(self):
        original = self.path.read_bytes()
        self.assertFalse(self.config.data_dir.exists())
        self.assertEqual(effective_config(self.config).locale, 'en')
        self.assertEqual(effective_config(replace(self.config, locale='ru')).locale, 'en')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.config.data_dir / 'library.sqlite3').exists())
        self.assertEqual((self.config.data_dir / 'assistant.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_explicit_startup_override_persists_and_reset_uses_config(self):
        self.assertEqual(effective_config(self.config, language='ru').locale, 'ru')
        self.assertEqual(effective_config(self.config).locale, 'ru')
        self.assertEqual(self.invoke('--language', 'en', 'rank', 'Pause')[0], 0)
        self.assertEqual(effective_config(self.config).locale, 'en')
        self.assertEqual(language_command(self.config, ['reset'])['locale'], 'en')

    def test_single_language_changes_both_commands_and_responses(self):
        app = Application(self.config)
        self.assertEqual(app.request('/rank Pause')['action'], 'pause')
        changed = app.request('/language ru')
        self.assertEqual(changed['response']['language'], 'ru')
        self.assertEqual(changed['response']['code'], 'language.changed')
        self.assertEqual(app.request('/rank Пауза')['action'], 'pause')
        with self.assertRaises(ValueError):
            app.request('/rank Pause')
        changed = app.request('Переключи язык на английский')
        self.assertEqual(changed['response']['language'], 'en')
        self.assertEqual(Application(self.config).request('/language')['locale'], 'en')
        app.request('Switch language to русский')
        self.assertEqual(app.config.locale, 'ru')
        with self.assertRaises(ValueError):
            app.request('/language ru en')

    def test_invalid_locale_does_not_replace_saved_value(self):
        language_command(self.config, ['ru'])
        for args in (['zz'], ['../en'], ['ru', 'en'], ['reset', 'en']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                language_command(self.config, args)
            self.assertEqual(language_command(self.config)['locale'], 'ru')

    def test_legacy_input_takes_precedence_over_reply_and_first_list_entry_wins(self):
        self.legacy(**{'language.enabled': ['ru', 'en'], 'response.preferences': {'language': 'en', 'mode': 'all'}})
        active = effective_config(self.config)
        self.assertEqual((active.locale, active.response_mode), ('ru', 'all'))
        with Preferences(self.config.data_dir) as preferences:
            keys = {row[0] for row in preferences.db.execute('SELECT key FROM settings')}
        self.assertEqual(keys, {'language.locale', 'response.mode'})
        self.assertEqual(effective_config(self.config), active)

    def test_legacy_reply_locale_is_used_only_without_input_setting(self):
        self.legacy(**{'response.preferences': {'language': 'ru', 'mode': 'none'}})
        self.assertEqual(effective_config(self.config).locale, 'ru')

    def test_migration_is_atomic_and_recovery_does_not_clear_other_preferences(self):
        self.legacy(**{'language.enabled': ['ru', 'en'], 'response.preferences': {'language': 'en', 'mode': 'bad'}, 'other': True})
        with self.assertRaises(ValueError):
            effective_config(self.config)
        with Preferences(self.config.data_dir) as preferences:
            self.assertIsNone(preferences.read('language.locale'))
            self.assertEqual(preferences.read('language.enabled'), ['ru', 'en'])
        self.assertEqual(self.invoke('response', 'reset')[0], 0)
        self.assertEqual(effective_config(self.config).locale, 'ru')
        language_command(self.config, ['reset'])
        with Preferences(self.config.data_dir) as preferences:
            self.assertTrue(preferences.read('other'))

    def test_corrupt_saved_locale_can_be_reset(self):
        effective_config(self.config)
        with Preferences(self.config.data_dir) as preferences, preferences.db:
            preferences.db.execute("UPDATE settings SET value_json='broken' WHERE key='language.locale'")
        self.assertEqual(self.invoke('language', 'reset')[0], 0)
        self.assertEqual(effective_config(self.config).locale, 'en')

    def test_response_mode_cannot_change_locale(self):
        language_command(self.config, ['ru'])
        self.assertEqual(response_command(self.config, ['mode', 'all'])['locale'], 'ru')
        with self.assertRaisesRegex(ValueError, '/language'):
            response_command(self.config, ['language', 'en'])
        response_command(self.config, ['reset'])
        self.assertEqual(effective_config(self.config).locale, 'ru')

    def test_rank_language_intent_is_dry_run_and_ask_applies_it_without_search(self):
        result = self.invoke('rank', 'Switch language to Russian')[1]
        self.assertEqual(result['action'], 'set_language')
        self.assertEqual(effective_config(self.config).locale, 'en')
        result = self.invoke('ask', 'Switch language to Russian')[1]
        self.assertEqual(result['response']['language'], 'ru')
        self.assertEqual(self.invoke('rank', 'Пауза')[0], 0)

    def test_new_config_locale_overrides_legacy_fields(self):
        self.path.write_text(self.path.read_text().replace('locale="en"', 'locale="en"\nenabled=["ru"]') +
                             '\n[response]\nlanguage="ru"\nmode="none"\n')
        self.assertEqual(load(self.path).locale, 'en')
        self.assertEqual(load(self.path).response_mode, 'none')

    def test_unknown_database_version_is_not_overwritten(self):
        effective_config(self.config)
        with Preferences(self.config.data_dir) as preferences:
            preferences.db.execute('PRAGMA user_version=99')
        with self.assertRaisesRegex(ValueError, 'unsupported assistant database version'):
            effective_config(self.config)

    def test_launcher_rejects_unknown_locale_before_starting_services(self):
        with patch.object(launcher.subprocess, 'run') as run, redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(['--config', str(self.path), '--language', 'missing', 'start']), 1)
        run.assert_not_called()

    def test_launcher_forwards_locale_without_interpreting(self):
        with patch.object(launcher, 'environment', side_effect=ValueError('no search key')), \
                patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(launcher.main(['--config', str(self.path), '--language', 'ru', 'rank', 'Пауза']), 0)
            self.assertEqual(run.call_args.args[0][-4:], ['--language', 'ru', 'rank', 'Пауза'])
