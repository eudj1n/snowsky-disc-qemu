"""Persistent Assistant preferences, separate from catalog snapshots and secrets."""
from dataclasses import replace
import json
from pathlib import Path

from research.disc_assistant.assistant.database import connect
from research.disc_assistant.assistant.languages import LOCALES, load_languages
from research.disc_assistant.assistant.responses import available_reply_languages, validate_response_preferences


class Preferences:
    def __init__(self, directory):
        self.path = Path(directory) / 'assistant.sqlite3'
        self.db = connect(directory)

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

    def response(self):
        row = self.db.execute("SELECT value_json FROM settings WHERE key='response.preferences'").fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row[0])
            if not isinstance(value, dict) or set(value) != {'language', 'mode'}:
                raise ValueError('invalid response preferences')
            return validate_response_preferences(**value)
        except (ValueError, TypeError) as exc:
            raise ValueError('invalid saved response preferences; use response reset') from exc

    def set_response(self, language, mode):
        value = validate_response_preferences(language, mode)
        with self.db:
            self.db.execute("""INSERT INTO settings(key,value_json) VALUES('response.preferences',?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""", (json.dumps(value),))

    def reset_response(self):
        with self.db:
            self.db.execute("DELETE FROM settings WHERE key='response.preferences'")


def effective_config(config):
    """Read a saved override when present; plain reads never create storage."""
    if not (config.data_dir / 'assistant.sqlite3').exists():
        return config
    with Preferences(config.data_dir) as preferences:
        enabled = preferences.languages()
        response = preferences.response()
    return replace(config, languages=enabled if enabled is not None else config.languages,
                   response_language=response['language'] if response else config.response_language,
                   response_mode=response['mode'] if response else config.response_mode)


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


def response_command(config, arguments=()):
    """Persist output policy independently of accepted command languages."""
    args = tuple(arguments)
    if args and args != ('reset',) and not (len(args) == 2 and args[0] in ('language', 'mode')):
        raise ValueError('response: [language CODE | mode none|errors|all | reset]')
    configured = {'language': config.response_language, 'mode': config.response_mode}
    saved = None
    if args or (config.data_dir / 'assistant.sqlite3').exists():
        with Preferences(config.data_dir) as preferences:
            if args == ('reset',):
                preferences.reset_response()
            saved = preferences.response()
            if args and args != ('reset',):
                updated = dict(saved or configured)
                updated[args[0]] = args[1]
                preferences.set_response(**updated)
                saved = updated
    return dict(saved or configured, source='saved' if saved else 'config',
                configured=configured, available=available_reply_languages())
