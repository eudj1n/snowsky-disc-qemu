"""Shared Controller facade acceptance on generated media in a disposable guest."""
from controller.models import ConnectionState, OperationStatus, PlaybackState, PlayMode


def check_session(session, *, artist, album, index):
    initial = session.client
    result = session.play_artist(artist, album=album, index=index)
    assert result.status == OperationStatus.PLAYING, result
    assert result.playback.track.artist == artist and result.playback.track.album == album, result
    assert result.queue is not None and result.queue.selected_position == index, result
    # Generated-media fixture explicitly exercises persistent mode writes/readback.
    original_mode = result.queue.mode
    alternate = PlayMode.LIST_ONCE if original_mode != PlayMode.LIST_ONCE else PlayMode.REPEAT_LIST
    assert session.set_play_mode(alternate).status == OperationStatus.CONFIRMED
    assert session.set_play_mode(original_mode).status == OperationStatus.CONFIRMED
    assert session.set_play_mode(original_mode).status == OperationStatus.ALREADY_SATISFIED
    for method, expected in [('pause', OperationStatus.CONFIRMED),
                              ('pause', OperationStatus.ALREADY_SATISFIED),
                              ('resume', OperationStatus.CONFIRMED)]:
        result = getattr(session, method)()
        assert result.status == expected, result
        assert session.client is initial
    queue = session.queue()
    assert queue.status == OperationStatus.OBSERVED and len(queue.queue.items) > 0, queue
    state = session.snapshot()
    assert state.connection == ConnectionState.READY and state.playback.state == PlaybackState.PLAYING, state
    assert state.playback.track.title == queue.queue.items[queue.queue.selected_position].title
    print('PASS: shared Controller API selects/pauses/resumes/sets mode/reads queue and normalized state on one socket', flush=True)
