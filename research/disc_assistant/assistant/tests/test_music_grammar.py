"""Exercise the complete live interpretation boundary, including its shared gate."""
import unittest
from research.disc_assistant.assistant.interpreter import interpret_request, InterpretationContext, UnsupportedCommand
from research.disc_assistant.assistant.intents import Intent, ControlIntent


class MusicGrammarTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_synonyms_and_music_names(self):
        for verb in ('Включи', 'играй', 'запусти'):
            self.assertEqual(await interpret_request(verb + ' Guano Apes — Open Your Eyes', InterpretationContext('ru')),
                Intent('Guano Apes — Open Your Eyes', 'track', 'Guano Apes', 'Open Your Eyes'))
        for word, action in [('хватит', 'stop'), ('назад', 'previous'), ('вперед', 'next'), ('вперёд', 'next')]:
            self.assertEqual(await interpret_request(word, InterpretationContext('ru')), ControlIntent(action))

    async def test_semicolons_belong_to_music_credit(self):
        for locale, prefix in [('en', 'Play'), ('ru', 'Включи')]:
            result = await interpret_request(prefix + ' Eminem;Dido — Stan', InterpretationContext(locale))
            self.assertEqual(result.artist, 'Eminem;Dido')
            self.assertEqual(result.title, 'Stan')

    async def test_quoted_command_like_titles_are_literal(self):
        for locale, text, title in [('en', 'Play track "Pause and Resume"', 'Pause and Resume'),
                ('en', 'Play "Stop — In the Name of Love"', 'Stop — In the Name of Love'),
                ('ru', 'Играй трек «Стоп; затем продолжи»', 'Стоп; затем продолжи'),
                ('ru', 'Включи свет в комнате', 'свет в комнате')]:
            result = await interpret_request(text, InterpretationContext(locale))
            self.assertEqual(result.query, title)
            self.assertIsNone(result.artist)

    async def test_sequence_negation_and_unbalanced_quotes_never_execute(self):
        for locale, texts in [('en', ['Play Eminem;Dido — Stan;pause', 'Play Moby; then stop',
                'Pause; resume', 'Play Moby and then stop', 'Play "unfinished']),
                ('ru', ['играй Кино; затем хватит', 'запусти Кино и вперед', 'включи Кино;назад'])]:
            for text in texts:
                with self.subTest(text=text), self.assertRaises(UnsupportedCommand):
                    await interpret_request(text, InterpretationContext(locale))
        for locale, text in [('en', 'Do not play Moby'), ('ru', 'Не играй Кино')]:
            with self.assertRaises(ValueError):
                await interpret_request(text, InterpretationContext(locale))
