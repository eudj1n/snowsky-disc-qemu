"""Stock timing guard: idle fast path, fresh preflight and no replay."""
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

from controller.controls import control
from controller.device import MutationPacer, ObservedSocket
from controller.fiio_link import frame


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.waits = []
        self.clock = patch('controller.device.time.monotonic', side_effect=lambda: self.now)
        self.sleep = patch('controller.device.time.sleep', side_effect=self.advance)
        self.clock.start()
        self.sleep.start()
        self.addCleanup(self.clock.stop)
        self.addCleanup(self.sleep.stop)

    def advance(self, seconds):
        self.waits.append(seconds)
        self.now += seconds

    def peer(self, pacer=None):
        pacer = pacer or MutationPacer()
        session = SimpleNamespace(pacer=pacer, wait_for_mutation=pacer.wait,
            mutation_attempted=False, mutation_phase='selection', attempted_phases=set())
        raw = Mock()
        return session, raw, ObservedSocket(raw, session)

    def test_connection_quarantine_counts_elapsed_time_and_idle_has_no_delay(self):
        pacer = MutationPacer()
        self.now += .7  # handshake / initial reads count toward the interval
        pacer.wait()
        self.assertAlmostEqual(sum(self.waits), 1.4)
        self.waits.clear()
        self.now += 30
        pacer.wait()
        self.assertEqual(self.waits, [])

    def test_read_and_rejected_replay_do_not_extend_mutation_deadline(self):
        peer, raw, socket = self.peer()
        self.now += 10
        socket.sendall(frame('0202'))
        socket.sendall(frame('0201', '0000'))
        self.assertEqual(self.waits, [])
        self.assertTrue(peer.mutation_attempted)
        self.now += .6
        with self.assertRaisesRegex(RuntimeError, 'replay'):
            socket.sendall(frame('0201', '0000'))
        peer.attempted_phases.clear()  # next explicit operation, same connection
        socket.sendall(frame('0201', '0000'))
        self.assertAlmostEqual(sum(self.waits), 1.5)
        self.assertEqual(raw.sendall.call_count, 3)

    def test_mode_then_selection_waits_only_remaining_time(self):
        peer, raw, socket = self.peer()
        self.now += 10
        peer.mutation_phase = 'mode'
        socket.sendall(frame('0102', '0003'))
        self.now += .8  # mode readback
        peer.mutation_phase = 'selection'
        peer.wait_for_mutation()
        self.now += .2  # fresh source checks after the wait
        socket.sendall(frame('0101', '0007Artist'))
        self.assertAlmostEqual(sum(self.waits), 1.3)
        self.assertEqual(raw.sendall.call_count, 2)

    def test_failed_write_is_attempted_once_and_keeps_interval(self):
        peer, raw, socket = self.peer()
        self.now += 10
        raw.sendall.side_effect = OSError('lost')
        with self.assertRaises(OSError):
            socket.sendall(frame('0201', '0000'))
        self.assertTrue(peer.mutation_attempted)
        with self.assertRaisesRegex(RuntimeError, 'replay'):
            socket.sendall(frame('0201', '0000'))
        peer.wait_for_mutation()
        self.assertAlmostEqual(sum(self.waits), 2.1)
        raw.sendall.assert_called_once()

    def test_disconnect_during_wait_prevents_send_and_attempt_marker(self):
        closed = Mock()
        closed.is_set.return_value = False
        closed.wait.return_value = True  # disconnect wakes the wait
        peer, raw, socket = self.peer(MutationPacer(closed=closed))
        with self.assertRaises(ConnectionError):
            socket.sendall(frame('0201', '0000'))
        self.assertFalse(peer.mutation_attempted)
        self.assertEqual(peer.attempted_phases, set())
        raw.sendall.assert_not_called()

    def test_closed_idle_connection_never_sends(self):
        closed = threading.Event()
        peer, raw, socket = self.peer(MutationPacer(closed=closed))
        self.now += 30
        closed.set()
        with self.assertRaises(ConnectionError):
            socket.sendall(frame('0101', '0007Artist'))
        raw.sendall.assert_not_called()
        self.assertFalse(peer.mutation_attempted)

    def test_state_is_read_after_wait_so_external_pause_does_not_resume(self):
        client = Mock(mutation_attempted=False)
        pacer = MutationPacer()
        client.wait_for_mutation.side_effect = pacer.wait
        client.handshake.return_value = '0306'
        client.settings.return_value = {'soc_version': 257}
        client.take_events.return_value = []
        def state():
            self.assertGreaterEqual(self.now, 102.1)
            return {'state': 1, 'playerflag': 7, 'song': {'song_name': 'Track'}}
        client.now_playing.side_effect = state
        result = control(client, 'pause', 1)
        self.assertEqual(result['status'], 'already_satisfied')
        client.play_pause.assert_not_called()
        # Repeating this read-only operation must not start another interval.
        self.waits.clear()
        self.assertEqual(control(client, 'pause', 1)['status'], 'already_satisfied')
        self.assertEqual(self.waits, [])
