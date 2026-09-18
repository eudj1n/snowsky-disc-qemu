# Shared Controller session API

Implemented on **2026-09-18** for reviewed DISC **V2.57**. Assistant and a future
software remote can share connection/state/control behavior without interpreting
wire tags. This is an in-process Python API, not a new HTTP server or IPC daemon.

## Ownership and boundaries

| Layer | Owns |
| --- | --- |
| `controller.fiio_link`, `fiio_http`, `fiio_ws` | Existing diagnostic transport APIs, codecs and guarded stock operations |
| `controller.events`, `device`, `catalog` | Partial state reduction, scan guards, sequential event-preserving operations, bounded HTTP pagination |
| `controller.controls`, `playback`, `queue` | State-aware control, explicit mode readback, fresh selection verification and native queue observations |
| `controller.session`, `models` | One persistent receiver, serialized operations, reconnect without replay, normalized immutable snapshots/results |
| Assistant / application adapters | Language and intent, catalog persistence and ranking, automatic match policy, request journal, preferences and recommendation policy |
| Future application backend | One session shared by its adapters; browser authentication, HTTP/WebSocket presentation and optional local IPC |

Controller imports no Assistant, research, emulator, viewer or firmware components.
`DeviceConfig` contains only the device endpoint and transport/read budgets, with
physical ports 12100/12103 by default. Device compatibility is checked from the
remote handshake and reported version, not a local firmware profile.

The stock player accepts one TCP client. A reusable class does not allow separate
Assistant/remote processes to own simultaneous connections. A backend should own
one `DiscSession` and share it with its adapters. Optional `ownership=` accepts an
application-provided context manager held for the session lifetime; Controller
does not create lock files or select a personal data directory. Assistant keeps
its existing data-directory lock and thin configuration adapter in research.

## Use

Run from the repository root; no search server or Assistant database is needed:

```python
from controller.models import DeviceConfig, OperationStatus, PlayMode
from controller.session import DiscSession

config = DeviceConfig("192.168.1.50")  # Select the actual player explicitly.
with DiscSession(config) as device:
    device.connect()
    if not device.wait_ready(35):
        print(device.snapshot().to_dict())
    else:
        print(device.snapshot().playback.track)
        result = device.play_artist("Linkin Park", album="Meteora", index=0)
        if result.status == OperationStatus.PLAYING:
            print(device.queue().queue)
        print(device.pause().status.value)
        print(device.resume().status.value)
        # Optional explicit persistent setting; ordinary selections preserve mode.
        # device.set_play_mode(PlayMode.REPEAT_LIST)
```

The context owns receiver/connection-worker lifetime. Use `connect`/`disconnect`
inside that lifetime; create a new instance for a new target or process lifecycle.
Connection is asynchronous. `wait_ready` provides a bounded startup wait; ordinary
commands fail `not_sent` when not ready rather than waiting to execute after recovery.
Exit closes the link without stopping playback or restoring settings.

| Method | Contract |
| --- | --- |
| `connect()` | Enable connection and observation-only recovery |
| `disconnect()` | Close TCP, discard connection observations and disable recovery; application ownership remains until context exit |
| `wait_ready(timeout)` | Return whether initial acquisition reached ready before the deadline |
| `snapshot()` | Cached immutable `DeviceSnapshot`; no network read or mutation |
| `pause()` / `resume()` | Read fresh state, toggle only when necessary and verify the same recording context |
| `next_track()` / `previous_track()` | Send once, verify observed track change or progress rollback; previous after >10 seconds can restart |
| `control(action)` | Equivalent named pause/resume/next/previous dispatch; unsupported actions raise `ValueError` |
| `set_play_mode(mode)` | Accept `PlayMode` or its string value; read/set/read back once; already satisfied sends nothing |
| `queue()` | Read the full native queue twice under budgets, preserve duplicate rows and check mode/state consistency |
| `play_artist(artist, album=None, index=None)` | Read a fresh named source twice, check the final row, select once, then verify playback/queue; indexed playback requires an album |

Artist and album names are literal. This API does not search, rank or resolve
aliases. Indices are zero-based positions in the current artist-album source,
not permanent IDs or cached search offsets. Album Play all also verifies the
reported album. No atomic device revision exists, so external edits can still race
reads and mutations. Queue observation likewise is not a lease on its positions.

Physical playback reported on 2026-09-18 exposed different album text between
HTTP catalog and now-playing metadata: the latter can contain only a prefix of
the full catalog name. Confirmation accepts that difference only when two fresh
`artist/album` reads agree and the requested full name is the only name compatible
with the nonempty prefix. Title, artist, playing state and type-7 source remain
exact; the full native queue is checked and indexed playback must report the
requested position. A final state read follows the extra album queries. Ambiguous
prefixes, changed catalogs/queues and other metadata differences remain uncertain,
with no replay. No fixed truncation length or universal ID mapping is assumed.

## Normalized data and outcomes

