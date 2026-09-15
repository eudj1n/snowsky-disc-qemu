import struct
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from fiio_http import Reply
from fiio_theme import read_lock_screen, upload_lock_screen, select_system_lock_screen, FIELDS


class ThemeTests(unittest.TestCase):
    def test_selection_matches_observed_ios_requests(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_460_themes.json').read_text())
        for selection in fixture['selections']:
            with self.subTest(slot=selection['slot']):
                http = Mock()
                # Full PNGs were verified in the private HAR; do not publish artwork.
                http.request.return_value = Reply(200, selection['response_headers'], b'image omitted')
                select_system_lock_screen(http, selection['slot'])
                args, kwargs = http.request.call_args
                self.assertEqual(args, ('POST', '/image/lock_screen/'))
                self.assertEqual(kwargs['headers'], selection['post_headers'])
                self.assertEqual(len(kwargs['body']), selection['post_body_size'])
                # In particular FIIO%20Sheep must not become FIIO%2520Sheep.
                self.assertNotIn('%25', kwargs['headers']['alias'])

    def test_upload_headers_and_full_binary_body(self):
        http = Mock()
        data = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 360, 360) + b'\0' * 9
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'fixture.png'
            p.write_bytes(data)
            upload_lock_screen(http, p, alias='Ё +', alpha=70, color=(12, 34, 56))
            args, kw = http.request.call_args
            self.assertEqual(args, ('POST', '/image/lock_screen/'))
            self.assertEqual(kw['body'], data)
            self.assertEqual(kw['headers']['alias'], '%D0%81%20%2B')
            self.assertEqual(kw['headers']['flag-in-use'], '1')
            self.assertEqual(kw['headers']['front-color'], 'r=12;g=34;b=56')
            for invalid in ({'alias':'Ё'*11}, {'alpha':True}, {'color':(1,2,256)}, {'show_time':1}):
                http.reset_mock()
                with self.assertRaises(ValueError):
                    upload_lock_screen(http, p, **invalid)
                http.request.assert_not_called()
            p.write_bytes(b'')
            with self.assertRaises(ValueError):
                upload_lock_screen(http, p)

    def test_system_selection_requires_matching_complete_readback(self):
        http = Mock()
        http.request.return_value = Reply(200, {}, b'')
        with self.assertRaises(ValueError):
            select_system_lock_screen(http, 0)
        self.assertEqual(http.request.call_count, 1)
        headers = dict.fromkeys(FIELDS, '')
        headers.update({'x-fields-to-update':'2', 'file-source':'lock_screen/system', 'alias':'Stock'})
        http.reset_mock()
        http.request.return_value = Reply(200, headers, b'image')
        select_system_lock_screen(http, 2)
        self.assertEqual(http.request.call_args.kwargs['body'], b'')
        self.assertEqual(http.request.call_args.kwargs['headers']['flag-in-use'], '1')
        self.assertEqual(headers['flag-in-use'], '')
        http.reset_mock()
        with self.assertRaises(ValueError):
            read_lock_screen(http, 1)
        with self.assertRaises(ValueError):
            read_lock_screen(http, 5, system=True)
        http.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
