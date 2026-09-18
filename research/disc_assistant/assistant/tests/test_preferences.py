from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.disc_assistant import launcher
from research.disc_assistant.assistant.__main__ import main
from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.console import Application
from research.disc_assistant.assistant.preferences import Preferences, effective_config, language_command


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'config.toml'
        self.path.write_text(f'[device]\nkey="test"\nhost="127.0.0.1"\n'
                             f'[storage]\ndata_dir="{self.root}/data"\n'
                             '[language]\nenabled=["en"]\n')
        self.config = load(self.path)

    def test_unset_preferences_use_config_without_creating_storage(self):
        self.assertEqual(language_command(self.config)['enabled'], ['en'])
        self.assertEqual(language_command(self.config)['source'], 'config')
        self.assertEqual(effective_config(self.config), self.config)
        self.assertFalse(self.config.data_dir.exists())

    def test_saved_override_survives_reopen_without_modifying_toml_or_catalog(self):
        original = self.path.read_bytes()
        result = language_command(self.config, ['ru'])
        self.assertEqual(result['source'], 'saved')
        self.assertEqual(effective_config(load(self.path)).languages, ('ru',))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.config.data_dir / 'library.sqlite3').exists())
        self.assertEqual((self.config.data_dir / 'assistant.sqlite3').stat().st_mode & 0o777, 0o600)
        with Preferences(self.config.data_dir) as preferences:
            row = preferences.db.execute('SELECT key,value_json,updated_at FROM settings').fetchone()
            self.assertEqual(row[:2], ('language.enabled', '["ru"]'))
            self.assertTrue(row[2].endswith('Z'))

    def test_reset_restores_current_toml_defaults_and_preserves_other_settings(self):
        language_command(self.config, ['ru'])
        with Preferences(self.config.data_dir) as preferences:
            with preferences.db:
                preferences.db.execute("INSERT INTO settings(key,value_json) VALUES('future.setting','true')")
        updated = replace(self.config, languages=('ru', 'en'))
        self.assertEqual(language_command(updated, ['reset'])['enabled'], ['ru', 'en'])
        self.assertEqual(language_command(updated)['source'], 'config')
        with Preferences(self.config.data_dir) as preferences:
            self.assertIsNone(preferences.languages())
            self.assertEqual(preferences.db.execute('SELECT key FROM settings').fetchall(), [('future.setting',)])

    def test_invalid_language_does_not_replace_saved_selection(self):
        language_command(self.config, ['ru'])
        for invalid in (['zz'], ['../en'], ['ru', 'ru'], ['reset', 'en']):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                language_command(self.config, invalid)
            self.assertEqual(language_command(self.config)['enabled'], ['ru'])

    def test_unknown_database_version_is_not_overwritten(self):
        language_command(self.config, ['ru'])
        with sqlite3.connect(self.config.data_dir / 'assistant.sqlite3') as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaisesRegex(ValueError, 'unsupported assistant database version'):
            effective_config(self.config)
        with sqlite3.connect(self.config.data_dir / 'assistant.sqlite3') as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 99)

    def test_invalid_saved_value_can_be_reset_without_silent_fallback(self):
        language_command(self.config, ['ru'])
        with Preferences(self.config.data_dir) as preferences:
            with preferences.db:
                preferences.db.execute("UPDATE settings SET value_json='broken'")
        with self.assertRaisesRegex(ValueError, 'language reset'):
            effective_config(self.config)
        self.assertEqual(language_command(self.config, ['reset'])['enabled'], ['en'])

    def test_console_language_applies_immediately_and_next_session_reuses_it(self):
        app = Application(self.config)
        self.assertEqual(app.request('/rank Pause')['action'], 'pause')
        self.assertEqual(app.request('/language ru')['enabled'], ['ru'])
        self.assertEqual(app.request('/rank Пауза')['action'], 'pause')
        with self.assertRaises(ValueError):
            app.request('/rank Pause')
        with self.assertRaises(ValueError):
            app.request('Play Linkin Park')
        with self.assertRaises(ValueError):
            app.request('/language missing')
        self.assertEqual(app.request('/language')['enabled'], ['ru'])
        reopened = Application(self.config)
        self.assertEqual(reopened.request('/rank Продолжи')['action'], 'resume')
        reopened.request('/language ru en')
        self.assertEqual(reopened.request('/rank Resume')['action'], 'resume')
        reopened.request('/language reset')
        with self.assertRaises(ValueError):
            reopened.request('/rank Продолжи')

    def test_one_shot_language_and_rank_share_preferences_without_search_or_device(self):
        def invoke(*arguments):
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()), patch.dict('os.environ', {}, clear=True):
                code = main(['--config', str(self.path), *arguments])
            return code, json.loads(output.getvalue()) if output.getvalue() else None
        self.assertEqual(invoke('language', 'ru')[1]['enabled'], ['ru'])
        self.assertEqual(invoke('rank', 'Пауза')[1]['action'], 'pause')
        self.assertEqual(invoke('rank', 'Pause')[0], 1)
        self.assertEqual(invoke('language', 'reset')[1]['enabled'], ['en'])

    def test_launcher_uses_saved_languages_before_deciding_search_is_required(self):
        language_command(self.config, ['ru'])
        with patch.object(launcher, 'environment', side_effect=AssertionError('search used')), \
                patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(launcher.main(['--config', str(self.path), 'rank', 'Пауза']), 0)
            self.assertEqual(run.call_args.args[0][-2:], ['rank', 'Пауза'])
            self.assertEqual(launcher.main(['--config', str(self.path), 'language', 'ru', 'en']), 0)
            self.assertEqual(run.call_args.args[0][-3:], ['language', 'ru', 'en'])
