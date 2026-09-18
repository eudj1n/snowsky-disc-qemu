"""Fresh artist selection and verified playback observations, without ranking."""
import time
from controller.fiio_link import playback_snapshot
from controller.catalog import CatalogChanged
from controller.events import merge_snapshot, validate_scan_events


class GuardedHTTP:
    """Recheck identity in the Controller's final HTTP preflight, not just bounds."""
    def __init__(self, http, category, filters, rows, index, client):
        self.http, self.category, self.filters = http, category, filters
        self.rows, self.index, self.client = rows, index, client

    def catalog(self, category, offset=0, limit=200, **filters):
        if (category, filters, offset, limit) != (self.category, self.filters, self.index, 1):
            raise ValueError('unexpected playback preflight scope')
        page = self.http.catalog(category, offset=offset, limit=limit, **filters)
        if page['total'] != len(self.rows) or page['items'] != [self.rows[self.index]]:
            raise CatalogChanged('selection changed immediately before playback; refresh the source')
        # settings() inside Controller retains scan events; check them just before
        # its sendall. No settings query drains away the evidence.
        self.client.scan_guard()
        return page


def matches(state, selected, rows):
    song = state.get('song')
    if state.get('state') != 0 or state.get('playerflag') != 7 or not isinstance(song, dict):
        return False
    artist, title = song.get('song_artist_name'), song.get('song_name')
    if artist != selected['artist']:
        return False
    if selected.get('album') is not None and song.get('song_album_name') != selected['album']:
        return False
    if selected['kind'] == 'track':
        return title == selected['title'] and song.get('song_album_name') == selected['album']
    return any(r['author'] == artist and r['name'] == title for r in rows)


def verify_playing(client, selected, rows, timeout):
    deadline = time.monotonic() + timeout
    state = {}
    while time.monotonic() < deadline:
        # A fresh read is evidence of the requested playback state, not a wire
        # acknowledgement or proof of audible output. Never repeat selection.
        client.timeout = max(.05, min(2, deadline - time.monotonic()))
        try:
            update = client.now_playing()
        except TimeoutError:
            update = {}
        events = client.take_events()
        validate_scan_events(events)
        for tag, payload in events:
            if tag == 'a202':
                state = merge_snapshot(state, playback_snapshot(payload))
        state = merge_snapshot(state, update)
        if matches(state, selected, rows):
            return state
        time.sleep(.15)
    return None
