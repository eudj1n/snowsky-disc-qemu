"""Resolve interpreted music references against catalog metadata; no input parsing."""
from research.disc_assistant.assistant.intents import Intent, names, normalized


def infer(intent, documents, aliases):
    if intent.kind != 'auto' or intent.artist is not None:
        return intent
    artists = sorted({d['artist'] for d in documents})
    q = normalized(intent.query)
    entries = [(alias, artist) for artist in artists for alias in names(artist, aliases.get('artists', {}))]
    if any(q == alias for alias, _ in entries):
        return Intent(intent.query, 'artist')
    # An exact standalone title takes precedence over a coincidental artist prefix.
    if any(q in names(d['title'], aliases.get('titles', {})) for d in documents):
        return Intent(intent.query, 'track')
    prefixes = [alias for alias, _ in entries if q.startswith(alias + ' ')]
    if prefixes:
        prefix = max(prefixes, key=lambda a: (len(a), a))
        return Intent(intent.query, 'track', prefix, q[len(prefix):].strip())
    return intent

