import struct
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote

from controller.fiio_http import Reply
from controller.fiio_theme import read_lock_screen, upload_lock_screen, select_system_lock_screen, FIELDS, CUSTOM_STYLES, update_system_lock_screen


class ThemeTests(unittest.TestCase):
    def system_fixture(self):
        return json.loads((Path(__file__).parent / 'fixtures' /
                           'fiio_control_ios_system_theme_colors.json').read_text())

    def test_system_edit_matches_captured_color_post_and_reads_original(self):
        fixture = self.system_fixture()
        for update in fixture['updates']:
            before = Reply(200, fixture['initial']['response_headers'].copy(), b'image')
            after = Reply(200, update['readback']['response_headers'].copy(), b'image')
            rgb = tuple(int(v.split('=')[1]) for v in after.headers['front-color'].split(';'))
            http = Mock()
            http.request.side_effect = [before, Reply(200, {}, b''), after]
            self.assertIs(update_system_lock_screen(http, 1, color=rgb), after)
            self.assertEqual(http.request.call_args_list[1].kwargs,
                             dict(body=b'', headers=update['post']['request_headers']))
            for index in (0, 2):
                self.assertEqual(http.request.call_args_list[index].args, ('GET', '/image/lock_screen/'))
                self.assertEqual(http.request.call_args_list[index].kwargs['headers']['preview-flag'], '0')
            self.assertEqual(before.headers, fixture['initial']['response_headers'])

    def test_system_edit_merges_false_zero_and_style_without_coupling(self):
        original = self.system_fixture()['initial']['response_headers']
        for change, fields in (
            ({'alpha': 0}, {'back-groud': 'alpha=0'}),
            ({'show_date': False}, {'lock-screen': 'time=1;date=0;battery=1;id3=1'}),
            ({'show_time': False, 'style': 'clock/0'},
             {'msg-style': 'clock/0', 'lock-screen': 'time=0;date=1;battery=1;id3=1'}),
            ({'style': 'default/0'}, {'msg-style': 'default/0'}),
        ):
            with self.subTest(change=change):
                expected = dict(original, **fields)
                http = Mock()
                http.request.side_effect = [Reply(200, original.copy(), b'image'),
                                            Reply(200, {}, b''), Reply(200, expected, b'image')]
                update_system_lock_screen(http, 1, **change)
                self.assertEqual(http.request.call_args_list[1].kwargs['headers'], expected)

    def test_system_edit_rejects_invalid_input_before_io(self):
        for change in ({}, {'alpha': True}, {'alpha': -1}, {'alpha': 101},
                       {'color': (1, 2)}, {'color': (False, 0, 0)}, {'color': (0, 0, 256)},
                       {'style': []}, {'style': 'default/3'}, {'show_time': 0}):
            http = Mock()
            with self.subTest(change=change), self.assertRaises(ValueError):
                update_system_lock_screen(http, 1, **change)
            http.request.assert_not_called()
        for slot in (True, -1, 5, '1'):
            http = Mock()
            with self.assertRaises(ValueError):
                update_system_lock_screen(http, slot, alpha=0)
            http.request.assert_not_called()

    def test_system_edit_refuses_bad_snapshot_or_flags_without_post(self):
        headers = self.system_fixture()['initial']['response_headers']
        for patch, body in (({'file-source': 'lock_screen/custom'}, b'image'),
                            ({'x-fields-to-update': '2'}, b'image'),
                            ({'lock-screen': 'time=1'}, b'image'),
                            ({'alias': 'bad\r\nheader'}, b'image'), ({}, b'')):
            http = Mock()
            http.request.return_value = Reply(200, dict(headers, **patch), body)
            with self.assertRaises(ValueError):
                update_system_lock_screen(http, 1, show_date=False)
            self.assertEqual(http.request.call_count, 1)

    def test_system_edit_detects_ignored_write_image_change_and_other_field_loss(self):
        original = self.system_fixture()['initial']['response_headers']
        expected = dict(original, **{'back-groud': 'alpha=0'})
        for headers, body in ((original, b'image'), (expected, b'changed'),
                              (dict(expected, **{'msg-style': 'clock/0'}), b'image')):
            http = Mock()
            http.request.side_effect = [Reply(200, original, b'image'),
                                        Reply(200, {}, b''), Reply(200, headers, body)]
            with self.assertRaisesRegex(OSError, 'state may have changed'):
                update_system_lock_screen(http, 1, alpha=0)
            self.assertEqual(http.request.call_count, 3)  # no write replay or rollback

    def test_system_edit_does_not_retry_uncertain_post(self):
        http = Mock()
        http.request.side_effect = [Reply(200, self.system_fixture()['initial']['response_headers'], b'image'),
                                    TimeoutError('write response lost')]
        with self.assertRaises(TimeoutError):
            update_system_lock_screen(http, 1, alpha=49)
        self.assertEqual(http.request.call_count, 2)

    def test_system_selection_preserves_captured_rgb_without_quantization(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_system_theme_colors.json').read_text())
        for update in fixture['updates']:
            post, readback = update['post'], update['readback']
            with self.subTest(color=post['request_headers']['front-color']):
                headers = readback['response_headers'].copy()
                self.assertEqual(headers['front-color'],
                                 post['request_headers']['front-color'])
                http = Mock()
                http.request.return_value = Reply(readback['status'], headers,
                                                  b'artwork omitted')
                select_system_lock_screen(http, 1)
                args, kwargs = http.request.call_args
                self.assertEqual(args, ('POST', fixture['route']))
                # Preserve near-primary RGB bytes (253/0/255, 251/255/0),
                # white and pink exactly; selecting must not reconstruct hue.
                self.assertEqual(kwargs['headers'], post['request_headers'])
                self.assertEqual(kwargs['body'], b'')
                self.assertEqual(headers, readback['response_headers'])

    def test_system_selection_preserves_captured_opacity_including_zero(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_system_theme_opacity.json').read_text())
        # Reselecting a system slot must preserve its saved opacity, including
        # zero, without uploading artwork or double-encoding the stock alias.
        for post, readback in zip(fixture['posts'][1:], fixture['readbacks']):
            with self.subTest(opacity=post['displayed_percent']):
                headers = readback['response_headers'].copy()
                self.assertEqual(headers['back-groud'], post['back-groud'])
                http = Mock()
                http.request.return_value = Reply(readback['status'], headers,
                                                  b'artwork omitted')
                select_system_lock_screen(http, int(headers['x-fields-to-update']))
                args, kwargs = http.request.call_args
                self.assertEqual(args, ('POST', fixture['route']))
                expected = dict(fixture['common_post_headers'],
                                **{'back-groud': post['back-groud']})
                self.assertEqual(kwargs['headers'], expected)
                self.assertEqual(kwargs['body'], b'')
                self.assertEqual(headers, readback['response_headers'])

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
