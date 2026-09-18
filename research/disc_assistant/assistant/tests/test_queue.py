from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from research.disc_assistant.assistant import queue, playback
from research.disc_assistant.assistant.device import PlaybackClient, ObservedSocket
from controller.fiio_link import frame
from research.disc_assistant.assistant.tests import test_playback as fixtures


class QueueTests(unittest.TestCase):
    setUp = fixtures.PlaybackTests.setUp
    execute = fixtures.PlaybackTests.execute

    def test_mode_and_selection_each_allow_one_attempt_with_no_replay(self):
        client = PlaybackClient.__new__(PlaybackClient)
        client.mutation_attempted, client.mutation_phase, client.attempted_phases = False, 'selection', set()
        raw = Mock()
        socket = ObservedSocket(raw, client)
        client.begin_phase('mode')
        socket.sendall(frame('0102', '0003'))
        with self.assertRaises(RuntimeError):
            socket.sendall(frame('0102', '0003'))
        client.begin_phase('selection')
        socket.sendall(frame('0100', '00000007'))
        with self.assertRaises(RuntimeError):
            socket.sendall(frame('0101', '0007'))
        with self.assertRaises(RuntimeError):
            client.begin_phase('mode')
        self.assertEqual(raw.sendall.call_count, 2)

    def test_empty_queue_and_invalid_mark_are_not_playable(self):
        empty = Mock()
        empty.catalog.return_value = {'items': [], 'total': 0, 'mark': -1}
        self.assertEqual(queue.read_queue(self.config, empty)['total'], 0)
        empty.catalog.return_value['mark'] = 0
        with self.assertRaisesRegex(ValueError, 'mark'):
            queue.read_queue(self.config, empty)
    def test_queue_contains_actual_order_and_preserves_default_mode(self):
        result = self.execute()
        observed = result['queue']
        self.assertEqual([r['name'] for r in observed['items']], ['Earlier', 'Numb'])
        self.assertEqual(observed['mark'], 1)
        self.assertEqual(observed['continuation'], 'stop_after_current')
        self.assertNotIn('mode_change', result)

    def test_five_modes_and_empty_or_single_entry_context(self):
        expected = ['remaining_queue_then_stop', 'random_within_queue', 'repeat_current',
                    'wrap_queue', 'stop_after_current']
        for mode, behavior in enumerate(expected):
            self.assertEqual(queue.continuation(mode, 3, 1), behavior)
            self.assertEqual(queue.continuation(mode, 0, -1), 'empty')
        self.assertEqual(queue.continuation(0, 1, 0), 'stop_after_current')
        self.assertEqual(queue.continuation(3, 1, 0), 'wrap_queue')

    def test_queue_changes_after_send_are_uncertain_without_retry(self):
        original = self.http.catalog
        def changed(category, **kwargs):
            page = original(category, **kwargs)
            if category == 'curlist/song':
                page['items'] = [dict(row, author='Other') for row in page['items']]
            return page
        self.http.catalog = changed
        result = self.execute()
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(self.client.calls, 1)

    def test_queue_mark_must_remain_consistent_across_pages(self):
        self.config = replace(self.config, page_size=1)
        original = self.http.catalog
        def changed(category, **kwargs):
            page = original(category, **kwargs)
            page['mark'] = kwargs.get('offset', 0)
            return page
        self.http.catalog = changed
        with self.assertRaisesRegex(ValueError, 'changed'):
            queue.read_queue(self.config, self.http)

    def test_mode_change_during_observation_is_rejected(self):
        self.client.play_mode = Mock(side_effect=[0, 1])
        with self.assertRaisesRegex(ValueError, 'mode changed'):
            queue.snapshot(self.config, self.client, self.http)

    def test_unreadable_current_state_is_reported_unknown_for_read_only_queue(self):
        self.client.now_playing = Mock(side_effect=TimeoutError)
        observed = queue.snapshot(self.config, self.client, self.http)
        self.assertFalse(observed['playback_known'])
        self.assertEqual(observed['total'], 2)
        with self.assertRaisesRegex(ValueError, 'not confirmed'):
            queue.snapshot(self.config, self.client, self.http, expected=self.http.rows)

    def test_uncertain_mode_write_prevents_selection(self):
        self.config = replace(self.config, continuous_context=True)
        mode = {'status': 'uncertain', 'mutation_attempted': True}
        with patch.object(playback, 'ensure_continuous', return_value=mode):
            result = self.execute()
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(self.client.calls, 0)
        self.assertEqual(result['mode_change'], mode)

    def test_confirmed_mode_remains_visible_after_selection_failure(self):
        self.config = replace(self.config, continuous_context=True)
        self.http.rows = []
        mode = {'status': 'confirmed', 'previous': 0, 'requested': 3, 'mutation_attempted': True}
        with patch.object(playback, 'ensure_continuous', return_value=mode):
            result = self.execute()
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['mode_change'], mode)
        self.assertEqual(self.client.calls, 0)

    def test_mode_operation_sends_once_and_handles_lost_readback(self):
        self.client.play_mode = Mock(side_effect=[0, TimeoutError('readback lost')])
        def send(mode):
            self.client.calls += 1
            self.client.mutation_attempted = True
        self.client.set_play_mode = send
        with patch.object(queue, 'PlaybackClient', return_value=self.client):
            result = queue.ensure_continuous(self.client)
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(self.client.calls, 1)

    def test_already_repeat_list_has_no_mode_write(self):
        self.client.play_mode = Mock(return_value=3)
        self.client.set_play_mode = Mock()
        with patch.object(queue, 'PlaybackClient', return_value=self.client):
            result = queue.ensure_continuous(self.client)
        self.assertEqual(result['status'], 'already_satisfied')
        self.client.set_play_mode.assert_not_called()
