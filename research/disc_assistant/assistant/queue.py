"""Observe native queues; never treat search alternatives as a playlist."""
from collections import Counter
from uuid import uuid4

from controller.fiio_http import HTTPClient
from research.disc_assistant.assistant.device import PlaybackClient, device_lock
from research.disc_assistant.library.catalog import CatalogReader, CatalogChanged

MODES = ('list_once', 'random', 'repeat_one', 'repeat_list', 'single_once')


def read_queue(config, http):
    marks = []

    class Pages:
        def catalog(self, *args, **kwargs):
            page = http.catalog(*args, **kwargs)
            mark = page.get('mark')
            total = page.get('total')
            if (type(total) is not int or total < 0 or type(mark) is not int
                    or not -1 <= mark < total or (total == 0 and mark != -1)):
                raise CatalogChanged('missing or invalid queue mark')
            marks.append(mark)
            return page

    reader = CatalogReader(Pages(), page_size=config.page_size, max_tracks=config.max_tracks,
                           max_requests=config.max_requests)
    rows = reader.rows('curlist/song')
    if rows != reader.rows('curlist/song') or len(set(marks)) != 1:
        raise CatalogChanged('queue changed during observation')
    return {'items': rows, 'total': len(rows), 'mark': marks[0]}


def continuation(mode, total, mark):
    if not total:
        return 'empty'
    if mark < 0:
        return 'unknown_current_position'
    if mode == 0:
        return 'stop_after_current' if mark == total - 1 else 'remaining_queue_then_stop'
    return ('random_within_queue', 'repeat_current', 'wrap_queue', 'stop_after_current')[mode-1]


def snapshot(config, client, http, *, expected=None, selected=None):
    mode = client.play_mode()
    result = read_queue(config, http)
    # A fresh state read AFTER HTTP checks catches observed source replacement.
    # No stock atomic revision exists; report this as an observation, not a lease.
    try:
        state = client.now_playing()
    except TimeoutError:
        state = {}
    client.scan_guard()
    if client.play_mode() != mode:
        raise CatalogChanged('play mode changed during queue observation')
    if expected is not None:
        keys = lambda rows: Counter((r['name'], r['author']) for r in rows)
        if keys(result['items']) != keys(expected):
            raise CatalogChanged('actual queue differs from the requested source')
        song = state.get('song', {})
        mark = result['mark']
        if (state.get('state') != 0 or state.get('playerflag') != 7 or not 0 <= mark < result['total']
                or song.get('pos_id') != mark + 1
                or song.get('song_name') != result['items'][mark]['name']
                or song.get('song_artist_name') != result['items'][mark]['author']):
            raise CatalogChanged('queue selection is not confirmed by fresh playback state')
        if selected is not None and (song.get('song_artist_name') != selected['artist'] or
                (selected['kind'] == 'track' and
                 (song.get('song_name') != selected['title'] or song.get('song_album_name') != selected['album']))):
            raise CatalogChanged('playback changed during queue observation')
    result.update(mode=mode, mode_name=MODES[mode], state=state,
                  continuation=continuation(mode, result['total'], result['mark']),
                  consistency='two_equal_reads_not_atomic',
                  playback_known=bool(state.get('song')) and state.get('state') in (0, 1))
    return result


def observe(config):
    with device_lock(config.data_dir), PlaybackClient(config.host, config.tcp_port, config.timeout) as client:
        if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
            raise ValueError('queue observation requires reviewed DISC V2.57')
        result = snapshot(config, client, HTTPClient(config.host, config.http_port, config.timeout))
    return {'status': 'observed', 'queue': result}


def ensure_continuous(client):
    """One separately reported mode phase on the existing locked connection."""
    result = {'operation_id': uuid4().hex, 'requested': 3, 'status': 'not_sent', 'mutation_attempted': False}
    try:
        result['previous'] = client.play_mode()
        if result['previous'] == 3:
            return dict(result, status='already_satisfied')
        client.scan_guard()
        client.set_play_mode(3)
        if client.play_mode() != 3:
            raise ValueError('repeat-list mode not confirmed')
        result.update(status='confirmed', mutation_attempted=True)
    except (OSError, ValueError, RuntimeError) as exc:
        attempted = client.mutation_attempted
        result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted, reason=str(exc))
    return result
