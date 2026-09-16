import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from urllib.parse import unquote

from fiio_library import (genre_command, folder_command, verify_folder, verify_genre,
                          artist_command, verify_artist)
from fiio_link import Client, Frames, frame, index_payload, list_payload, playback_snapshot
from fiio_ws import WSClient
from fiio_http import HTTPClient, Reply


def page(pos=0, name='01.flac', total=1, **fields):
    row = dict(pos=pos, name=name, is_dir=False, is_cue=False, is_m3u=False, is_image=False)
    row.update(fields)
    return dict(total=total, items=[row], mark=-1)


class LibraryTests(unittest.IsolatedAsyncioTestCase):
    def root_capture(self):
        return json.loads((Path(__file__).parent / 'fixtures' /
                           'fiio_control_ios_root_play_all.json').read_text())

    def test_root_capture_only_sends_named_genre_playback(self):
        fixture = self.root_capture()
        # Fragment a coalesced outgoing stream: queries must not be classified
        # as playback, and only the later named-genre action is present.
        wire = b''.join(frame(r['tag'], r['payload']) for r in fixture['outgoing_link'])
        decoder = Frames()
        decoded = []
        for offset in range(0, len(wire), 7):
            decoded.extend(decoder.feed(wire[offset:offset + 7]))
        self.assertFalse(decoder.buffer)
        playback = [(tag, payload.decode()) for tag, payload in decoded
                    if tag in ('0100', '0101', '0201')]
        self.assertEqual(playback, [genre_command(fixture['genre']), ('0201', '0000')])
        states = [playback_snapshot(r['payload'].encode())
                  for r in fixture['genre_events'] if r['tag'] == 'a202']
        self.assertEqual([s['state'] for s in states], [2, 1, 0, 0, 1, 1])
        self.assertEqual(states[0]['playerflag'], 8)
        self.assertEqual(states[0]['playing_num'], '1/177')

    def test_root_capture_http_tabs_have_no_implicit_name_filters(self):
        http = HTTPClient()
        http.request = Mock(return_value=Reply(200, {'total-num': '0'}, b'[]'))
        requests = self.root_capture()['http_requests']
        self.assertEqual([r['category'] for r in requests],
                         ['all/song', 'artist', 'album', 'style', 'style/album'])
        for request in requests:
            http.catalog(request['category'], limit=100, **request['filters'])
            http.request.assert_called_with('GET', '/song_category_tree/',
                                            headers={k: v for k, v in request['headers'].items() if v})

    def folder_artist_capture(self):
        return json.loads((Path(__file__).parent / 'fixtures' /
                           'fiio_control_ios_folders_artists.json').read_text())

    def test_physical_folder_album_artist_selectors(self):
        fixture = self.folder_artist_capture()
        for session in fixture['sessions']:
            for item in session['commands']:
                action, index = item['action'], item.get('index')
                if action == 'toggle':
                    continue
                if action.startswith('folder'):
                    command = folder_command(fixture['folder'], index,
                                             '02. Second.flac' if index is not None else None)
                elif action.startswith('album'):
                    command = (('0100', index_payload(index, 3, fixture['album']))
                               if index is not None else ('0101', list_payload(3, fixture['album'])))
                else:
                    command = artist_command(fixture['solo_artist'] if action == 'artist_all'
                                             else fixture['artist'], index,
                                             None if action == 'artist_all' else fixture['artist_album'])
                with self.subTest(action=action):
                    self.assertEqual(command, (item['tag'], item['payload']))
                    self.assertEqual(int(frame(*command)[4:8], 16), len(frame(*command)))

    def test_physical_folder_position_and_artist_http_scoping(self):
        fixture = self.folder_artist_capture()
        http = HTTPClient()
        http.request = Mock(return_value=Reply(200, {'total-num': '0'}, b'[]'))
        for session in fixture['sessions']:
            for request in session['http_requests']:
                if 'category' in request:
                    http.catalog(request['category'], limit=100, **request['filters'])
                    expected = {k: v for k, v in request['headers'].items() if v}
                    http.request.assert_called_with('GET', '/song_category_tree/', headers=expected)
                else:
                    http.directory(fixture['folder'], limit=100, local=True)
                    self.assertEqual(unquote(http.request.call_args.args[1]), unquote(request['path']))
                    rows = request['first_rows']
                    http.directory = Mock(return_value=page(2, rows[2]['name'], request['total']))
                    self.assertTrue(rows[0]['is_dir'])
                    verify_folder(http, fixture['folder'], 2, rows[2]['name'])
                    with self.assertRaises(ValueError):
                        verify_folder(http, fixture['folder'], 1, rows[2]['name'])

    def test_artist_scope_guards_and_utf8(self):
        command = artist_command('Artist Ё', 1, 'Shared Album')
        self.assertEqual(command, ('0100', '00010007{"artist":"Artist Ё", "album":"Shared Album"}'))
        self.assertEqual(int(frame(*command)[4:8], 16), len(frame(*command)))
        for artist, index, album in (('', None, None), ('unknown_artist', None, None),
                                    ('x', None, 'unknown_album'), ('x', None, ''),
                                    ('x', 0, None), ('x', True, 'a'), ('x', 65536, 'a'),
                                    ('x', -1, 'a'), ('x"y', None, None), ('x', 0, 'a\\b'),
                                    ('Ё' * 43, None, None), ('x\0y', None, None)):
            with self.subTest(artist=artist, index=index, album=album), self.assertRaises(ValueError):
                artist_command(artist, index, album)
        http = Mock()
        http.catalog.return_value = page(1, total=2)
        verify_artist(http, 'Artist Ё', 1, 'Shared Album')
        http.catalog.assert_called_once_with('artist/album/song', offset=1, limit=1,
                                             artist='Artist Ё', album='Shared Album')
        http.catalog.return_value = page()
        verify_artist(http, 'Artist Ё')
        http.catalog.assert_called_with('artist/song', offset=0, limit=1, artist='Artist Ё')

    async def test_artist_clients_scope_rejection_and_no_retry(self):
        for index, album in ((None, None), (None, 'Shared Album'), (1, 'Shared Album')):
            tcp, ws = self.clients()
            for client in (tcp, ws):
                http = Mock()
                http.catalog.return_value = page(index or 0, total=2)
                result = client.play_artist('Artist Ё', index, album=album, http=http)
                command = artist_command('Artist Ё', index, album)
                if client is ws:
                    await result
                    ws.send.assert_awaited_once_with(*command)
                else:
                    tcp.socket.sendall.assert_called_once_with(frame(*command))
                http.catalog.return_value = page(total=0)
                with self.assertRaises(ValueError):
                    result = client.play_artist('Artist Ё', index, album=album, http=http)
                    if client is ws:
                        await result
                sender = ws.send if client is ws else tcp.socket.sendall
                self.assertEqual(sender.call_count, 1)
                http.catalog.return_value = page(index or 0, total=2)
                sender.side_effect = TimeoutError('uncertain write')
                with self.assertRaises(TimeoutError):
                    result = client.play_artist('Artist Ё', index, album=album, http=http)
                    if client is ws:
                        await result
                self.assertEqual(sender.call_count, 2)

    def capture(self):
        return json.loads((Path(__file__).parent / 'fixtures' /
                           'fiio_control_ios_genres.json').read_text())

    def test_physical_scoped_album_commands(self):
        fixture = self.capture()
        for item in fixture['commands']:
            if item['action'] not in ('album_track', 'album_all'):
                continue
            with self.subTest(action=item['action']):
                tag, payload = genre_command(fixture['genre'], item.get('index'), fixture['album'])
                self.assertEqual(tag, item['tag'])
                # The app uses lowercase hexadecimal positions; integer meaning
                # is identical. Do not case-fold the case-sensitive names.
                size = 8 if item['action'] == 'album_track' else 4
                self.assertEqual(payload[:size].lower(), item['payload'][:size].lower())
                self.assertEqual(payload[size:], item['payload'][size:])
                wire = frame(tag, payload)
                self.assertEqual(int(wire[4:8], 16), len(wire))

    def test_physical_genre_http_filters(self):
        http = HTTPClient()
        http.request = Mock(return_value=Reply(200, {'total-num': '0'}, b'[]'))
        for request in self.capture()['http_requests']:
            http.catalog(request['category'], limit=100, **request['filters'])
            # App sends unused name headers as empty; helper omits them.
            expected = {key: value for key, value in request['headers'].items() if value}
            http.request.assert_called_with('GET', '/song_category_tree/',
                                            headers=expected)

    def test_captured_whole_genre_and_separate_indexed_path(self):
        fixture = self.capture()
        observed = [c for c in fixture['commands'] if c['action'] == 'genre_all']
        self.assertTrue(all(c['payload'].startswith('0008') for c in observed))
        self.assertEqual(genre_command(fixture['genre']),
                         (observed[1]['tag'], observed[1]['payload']))
        self.assertEqual(genre_command(fixture['genre'], 2)[1], '0002000A' + fixture['genre'])
        with self.assertRaises(ValueError):
            genre_command(fixture['genre'], album='')

    def clients(self, version=257):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.settings = Mock(return_value={'soc_version': version})
        ws = WSClient()
        ws.send = AsyncMock()
        ws.settings = AsyncMock(return_value={'soc_version': version})
        return tcp, ws

    def test_wire_context_and_utf8(self):
        self.assertEqual(genre_command('Genre Ё'),
                         ('0101', '0008{"style":"Genre Ё", "album":""}'))
        self.assertEqual(genre_command('Genre Ё', 2), ('0100', '0002000AGenre Ё'))
        command = genre_command('Genre Ё', 1, 'Shared Album')
        self.assertEqual(command, ('0100', '00010008{"style":"Genre Ё", "album":"Shared Album"}'))
        data = frame(*command)
        self.assertEqual(int(data[4:8], 16), len(data))
        self.assertEqual(folder_command('/tmp/sdcard/A', 2, '02.flac'),
                         ('0100', '00020004/tmp/sdcard/A'))

    def test_argument_guards(self):
        for genre, index, album in (('', None, None), ('x\0y', 0, None),
                                   ('unknown_style', None, None), ('x', True, None),
                                   ('x', 65536, None), ('x', -1, None),
                                   ('x', 0, 'unknown_album'), ('x"y', 0, 'a'),
                                   ('x"y', None, None), ('x\\y', None, None),
                                   ('x', 0, 'a\\b'), ('Ё' * 43, 0, None)):
            with self.assertRaises(ValueError):
                genre_command(genre, index, album)
        for path, index, name in (('/tmp', None, None), ('/tmp/sdcard/../x', None, None),
                                 ('/tmp/sdcard/x.M3U/y', None, None),
                                 ('/tmp/sdcard/' + 'x' * 499, None, None),
                                 ('/tmp/sdcard/A', True, 'x'),
                                 ('/tmp/sdcard/A', 0, None),
                                 ('/tmp/sdcard/A', 0, 'x/y'),
                                 ('/tmp/sdcard/A', None, 'x')):
            with self.assertRaises(ValueError):
                folder_command(path, index, name)

    def test_fresh_scoped_catalog(self):
        http = Mock()
        http.catalog.return_value = page(1, total=2)
        verify_genre(http, 'Genre Ё', 1, 'Shared Album')
        http.catalog.assert_called_once_with('style/album/song', offset=1, limit=1,
                                              style='Genre Ё', album='Shared Album')
        for invalid in (page(total=0), page(pos=True), page(total=True),
                        dict(total=2, items=[]), page(pos=1)):
            http.catalog.return_value = invalid
            with self.assertRaises(ValueError):
                verify_genre(http, 'Genre Ё')

    def test_folder_positions_include_directories_and_play_all_skips_them(self):
        http = Mock()
        http.directory.side_effect = [page(0, 'Nested', 2, is_dir=True), page(1, total=2)]
        verify_folder(http, '/tmp/sdcard/A')
        self.assertEqual(http.directory.call_args_list[1].kwargs,
                         dict(offset=1, local=True))
        http.directory.side_effect = None
        http.directory.return_value = page(1, total=2)
        verify_folder(http, '/tmp/sdcard/A', 1, '01.flac')
        http.directory.assert_called_with('/tmp/sdcard/A', offset=1, limit=1, local=True)
        with self.assertRaises(ValueError):
            verify_folder(http, '/tmp/sdcard/A', 1, 'stale.flac')
        for flag in ('is_dir', 'is_cue', 'is_m3u', 'is_image'):
            http.directory.return_value = page(**{flag: True})
            with self.assertRaises(ValueError):
                verify_folder(http, '/tmp/sdcard/A', 0, '01.flac')
        for invalid in (dict(total=None, items=[]), dict(total=0, items=[]),
                        page(pos=True), page(total=True), page(pos=2),
                        page(is_dir=True)):
            http.directory.return_value = invalid
            with self.assertRaises(ValueError):
                verify_folder(http, '/tmp/sdcard/A')

    async def test_clients_preflight_and_send_exactly_once(self):
        for folder in (False, True):
            tcp, ws = self.clients()
            for client in (tcp, ws):
                http = Mock()
                http.catalog.return_value = http.directory.return_value = page()
                if folder:
                    result = client.play_folder('/tmp/sdcard/A', 0, http=http, expected_name='01.flac')
                    command = folder_command('/tmp/sdcard/A', 0, '01.flac')
                else:
                    result = client.play_genre('Genre Ё', http=http, album='Shared Album')
                    command = genre_command('Genre Ё', album='Shared Album')
                if client is ws:
                    await result
                    ws.send.assert_awaited_once_with(*command)
                else:
                    tcp.socket.sendall.assert_called_once_with(frame(*command))

    async def test_unknown_firmware_and_failed_preflight_do_not_select(self):
        for version in (240, '257', 257.0, None, 999, 257):
            tcp, ws = self.clients(version)
            http = Mock()
            http.catalog.return_value = http.directory.return_value = page(total=0)
            for client in (tcp, ws):
                for action in (lambda: client.play_genre('x', http=http),
                               lambda: client.play_artist('x', http=http),
                               lambda: client.play_folder('/tmp/sdcard/A', http=http)):
                    with self.assertRaises(ValueError):
                        result = action()
                        if client is ws:
                            await result
            if version != 257 or type(version) is not int:
                http.catalog.assert_not_called()
                http.directory.assert_not_called()
            tcp.socket.sendall.assert_not_called()
            ws.send.assert_not_awaited()

    async def test_invalid_input_and_uncertain_mutation_are_not_retried(self):
        tcp, ws = self.clients()
        http = Mock()
        for client in (tcp, ws):
            with self.assertRaises(ValueError):
                result = client.play_folder('/etc', http=http)
                if client is ws:
                    await result
        tcp.settings.assert_not_called()
        ws.settings.assert_not_awaited()
        http.directory.assert_not_called()
        tcp.socket.sendall.side_effect = ws.send.side_effect = TimeoutError('uncertain write')
        http.directory.return_value = page()
        for client in (tcp, ws):
            with self.assertRaises(TimeoutError):
                result = client.play_folder('/tmp/sdcard/A', http=http)
                if client is ws:
                    await result
        self.assertEqual(tcp.socket.sendall.call_count, 1)
        self.assertEqual(ws.send.await_count, 1)
