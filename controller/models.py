"""Public device models. No wire tags, application configuration or storage paths."""
from dataclasses import asdict, dataclass
from enum import Enum


@dataclass(frozen=True)
class DeviceConfig:
    host: str
    tcp_port: int = 12100
    http_port: int = 12103
    timeout: float = 8
    page_size: int = 200
    max_tracks: int = 100000
    max_requests: int = 10000

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host.strip() or self.host != self.host.strip():
            raise ValueError('host must be a nonempty trimmed string')
        for name, low, high in (('tcp_port', 1, 65535), ('http_port', 1, 65535),
                                ('page_size', 1, 200), ('max_tracks', 1, 1000000), ('max_requests', 2, 100000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{name} outside {low}..{high}')
        if type(self.timeout) not in (int, float) or not 0 < self.timeout <= 120:
            raise ValueError('timeout must be in (0,120] seconds')


class ConnectionState(str, Enum):
    DISCONNECTED = 'disconnected'
    CONNECTING = 'connecting'
    READY = 'ready'
    RECONNECTING = 'reconnecting'


class PlaybackState(str, Enum):
    UNKNOWN = 'unknown'
    LOADING = 'loading'
    PLAYING = 'playing'
    PAUSED = 'paused'
    STOPPED = 'stopped'


class OperationStatus(str, Enum):
    NOT_SENT = 'not_sent'
    UNCERTAIN = 'uncertain'
    CONFIRMED = 'confirmed'
    ALREADY_SATISFIED = 'already_satisfied'
    PLAYING = 'playing'
    OBSERVED = 'observed'


class PlayMode(str, Enum):
    LIST_ONCE = 'list_once'
    RANDOM = 'random'
    REPEAT_ONE = 'repeat_one'
    REPEAT_LIST = 'repeat_list'
    SINGLE_ONCE = 'single_once'


MODES = tuple(PlayMode)


@dataclass(frozen=True)
class Track:
    title: str
    artist: str | None
    album: str | None
    queue_position: int | None

    @classmethod
    def from_wire(cls, state):
        song = state.get('song') or {}
        if not isinstance(song, dict) or not song.get('song_name'):
            return None
        position = song.get('pos_id')
        return cls(song['song_name'], song.get('song_artist_name'), song.get('song_album_name'),
                   position - 1 if type(position) is int and position > 0 else None)


@dataclass(frozen=True)
class PlaybackSnapshot:
    state: PlaybackState
    track: Track | None = None
    position_ms: int | None = None
    mode: PlayMode | None = None
    scan_active: bool | None = None
    observed_at: float | None = None

    @classmethod
    def from_observation(cls, observation):
        mode = observation.get('mode')
        return cls(PlaybackState(observation.get('playback', 'unknown')),
                   Track.from_wire(observation.get('state') or {}), observation.get('position_ms'),
                   MODES[mode] if type(mode) is int and 0 <= mode < len(MODES) else None,
                   observation.get('scan_active'), observation.get('observed_at'))

    @classmethod
    def from_wire(cls, state):
        state = state or {}
        track = Track.from_wire(state)
        value = state.get('state')
        label = ('playing' if value == 0 else 'paused') if track and value in (0, 1) else 'unknown'
        if value == 2:
            label = 'loading'  # A snapshot alone never proves final stop.
        return cls(PlaybackState(label), track)


@dataclass(frozen=True)
class QueueItem:
    position: int
    title: str
    artist: str


@dataclass(frozen=True)
class QueueSnapshot:
    items: tuple[QueueItem, ...]
    selected_position: int | None
    mode: PlayMode
    continuation: str
    playback: PlaybackSnapshot

    @classmethod
    def from_wire(cls, value):
        return cls(tuple(QueueItem(row['pos'], row['name'], row['author']) for row in value['items']),
                   value['mark'] if value['mark'] >= 0 else None, MODES[value['mode']],
                   value['continuation'], PlaybackSnapshot.from_wire(value.get('state')))


@dataclass(frozen=True)
class DeviceSnapshot:
    connection: ConnectionState
    enabled: bool
    generation: int
    playback: PlaybackSnapshot
    error: str | None = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_status(cls, status):
        return cls(ConnectionState(status['connection']), status['enabled'], status['generation'],
                   PlaybackSnapshot.from_observation(status['observation']), status.get('last_error'))


@dataclass(frozen=True)
class CommandResult:
    operation_id: str
    status: OperationStatus
    action: str
    mutation_attempted: bool
    playback: PlaybackSnapshot
    queue: QueueSnapshot | None = None
    outcome: str | None = None
    reason: str | None = None
    requested_mode: PlayMode | None = None
    previous_mode: PlayMode | None = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_result(cls, result, action):
        return cls(result['operation_id'], OperationStatus(result['status']), action,
                   result.get('mutation_attempted', False), PlaybackSnapshot.from_wire(result.get('state')),
                   QueueSnapshot.from_wire(result['queue']) if 'queue' in result else None,
                   result.get('outcome'), result.get('reason'),
                   MODES[result['requested']] if 'requested' in result else None,
                   MODES[result['previous']] if 'previous' in result else None)
