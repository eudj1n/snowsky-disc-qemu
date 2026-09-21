"""Search context derived from a fresh Controller queue observation."""
from controller.compatibility import Capability, require_client
from collections import Counter
from enum import Enum
from typing import Any, Callable, TypedDict
from controller.models import PlaybackSource, WirePlaybackState
from controller.fiio_link import Client
from experiments.disc_assistant.assistant.config import Config
from controller.controls import identity, observe, UnknownPlayback
from controller.queue import snapshot
from controller.fiio_http import HTTPClient
from controller.catalog import CatalogChanged


class QueueRow(TypedDict):
    name: str
    author: str
    pos: int


class CatalogDocument(TypedDict):
    id: str
    title: str
    artist: str
    album: str


class PlaybackContext(TypedDict):
    state: dict[str, Any]
    items: list[QueueRow]
    mark: int
    playback_known: bool


class SearchScope(str, Enum):
    ALBUM = 'album'
    ARTIST = 'artist'


ContextProvider = Callable[[], PlaybackContext | None]


def read(config: Config, client: Client) -> PlaybackContext | None:
    require_client(client, Capability.QUEUE_READ)
    try:
        before, _ = observe(client)
    except (UnknownPlayback, TimeoutError):
        return None
    if before.get('playerflag') not in (PlaybackSource.CURRENT_QUEUE, PlaybackSource.ARTIST,
                                      PlaybackSource.ALBUM, PlaybackSource.ARTIST_SCOPE):
        return None
    result = snapshot(config, client, HTTPClient(config.host, config.http_port, config.timeout))
    return result if result['playback_known'] else None


def scopes(context: PlaybackContext | None, documents: list[CatalogDocument]) -> list[tuple[SearchScope, list[CatalogDocument]]]:
    if not context:
        return []
    state = context['state']
    try:
        source = PlaybackSource(state.get('playerflag'))
        playback = WirePlaybackState(state.get('state'))
    except (ValueError, TypeError):
        return []
    if source not in (PlaybackSource.CURRENT_QUEUE, PlaybackSource.ARTIST,
                      PlaybackSource.ALBUM, PlaybackSource.ARTIST_SCOPE):
        return []
    if playback not in (WirePlaybackState.PLAYING, WirePlaybackState.PAUSED):
        return []
    song = state.get('song') or {}
    artist, album = song.get('song_artist_name'), song.get('song_album_name')
    items, mark = context['items'], context['mark']
    if (not 0 <= mark < len(items) or song.get('pos_id') != mark + 1
            or (items[mark]['name'], items[mark]['author']) != (song.get('song_name'), artist)):
        return []
    actual = Counter((r['name'], r['author']) for r in items)
    artist_docs = [d for d in documents if d['artist'] == artist]
    album_docs = [d for d in documents if d['album'] == album and (source == PlaybackSource.ALBUM or d['artist'] == artist)]
    same = lambda docs: bool(docs) and Counter((d['title'], d['artist']) for d in docs) == actual
    # Type 7 covers both artist and artist/album. Match complete membership;
    # metadata alone does not establish which source is playing.
    if source != PlaybackSource.ARTIST and same(album_docs):
        return [(SearchScope.ALBUM, album_docs), (SearchScope.ARTIST, artist_docs)]
    if source != PlaybackSource.ALBUM and same(artist_docs):
        return [(SearchScope.ARTIST, artist_docs)]
    return []


def verify(config: Config, client: Client, expected: PlaybackContext) -> None:
    fresh = read(config, client)
    if (fresh is None or fresh['items'] != expected['items'] or fresh['mark'] != expected['mark']
            or identity(fresh['state']) != identity(expected['state'])):
        raise CatalogChanged('playback context changed during search; request a new selection')
