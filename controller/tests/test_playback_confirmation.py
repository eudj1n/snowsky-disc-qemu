"""Metadata differences must be corroborated by fresh source/queue evidence."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from controller.catalog import CatalogChanged
from controller.models import DeviceConfig
from controller.playback import album_matches, matches, verify_playing
from controller.queue import snapshot


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.config = DeviceConfig('localhost')
        self.album = 'Fixture Anniversary Edition'
        self.short = 'Fixture Anniversary Edit'
        self.selected = dict(kind='track', title='Track', artist='Artist', album=self.album)
        self.rows = [dict(pos=0, name='Track', author='Artist')]
        self.state = dict(state=0, playerflag=7, song=dict(song_name='Track',
            song_artist_name='Artist', song_album_name=self.short, pos_id=1))
        self.names = [self.album]
        self.http = Mock()
        self.http.catalog.side_effect = self.catalog
        self.client = Mock(timeout=1)
        self.client.now_playing.return_value = self.state
        self.client.take_events.return_value = []
        self.client.play_mode.return_value = 0

    def catalog(self, category, offset=0, limit=200, **filters):
        if category == 'artist/album':
            self.assertEqual(filters, {'artist': 'Artist'})
            rows = [dict(pos=i, name=name) for i, name in enumerate(self.names)]
        elif category == 'curlist/song':
            rows = self.rows
        else:
            raise AssertionError(category)
        return dict(total=len(rows), items=deepcopy(rows[offset:offset+limit]), mark=0)

    def queue(self):
        return snapshot(self.config, self.client, self.http, expected=self.rows,
                        selected=self.selected, selected_position=0)

    def test_shortened_album_requires_fresh_unique_name_and_queue(self):
        self.assertFalse(matches(self.state, self.selected, self.rows))
        result = verify_playing(self.client, self.selected, self.rows, 1,
                                config=self.config, http=self.http)
        self.assertEqual(result, self.state)
        self.assertEqual(self.queue()['state'], self.state)
        self.assertEqual(self.client.now_playing.call_count, 3)  # Final read after album HTTP.

    def test_exact_album_does_not_need_extra_catalog_reads(self):
        self.state['song']['song_album_name'] = self.album
        self.assertTrue(album_matches(self.state, self.selected, config=self.config, http=self.http))
        self.http.catalog.assert_not_called()

    def test_prefix_alone_missing_names_and_collisions_are_not_proof(self):
        self.assertFalse(album_matches(self.state, self.selected))
        for names in ([], [self.album, self.short], [self.album, self.album + ' Deluxe'],
                      [self.album, self.album]):
            self.names = names
            with self.subTest(names=names), self.assertRaisesRegex(CatalogChanged, 'ambiguous or absent'):
                self.queue()

    def test_changed_album_catalog_is_rejected(self):
        self.http.catalog.side_effect = [
            dict(total=1, items=[dict(pos=0, name=self.album)]),
            dict(total=1, items=[dict(pos=0, name=self.album + ' Deluxe')])]
        with self.assertRaisesRegex(CatalogChanged, 'albums changed'):
            album_matches(self.state, self.selected, config=self.config, http=self.http)

    def test_wrong_metadata_state_and_source_are_not_rescued(self):
        for key, value in [('song_name', 'Other'), ('song_artist_name', 'Other')]:
            state = deepcopy(self.state)
            state['song'][key] = value
            self.assertFalse(matches(state, self.selected, self.rows, album_verified=True))
        for fields in ({'state': 1}, {'state': 2}, {'playerflag': 3}):
            self.assertFalse(matches(dict(self.state, **fields), self.selected, self.rows, album_verified=True))
        for album in ('Other Album', '', None, self.album + ' Deluxe'):
            self.state['song']['song_album_name'] = album
            self.assertFalse(album_matches(self.state, self.selected, config=self.config, http=self.http))
        self.http.catalog.assert_not_called()

    def test_wrong_queue_position_is_rejected_even_for_identical_metadata(self):
        self.rows.append(dict(pos=1, name='Track', author='Artist'))
        with self.assertRaisesRegex(CatalogChanged, 'queue position differs'):
            snapshot(self.config, self.client, self.http, expected=self.rows,
                     selected=self.selected, selected_position=1)

    def test_queue_membership_and_playback_changes_still_reject(self):
        with self.assertRaisesRegex(CatalogChanged, 'queue differs'):
            snapshot(self.config, self.client, self.http,
                     expected=[dict(pos=0, name='Other', author='Artist')], selected=self.selected)
        self.client.now_playing.side_effect = [self.state, dict(self.state, state=1)]
        with self.assertRaisesRegex(CatalogChanged, 'playback changed'):
            self.queue()

    def test_timeout_keeps_compact_observation_for_diagnosis(self):
        diagnostics = {}
        with patch('controller.playback.time.monotonic', side_effect=[0, 0, 0, 2]), \
                patch('controller.playback.time.sleep'):
            self.assertIsNone(verify_playing(self.client, self.selected, self.rows, 1,
                                           diagnostics=diagnostics))
        self.assertEqual(diagnostics['last_observed']['album'], self.short)
        self.assertNotIn('song_file_path', diagnostics['last_observed'])
