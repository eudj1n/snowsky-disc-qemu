"""Pure assertions for the generated six-second, three-track EOF scenario.

This is a test oracle, not a general client state reducer. Full metadata with
state 2 marks loading; only a metadata-free state 2 after progress zero is the
terminal sequence observed here. Duplicate playing deltas are not new tracks.
"""


def is_start(event):
    return event[1] == 'a202' and event[3] is not None


def is_stop(event):
    return event[1] == 'a202' and event[2:] == (2, None, None, None)


def validate(events, mode, start, order, duration=6):
    assert mode in range(5) and len(order) == 3 and len(set(order)) == 3
    assert events and all(a[0] <= b[0] for a, b in zip(events, events[1:]))
    starts = [i for i, event in enumerate(events) if is_start(event)]
    assert starts and starts[0] == 0, 'missing initial selected-track metadata'
    positions = []
    for i in starts:
        _, _, state, name, position, counter = events[i]
        assert name in order and state == 2
        index = order.index(name)
        assert position == index + 1 and counter == f'{index + 1}/3'
        positions.append(index)
    assert positions[0] == start
    stopped = mode in (0, 4)
    if mode == 0:
        assert positions == list(range(start, len(order)))
    elif mode == 4:
        assert positions == [start]
    elif mode == 2:
        assert len(positions) >= 3 and all(p == start for p in positions)
    elif mode == 3:
        assert len(positions) >= 3
        assert positions == [(start + i) % len(order) for i in range(len(positions))]
    else:
        # Membership and continued automatic playback, not a randomness test.
        assert len(positions) >= 4

    stops = [i for i, event in enumerate(events) if is_stop(event)]
    if stopped:
        assert len(stops) == 1 and stops[0] == len(events) - 1
        assert events[stops[0] - 1][1:] == ('a103', 0)
    else:
        assert not stops, 'loop/random mode unexpectedly stopped'

    for cycle, begin in enumerate(starts):
        end = starts[cycle + 1] if cycle + 1 < len(starts) else len(events)
        segment = events[begin:end]
        assert any(e[1] == 'a202' and e[2] == 0 for e in segment)
        ticks = [e for e in segment if e[1] == 'a103' and e[2] > 0]
        assert ticks and ticks[0][2] == 1000, 'progress did not restart at one second'
        assert all(a[2] <= b[2] for a, b in zip(ticks, ticks[1:]))
        complete = stopped or cycle + 1 < len(starts)
        if complete:
            assert ticks[-1][2] == duration * 1000, 'track did not reach its end'
            assert ticks[-1][0] - segment[0][0] >= duration - .5
            # Decoder-only transitions can omit the transient paused delta.
            # Completion still requires full duration/progress, next metadata,
            # correct queue order and (for the last track) the terminal sequence.
            if stopped and cycle == len(starts) - 1:
                assert any(e[1] == 'a202' and e[2] == 1 for e in segment)
    return positions
