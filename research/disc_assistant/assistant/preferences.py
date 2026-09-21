"""One durable interaction locale; speech policy is a separate preference."""
from dataclasses import replace
import json
from pathlib import Path

from research.disc_assistant.assistant.database import connect
from research.disc_assistant.assistant.nlu.languages import load_languages
from research.disc_assistant.assistant.responses import available_reply_languages, validate_locale, MODES


class Preferences:
    def __init__(self, directory):
        self.path = Path(directory) / 'assistant.sqlite3'
        self.db = connect(directory)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def read(self, key):
        row = self.db.execute('SELECT value_json FROM settings WHERE key=?', (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except ValueError as exc:
            raise ValueError(f'invalid saved setting {key}; use language reset or response reset') from exc

    def write(self, key, value):
        self.db.execute('''INSERT INTO settings(key,value_json) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            WHERE settings.value_json != excluded.value_json''', (key, json.dumps(value)))


def effective_config(config, *, language=None, reset_language=False, reset_response=False, mode=None):
    """Resolve and persist settings atomically, including legacy-key migration.

    Explicit startup language > saved locale > old input list's first locale >
    old reply locale > configured locale. A reset explicitly selects the config.
    Validation precedes every write, so failed migration preserves old settings.
    """
    if language is not None:
        validate_locale(language)
    if mode is not None and mode not in MODES:
        raise ValueError('response mode must be none, errors or all')
    with Preferences(config.data_dir) as preferences, preferences.db:
        preferences.db.execute('BEGIN IMMEDIATE')
        # A legacy response object bundled locale and mode. Resetting that object
        # must remain possible even if its JSON is corrupt.
        legacy_response = {} if reset_response else preferences.read('response.preferences')
        if legacy_response is None:
            legacy_response = {}
        if not isinstance(legacy_response, dict):
            raise ValueError('invalid saved response preferences; use response reset')
        selected = config.locale if reset_language else language
        if selected is None:
            selected = preferences.read('language.locale')
        if selected is None:
            legacy_languages = preferences.read('language.enabled')
            if legacy_languages is not None:
                selected = load_languages(legacy_languages).enabled[0]
        if selected is None:
            selected = legacy_response.get('language', config.locale)
        selected = validate_locale(selected)
        selected_mode = config.response_mode if reset_response else mode
        if selected_mode is None:
            selected_mode = preferences.read('response.mode')
        if selected_mode is None:
            selected_mode = legacy_response.get('mode', config.response_mode)
        if selected_mode not in MODES:
            raise ValueError('invalid saved response mode; use response reset')
        preferences.write('language.locale', selected)
        preferences.write('response.mode', selected_mode)
        preferences.db.execute("DELETE FROM settings WHERE key IN ('language.enabled','response.preferences')")
    return replace(config, locale=selected, response_mode=selected_mode)


def language_command(config, arguments=()):
    args = tuple(arguments)
    if len(args) > 1:
        raise ValueError('language accepts one locale: CODE or reset')
    active = effective_config(config, language=args[0] if args and args != ('reset',) else None,
                              reset_language=args == ('reset',))
    result = {'locale': active.locale, 'configured': config.locale, 'source': 'saved',
              'available': available_reply_languages()}
    if args:
        result.update(status='confirmed', action='set_language')
    return result


def response_command(config, arguments=()):
    args = tuple(arguments)
    if args and args != ('reset',) and not (len(args) == 2 and args[0] == 'mode'):
        raise ValueError('response: [mode none|errors|all | reset]; use /language CODE to change language')
    active = effective_config(config, mode=args[1] if len(args) == 2 else None,
                              reset_response=args == ('reset',))
    return {'locale': active.locale, 'mode': active.response_mode, 'configured': config.response_mode,
            'source': 'saved'}
