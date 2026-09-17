from html.parser import HTMLParser
import unittest
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
        self.assertLess(stream.PAGE.index('<details'), stream.PAGE.index('id=audio-replay'))
        self.assertNotIn('type=range', stream.PAGE)
        self.assertNotIn('id=key-help', stream.PAGE)

    def test_self_contained_device_keeps_live_screen_and_accessible_ports(self):
        tags = Tags(stream.PAGE).tags
        images = [attrs for tag, attrs in tags if tag == 'img']
        self.assertEqual([img['id'] for img in images], ['scr'])
        ports = [attrs for tag, attrs in tags if attrs.get('id') in
                 ('audio-toggle', 'usb-toggle', 'sd-toggle')]
        self.assertEqual(len(ports), 3)
        for port in ports:
            self.assertIn('aria-pressed', port)
            self.assertTrue(port['aria-label'])
        self.assertNotRegex(stream.PAGE, r'__[A-Z]+__')
        self.assertNotIn('/skin', stream.PAGE)
        self.assertNotIn('alignbtn', stream.PAGE)
