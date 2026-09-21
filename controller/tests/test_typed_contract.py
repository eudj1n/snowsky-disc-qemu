"""Malformed input and typed-result regression contracts, without firmware."""
import json
from unittest import TestCase
from unittest.mock import Mock, patch

from controller import CommandResult, DeviceConfig, DiscSession, OperationStatus, PlaybackState
from controller.controls import observe
from controller.device import MutationPacer
from controller.fiio_link import Client, playback_snapshot
from controller.models import PlaybackSnapshot
from controller.models import PlaybackSource
from controller.session import LiveClient
from controller.tests.session_fixture import Server
from controller.wire import settings_snapshot


class WireContractTests(TestCase):
    def test_malformed_scalar_types_do_not_become_playback_evidence(self):
        song = {'song_name': 'Track', 'pos_id': 1}
        for key, values in {'state': [True, False, 0.0, '0', None],
                            'playerflag': [True, 3.0, '3', None],
                            'love': [0, 1, 'true', None]}.items():
            for value in values:
                state = {'state': 0, 'song': song, key: value}
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError):
                        playback_snapshot(json.dumps(state).encode())
                    with self.assertRaises(ValueError):
                        PlaybackSnapshot.from_wire(state)
                    with self.assertRaises(ValueError):
                        observe(Mock(now_playing=Mock(return_value=state)))

    def test_unknown_absent_loading_and_stopped_are_distinct(self):
        for state in ({}, {'state': 99, 'song': {'song_name': 'Track'}}, {'state': 1}):
            self.assertEqual(PlaybackSnapshot.from_wire(state).state, PlaybackState.UNKNOWN)
        self.assertEqual(PlaybackSnapshot.from_wire({'state': 2}).state, PlaybackState.LOADING)
        snapshot = PlaybackSnapshot.from_observation({'playback': 'stopped', 'state': {'state': 2}})
        self.assertEqual(snapshot.state, PlaybackState.STOPPED)

    def test_nested_song_json_is_validated_and_not_mutated(self):
        for song in ('[]', 'null', [], None, {'song_name': 123}, {'pos_id': True}, {'song_file_path': 123}):
            with self.subTest(song=song), self.assertRaises(ValueError):
                playback_snapshot(json.dumps({'state': 0, 'song': song}).encode())
        state = {'state': 0, 'song': json.dumps({'song_name': 'Track', 'pos_id': 1})}
        self.assertEqual(playback_snapshot(json.dumps(state).encode())['song']['song_name'], 'Track')
        self.assertIsInstance(state['song'], str)

    def test_settings_reject_boolean_version_and_volume(self):
        for state in ([], {'soc_version': True}, {'currentVolume': False},
                      {'currentVolume': 121}, {'currentVolume': '20'}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                settings_snapshot(json.dumps(state).encode())

    def test_persistent_client_has_no_raw_destructive_surface(self):
        self.assertFalse(issubclass(LiveClient, Client))
        for method in ('scan_library', 'reset_library', 'set_device_setting', 'set_peq', 'seek'):
            self.assertFalse(hasattr(LiveClient, method), method)


class TypedResultTests(TestCase):
    def test_conversion_retains_volume_error_and_unavailable(self):
        observed = CommandResult.from_result({'operation_id': 'read', 'status': 'observed',
            'state': {'state': 0, 'song': {'song_name': 'Track', 'song_file_path': '/synthetic.flac'}}},
            'now_playing')
        self.assertEqual(observed.playback.track.path, '/synthetic.flac')
        value = CommandResult.from_result({'operation_id': 'test', 'status': 'confirmed',
            'volume': 40, 'previous_volume': 20, 'mutation_attempted': True}, 'volume')
        self.assertEqual((value.volume, value.previous_volume), (40, 20))
        self.assertEqual(value.to_dict()['volume'], 40)
        value = CommandResult.from_result({'operation_id': 'test', 'status': 'unavailable',
                                           'error_type': 'TimeoutError'}, 'now_playing')
        self.assertEqual(value.status, OperationStatus.UNAVAILABLE)
        self.assertEqual(value.error_type, 'TimeoutError')

    def test_session_current_favorites_and_volume_use_typed_results(self):
        server = Server()
        self.addCleanup(server.close)
        with patch.object(MutationPacer, 'interval', 0), DiscSession(
                DeviceConfig('127.0.0.1', tcp_port=server.server_address[1], timeout=.2)) as player:
            player.connect()
            self.assertTrue(player.wait_ready(2))
            self.assertEqual(player.current_track().status, OperationStatus.OBSERVED)
            self.assertEqual(player.current_track().playback.source, PlaybackSource.ARTIST_SCOPE)
            self.assertTrue(player.set_favorite(True).playback.favorite)
            self.assertEqual(player.set_favorite(True).status, OperationStatus.ALREADY_SATISFIED)
            self.assertFalse(player.set_favorite(False).playback.favorite)
            result = player.set_volume(40)
            self.assertEqual(result.volume, 40)
            self.assertIsNotNone(result.previous_volume)
            self.assertEqual(player.adjust_volume(120).volume, 120)
            server.silent_now = True
            self.assertEqual(player.current_track().status, OperationStatus.UNAVAILABLE)
            server.drop_write = True
            result = player.set_volume(50)
            self.assertEqual(result.status, OperationStatus.UNCERTAIN)
            self.assertTrue(result.mutation_attempted)
            self.assertEqual(result.volume, 50)