`DeviceSnapshot` contains connection state, enabled flag, connection generation,
latest `PlaybackSnapshot` and any connection error. Connection states are
`disconnected`, `connecting`, `ready`, `reconnecting`. Playback states are
`unknown`, `loading`, `playing`, `paused`, `stopped`. Final stop requires observed
completion evidence; a missing reply or a loading snapshot alone cannot prove it.

`Track` exposes `title`, `artist`, `album`, and optional zero-based
`queue_position`. It is observed metadata, not a permanent recording identity.
`PlaybackSnapshot` additionally holds optional position in milliseconds, named
play mode, scan activity and observation time. Missing fields remain unknown.
Snapshots are detached immutable dataclasses; receiving another push cannot
mutate a previously returned snapshot. `to_dict()` on the top-level snapshot or
result is JSON-serializable, with string enum values through `json.dumps`.

`QueueSnapshot` contains immutable ordered `QueueItem` entries, selected position,
named mode, continuation policy and playback observation. Duplicate/CUE entries
stay separate. A retained queue after EOF does not establish active playback.

`CommandResult` provides an operation ID, action, `OperationStatus`, mutation-attempt
flag, playback observation, optional queue/outcome/reason, and requested/previous
mode for mode changes. Statuses are `not_sent`, `uncertain`, `confirmed`,
`already_satisfied`, `playing`, and read-only `observed`. `playing` verifies device
metadata/state, not audible output. An error after a possible write is uncertain;
never automatically repeat it. Operation results can have fewer fields than the
cached session snapshot; unknown state is not fabricated from earlier success.

The receiver continuously updates state, including while a caller blocks on HTTP,
search or user input. Adapters can read cached snapshots independently; a callback
subscription or browser event endpoint is not part of this first public surface.
Do not implement a second raw socket reader in a presentation adapter.

## Protocol and concurrency guarantees

The persistent core retains the prototype's single receiver, tagged-query
serialization, connection-generation checks, bounded event buffer, 2.1-second
mutation pacing and per-operation mutation guards. EOF/loss invalidates pending
work; reconnect repeats handshake and fresh observations only. Explicit disconnect
suppresses reconnect. Health reads use mode every 30 seconds when operations are
idle, with capped backoff/jitter after loss. Physical sleep/Wi-Fi behavior remains
a separate acceptance question.

The persistent session is currently **TCP only**. Existing diagnostic TCP/WS/HTTP
APIs remain available and compatible; they do not acquire these new lifecycle or
state guarantees automatically. Extending the facade to other transports or
settings requires its own tests and declared outcome semantics.

`status()` and `operation()` remain advanced adapter interfaces for Assistant's
existing output and fresh catalog-selection workflow. The operation lease pins a
client/generation and serializes work; callers must not retain the client beyond
the lease, nest operations, read its socket or construct an unreviewed mutation.
Its outbound persistent surface admits the four current read commands and four
reviewed playback/mode mutation tags only. Other inherited diagnostic methods,
such as volume or library reset, are rejected on this persistent client until
explicitly integrated. Use facade methods for new application features; do not
expose arbitrary tag forwarding through a web endpoint.

There is no native `stop()` in this API. Assistant maps its Stop intent to pause
while preserving position/queue. Repeat-list opt-in is likewise Assistant policy;
Controller only executes an explicitly requested named mode. History, preferences,
search results and automatic recommendation launches are not Controller features.

## Validation

The 2026-09-18 checkpoint passed 322 firmware-free Python tests (including nine
new session/boundary tests), 37 JavaScript tests and 142 Assistant prototype tests.
The disposable Typesense end-to-end check and generated-media V2.57 persistent
acceptance also passed. This checkpoint does not claim new physical-device validation.

The subsequent shortened-album fix passed 330 firmware-free Python tests, 37
JavaScript tests and 144 Assistant tests. Eight new Controller regression tests
cover corroborated prefixes, ambiguity, changing catalogs, wrong metadata/positions
and retained timeout observations. The generated V2.57 fixture independently
reproduces a shortened album in now-playing metadata; Assistant and the public
facade both confirm it through fresh catalog/queue evidence. The owner supplied
the physical failure and matching `/status`; physical revalidation of the fix is
still pending.

Controller unit tests use an independent synthetic wire peer and enforce the
production import boundary. They cover immutable state, one connection across
commands, idempotent pause/resume, uncertain writes, no replay, explicit disconnect,
final-stop silence, queue changes, named modes and rejection of unsupported operations.
Assistant regression tests preserve one-shot/console, Stop policy, ranking and
request-journal behavior. Synthetic wire fixtures deliberately retain raw tags;
they independently check the client rather than calling its encoders as a server API.

Generated-media V2.57 acceptance uses
`tests/integration/session_check.py`, invoked by the prototype's existing disposable
`emulator_check.sh OTA_PATH persistent` scenario. It exercises facade selection,
pause/resume, mode changes/readback, queue and normalized state on the same socket
as Assistant operations, then checks idle pushes, reconnect without replay and
healthy final-stop silence. It never uses personal media or the interactive volume.
