"""Deterministic lexical ranking. No invented history, likes or confidence values."""
from difflib import SequenceMatcher
import re

from research.disc_assistant.assistant.intents import Intent, parse, normalized, names
from research.disc_assistant.assistant.languages import load_languages
from research.disc_assistant.library.store import StaleSnapshot

def words(value):
    return re.findall(r'[^\W_]+', normalized(value))


def versions(value, rules):
    return rules.version_parts(value)[0]


def clean_title(value):
    return re.sub(r'\.(?:flac|mp3|wav|m4a|aac|ogg|dsf|dff)$', '', normalized(value))


def base_title(value, rules):
    value = clean_title(value)
    value = re.sub(r'\([^)]*\)|\[[^]]*\]', lambda m: '' if versions(m[0], rules) else m[0], value)
    parts = re.split(r'\s+[-–—]\s+', value, maxsplit=1)
    if len(parts) == 2 and versions(parts[1], rules):
        value = parts[0]
    return ' '.join(value.split())


def similarity(query, canonical, aliases=()):
    q = ' '.join(words(query))
    best = (0.0, 'none')
    for value, label in [(canonical, 'literal'), *((a, 'alias') for a in aliases)]:
        candidate = ' '.join(words(value))
        if not q or not candidate:
            continue
        score = 1.0 if q == candidate else SequenceMatcher(None, q, candidate, autojunk=False).ratio()
        if score > best[0]:
            best = (score, label if score == 1 else 'fuzzy_' + label)
    return best


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


def score_tracks(intent, documents, aliases, rules=None):
    rules = rules if rules is not None else load_languages()
    ranked = []
    requested_title = intent.title if intent.title is not None else intent.query
    requested_versions, query_core = rules.version_parts(clean_title(requested_title))
    for doc in documents:
        edition = versions(doc['title'], rules) | versions(doc['album'], rules)
        if requested_versions and not requested_versions <= edition:
            continue
        title_score, title_match = similarity(clean_title(requested_title), clean_title(doc['title']),
                                             aliases.get('titles', {}).get(doc['title'], []))
        base_score, base_match = similarity(query_core or requested_title, base_title(doc['title'], rules),
                                           aliases.get('titles', {}).get(doc['title'], []))
        if base_score > title_score:
            title_score, title_match = base_score, 'base_' + base_match
        artist_score, artist_match = 0.0, 'not_requested'
        if intent.artist is not None:
            artist_score, artist_match = similarity(intent.artist, doc['artist'],
                                                    aliases.get('artists', {}).get(doc['artist'], []))
            if artist_score < .72 or title_score < .55:
                continue
            score = 75 * title_score + 25 * artist_score
        else:
            # Mixed requests with a misspelled artist can still be retrieved and
            # ranked as a complete artist/title phrase; never discard its words.
            combined, combined_match = similarity(intent.query, doc['artist'] + ' ' + doc['title'])
            if intent.kind == 'auto' and combined > title_score:
                title_score, title_match = combined, 'combined_' + combined_match
            if title_score < .60:
                continue
            score = 100 * title_score
        penalty = 0 if requested_versions else (2 if edition == {'remaster'} else 12 if edition else 0)
        evidence = {'title_similarity': round(title_score, 4), 'title_match': title_match,
                    'artist_similarity': round(artist_score, 4), 'artist_match': artist_match,
                    'requested_versions': sorted(requested_versions), 'version_markers': sorted(edition),
                    'unrequested_version_penalty': penalty}
        ranked.append({'kind': 'track', 'track_id': doc['id'], 'title': doc['title'],
                       'artist': doc['artist'], 'album': doc['album'],
                       'score': round(score - penalty, 4), 'evidence': evidence})
    return ranked


def score_artists(intent, documents, aliases):
    result = []
    for artist in sorted({d['artist'] for d in documents}):
        score, match = similarity(intent.query, artist, aliases.get('artists', {}).get(artist, []))
        if score >= .80:
            result.append({'kind': 'artist', 'artist': artist, 'score': round(score * 100, 4),
                           'evidence': {'artist_similarity': round(score, 4), 'artist_match': match}})
    return result


def ordered(candidates):
    # Metadata ordering then snapshot ordinal break ties, never random UUIDs or
    # hidden popularity. An artist wins an exact same-name artist/title tie.
    return sorted(candidates, key=lambda c: (-c['score'], c['kind'] != 'artist',
        normalized(c['artist']), normalized(c.get('album', '')), normalized(c.get('title', '')),
        int(c['track_id'].rsplit(':', 1)[1]) if c['kind'] == 'track' else -1))


async def rank(config, store, search, text):
    rules = load_languages(config.languages)
    head = store.verify_index(config.device_key, search.signature)
    documents = store.documents(head['generation'])
    intent = infer(parse(text, rules), documents, config.aliases)
    if intent.artist is not None:
        known = {d['artist'] for d in documents if normalized(intent.artist)
                 in names(d['artist'], config.aliases.get('artists', {}))}
        if known:
            documents = [d for d in documents if d['artist'] in known]
    else:
        known = set()
    candidates = score_artists(intent, documents, config.aliases) if intent.kind != 'track' else []
    retrieval = {'source': 'sqlite', 'truncated': False}
    if intent.kind != 'artist':
        # Exact/base-title/alias matches across the whole SQLite snapshot are not
        # subject to the search engine's top-k limit. Fuzzy retrieval is bounded.
        exact = [r for r in score_tracks(intent, documents, config.aliases, rules)
                 if r['evidence']['title_similarity'] == 1 and
                 (intent.artist is None or r['evidence']['artist_similarity'] == 1)]
        if exact:
            candidates.extend(exact)
        else:
            query = (intent.artist + ' ' + intent.title) if intent.artist is not None else intent.query
            response = await search.search(store, config.device_key, query, limit=50,
                                           fields=('title', 'artist', 'title_aliases', 'artist_aliases', 'album'))
            if response['generation'] != head['generation']:
                raise StaleSnapshot('catalog changed during ranking; repeat the command')
            pool = [dict(r, id=r['id']) for r in response['candidates'] if not known or r['artist'] in known]
            candidates.extend(score_tracks(intent, pool, config.aliases, rules))
            retrieval = {'source': 'typesense', 'found': response['found'],
                         'truncated': response['found'] > len(pool)}
    if store.verify_index(config.device_key, search.signature) != head:
        raise StaleSnapshot('catalog or index changed during ranking; repeat the command')
    candidates = ordered(candidates)
    return {'status': 'ranked' if candidates else 'not_found', 'query': intent.query,
            'intent': intent.kind, 'generation': head['generation'], 'device': config.device_key,
            'retrieval': retrieval, 'candidates': candidates[:10],
            'ranking_policy': 'lexical-v1; scores are not probabilities; no history/likes'}
