"""Native queue observations; independent of search and recommendation policy."""
from collections import Counter
from controller.catalog import CatalogReader, CatalogChanged
from controller.playback import album_matches

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


def snapshot(config, client, http, *, expected=None, selected=None, selected_position=None):
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
        source = 3 if selected and selected['kind'] == 'album' and selected.get('artist') is None else 7
        if (state.get('state') != 0 or state.get('playerflag') != source or not 0 <= mark < result['total']
                or song.get('pos_id') != mark + 1
                or song.get('song_name') != result['items'][mark]['name']
                or song.get('song_artist_name') != result['items'][mark]['author']):
            raise CatalogChanged('queue selection is not confirmed by fresh playback state')
        if selected is not None and ((selected.get('artist') is not None and song.get('song_artist_name') != selected['artist']) or
                (selected['kind'] == 'track' and song.get('song_name') != selected['title'])):
            raise CatalogChanged('playback changed during queue observation')
        if selected_position is not None and mark != selected_position:
            raise CatalogChanged('queue position differs from the requested selection')
        if selected is not None and not album_matches(state, selected, config=config, http=http):
            raise CatalogChanged('playback album differs from the requested selection')
        if (selected is not None and selected.get('album') is not None
                and song.get('song_album_name') != selected['album']):
            fresh = client.now_playing()
            if any(fresh.get(key) != state.get(key) for key in ('state', 'playerflag', 'song')):
                raise CatalogChanged('playback changed while resolving the shortened album')
        # The extra HTTP reads for a shortened album can receive scan events too.
        client.scan_guard()
    result.update(mode=mode, mode_name=MODES[mode], state=state,
                  continuation=continuation(mode, result['total'], result['mark']),
                  consistency='two_equal_reads_not_atomic',
                  playback_known=bool(state.get('song')) and state.get('state') in (0, 1))
    return result


def _row_matches(state, row, index):
    from pathlib import PurePosixPath
    song = state.get('song') or {}
    names = {song.get('song_name'), PurePosixPath(song.get('song_file_path') or '').name}
    # Queue selection changes the source flag to type 0 even if the queue was
    # created from type 7. Position, row identity and stable membership are proof.
    return (song.get('pos_id') == index + 1
            and row['name'] in names and (not row['author'] or row['author'] == song.get('song_artist_name')))


def previous_in_queue(config, client, http):
    """One guarded predecessor selection, independent of elapsed time or shuffle history.

    At the start of the displayed queue, leave playback unchanged in every mode.
    No atomic device revision exists; observed races block or make the result uncertain.
    """
    import time
    from uuid import uuid4
    from controller.controls import identity
    result = {'operation_id': uuid4().hex, 'action': 'previous', 'status': 'not_sent',
              'mutation_attempted': False, 'navigation_policy': 'previous_queue_row'}
    try:
        if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
            raise ValueError('queue navigation requires reviewed DISC V2.57')
        time.sleep(2.1)
        before = snapshot(config, client, http)
        current = before['mark']
        state = before['state']
        if (state.get('state') not in (0, 1) or not 0 <= current < before['total']
                or not _row_matches(state, before['items'][current], current)):
            raise CatalogChanged('current queue position is not confirmed; no selection sent')
        if current == 0:
            return dict(result, status='already_satisfied', outcome='queue_start', state=state, queue=before)
        index = current - 1
        target = before['items'][index]

        class Guard:
            def catalog(self, category, offset=0, limit=200, **filters):
                if (category, offset, limit, filters) != ('curlist/song', index, 1, {}):
                    raise ValueError('unexpected queue selection preflight')
                fresh = snapshot(config, client, http)
                if (any(fresh[k] != before[k] for k in ('items', 'mark', 'mode'))
                        or identity(fresh['state']) != identity(state)
                        or fresh['state'].get('state') != state['state']):
                    raise CatalogChanged('queue or playback changed before selection')
                return {'total': fresh['total'], 'items': [fresh['items'][index]]}

        client.play_queue_index(index, http=Guard())
        result.update(mutation_attempted=True, selected_position=index)
        deadline = time.monotonic() + config.timeout
        while time.monotonic() < deadline:
            try:
                after = snapshot(config, client, http)
            except TimeoutError:
                continue
            if after['items'] != before['items'] or after['mode'] != before['mode']:
                raise CatalogChanged('queue changed after selection; selection was not retried')
            if (after['mark'] == index and after['state'].get('state') == 0
                    and _row_matches(after['state'], target, index)):
                return dict(result, status='confirmed', outcome='track_changed', state=after['state'], queue=after)
            time.sleep(.15)
        result.update(status='uncertain', reason='previous queue row not confirmed; selection was not retried')
    except (OSError, ValueError, RuntimeError) as exc:
        attempted = result['mutation_attempted'] or bool(client.mutation_attempted)
        result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted,
                      reason=str(exc), error_type=type(exc).__name__)
    return result
