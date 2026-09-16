import struct
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote

from fiio_http import Reply
from fiio_theme import read_lock_screen, upload_lock_screen, select_system_lock_screen, FIELDS, CUSTOM_STYLES


class ThemeTests(unittest.TestCase):
    def test_alias_limit_counts_encoded_bytes_before_decoding(self):
        data = (b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' +
                struct.pack('>II', 360, 360) + b'\0' * 9)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.png'
            path.write_bytes(data)
            for alias in ('A' * 63, 'Ё' * 10 + 'ABC'):
                self.assertEqual(len(quote(alias, safe='')), 63)
                http = Mock()
                upload_lock_screen(http, path, alias=alias)
                self.assertEqual(http.request.call_args.kwargs['headers']['alias'], quote(alias, safe=''))
        for alias in ('A' * 64, 'Ё' * 11):
            http = Mock()
            with self.assertRaisesRegex(ValueError, '63-byte'):
                upload_lock_screen(http, '/not-read.png', alias=alias)
            http.request.assert_not_called()

    def test_custom_styles_match_physical_capture_except_alias(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_custom_theme_styles.json').read_text())
        self.assertEqual(set(CUSTOM_STYLES), {p['style'] for p in fixture['posts']})
        data = (b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' +
                struct.pack('>II', 360, 360) + b'\0' * 9)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'fixture.png'
            path.write_bytes(data)
            for post in fixture['posts']:
                with self.subTest(style=post['style'], flags=post['flags']):
                    flags = dict(item.split('=') for item in post['flags'].split(';'))
                    http = Mock()
                    upload_lock_screen(http, path, style=post['style'],
                                       **{f'show_{key}': value == '1' for key, value in flags.items()})
                    args, kw = http.request.call_args
                    self.assertEqual(args, ('POST', '/image/lock_screen/'))
                    self.assertEqual(kw['body'], data)
                    expected = dict(fixture['common_post_headers'], alias='')
                    expected.update({'msg-style': post['style'], 'lock-screen': post['flags']})
                    self.assertEqual(kw['headers'], expected)

    def test_style_validation_precedes_file_and_network_access(self):
        for style in (None, True, 0, [], {}, 'default/3', 'clock/1',
                      'DEFAULT/0', 'default/0\r\nInjected: yes'):
            with self.subTest(style=style):
                http = Mock()
                with self.assertRaisesRegex(ValueError, 'unsupported DISC'):
                    upload_lock_screen(http, '/not-read.png', style=style)
                http.request.assert_not_called()

    def test_custom_metadata_save_matches_physical_capture_except_alias(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_custom_theme_save.json').read_text())
        # Original artwork stays private. Exercise the same header changes with
        # synthetic bytes and assert every save still sends the complete image.
        data = (b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' +
                struct.pack('>II', 360, 360) + b'\0' * 9)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'fixture.png'
            p.write_bytes(data)
            for post in fixture['posts']:
                with self.subTest(time=post['time']):
                    http = Mock()
                    upload_lock_screen(http, p, color=post['color'],
                                       show_time=False, show_date=post['date'],
                                       show_battery=False, show_id3=False)
                    args, kw = http.request.call_args
                    self.assertEqual(args, ('POST', '/image/lock_screen/'))
                    expected = dict(fixture['common_post_headers'], alias='')
                    expected['front-color'] = 'r=%d;g=%d;b=%d' % tuple(post['color'])
                    expected['lock-screen'] = (
                        f'time=0;date={int(post["date"])};battery=0;id3=0')
                    self.assertEqual(kw['headers'], expected)
                    self.assertEqual(kw['body'], data)

    def test_observed_long_app_alias_remains_outside_reviewed_limit(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_custom_theme_save.json').read_text())
        http = Mock()
        self.assertEqual(len(quote(fixture['app_alias'], safe='')), 96)
        # The app sends this localized label, but GET returns an empty alias.
        # That is not proof of lossless persistence or permission to lift the guard.
        with self.assertRaisesRegex(ValueError, '63-byte'):
            upload_lock_screen(http, '/not-read.png', alias=fixture['app_alias'])
        http.request.assert_not_called()

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
