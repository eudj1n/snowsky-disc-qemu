"""Deterministic lexical ranking. No invented history, likes or confidence values."""
from difflib import SequenceMatcher
import re

from research.disc_assistant.assistant.intents import Intent, normalized, names
from research.disc_assistant.assistant.languages import load_languages
from research.disc_assistant.library.store import StaleSnapshot
from research.disc_assistant.library.versions import with_query_markers
from research.disc_assistant.assistant.resolver import infer

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



def score_tracks(intent, documents, aliases, rules=None):
    rules = rules if rules is not None else load_languages()
    metadata_rules = with_query_markers(rules.versions)
    ranked = []
    requested_title = intent.title if intent.title is not None else intent.query
    requested_versions, query_core = metadata_rules.version_parts(clean_title(requested_title))
    for doc in documents:
        edition = versions(doc['title'], metadata_rules) | versions(doc['album'], metadata_rules)
        if requested_versions and not requested_versions <= edition:
            continue
        title_score, title_match = similarity(clean_title(requested_title), clean_title(doc['title']),
                                             aliases.get('titles', {}).get(doc['title'], []))
        base_score, base_match = similarity(query_core or requested_title, base_title(doc['title'], metadata_rules),
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


async def rank(config, store, search, intent, *, trace=None):
    if type(intent) is not Intent:
        raise TypeError('rank requires an interpreted music Intent')
    rules = load_languages((config.locale,))
    head = store.verify_index(config.device_key, search.signature)
    documents = store.documents(head['generation'])
    if trace:
        trace.event('catalog_loaded', {'track_count': len(documents),
                                      'artist_count': len({d['artist'] for d in documents})})
    intent = infer(intent, documents, config.aliases)
    if trace:
        from dataclasses import asdict
        trace.event('intent_resolved', asdict(intent))
    if intent.artist is not None:
        known = {d['artist'] for d in documents if normalized(intent.artist)
                 in names(d['artist'], config.aliases.get('artists', {}))}
        if known:
            documents = [d for d in documents if d['artist'] in known]
    else:
        known = set()
    candidates = score_artists(intent, documents, config.aliases) if intent.kind != 'track' else []
    if trace:
        artist_query = normalized(intent.artist if intent.artist is not None else intent.query)
        exact_artists = sorted({d['artist'] for d in documents if artist_query
                                in names(d['artist'], config.aliases.get('artists', {}))})
        trace.event('local_matches', {'scoped_track_count': len(documents),
                    'exact_artist_count': len(exact_artists), 'exact_artists': exact_artists[:10],
                    'exact_artists_truncated': len(exact_artists) > 10,
                    'artist_candidate_count': len(candidates),
                    'track_search_enabled': intent.kind != 'artist'})
    retrieval = {'source': 'sqlite', 'truncated': False}
    if intent.kind != 'artist':
        # Exact/base-title/alias matches across the whole SQLite snapshot are not
        # subject to the search engine's top-k limit. Fuzzy retrieval is bounded.
        exact = [r for r in score_tracks(intent, documents, config.aliases, rules)
                 if r['evidence']['title_similarity'] == 1 and
                 (intent.artist is None or r['evidence']['artist_similarity'] == 1)]
        if trace:
            trace.event('local_track_matches', {'exact_track_count': len(exact),
                                               'typesense_needed': not bool(exact)})
        if exact:
            candidates.extend(exact)
        else:
            query = (intent.artist + ' ' + intent.title) if intent.artist is not None else intent.query
            if trace:
                trace.event('search_query', {'query': query, 'limit': 50})
            response = await search.search(store, config.device_key, query, limit=50,
                                           fields=('title', 'artist', 'title_aliases', 'artist_aliases', 'album'))
            if trace:
                trace.search(response, phase='retrieval')
            if response['generation'] != head['generation']:
                raise StaleSnapshot('catalog changed during ranking; repeat the command')
            pool = [dict(r, id=r['id']) for r in response['candidates'] if not known or r['artist'] in known]
            scored = score_tracks(intent, pool, config.aliases, rules)
            if trace:
                trace.event('retrieval_filtered', {'found': response['found'],
                            'returned_count': len(response['candidates']), 'scoped_count': len(pool),
                            'ranked_track_count': len(scored)})
            candidates.extend(scored)
            retrieval = {'source': 'typesense', 'found': response['found'],
                         'truncated': response['found'] > len(pool)}
    if store.verify_index(config.device_key, search.signature) != head:
        raise StaleSnapshot('catalog or index changed during ranking; repeat the command')
    candidates = ordered(candidates)
    return {'status': 'ranked' if candidates else 'not_found', 'query': intent.query,
            'intent': intent.kind, 'generation': head['generation'], 'device': config.device_key,
            'retrieval': retrieval, 'candidates': candidates[:10],
            'candidate_count': len(candidates), 'candidates_truncated': len(candidates) > 10,
            'ranking_policy': 'lexical-v2; scores are not probabilities; no history/likes'}
