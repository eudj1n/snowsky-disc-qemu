from pathlib import Path
import tempfile
import unittest

from experiments.disc_assistant.assistant.nlu.intents import Intent, parse as parse_text
from experiments.disc_assistant.assistant.nlu.languages import load_languages
from experiments.disc_assistant.assistant.ranking import score_tracks


def parse(text, rules=None):
    # Low-level grammar comparisons explicitly exercise both dictionaries.
    return parse_text(text, rules or load_languages(('ru', 'en')))


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def write(self, code, text):
        (self.directory / (code + '.toml')).write_text(text, encoding='utf-8')

    def test_merged_languages_allow_mixed_commands(self):
        for phrase in ('Play песню Numb', 'Включи song Numb'):
            self.assertEqual(parse(phrase), Intent('Numb', 'track'))
        a, b = load_languages(('ru', 'en')), load_languages(('en', 'ru'))
        self.assertEqual((a.commands, a.targets, a.versions), (b.commands, b.targets, b.versions))

    def test_language_selection_excludes_other_prefixes(self):
        for code, accepted, rejected in [('ru', 'Включи Numb', 'Play Numb'),
                                         ('en', 'Play Numb', 'Включи Numb')]:
            rules = load_languages((code,))
            self.assertEqual(parse(accepted, rules), Intent('Numb'))
            with self.assertRaises(ValueError):
                parse(rejected, rules)

    def test_new_language_and_multiword_forms_need_no_parser_changes(self):
        self.write('fr', '[commands]\nplay=["mets", "mets moi"]\n'
                        '[targets]\nartist=["artiste"]\ntrack=["la chanson"]\n'
                        '[versions]\nlive=["en concert"]\n')
        rules = load_languages(('fr',), directory=self.directory)
        self.assertEqual(parse('METS   MOI la   chanson Numb', rules), Intent('Numb', 'track'))
        docs = [{'id': 's:0', 'title': 'Numb (En concert)', 'artist': 'LP', 'album': 'Album'},
                {'id': 's:1', 'title': 'Numb', 'artist': 'LP', 'album': 'Album'}]
        results = score_tracks(parse('mets la chanson Numb en concert', rules), docs, {}, rules)
        self.assertEqual([r['track_id'] for r in results], ['s:0'])
        self.assertEqual(results[0]['evidence']['title_similarity'], 1)

    def test_regex_symbols_are_literal_and_markers_have_boundaries(self):
        self.write('xx', '[commands]\nplay=["play+"]\n[versions]\nlive=["live+", "live"]\n')
        rules = load_languages(('xx',), directory=self.directory)
        self.assertEqual(parse('play+ Numb', rules), Intent('Numb'))
        with self.assertRaises(ValueError):
            parse('playyy Numb', rules)
        self.assertEqual(rules.version_parts('Alive deliver'), (set(), 'alive deliver'))
        self.assertEqual(rules.version_parts('Numb (LIVE+)')[0], {'live'})
        self.assertNotIn('+', rules.version_parts('Numb (LIVE+)')[1])

    def test_conflicting_meanings_rejected_after_normalization(self):
        self.write('aa', '[commands]\nplay=["play"]\n[targets]\nartist=["THE Artist"]\n')
        self.write('bb', '[targets]\ntrack=["the  artist"]\n')
        with self.assertRaisesRegex(ValueError, 'conflicting phrase'):
            load_languages(('aa', 'bb'), directory=self.directory)
        self.write('bb', '[versions]\nlive=["concert"]\nremix=["CONCERT"]\n')
        with self.assertRaisesRegex(ValueError, 'conflicting phrase'):
            load_languages(('aa', 'bb'), directory=self.directory)

    def test_identical_meanings_merge_and_sections_are_independent(self):
        for code in ('aa', 'bb'):
            self.write(code, '[commands]\nplay=["play"]\n[targets]\ntrack=["play"]\n')
        rules = load_languages(('aa', 'bb'), directory=self.directory)
        self.assertEqual(len(rules.commands), 1)
        self.assertEqual(parse('play play Numb', rules).kind, 'track')

    def test_invalid_language_selection_and_missing_file(self):
        for enabled in ([], 'ru', ['ru', 'ru'], ['../ru'], [True], ['zz']):
            with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                load_languages(enabled)

    def test_invalid_dictionary_schema_and_phrases(self):
        for body in ('', '[unknown]\nx=["x"]', '[commands]\ndelete=["delete"]',
                     '[commands]\nplay="play"', '[commands]\nplay=[]',
                     '[commands]\nplay=[""]', '[commands]\nplay=[" play"]',
                     '[commands]\nplay=[12]', '[commands]\nplay=["play\\n"]',
                     '[commands]\nplay=[', '[targets]\ntrack=["track"]'):
            self.write('xx', body)
            with self.subTest(body=body), self.assertRaises(ValueError):
                load_languages(('xx',), directory=self.directory)
