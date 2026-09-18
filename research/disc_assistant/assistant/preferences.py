"""Persistent Assistant preferences, separate from catalog snapshots and secrets."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3

from research.disc_assistant.assistant.languages import LOCALES, load_languages


class Preferences:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / 'assistant.sqlite3'
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        self.db = sqlite3.connect(self.path, timeout=10)
        try:
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f'unsupported assistant database version {version}')
            if version == 0:
                self.db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                    PRAGMA user_version=1;
                    COMMIT;
                ''')
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def languages(self):
        row = self.db.execute("SELECT value_json FROM settings WHERE key='language.enabled'").fetchone()
        if row is None:
            return None
        try:
            return load_languages(json.loads(row[0])).enabled
        except ValueError as exc:
            raise ValueError('invalid saved command languages; use language reset') from exc

    def set_languages(self, enabled):
        enabled = load_languages(enabled).enabled  # Validate before writing anything.
        with self.db:
            self.db.execute('''INSERT INTO settings(key,value_json) VALUES('language.enabled',?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''', (json.dumps(enabled),))

    def reset_languages(self):
        with self.db:
            self.db.execute("DELETE FROM settings WHERE key='language.enabled'")


def effective_config(config):
    """Read a saved override when present; plain reads never create storage."""
    if not (config.data_dir / 'assistant.sqlite3').exists():
        return config
    with Preferences(config.data_dir) as preferences:
        enabled = preferences.languages()
    return replace(config, languages=enabled) if enabled is not None else config


def language_command(config, arguments=()):
    """Show/set command dictionaries, or remove the override and use TOML defaults."""
    arguments = tuple(arguments)
    if arguments and arguments != ('reset',):
        load_languages(arguments)
    if arguments:
        with Preferences(config.data_dir) as preferences:
            if arguments == ('reset',):
                preferences.reset_languages()
            else:
                preferences.set_languages(arguments)
    enabled = None
    if (config.data_dir / 'assistant.sqlite3').exists():
        with Preferences(config.data_dir) as preferences:
            enabled = preferences.languages()
    return {'enabled': list(enabled if enabled is not None else config.languages),
            'source': 'saved' if enabled is not None else 'config',
            'configured': list(config.languages),
            'available': sorted(path.stem for path in LOCALES.glob('*.toml'))}
