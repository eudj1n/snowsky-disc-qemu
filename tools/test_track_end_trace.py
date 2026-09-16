"""Natural EOF assertions must reject loading/duplicate/partial-track false positives."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
from track_end_trace import validate

ORDER = ['A.wav', 'B.flac', 'C.flac']


def trace(positions, stopped):
    events = []
    for i, position in enumerate(positions):
        t = i * 7
        events += [(t, 'a202', 2, ORDER[position], position + 1, f'{position + 1}/3'),
                   (t + .1, 'a202', 0, None, None, None),
                   (t + .2, 'a202', 0, None, None, None)]
        complete = stopped or i < len(positions) - 1
        events += [(t + tick, 'a103', tick * 1000) for tick in range(1, 7 if complete else 2)]
        if complete:
            events.append((t + 6.3, 'a202', 1, None, None, None))
    if stopped:
        events += [(t + 6.7, 'a103', 0), (t + 6.7, 'a202', 2, None, None, None)]
    return events


class TrackEndTraceTests(unittest.TestCase):
    def test_all_modes(self):
        for mode, positions in ((0, [1, 2]), (4, [1]), (2, [1, 1, 1]),
                                (3, [2, 0, 1]), (1, [1, 0, 2, 1])):
            with self.subTest(mode=mode):
                self.assertEqual(validate(trace(positions, mode in (0, 4)), mode,
                                          positions[0], ORDER), positions)

    def test_random_does_not_pin_a_permutation(self):
        for positions in ([1, 2, 0, 2], [1, 0, 1, 2]):
            validate(trace(positions, False), 1, 1, ORDER)

    def test_automatic_transition_can_omit_pause_delta(self):
        # Observed in V2.57 full integration: 6000 ms, next full metadata,
        # playing deltas, restarted ticks; no state=1 between B and C.
        events = [e for e in trace([1, 2], True)
                  if not (e[1] == 'a202' and e[2] == 1 and e[0] < 7)]
        self.assertEqual(validate(events, 0, 1, ORDER), [1, 2])

    def test_terminal_pause_delta_still_required(self):
        events = [e for e in trace([1], True) if not (e[1] == 'a202' and e[2] == 1)]
        with self.assertRaises(AssertionError):
            validate(events, 4, 1, ORDER)

    def test_loading_state_is_not_terminal(self):
        with self.assertRaises(AssertionError):
            validate(trace([1], False), 4, 1, ORDER)

    def test_duplicate_playing_is_not_repeat(self):
        with self.assertRaises(AssertionError):
            validate(trace([1], False), 2, 1, ORDER)

    def test_incomplete_track_is_not_eof(self):
        events = [e for e in trace([1], True) if e[1:] != ('a103', 6000)]
        with self.assertRaises(AssertionError):
            validate(events, 4, 1, ORDER)

    def test_progress_must_restart(self):
        events = trace([1, 1, 1], False)
        events = [e for e in events if not (e[0] == 8 and e[1] == 'a103')]
        with self.assertRaises(AssertionError):
            validate(events, 2, 1, ORDER)

    def test_skipped_or_wrong_queue_entry(self):
        for mode, positions in ((0, [1]), (4, [1, 2]), (2, [1, 2, 1]), (3, [2, 1, 0])):
            with self.subTest(mode=mode), self.assertRaises(AssertionError):
                validate(trace(positions, mode in (0, 4)), mode, positions[0], ORDER)

    def test_wrong_position_metadata(self):
        events = trace([1], True)
        events[0] = (0, 'a202', 2, ORDER[1], 1, '2/3')
        with self.assertRaises(AssertionError):
            validate(events, 4, 1, ORDER)

    def test_zero_tick_required_for_terminal_sequence(self):
        events = trace([1], True)
        del events[-2]
        with self.assertRaises(AssertionError):
            validate(events, 4, 1, ORDER)

    def test_no_selection_after_terminal_stop(self):
        events = trace([1, 2], True) + [(15, 'a202', 2, ORDER[0], 1, '1/3')]
        with self.assertRaises(AssertionError):
            validate(events, 0, 1, ORDER)

    def test_immediate_synthetic_completion_rejected(self):
        events = [(e[0] / 100, *e[1:]) for e in trace([1], True)]
        with self.assertRaises(AssertionError):
            validate(events, 4, 1, ORDER)
