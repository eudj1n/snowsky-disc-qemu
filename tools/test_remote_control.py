import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import socket

from fiio_link import Client, Frames, frame, index_payload, library_page, main, playback_snapshot
from fiio_ws import WSClient
from fiio_http import HTTPClient, Reply


class RemoteControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_physical_ios_http_queue_and_random_navigation(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_460_queue.json').read_text())
        response = observed['queue_response']
        reply = Reply(200, response['headers'], json.dumps(response['rows']).encode())
        with patch.object(HTTPClient, 'request', return_value=reply) as request:
            page = HTTPClient().catalog('curlist/song', limit=100)
        request.assert_called_once_with('GET', '/song_category_tree/', headers={
            'type': 'curlist/song', 'start-pos': '0', 'num-max': '100'})
        self.assertEqual((page['total'], page['mark']), (15, 0))
        [(tag, selector)] = Frames().feed(observed['commands'][0]['wire'].encode())
        self.assertEqual((tag, selector[:8]), ('0100', b'00020000'))
        self.assertEqual(selector[8:].decode(), 'Список воспроизведения')
        # Preserve the app's Unicode queue label and DISC's byte-counted length.
        self.assertEqual(frame(tag, selector).lower(),
                         observed['commands'][0]['wire'].encode().lower())
        states = [playback_snapshot(s['payload'].encode()) for s in observed['snapshots']]
        self.assertEqual([s['playerflag'] for s in states], [3, 0, 0, 0])
        self.assertEqual([s['playing_num'] for s in states], ['1/15', '3/15', '11/15', '3/15'])
        for state in states:
            position = state['song']['pos_id'] - 1
            self.assertEqual(page['items'][position]['pos'], position)
            self.assertEqual(page['items'][position]['name'], state['song']['song_name'])
        self.assertEqual(states[1]['song'], states[3]['song'])
        self.assertEqual(observed['initial_play_mode'], 1)  # Do not infer next = index + 1.
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        for event, method in zip(observed['commands'][1:], ('next_track', 'previous_track', 'play_pause')):
            getattr(tcp, method)()
            await getattr(ws, method)()
            expected = Frames().feed(event['wire'].encode())
            self.assertEqual(Frames().feed(tcp.socket.sendall.call_args.args[0]), expected)
            self.assertEqual(Frames().feed(frame(*ws.send.call_args.args)), expected)

    async def test_physical_ios_paused_seek_and_play_modes(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_460_seek_modes.json').read_text())
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        state = observed['initial']['state']
        mode = observed['initial']['play_mode']
        seeks, first_positions, changes = [], [], []
        pending_seek = None
        parser = Frames()
        for event in observed['events']:
            [(tag, payload)] = parser.feed(event['wire'].encode())
            if event['direction'] == 'app' and tag in ('0103', '0102'):
                value = int(payload, 16)
                method = 'seek' if tag == '0103' else 'set_play_mode'
                getattr(tcp, method)(value)
                await getattr(ws, method)(value)
                # These commands contain only hexadecimal numbers, so payload
                # case may differ too (iOS seek uses lowercase, our encoder uppercase).
                self.assertEqual(tcp.socket.sendall.call_args.args[0].lower(),
                                 event['wire'].encode().lower())
                self.assertEqual(frame(*ws.send.call_args.args).lower(),
                                 event['wire'].encode().lower())
                if tag == '0103':
                    self.assertEqual(state, 1)
                    seeks.append(value)
                    pending_seek = value
                else:
                    changes.append(value)
            elif event['direction'] == 'disc':
                if tag == 'a202':
                    state = playback_snapshot(payload)['state']
                elif tag == 'a103':
                    self.assertEqual(state, 0)  # No paused-position acknowledgement.
                    if pending_seek is not None:
                        first_positions.append((pending_seek, int(payload, 16)))
                        pending_seek = None
                elif tag == 'a102':
                    mode = int(payload, 16)
                    self.assertEqual(mode, changes[-1])
        self.assertEqual(seeks, [16090, 120401, 108392, 151953,
                                158311, 210113, 157604, 216235])
        self.assertEqual(first_positions, [(151953, 152000), (216235, 217000)])
        self.assertEqual(changes, [2, 3, 4, 0, 1])
        self.assertEqual([x['mode'] for x in observed['screenshots']], [1, *changes])
        self.assertEqual((state, mode), (1, 1))
        self.assertFalse(parser.buffer)

    async def test_physical_ios_playback_and_favorite_events(self):
        observed = json.loads((Path(__file__).parent / 'fixtures' /
                               'fiio_control_ios_460_playback.json').read_text())
        snapshots, deltas, positions, commands = [], [], [], []
        parser = Frames()
        for event in observed['events']:
            [(tag, payload)] = parser.feed(event['wire'].encode())
            if event['direction'] == 'app':
                commands.append((tag, payload))
            elif tag == 'a202':
                state = playback_snapshot(payload)
                if 'song' in state:
                    self.assertIsInstance(state['song'], dict)
                    self.assertIs(type(state['love']), bool)
                    snapshots.append(state)
                else:
                    deltas.append(state)
            elif tag == 'a103':
                positions.append(int(payload, 16))
        self.assertEqual(commands, [('0100', b'00000001'),
                                   *[('0201', b'0000')] * 3,
                                   ('0104', b'0001'), ('0104', b'0000')])
        self.assertEqual([s['state'] for s in snapshots], [2, 1, 1])
        self.assertEqual([s['love'] for s in snapshots], [False, True, False])
        self.assertEqual(snapshots[0]['song'], snapshots[1]['song'])
        self.assertEqual(snapshots[1]['song'], snapshots[2]['song'])
        self.assertEqual(deltas, [{'state': s} for s in (0, 0, 1, 1, 0, 0, 1, 1)])
        self.assertEqual(positions, list(range(1000, 12001, 1000)))
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        tcp.play_pause()
        await ws.play_pause()
        self.assertEqual(Frames().feed(tcp.socket.sendall.call_args.args[0]), [commands[1]])
        self.assertEqual(Frames().feed(frame(*ws.send.call_args.args)), [commands[1]])
        self.assertFalse(parser.buffer)

    def test_empty_transition_is_not_invented_playback_state(self):
        self.assertEqual(playback_snapshot(b''), {})
        self.assertEqual(playback_snapshot(b'{"state":1}'), {'state': 1})
        self.assertEqual(playback_snapshot(b'{"song":"{\\"id\\":3}","state":0}'),
                         {'song': {'id': 3}, 'state': 0})
        for malformed in (b'0000', b'[]', b'not json'):
            with self.assertRaises(ValueError):
                playback_snapshot(malformed)

    def test_invalid_cli_cannot_change_volume_before_rejecting_navigation(self):
        for args in (['--volume', '30', '--play-index', '-1'],
                     ['--play-all', '--list-type', '6'],
                     ['--next', '--previous'], ['--seek-ms', '-1']):
            with self.subTest(args=args), patch('sys.argv', ['fiio_link'] + args), \
                 patch('sys.stderr', io.StringIO()), patch('fiio_link.Client') as client:
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                client.assert_not_called()

    async def test_tcp_and_ws_wire_contract(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.settings = Mock(return_value={'soc_version': 257})
        ws = WSClient()
        ws.send = AsyncMock()
        ws.settings = AsyncMock(return_value={'soc_version': 257})
        # Literal wire examples independently pin tag, field order and units.
        cases = [
            ('next_track', (), b'0201000C0001'),
            ('previous_track', (), b'0201000C0002'),
            ('seek', (15000,), b'0103001000003A98'),
            ('set_play_mode', (3,), b'0102000C0003'),
            ('scan_library', (), b'0622000C0000'),
            ('play_index', (1,), b'0100001000010001'),
            ('play_index', (0, 6), b'0100001000000006'),
            ('play_index', (1, 3, 'CI Album'), b'0100001800010003CI Album'),
            ('play_all', (3, 'CI Album'), b'010100140003CI Album'),
        ]
        for method, args, expected in cases:
            with self.subTest(method=method, args=args):
                getattr(tcp, method)(*args)
                tcp.socket.sendall.assert_called_with(expected)
                await getattr(ws, method)(*args)
                self.assertEqual(frame(*ws.send.call_args.args), expected)

    async def test_favorite_selection_rejects_v240_and_unknown_before_write(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        for version in (240, 999):
            tcp.settings = Mock(return_value={'soc_version': version})
            ws.settings = AsyncMock(return_value={'soc_version': version})
            with self.assertRaises(ValueError):
                tcp.play_index(0, 6)
            with self.assertRaises(ValueError):
                await ws.play_index(0, 6)
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_called()

    async def test_invalid_commands_never_write(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        ws = WSClient()
        ws.send = AsyncMock()
        cases = [('seek', (-1,)), ('seek', (0x80000000,)), ('seek', (True,)),
                 ('seek', (1.5,)), ('set_play_mode', (5,)), ('set_play_mode', (True,)),
                 ('play_index', (-1,)), ('play_index', (65536,)), ('play_index', (True,)),
                 ('play_index', (0, 99)), ('play_index', (0, 3)),
                 ('play_index', (0, 3, 'x\0y')), ('play_index', (0, 3, 'Ё' * 128)),
                 ('play_all', (6,)), ('play_all', (1, 'unexpected'))]
        for method, args in cases:
            with self.subTest(method=method, args=args):
                with self.assertRaises(ValueError):
                    getattr(tcp, method)(*args)
                with self.assertRaises(ValueError):
                    await getattr(ws, method)(*args)
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_called()

    async def test_unicode_named_page_and_invalid_pages(self):
        tcp = Client.__new__(Client)
        tcp.request = Mock(return_value=b'0001[{"id":9,"title":"test"}]')
        ws = WSClient()
        ws.request = AsyncMock(return_value=tcp.request.return_value)
        self.assertEqual(tcp.library('album_tracks', 2, 'Ё'),
                         await ws.library('album_tracks', 2, 'Ё'))
        tcp.request.assert_called_with('0413', '0002Ё')
        self.assertEqual(frame(*tcp.request.call_args.args), b'0413000E0002\xd0\x81')
        self.assertEqual(frame('0100', index_payload(1, 3, 'Ё')), b'0100001200010003\xd0\x81')
        for payload in (b'', b'zzzz[]', b'0000{}', b'0001invalid'):
            with self.assertRaises(ValueError):
                library_page(payload)

    async def test_events_keep_coalesced_notifications_and_partial_frames(self):
        client = Client.__new__(Client)
        client.socket, peer = socket.socketpair()
        client.timeout, client.frames, client.pending = .1, Frames(), []
        try:
            peer.sendall(b'a2020013{"state":1}a103001000003')
            self.assertEqual(client.event(), ('a202', b'{"state":1}'))
            with self.assertRaises(TimeoutError):
                client.event(.01)
            self.assertIsNone(client.socket.gettimeout())
            peer.sendall(b'A98a102000C0003')
            self.assertEqual(client.event(), ('a103', b'00003A98'))
            self.assertEqual(client.event(), ('a102', b'0003'))
            peer.settimeout(.01)
            with self.assertRaises(TimeoutError):
                peer.recv(100)  # event timeout sends/replays no commands
        finally:
            client.close()
            peer.close()


if __name__ == '__main__':
    unittest.main()
