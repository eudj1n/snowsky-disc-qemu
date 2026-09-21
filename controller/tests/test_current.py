"""Current-track controls against synthetic clients and a persistent wire peer."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from controller.current import current
from controller.device import PlaybackClient, ObservedSocket, MutationPacer
from controller.fiio_link import Client, frame
from controller.session import DiscSession
from controller.models import DeviceConfig
from controller.tests.session_fixture import Server


class FakeClient:
    begin_phase = PlaybackClient.begin_phase
    set_volume = Client.set_volume
    set_favorite = Client.set_favorite

    def __init__(self):
        self.mutation_attempted = False
        self.mutation_phase = 'selection'
        self.attempted_phases = set()
        self.pacer = Mock()
        self.raw = Mock()
        self.raw.sendall.side_effect = self.send
        self.socket = ObservedSocket(self.raw, self)
        self.state = {'state': 0, 'love': False, 'playerflag': 7, 'song': {
            'song_name': 'Track', 'song_artist_name': 'Artist', 'song_album_name': 'Album', 'pos_id': 1}}
        self.volume = 30
        self.fail = False
        self.wait_for_mutation = Mock()
        self.scan_guard = Mock()

    def send(self, data):
        if self.fail:
            raise OSError('lost write')
        if data[:4] == b'0104':
            self.state['love'] = bool(int(data[8:], 16))
        elif data[:4] == b'0502':
            self.volume = int(data[8:], 16)

    def handshake(self):
        return '0306'

    def settings(self):
        return {'soc_version': 257, 'currentVolume': self.volume}

    def now_playing(self):
        return deepcopy(self.state)

    def take_events(self):
        return []


class CurrentTests(TestCase):
    def test_favorites_are_absolute_idempotent_and_read_back(self):
        for action, initial, expected in [('like', False, True), ('dislike', True, False),
                                         ('like', True, True), ('dislike', False, False)]:
            with self.subTest(action=action, initial=initial):
                client = FakeClient()
                client.state['love'] = initial
                result = current(client, action)
                self.assertEqual(result['status'], 'already_satisfied' if initial == expected else 'confirmed')
                self.assertEqual(client.state['love'], expected)
                self.assertEqual(client.raw.sendall.call_count, int(initial != expected))

    def test_unknown_favorite_or_loading_never_writes(self):
        for state in ({}, {'state': 2}, {'love': None}, {'love': 1}):
            client = FakeClient()
            client.state = {**client.state, **state} if state else {}
            self.assertEqual(current(client, 'like')['status'], 'not_sent')
            client.raw.sendall.assert_not_called()

    def test_favorite_change_between_reads_blocks_and_after_write_is_uncertain(self):
        for after_write in (False, True):
            client = FakeClient()
            before = deepcopy(client.state)
            changed = deepcopy(before)
            changed['song']['song_name'] = 'Other'
            states = [before, before, changed] if after_write else [before, changed]
            client.now_playing = Mock(side_effect=states)
            result = current(client, 'like')
            self.assertEqual(result['status'], 'uncertain' if after_write else 'not_sent')
            self.assertEqual(client.raw.sendall.call_count, int(after_write))

    def test_volume_uses_fresh_value_after_wait_and_clamps(self):
        for start, delta, expected in [(115, 20, 120), (5, -20, 0), (120, 20, 120)]:
            client = FakeClient()
            client.wait_for_mutation.side_effect = lambda: setattr(client, 'volume', start)
            result = current(client, 'volume', delta=delta)
            self.assertEqual(result['volume'], expected)
            self.assertEqual(client.volume, expected)
            self.assertEqual(client.raw.sendall.call_count, int(start != expected))

    def test_volume_rejects_invalid_arguments_and_missing_state(self):
        for arguments in ({}, {'value': True}, {'value': 121}, {'delta': 0}, {'value': 20, 'delta': 2}):
            client = FakeClient()
            with self.assertRaises(ValueError):
                current(client, 'volume', **arguments)
            client.raw.sendall.assert_not_called()
        client = FakeClient()
        client.volume = None
        self.assertEqual(current(client, 'volume', value=10)['status'], 'not_sent')
        client.raw.sendall.assert_not_called()

    def test_failed_sends_are_uncertain_and_never_replayed(self):
        for action, arguments in [('like', {}), ('volume', {'value': 50})]:
            client = FakeClient()
            client.fail = True
            result = current(client, action, **arguments)
            self.assertEqual(result['status'], 'uncertain')
            self.assertTrue(result['mutation_attempted'])
            self.assertEqual(client.raw.sendall.call_count, 1)
            with self.assertRaises(RuntimeError):
                client.socket.sendall(frame('0104' if action == 'like' else '0502', '0001'))
            self.assertEqual(client.raw.sendall.call_count, 1)

    def test_now_playing_is_read_only_and_does_not_wait(self):
        client = FakeClient()
        self.assertEqual(current(client, 'now_playing')['status'], 'observed')
        client.state = {}
        self.assertEqual(current(client, 'now_playing')['status'], 'unavailable')
        client.raw.sendall.assert_not_called()
        client.wait_for_mutation.assert_not_called()

    def test_real_persistent_socket_allows_only_reviewed_new_writes(self):
        server = Server()
        self.addCleanup(server.close)
        with patch.object(MutationPacer, 'interval', 0), DiscSession(DeviceConfig('127.0.0.1', tcp_port=server.server_address[1])) as session:
            session.connect()
            self.assertTrue(session.wait_ready(2))
            for action, arguments in [('like', {}), ('dislike', {}), ('volume', {'value': 50})]:
                with session.operation() as client:
                    self.assertEqual(current(client, action, **arguments)['status'], 'confirmed')
            self.assertEqual(server.writes, 3)
            with session.operation() as client:
                with self.assertRaises(AttributeError):
                    client.scan_library()
