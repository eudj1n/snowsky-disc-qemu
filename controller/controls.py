"""Verified pause/resume/navigation over an event-preserving Controller client."""
import time
from uuid import uuid4
from controller.fiio_link import playback_snapshot
from controller.events import merge_snapshot, validate_scan_events
from controller.models import PlayMode, MODES

class UnknownPlayback(ValueError):
    pass


def identity(state):
    song = state.get('song')
    if not isinstance(song, dict) or not song.get('song_name'):
        return None
    return (state.get('playerflag'), *(song.get(k) for k in
            ('song_name', 'song_artist_name', 'song_album_name', 'pos_id')))


def observe(client):
    """A fresh snapshot, plus retained progress. Never infer stop from silence."""
    update = client.now_playing()
    events = client.take_events()
    validate_scan_events(events)
    state, position = {}, None
    for tag, payload in events:
        if tag == 'a202':
            previous = identity(state)
            state = merge_snapshot(state, playback_snapshot(payload))
            if identity(state) != previous or state.get('state') == 2:
                position = None
        elif tag == 'a103':
            try:
                position = int(payload, 16)
            except ValueError:
                raise ValueError('invalid playback progress') from None
    previous = identity(state)
    state = merge_snapshot(state, update)
    if previous is not None and identity(state) != previous:
        position = None
    # Only the query's response establishes a current playing/paused state.
    # Old retained notifications cannot rescue a blank/loading response.
    if update.get('state') not in (0, 1) or identity(state) is None:
        raise UnknownPlayback('current playback is unknown or loading; no blind control')
    return state, position


def verify(client, before, before_position, action, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client.timeout = max(.05, min(2, deadline - time.monotonic()))
        try:
            state, position = observe(client)
        except (TimeoutError, UnknownPlayback):
            time.sleep(.1)
            continue
        if action in ('pause', 'resume'):
            wanted = 0 if action == 'resume' else 1
            if state['state'] == wanted and identity(state) == identity(before):
                return state, 'playing' if wanted == 0 else 'paused'
        elif identity(state) != identity(before):
            return state, 'track_changed'
        elif before_position is not None and position is not None and position < before_position:
            return state, 'restarted'
        time.sleep(.15)
    return None, None



def control(client, action, timeout):
    if action not in ('pause', 'resume', 'next', 'previous'):
        raise ValueError('unsupported device control action')
    result = {'operation_id': uuid4().hex, 'action': action, 'status': 'not_sent', 'mutation_attempted': False}
    try:
        if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
            raise ValueError('controls require reviewed DISC V2.57')
        time.sleep(2.1)
        before, position = observe(client)
        wanted = 0 if action == 'resume' else 1
        if action in ('pause', 'resume') and before['state'] == wanted:
            return dict(result, status='already_satisfied', state=before)
        # ObservedSocket records the attempt before sendall can fail.
        getattr(client, {'pause': 'play_pause', 'resume': 'play_pause',
                         'next': 'next_track', 'previous': 'previous_track'}[action])()
        state, outcome = verify(client, before, position, action, timeout)
        result.update(status='confirmed' if state else 'uncertain', state=state,
                      outcome=outcome, mutation_attempted=True)
        if not state:
            result['reason'] = 'control outcome not confirmed; command was not retried'
    except (OSError, ValueError, RuntimeError) as exc:
        attempted = bool(client and client.mutation_attempted)
        result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted,
                      reason=str(exc), error_type=type(exc).__name__)
    return result


def set_mode(client, mode):
    """One explicitly requested persistent mode change, with readback and no replay."""
    mode = PlayMode(mode)
    requested = MODES.index(mode)
    result = {'operation_id': uuid4().hex, 'requested': requested, 'status': 'not_sent', 'mutation_attempted': False}
    try:
        client.begin_phase('mode')
        result['previous'] = client.play_mode()
        if result['previous'] == requested:
            return dict(result, status='already_satisfied')
        client.scan_guard()
        client.set_play_mode(requested)
        if client.play_mode() != requested:
            raise ValueError('play mode not confirmed')
        result.update(status='confirmed', mutation_attempted=True)
    except (OSError, ValueError, RuntimeError) as exc:
        result.update(status='uncertain' if client.mutation_attempted else 'not_sent',
                      mutation_attempted=client.mutation_attempted, reason=str(exc), error_type=type(exc).__name__)
    return result
