"""Localized user feedback over application outcomes; no transport or speech I/O."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from string import Formatter
import tomllib
import unicodedata

from research.disc_assistant.assistant.languages import LOCALES, SECTIONS, load_languages

REPLIES = LOCALES / 'replies'
DEFAULT_LANGUAGE = 'ru'
MODES = ('none', 'errors', 'all')
MAX_TEXT_LENGTH = 2000  # Matches the journal's retained string bound.
# This contract describes meanings and allowed parameters, never locale-specific text.
MESSAGE_FIELDS = {
    **{key: frozenset() for key in (
        'command.completed', 'command.not_sent', 'command.uncertain', 'command.interrupted',
        'command.unrecognized', 'command.error', 'search.unavailable', 'search.no_match',
        'catalog.stale', 'preferences.invalid', 'playback.paused', 'playback.already_paused',
        'playback.resumed', 'playback.already_playing', 'playback.stopped', 'playback.restarted')},
    'playback.started': frozenset(('title', 'artist')),
    'playback.track_changed': frozenset(('title', 'artist')),
}


def locale_code(code):
    if not isinstance(code, str) or not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]+)*', code):
        raise ValueError('locale code must be a lowercase language tag')
    return code


def load_reply_locale(code, *, directory=REPLIES):
    code = locale_code(code)
    try:
        with (Path(directory) / (code + '.toml')).open('rb') as stream:
            raw = tomllib.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError(f'cannot load response locale {code}') from exc
    if set(raw) != {'locale', 'messages'} or not isinstance(raw['locale'], dict):
        raise ValueError(f'{code}: expected locale and messages tables')
    metadata, messages = raw['locale'], raw['messages']
    if (set(metadata) != {'code', 'name', 'native_name'} or metadata['code'] != code
            or any(not isinstance(value, str) or not value.strip()
                   or any(unicodedata.category(c).startswith('C') for c in value)
                   for value in metadata.values())):
        raise ValueError(f'{code}: invalid locale metadata')
    if not isinstance(messages, dict) or set(messages) != set(MESSAGE_FIELDS):
        raise ValueError(f'{code}: response keys must match MESSAGE_FIELDS exactly')
    for key, template in messages.items():
        if (not isinstance(template, str) or not template.strip() or len(template) > 1000
                or any(unicodedata.category(c).startswith('C') for c in template)):
            raise ValueError(f'{code}: invalid template {key}')
        try:
            fields = set()
            for _, field, spec, conversion in Formatter().parse(template):
                if field is not None:
                    if field not in MESSAGE_FIELDS[key] or spec or conversion:
                        raise ValueError('unsupported field, conversion or format specifier')
                    fields.add(field)
            if fields != MESSAGE_FIELDS[key]:
                raise ValueError('missing template parameters')
        except ValueError as exc:
            raise ValueError(f'{code}: invalid parameters in {key}: {exc}') from exc
    return raw


def available_reply_languages(*, directory=REPLIES):
    return sorted(path.stem for path in Path(directory).glob('*.toml'))


def validate_response_preferences(language, mode):
    load_reply_locale(language)
    if mode not in MODES:
        raise ValueError('response mode must be none, errors or all')
    return {'language': language, 'mode': mode}


def validate_locales(codes=(), *, directory=LOCALES):
    directory = Path(directory)
    codes = tuple(codes) or tuple(sorted({p.stem for p in directory.glob('*.toml')} |
                                        {p.stem for p in (directory / 'replies').glob('*.toml')}))
    if not codes:
        raise ValueError('no locale files found')
    result = []
    for code in codes:
        rules = load_languages((locale_code(code),), directory=directory)
        for section, required in SECTIONS.items():
            if {meaning for _, meaning in getattr(rules, section)} != required:
                raise ValueError(f'{code}: incomplete {section} dictionary')
        raw = load_reply_locale(code, directory=directory / 'replies')
        result.append(dict(raw['locale'], response_count=len(raw['messages'])))
    load_languages(codes, directory=directory)  # Catch cross-locale phrase conflicts too.
    return {'locales': result, 'status': 'validated'}


@dataclass(frozen=True)
class UserResponse:
    code: str
    text: str | None
    language: str
    speak: bool
    interactive: bool = False  # Reserved contract. No pending dialogue is created.


def message_for(result, command, failure=None):
    status = result.get('status')
    if status == 'uncertain':
        return 'command.uncertain', {}, True
    if status == 'not_sent':
        return 'command.not_sent', {}, True
    if status == 'interrupted':
        return 'command.interrupted', {}, True
    if status == 'error':
        code = {'unrecognized_or_invalid_command': 'command.unrecognized',
                'invalid_preference': 'preferences.invalid',
                'search_unavailable_or_invalid': 'search.unavailable',
                'stale_index_or_catalog': 'catalog.stale'}.get(failure, 'command.error')
        return code, {}, True
    if status == 'not_found':
        return 'search.no_match', {}, True
    if command != 'ask':
        return 'system.no_message', {}, False
    action = result.get('action')
    if status in ('confirmed', 'already_satisfied'):
        if action == 'pause':
            return ('playback.already_paused' if status == 'already_satisfied' else 'playback.paused'), {}, False
        if action == 'resume':
            return ('playback.already_playing' if status == 'already_satisfied' else 'playback.resumed'), {}, False
        if action == 'stop':
            return 'playback.stopped', {}, False
        if result.get('outcome') == 'restarted':
            return 'playback.restarted', {}, False
    if status == 'playing' or (status == 'confirmed' and action in ('next', 'previous')):
        song = (result.get('state') or {}).get('song') or {}
        selected = result.get('selected') or {}
        title = song.get('song_name') or selected.get('title')
        artist = song.get('song_artist_name') or selected.get('artist')
        if isinstance(title, str) and title and isinstance(artist, str) and artist:
            clean = lambda text: ''.join(c for c in text if not unicodedata.category(c).startswith('C'))[:200]
            return ('playback.started' if status == 'playing' else 'playback.track_changed'), {
                'title': clean(title), 'artist': clean(artist)}, False
    if status in ('confirmed', 'already_satisfied', 'playing'):
        return 'command.completed', {}, False
    return 'system.no_message', {}, False


class Responses:
    def __init__(self, language, mode, *, directory=REPLIES):
        self.locale = load_reply_locale(language, directory=directory)
        if mode not in MODES:
            raise ValueError('response mode must be none, errors or all')
        self.language, self.mode = language, mode

    def context(self):
        return {'language': self.language, 'mode': self.mode, 'version': 1,
                'templates_sha256': hashlib.sha256(json.dumps(self.locale, sort_keys=True,
                    ensure_ascii=False).encode()).hexdigest()}

    def attach(self, result, *, command, source, failure=None):
        if result is None:
            return None
        code, values, problem = message_for(result, command, failure)
        text = None if code == 'system.no_message' else self.locale['messages'][code].format_map(values)
        if text is not None and len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH - 1] + '…'
        speak = bool(text and source not in ('scheduled', 'startup')
                     and (self.mode == 'all' or (self.mode == 'errors' and problem)))
        result['response'] = asdict(UserResponse(code, text, self.language, speak))
        return result


def attach_response(config, result, *, command='ask', source='interactive', failure=None):
    return Responses(config.response_language, config.response_mode).attach(
        result, command=command, source=source, failure=failure)


def exception_result(config, exc, *, source='interactive'):
    if hasattr(exc, 'assistant_result'):
        return exc.assistant_result
    # Errors outside a traced request (including journal failures) must not claim
    # that a possibly completed device operation failed or should be replayed.
    return attach_response(config, {'status': 'uncertain', 'error_type': type(exc).__name__}, source=source)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate contributed command and response locales.')
    parser.add_argument('codes', nargs='*', help='locale codes; omit to validate every discovered locale')
    args = parser.parse_args()
    try:
        print(json.dumps(validate_locales(args.codes), ensure_ascii=False, indent=2))
    except ValueError as exc:
        parser.exit(1, f'{exc}\n')
