import unittest
from unittest.mock import Mock, AsyncMock, call

from fiio_link import Client, frame
from fiio_ws import WSClient
from fiio_playlist import playlist_command


def page(pos=2, name='List Ё', total=4):
    return {'total': total, 'items': [{'pos': pos, 'name': name}], 'mark': -1}


class PlaylistTests(unittest.IsolatedAsyncioTestCase):
    def clients(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.settings = Mock(return_value={'soc_version': 257})
        ws = WSClient()
        ws.send = AsyncMock()
        ws.settings = AsyncMock(return_value={'soc_version': 257})
        return tcp, ws

    def test_wire_position_is_decimal_json_not_database_id(self):
        self.assertEqual(playlist_command(12, 1, 'List'), ('0100', '00010005{"id":12}'))
        self.assertEqual(frame(*playlist_command(0, None, 'Ё')),
                         b'010100140005{"id":0}')
        self.assertEqual(frame(*playlist_command(0, 1, 'Ё')),
                         b'0100001800010005{"id":0}')

    async def test_both_transports_check_http_and_send_once(self):
        for index in (None, 1):
            tcp, ws = self.clients()
            for client in (tcp, ws):
                http = Mock()
                http.catalog.side_effect = [page(), page(pos=index or 0), page()]
                if client is tcp:
                    client.play_playlist(2, index, http=http, expected_name='List Ё')
                    client.socket.sendall.assert_called_once_with(frame(*playlist_command(2, index, 'List Ё')))
                else:
                    await client.play_playlist(2, index, http=http, expected_name='List Ё')
                    client.send.assert_awaited_once_with(*playlist_command(2, index, 'List Ё'))
                self.assertEqual(http.catalog.call_args_list, [
                    call('custom', offset=2, limit=1),
                    call('custom/song', offset=index or 0, limit=1, src_list_id=2),
                    call('custom', offset=2, limit=1)])

    async def test_bad_arguments_fail_before_network_io(self):
        tcp, ws = self.clients()
        http = Mock()
        for pos, index, name in ((-1, 0, 'x'), (True, 0, 'x'), (2**31, 0, 'x'),
                                 (0, -1, 'x'), (0, True, 'x'), (0, 65536, 'x'),
                                 (0, 1.0, 'x'), (0, 0, ''), (0, 0, 'x\0y')):
            with self.assertRaises(ValueError):
                tcp.play_playlist(pos, index, http=http, expected_name=name)
            with self.assertRaises(ValueError):
                await ws.play_playlist(pos, index, http=http, expected_name=name)
        tcp.settings.assert_not_called()
        ws.settings.assert_not_awaited()
        http.catalog.assert_not_called()

    async def test_unknown_firmware_never_reads_http_or_selects(self):
        for settings in ({}, {'soc_version': 240}, {'soc_version': '257'},
                         {'soc_version': 257.0}, {'soc_version': 999}):
            tcp, ws = self.clients()
            tcp.settings.return_value = ws.settings.return_value = settings
            http = Mock()
            with self.assertRaises(ValueError):
                tcp.play_playlist(2, http=http, expected_name='List Ё')
            with self.assertRaises(ValueError):
                await ws.play_playlist(2, http=http, expected_name='List Ё')
            http.catalog.assert_not_called()
            tcp.socket.sendall.assert_not_called()
            ws.send.assert_not_awaited()

    async def test_empty_missing_shifted_renamed_and_malformed_never_select(self):
        bad = [page(total=0), page(pos=0), page(name='Renamed'),
               {'total': 4, 'items': []}, page(pos=True), page(total=True)]
        replies = [[item] for item in bad]
        replies += [[page(), page(total=0)], [page(), page(pos=0), page(name='Changed')]]
        for responses in replies:
            tcp, ws = self.clients()
            for client in (tcp, ws):
                http = Mock()
                http.catalog.side_effect = responses
                with self.assertRaises(ValueError):
                    if client is tcp:
                        client.play_playlist(2, http=http, expected_name='List Ё')
                    else:
                        await client.play_playlist(2, http=http, expected_name='List Ё')
            tcp.socket.sendall.assert_not_called()
            ws.send.assert_not_awaited()

    async def test_http_failure_never_selects_and_mutation_is_not_retried(self):
        tcp, ws = self.clients()
        for client in (tcp, ws):
            http = Mock()
            http.catalog.side_effect = TimeoutError('HTTP unavailable')
            with self.assertRaises(TimeoutError):
                if client is tcp:
                    client.play_playlist(2, http=http, expected_name='List Ё')
                else:
                    await client.play_playlist(2, http=http, expected_name='List Ё')
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_awaited()
        tcp.socket.sendall.side_effect = ws.send.side_effect = TimeoutError('uncertain write')
        for client in (tcp, ws):
            http = Mock()
            http.catalog.side_effect = [page(), page(pos=0), page()]
            with self.assertRaises(TimeoutError):
                if client is tcp:
                    client.play_playlist(2, http=http, expected_name='List Ё')
                else:
                    await client.play_playlist(2, http=http, expected_name='List Ё')
        self.assertEqual(tcp.socket.sendall.call_count, 1)
        self.assertEqual(ws.send.await_count, 1)
