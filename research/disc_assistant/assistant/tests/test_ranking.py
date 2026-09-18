import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

from research.disc_assistant.assistant.intents import parse as parse_text, Intent
from research.disc_assistant.assistant.languages import load_languages
from research.disc_assistant.assistant.ranking import rank, score_tracks, ordered
from research.disc_assistant.library.tests.helpers import TRACKS, ALIASES
from research.disc_assistant.library.store import Store, StaleSnapshot


def parse(text, rules=None):
    # Low-level grammar comparisons explicitly exercise both dictionaries.
    return parse_text(text, rules or load_languages(('ru', 'en')))


class RankingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.addCleanup(self.store.close)
        self.head = self.store.publish('test', TRACKS, {}, expected_generation=None)
        self.store.publish_index('test', self.head['generation'], 'index', 'sig')
        self.config = Mock(device_key='test', aliases=ALIASES, locale='en')
        self.search = Mock(signature='sig')
        self.search.search = AsyncMock(return_value={'generation': self.head['generation'], 'found': 0, 'candidates': []})

    async def ranked(self, text):
        return await rank(self.config, self.store, self.search, parse(text))

    def test_bilingual_grammar_and_explicit_types(self):
        for phrase in ('Включи Linkin Park', 'Play Linkin Park', ' play   Linkin Park '):
            self.assertEqual(parse(phrase), Intent('Linkin Park'))
        self.assertEqual(parse('Включи Linkin Park — Numb').artist, 'Linkin Park')
        self.assertEqual(parse('Play artist AC - DC'), Intent('AC - DC', 'artist'))
        self.assertEqual(parse('Включи трек Numb').kind, 'track')
        for phrase in ('pause Numb', 'удали Numb', 'play ', 'Play Numb\nstop', ''):
            with self.assertRaises(ValueError):
                parse(phrase)

    async def test_exact_artist_and_cyrillic_alias_start_whole_artist(self):
        for phrase in ('Включи Linkin Park', 'Play artist Linkin Park', 'Включи линкин парк'):
            result = await self.ranked(phrase)
            self.assertEqual(result['candidates'][0]['kind'], 'artist')
            self.assertEqual(result['candidates'][0]['artist'], 'Linkin Park')
        self.search.search.assert_not_called()

    async def test_artist_title_constraints_and_default_version_penalty(self):
        for phrase in ('Play Linkin Park - Numb', 'Включи линкин парк намб', 'Play Linkin Park Numb'):
            result = await self.ranked(phrase)
            candidates = result['candidates']
            self.assertEqual(candidates[0]['album'], 'Meteora')
            self.assertEqual({c['artist'] for c in candidates}, {'Linkin Park'})
            self.assertEqual(candidates[1]['evidence']['unrequested_version_penalty'], 12)
            self.assertGreater(candidates[0]['score'], candidates[1]['score'])

    async def test_requested_live_is_mandatory_and_missing_remix_is_not_substituted(self):
        live = await self.ranked('Play Linkin Park - Numb live')
        self.assertEqual([c['album'] for c in live['candidates']], ['Live'])
        missing = await self.ranked('Play Linkin Park - Numb remix')
        self.assertEqual(missing['status'], 'not_found')

    async def test_duplicate_cue_rows_are_preserved_and_tie_break_is_stable(self):
        first = (await self.ranked('Play Cue entry'))['candidates']
        second = (await self.ranked('Play Cue entry'))['candidates']
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(first[0]['track_id'], self.head['generation'] + ':5')

    async def test_fuzzy_title_uses_typesense_and_can_rank_best_without_confirmation(self):
        docs = self.store.documents(self.head['generation'])[:3]
        self.search.search.return_value = {'generation': self.head['generation'], 'found': 3, 'candidates': docs}
        result = await self.ranked('Play Linkin Park - Nmb')
        self.assertEqual(result['candidates'][0]['album'], 'Meteora')
        self.assertEqual({c['artist'] for c in result['candidates']}, {'Linkin Park'})
        self.assertEqual(result['retrieval']['source'], 'typesense')

    async def test_stale_index_prevents_ranking(self):
        self.store.publish('test', TRACKS, {}, expected_generation=self.head['generation'])
        with self.assertRaises(StaleSnapshot):
            await self.ranked('Play Linkin Park')

    async def test_metadata_versions_are_independent_of_interaction_locale(self):
        self.config.locale = 'ru'
        intent = parse('Включи трек Linkin Park - Numb концертная', load_languages(('ru',)))
        live = await rank(self.config, self.store, self.search, intent)
        self.assertEqual([c['album'] for c in live['candidates']], ['Live'])
        ordinary = await rank(self.config, self.store, self.search, Intent('Linkin Park Numb'))
        self.assertEqual(ordinary['candidates'][0]['album'], 'Meteora')
        with self.assertRaises(TypeError):
            await rank(self.config, self.store, self.search, 'Включи Numb')

    async def test_foreign_edition_labels_remain_hard_constraints_in_russian_requests(self):
        self.config.locale = 'ru'
        for label, expected in [('live', ['Live']), ('remix', [])]:
            intent = parse('Включи Linkin Park - Numb ' + label, load_languages(('ru',)))
            result = await rank(self.config, self.store, self.search, intent)
            self.assertEqual([c['album'] for c in result['candidates']], expected)

    async def test_unmatched_text_never_falls_back_to_artist_only(self):
        result = await self.ranked('Play Linkin Park TotallyMissing')
        self.assertEqual(result['candidates'], [])

    async def test_fuzzy_artist_rank_and_same_name_explicit_track_override(self):
        result = await self.ranked('Play artist Linkn Park')
        self.assertEqual(result['candidates'][0]['artist'], 'Linkin Park')
        extra = self.store.documents(self.head['generation'])[0]
        from research.disc_assistant.assistant.ranking import infer
        self.assertEqual(infer(Intent('Numb'), [dict(extra, artist='Numb')], {}).kind, 'artist')
        self.assertEqual(infer(Intent('Numb', 'track'), [dict(extra, artist='Numb')], {}).kind, 'track')

    def test_requested_remaster_and_exact_alias_rank_like_metadata(self):
        docs = [{'id': 's:1', 'title': 'Numb (Remastered)', 'artist': 'Linkin Park', 'album': 'Meteora'},
                {'id': 's:0', 'title': 'Numb', 'artist': 'Linkin Park', 'album': 'Meteora'}]
        ordinary = ordered(score_tracks(Intent('Numb', 'track'), docs, {}))
        self.assertEqual(ordinary[0]['track_id'], 's:0')
        remaster = ordered(score_tracks(Intent('Numb remastered', 'track'), docs, {}, load_languages(('en',))))
        self.assertEqual([c['track_id'] for c in remaster], ['s:1'])
