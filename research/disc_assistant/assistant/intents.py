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


def parse(text, rules=None):
    if not isinstance(text, str) or not 1 <= len(text) <= 1000 or any(ord(c) < 32 for c in text):
        raise ValueError('command must contain 1..1000 characters without control characters')
    rules = rules if rules is not None else load_languages()
    match = rules.prefix('commands', unicodedata.normalize('NFC', text).strip())
    if not match:
        raise ValueError('supported play prefixes: ' + ', '.join(phrase for phrase, _ in rules.commands))
    _, query = match
    kind = 'auto'
    explicit = rules.prefix('targets', query)
    if explicit:
        kind, query = explicit
    parts = re.split(r'\s+[—–-]\s+', query, maxsplit=1) if kind != 'artist' else [query]
    if len(parts) == 2:
        return Intent(query, 'track', parts[0].strip(), parts[1].strip())
    return Intent(query, kind)


def names(canonical, aliases):
    return {normalized(s) for s in [canonical, *aliases.get(canonical, [])]}
