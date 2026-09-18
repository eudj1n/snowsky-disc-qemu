"""Play grammar with literal phrases supplied by language dictionaries."""
from dataclasses import dataclass
import re
import unicodedata

from research.disc_assistant.assistant.languages import load_languages, normalized


@dataclass(frozen=True)
class Intent:
    query: str
    kind: str = 'auto'
    artist: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class ControlIntent:
    action: str


@dataclass(frozen=True)
class LanguageIntent:
    locale: str


def language_target(text, rules):
    from research.disc_assistant.assistant.responses import available_reply_languages, load_reply_locale
    names = dict(rules.language_names)
    for code in available_reply_languages():
        try:
            metadata = load_reply_locale(code)['locale']
        except ValueError:
            continue  # /locales diagnoses unrelated incomplete contributions.
        for name in (code, metadata['name'], metadata['native_name']):
            names.setdefault(normalized(name), code)
    code = names.get(normalized(text))
    if code is None:
        raise ValueError('unknown language name; use /language CODE')
    return code


def parse(text, rules=None):
    if not isinstance(text, str) or not 1 <= len(text) <= 1000 or any(ord(c) < 32 for c in text):
        raise ValueError('command must contain 1..1000 characters without control characters')
    rules = rules if rules is not None else load_languages()
    for phrase, action in rules.commands:
        if action not in ('play', 'set_language') and normalized(text) == phrase:
            return ControlIntent(action)
    match = rules.prefix('commands', unicodedata.normalize('NFC', text).strip())
    if not match:
        raise ValueError('supported play prefixes: ' + ', '.join(phrase for phrase, _ in rules.commands))
    action, query = match
    if action == 'set_language':
        return LanguageIntent(language_target(query, rules))
    kind = 'auto'
    explicit = rules.prefix('targets', query)
    if explicit:
        kind, query = explicit
    return music_intent(query, kind)


def music_intent(query, kind='auto'):
    # Quotes delimit a literal music reference, including dashes/conjunctions.
    # Only balanced outer quotes are removed; punctuation inside names survives.
    quotes = {'"': '"', '«': '»', '“': '”'}
    if len(query) >= 2 and query[0] in quotes and query[-1] == quotes[query[0]]:
        value = query[1:-1].strip()
        if not value:
            raise ValueError('empty music reference')
        return Intent(value, kind)
    parts = re.split(r'\s+[—–-]\s+', query, maxsplit=1) if kind != 'artist' else [query]
    if len(parts) == 2:
        return Intent(query, 'track', parts[0].strip(), parts[1].strip())
    return Intent(query, kind)


def names(canonical, aliases):
    return {normalized(s) for s in [canonical, *aliases.get(canonical, [])]}
