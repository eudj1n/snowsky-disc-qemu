"""One serialized playback operation, with fresh selectors and no mutation retries."""
from collections import Counter
from contextlib import contextmanager
import os
import time
from uuid import uuid4

from controller.fiio_link import Client, frame, playback_snapshot
from controller.fiio_library import artist_command
from controller.fiio_http import HTTPClient
from research.disc_assistant.assistant.session import check_events
from research.disc_assistant.library.catalog import CatalogReader, CatalogChanged
from research.disc_assistant.library.store import StaleSnapshot


@contextmanager
def device_lock(directory):
    # Local CLI invocations in this data directory share one device session.
    # Other controllers/data directories cannot participate in this local lock.
    import fcntl
    descriptor = os.open(directory / 'device.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another assistant device operation is active') from exc
        yield
    finally:
        os.close(descriptor)


def validate_scan_events(events):
    pending = iter(events)
    class Pending:
        def event(self, timeout):
            try:
                return next(pending)
            except StopIteration as exc:
                raise TimeoutError from exc
    check_events(Pending(), during_read=True)


class ObservedSocket:
    def __init__(self, socket, session):
        self.socket, self.session = socket, session

    def __getattr__(self, name):
        return getattr(self.socket, name)

    def sendall(self, data):
        if data[:4] in (b'0100', b'0101'):
            if self.session.mutation_attempted:
                raise RuntimeError('playback mutation replay refused')
            self.session.mutation_attempted = True
        return self.socket.sendall(data)


class PlaybackClient(Client):
    """One synchronous reader; retain unrelated events across Controller queries."""
    def __init__(self, *args):
        super().__init__(*args)
        self.observed = []
        self.mutation_attempted = False
        self.socket = ObservedSocket(self.socket, self)

    def retain(self, event):
        if len(self.observed) >= 10000:
            raise ValueError('device event budget exhausted')
        self.observed.append(event)

    def collect(self):
        for _ in range(10000):
            try:
                self.retain(super().event(timeout=.01))
            except TimeoutError:
                return
        raise ValueError('device event budget exhausted')

    def request(self, tag, payload=b'', *, expected=None):
        self.collect()
        self.socket.sendall(frame(tag, payload))
        expected = expected or 'a' + tag[1:].lower()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            event = super().event(timeout=max(.001, deadline - time.monotonic()))
            if event[0] == expected:
                return event[1]
            self.retain(event)
        raise TimeoutError(f'no {expected} reply')

    def scan_guard(self):
        self.collect()
        events, self.observed = self.observed, []
        validate_scan_events(events)


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
            raise CatalogChanged('selection changed immediately before playback; run sync')
        # settings() inside Controller retains scan events; check them just before
        # its sendall. No settings query drains away the evidence.
        self.client.scan_guard()
        return page


def fresh_selection(config, store, generation, selected, http):
    local = store.documents(generation)
    artist = selected['artist']
    filters = {'artist': artist}
    category = 'artist/song'
    if selected['kind'] == 'track':
        found = [d for d in local if d['id'] == selected['track_id']]
        if len(found) != 1 or any(found[0][k] != selected[k] for k in ('artist', 'album', 'title')):
            raise StaleSnapshot('candidate no longer matches the local snapshot')
        filters['album'] = selected['album']
        category = 'artist/album/song'
    scope = [d for d in local if d['artist'] == artist and
             ('album' not in filters or d['album'] == filters['album'])]
    reader = CatalogReader(http, page_size=config.page_size, max_tracks=config.max_tracks,
                           max_requests=config.max_requests)
    rows = reader.rows(category, **filters)
    if not rows or rows != reader.rows(category, **filters):
        raise CatalogChanged('playback source is empty or changing; run sync')
    if Counter((r['name'], r['author']) for r in rows) != Counter((d['title'], d['artist']) for d in scope):
        raise CatalogChanged('playback source differs from the snapshot; run sync')
    matching = [r for r in rows if r['name'] == selected.get('title') and r['author'] == artist]
    # Metadata-identical copies are not permanently distinguishable. Policy v1
    # chooses the first CURRENT matching row, not a cached snapshot position.
    index = matching[0]['pos'] if selected['kind'] == 'track' and matching else 0
    if selected['kind'] == 'track' and not matching:
        raise CatalogChanged('requested track disappeared; run sync')
    return category, filters, rows, index, len(matching)


def merge_snapshot(state, update):
    if not update:
        return state
    if isinstance(update.get('song'), dict) and update['song']:
        if update['song'] != state.get('song'):
            state = {}
    elif update.get('state') == 2:
        # Loading/EOF state cannot retain a previous song as current evidence.
        state = {}
    return {**state, **update}


def matches(state, selected, rows):
    song = state.get('song')
    if state.get('state') != 0 or state.get('playerflag') != 7 or not isinstance(song, dict):
        return False
    artist, title = song.get('song_artist_name'), song.get('song_name')
    if artist != selected['artist']:
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
        events, client.observed = client.observed, []
        validate_scan_events(events)
        for tag, payload in events:
            if tag == 'a202':
                state = merge_snapshot(state, playback_snapshot(payload))
        state = merge_snapshot(state, update)
        if matches(state, selected, rows):
            return state
        time.sleep(.15)
    return None


def execute(config, store, ranking):
    selected = ranking['candidates'][0]
    result = {'operation_id': uuid4().hex, 'selected': selected, 'status': 'not_sent'}
    client = None
    with device_lock(config.data_dir):
        try:
            if store.head(config.device_key)['generation'] != ranking['generation']:
                raise StaleSnapshot('catalog changed after ranking; repeat the command')
            artist_command(selected['artist'], 0 if selected['kind'] == 'track' else None,
                           selected.get('album'))
            with PlaybackClient(config.host, config.tcp_port, config.timeout) as client:
                if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
                    raise ValueError('playback requires reviewed DISC V2.57')
                # Stock navigation ignores rapid commands. Give previous activity
                # time to settle before fresh preflight; do not alter mode/volume.
                time.sleep(2.1)
                http = HTTPClient(config.host, config.http_port, config.timeout)
                category, filters, rows, index, equivalents = fresh_selection(
                    config, store, ranking['generation'], selected, http)
                client.scan_guard()
                if store.head(config.device_key)['generation'] != ranking['generation']:
                    raise StaleSnapshot('catalog changed before playback')
                guard = GuardedHTTP(http, category, filters, rows, index, client)
                client.play_artist(selected['artist'], index if selected['kind'] == 'track' else None,
                                   album=selected.get('album'), http=guard)
                state = verify_playing(client, selected, rows, config.timeout)
                result.update(status='playing' if state else 'uncertain', mutation_attempted=True,
                              fresh_position=index if selected['kind'] == 'track' else None,
                              metadata_equivalent_rows=equivalents, state=state)
                if not state:
                    result['reason'] = 'playback not confirmed before timeout; selection was not retried'
        except (OSError, ValueError, RuntimeError) as exc:
            attempted = bool(client and client.mutation_attempted)
            result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted,
                          reason=str(exc), retry='never automatic')
    return result
