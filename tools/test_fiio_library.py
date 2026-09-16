import unittest
from unittest.mock import AsyncMock, Mock

from fiio_library import genre_command, folder_command, verify_folder, verify_genre
from fiio_link import Client, frame
from fiio_ws import WSClient


def page(pos=0, name='01.flac', total=1, **fields):
    row = dict(pos=pos, name=name, is_dir=False, is_cue=False, is_m3u=False, is_image=False)
    row.update(fields)
    return dict(total=total, items=[row], mark=-1)


class LibraryTests(unittest.IsolatedAsyncioTestCase):
    def clients(self, version=257):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.settings = Mock(return_value={'soc_version': version})
        ws = WSClient()
        ws.send = AsyncMock()
        ws.settings = AsyncMock(return_value={'soc_version': version})
        return tcp, ws

    def test_wire_context_and_utf8(self):
        self.assertEqual(genre_command('Genre Ё'), ('0101', '000AGenre Ё'))
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
