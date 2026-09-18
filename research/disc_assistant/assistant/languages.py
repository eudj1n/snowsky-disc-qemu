"""Validated literal dictionaries; the application selects one interaction locale."""
from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
import unicodedata

DEFAULT_LOCALE = 'ru'
DEFAULT_LANGUAGES = (DEFAULT_LOCALE,)
LOCALES = Path(__file__).with_name('locales')
SECTIONS = {
    'commands': {'play', 'pause', 'resume', 'stop', 'next', 'previous', 'set_language'},
    'targets': {'artist', 'track', 'album'},
    'versions': {'live', 'remix', 'acoustic', 'instrumental', 'demo', 'karaoke', 'cover', 'remaster'},
}


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def literal_pattern(phrase):
    return r'\s+'.join(re.escape(word) for word in phrase.split())


@dataclass(frozen=True)
class LanguageRules:
    enabled: tuple[str, ...]
    commands: tuple[tuple[str, str], ...]
    targets: tuple[tuple[str, str], ...]
    versions: tuple[tuple[str, str], ...]
    language_names: tuple[tuple[str, str], ...] = ()

    def prefix(self, section, text):
        """Return semantic key and untouched remainder; longest phrase wins."""
        for phrase, meaning in getattr(self, section):
            if section == 'commands' and meaning not in ('play', 'set_language'):
                continue
            match = re.fullmatch(literal_pattern(phrase) + r'\s+(.+)', text, re.IGNORECASE)
            if match:
                return meaning, match[1].strip()
        return None

    def version_parts(self, text):
        """Recognize whole literal phrases, returning markers and remaining text."""
        text = normalized(text)
        if not self.versions:
            return set(), text
        meanings = dict(self.versions)
        pattern = r'(?<!\w)(?:' + '|'.join(literal_pattern(p) for p, _ in self.versions) + r')(?!\w)'
        found = set()

        def remove(match):
            found.add(meanings[normalized(match[0])])
            return ' '

        rest = re.sub(pattern, remove, text)
        return found, ' '.join(rest.split())


def load_languages(enabled=DEFAULT_LANGUAGES, *, directory=LOCALES):
    if (not isinstance(enabled, (list, tuple)) or not enabled
            or any(not isinstance(code, str) or not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]+)*', code)
                   for code in enabled) or len(set(enabled)) != len(enabled)):
        raise ValueError('language dictionaries require unique, nonempty locale codes')
    merged = {section: {} for section in (*SECTIONS, 'language_names')}
    for code in enabled:
        path = Path(directory) / (code + '.toml')
        try:
            with path.open('rb') as stream:
                raw = tomllib.load(stream)
        except (OSError, ValueError) as exc:
            raise ValueError(f'cannot load language {code}: {exc}') from exc
        if not raw or set(raw) - merged.keys():
            raise ValueError(f'{code}: unknown or empty language sections')
        for section, table in raw.items():
            if (not isinstance(table, dict) or (section != 'language_names' and set(table) - SECTIONS[section])
                    or (section == 'language_names' and any(not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]+)*', key) for key in table))):
                raise ValueError(f'{code}: unknown meanings in [{section}]')
            for meaning, phrases in table.items():
                if not isinstance(phrases, list) or not phrases:
                    raise ValueError(f'{code}: {section}.{meaning} must be a nonempty list')
                for phrase in phrases:
                    if (not isinstance(phrase, str) or not phrase.strip() or phrase != phrase.strip()
                            or any(unicodedata.category(c).startswith('C') for c in phrase)):
                        raise ValueError(f'{code}: invalid phrase in {section}.{meaning}')
                    phrase = normalized(phrase)
                    previous = merged[section].get(phrase)
                    if previous is not None and previous != meaning:
                        raise ValueError(f'{code}: conflicting phrase {phrase!r} in [{section}]: {previous}/{meaning}')
                    merged[section][phrase] = meaning
    if 'play' not in merged['commands'].values():
        raise ValueError('enabled languages must define a play command')
    # Sorting also makes merging independent of configuration language order.
    return LanguageRules(tuple(enabled), *(tuple(sorted(mapping.items(), key=lambda item: (-len(item[0]), item[0])))
                                            for mapping in merged.values()))
