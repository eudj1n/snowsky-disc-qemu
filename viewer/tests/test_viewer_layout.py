from html.parser import HTMLParser
import unittest
from unittest.mock import patch
from viewer import server as stream


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, name, attributes):
        self.tags.append((name, dict(attributes)))


class ViewerLayoutTests(unittest.TestCase):
    def test_one_accessible_button_per_physical_key(self):
        buttons = [attrs for tag, attrs in Tags(stream.PAGE).tags if 'data-key' in attrs]
        self.assertEqual(len(buttons), 4)
        self.assertEqual({b['data-key'] for b in buttons},
                         {'power', 'play_pause', 'volume_up', 'volume_down'})
        for button in buttons:
            self.assertTrue(button['aria-label'])
            self.assertNotIn('aria-describedby', button)

    def test_debug_is_collapsed_by_default_and_english(self):
        details = [attrs for tag, attrs in Tags(stream.PAGE).tags if tag == 'details']
        self.assertEqual(details, [{'id': 'debug-tools'}])
        self.assertIn('<summary>Debug</summary>', stream.PAGE)
        self.assertLess(stream.PAGE.index('<details'), stream.PAGE.index('id=alignbtn'))
        self.assertLess(stream.PAGE.index('<details'), stream.PAGE.index('id=audio-replay'))
        self.assertNotIn('type=range', stream.PAGE)
        self.assertNotIn('id=key-help', stream.PAGE)

    def test_plain_and_skin_render_without_unresolved_fields(self):
        for skin, mode in ((None, 'plain'), ((b'', 1325, 1347), 'skin')):
            with patch.object(stream, 'SKIN_DATA', skin):
                fields = stream._skin_fields()
            self.assertEqual(fields['MODE'], mode)
            page = stream.PAGE
            for key, value in fields.items():
                page = page.replace('__%s__' % key, value)
            self.assertNotRegex(page, r'__[A-Z]+__')
            self.assertEqual(page.count('data-key='), stream.PAGE.count('data-key='))
