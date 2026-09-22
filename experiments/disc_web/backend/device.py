"""Application projection. All playback mutations use the Controller facade."""
import threading
from collections import OrderedDict
import secrets
import time

from controller import DeviceConfig, DiscSession, QueueItem, Track
from controller.models import PlaybackSource
from controller.catalog import CatalogReader
from controller.fiio_http import HTTPClient


class BusyError(ValueError):
    pass


class Device:
    demo = False

    def __init__(self, config: DeviceConfig, *, session=None, http=None):
        self.config = config
        self.session = session or DiscSession(config)
        self.http = http or HTTPClient(config.host, config.http_port, config.timeout)
        self.lock = threading.Lock()
        self.state_guard = threading.RLock()
        self.generation_base = 0
        self.volume = None
        self.sources = OrderedDict()

    def _source(self, kind, rows, name='', artist=''):
        token = secrets.token_urlsafe(18)
        expected = tuple(QueueItem(row['pos'], row['name'], row['author']) for row in rows)
        self.sources[token] = dict(kind=kind, expected=expected, name=name, artist=artist,
                                   generation=self.session.snapshot().generation + self.generation_base, created=time.monotonic())
        if len(self.sources) > 32:
            self.sources.popitem(last=False)
        return token

    def _selection(self, value):
        if not isinstance(value, str) or ':' not in value:
            raise ValueError('a displayed selection is required')
        token, number = value.rsplit(':', 1)
        source = self.sources.get(token)
        if (not source or source['generation'] != self.session.snapshot().generation + self.generation_base
                or time.monotonic() - source['created'] > 600):
            raise ValueError('displayed source expired; refresh before selecting')
        index = int(number)
        if not 0 <= index < len(source['expected']):
            raise ValueError('position outside the displayed source')
        return source, index

    def __enter__(self):
        self.session.__enter__()
        return self

    def __exit__(self, *args):
        self.session.__exit__(*args)

    def state(self):
        with self.state_guard:
            value = self.session.snapshot().to_dict()
            value['generation'] += self.generation_base
            if value['connection'] != 'ready':
                self.volume = None
            return {**value, 'demo': False, 'volume': self.volume,
                    'busy': self.lock.locked(), 'endpoint': self.config.host,
                    'tcp_port': self.config.tcp_port, 'http_port': self.config.http_port}

    def protocol_generation(self, displayed):
        with self.state_guard:
            if type(displayed) is not int or displayed != self.state()['generation']:
                raise ValueError('Connection changed; refresh before sending')
            return displayed - self.generation_base

    def configure(self, config, generation):
        """Explicitly replace the sole owner; old browser selections never carry over."""
        if not self.lock.acquire(False):
            raise BusyError('Another operation is in progress. Nothing was queued.')
        try:
            self.protocol_generation(generation)
            if config != self.config:
                replacement = DiscSession(config)
                self.session.__exit__(None, None, None)
                with self.state_guard:
                    self.generation_base += self.session.snapshot().generation + 1
                    self.session, self.config = replacement, config
                    self.http = HTTPClient(config.host, config.http_port, config.timeout)
                    self.volume = None
                    self.sources.clear()
                    self.session.__enter__()
            self.session.connect()
            return {'status': 'observed', 'state': self.state()}
        finally:
            self.lock.release()

    def _rows(self, category, **filters):
        return CatalogReader(self.http, max_tracks=10000, max_requests=60).rows(category, **filters)

    def browse(self, kind, name='', artist=''):
        if not self.lock.acquire(False):
            raise BusyError('Another operation is in progress. Nothing was queued.')
        try:
            with self.session.operation() as client:
                client.scan_guard()
                categories = {'albums': 'album', 'artists': 'artist', 'tracks': 'all/song',
                              'favorites': 'love/song', 'playlists': 'custom'}
                if kind in categories:
                    rows = self._rows(categories[kind])
                    item_type = {'albums': 'album', 'artists': 'artist', 'playlists': 'playlist'}.get(kind, 'track')
                elif kind == 'album':
                    rows = (self._rows('artist/album/song', artist=artist, album=name) if artist
                            else self._rows('album/song', album=name))
                    item_type = 'track'
                elif kind == 'artist':
                    rows, item_type = self._rows('artist/album', artist=name), 'album'
                elif kind == 'playlist':
                    playlists = self._rows('custom')
                    matches = [r for r in playlists if r['name'] == name]
                    if len(matches) != 1:
                        raise ValueError('Playlist changed or its name is ambiguous. Refresh the library.')
                    rows = self._rows('custom/song', src_list_id=matches[0]['pos'])
                    if self._rows('custom') != playlists:
                        raise ValueError('Playlists changed while reading. Refresh the library.')
                    item_type = 'track'
                else:
                    raise ValueError('Unsupported library view')
                client.scan_guard()
                token = self._source(kind, rows, name, artist) if item_type == 'track' else None
                return {'kind': kind, 'name': name, 'items': [
                    {'id': str(r['pos']), 'title': r['name'], 'artist': r.get('author', ''),
                     'count': r.get('count'), 'type': item_type,
                     'scope_artist': name if kind == 'artist' else None,
                     'selection': f"{token}:{r['pos']}" if token else None,
                     'playable': kind in ('album', 'tracks', 'favorites', 'playlist'),
                     'album': name if kind == 'album' else None,
                     'editable': kind in ('tracks', 'playlist') or (kind == 'album' and not artist),
                     'art': None, 'duration': None} for r in rows]}
        finally:
            self.lock.release()

    def queue(self):
        if not self.lock.acquire(False):
            raise BusyError('Another operation is in progress. Nothing was queued.')
        try:
            result = self.session.queue().to_dict()
            if result.get('queue'):
                rows = result['queue']['items']
                token = self._source('queue', [dict(pos=r['position'], name=r['title'], author=r['artist']) for r in rows])
                for row in rows:
                    row.update(selection=f"{token}:{row['position']}", playable=True)
            return result
        finally:
            self.lock.release()

    def cover(self):
        if not self.lock.acquire(False):
            raise BusyError('Another operation is in progress.')
        try:
            with self.session.operation():
                return self.http.cover()
        finally:
            self.lock.release()

    def action(self, body):
        if not self.lock.acquire(False):
            raise BusyError('Another operation is in progress. Nothing was queued.')
        try:
            action = body.get('action')
            if not isinstance(action, str):
                raise ValueError('A named action is required')
            if action in ('connect', 'disconnect'):
                if 'generation' in body:
                    self.protocol_generation(body['generation'])
                getattr(self.session, action)()
                return {'status': 'observed', 'state': self.state()}
            state = self.state()
            if (state['connection'] != 'ready' or type(body.get('generation')) is not int
                    or body['generation'] != state['generation']):
                raise ValueError('Connection changed. Refresh the state before a new command.')
            if action in ('pause', 'resume', 'next', 'previous'):
                result = self.session.control(action)
            elif action == 'favorite':
                result = self.session.set_favorite(body.get('value'))
            elif action == 'volume':
                value = body.get('value')
                if type(value) is not int or not 0 <= value <= 120:
                    raise ValueError('Volume must be an integer in 0..120')
                result = self.session.set_volume(value)
            elif action == 'mode':
                result = self.session.set_play_mode(body.get('value'))
            elif action == 'album':
                album = body.get('name')
                if not isinstance(album, str) or not album or len(album) > 1024:
                    raise ValueError('An album name is required')
                artist = body.get('artist')
                result = (self.session.play_artist(artist, album=album) if artist is not None
                          else self.session.play_album(album))
            elif action == 'playlist':
                source, _ = self._selection(body.get('selection'))
                if source['kind'] != 'playlist' or source['name'] != body.get('name'):
                    raise ValueError('playlist selection scope changed')
                result = self.session.play_playlist(source['name'], expected=source['expected'])
            elif action == 'seek':
                expected = body.get('expected')
                fields = {'title', 'artist', 'album', 'queue_position', 'path', 'duration_ms'}
                if not isinstance(expected, dict) or set(expected) != fields or type(body.get('source')) is not int:
                    raise ValueError('displayed track and source are required')
                result = self.session.seek(body.get('position_ms'), expected=Track(**expected),
                                           source=PlaybackSource(body['source']))
            elif action == 'artist':
                result = self.session.play_artist(body.get('name'))
            elif action in ('track', 'queue', 'playlist_add', 'playlist_remove'):
                source, index = self._selection(body.get('selection'))
                expected = source['expected']
                if action == 'queue' and source['kind'] == 'queue':
                    result = self.session.play_queue_index(index, expected=expected)
                elif action == 'track' and source['kind'] == 'album':
                    result = (self.session.play_artist(source['artist'], album=source['name'], index=index, expected=expected)
                              if source['artist'] else self.session.play_album(source['name'], index=index, expected=expected))
                elif action == 'track' and source['kind'] in ('tracks', 'favorites'):
                    result = self.session.play_catalog_track(index, favorites=source['kind'] == 'favorites', expected=expected)
                elif action == 'track' and source['kind'] == 'playlist':
                    result = self.session.play_playlist(source['name'], index=index, expected=expected)
                elif action == 'playlist_add' and (source['kind'] == 'tracks' or (source['kind'] == 'album' and not source['artist'])):
                    result = self.session.add_playlist_track(body.get('name'), index, expected=expected,
                        album=source['name'] if source['kind'] == 'album' else None)
                elif action == 'playlist_remove' and source['kind'] == 'playlist':
                    result = self.session.remove_playlist_track(source['name'], index, expected=expected)
                else:
                    raise ValueError('selection scope does not match the requested operation')
            elif action == 'playlist_create':
                result = self.session.create_playlist(body.get('name'))
            elif action == 'playlist_rename':
                result = self.session.rename_playlist(body.get('name'), body.get('new_name'))
            else:
                raise ValueError('Unsupported operation')
            if result.volume is not None:
                self.volume = result.volume
            return result.to_dict()
        finally:
            self.lock.release()
