# Assistant playback controls and queue

Playback and session increments following ranked text playback, **2026-09-18**. Work remains in
`experiments/disc_assistant/`. See [commands](ASSISTANT_COMMANDS.md) for available
behavior and [the implementation plan](ASSISTANT.md) for the broader roadmap.
M2a controls and M2b native queue observation/continuation are implemented.
M2c adds a persistent foreground text console. Existing one-shot commands remain
available for scripts and cron alongside the interactive application.

Earlier checkpoint on 2026-09-18: 116 prototype unit tests, 313 shared Python tests and
37 shared JavaScript tests pass. Disposable Typesense acceptance covers control
dispatch without search credentials/current index, queue pagination and explicit
repeat-list preparation. A separate generated-media V2.57 guest passed actual
pause/resume/stop/next, previous before/after ten seconds, native continuation
after Assistant disconnect, and type-7 natural EOF in all five modes. This does
not establish physical-device behavior or audible gapless transitions.

## M2a: current playback controls

Controls bypass Typesense and SQLite. Language dictionaries supply whole-phrase
pause/resume/stop/next/previous forms, while `Play Stop` remains a music request.
`rank` explains control intent offline; `ask` executes it.

| Intent | Contract |
| --- | --- |
| `pause` | One toggle from confirmed playing; no write if already paused |
| `resume` | One toggle from confirmed paused; no write if already playing |
| `stop` | Pause while retaining position and native queue; explicitly report pause semantics |
| `next` | One stock next command, then observe the actual result |
| `previous` | One explicit predecessor selection from the fresh queue, at every elapsed position; first row is a no-op |

There is no confirmed absolute pause/play or separate network stop. Native Controller controls
use `0201/0000`, `0201/0001` and `0201/0002`; Assistant previous instead uses guarded
queue-index selection (`0100`, type 0). Never emulate stop through power-off,
library reset, zero volume or seeking to the end. Evidence:
[remote control](REMOTE_CONTROL.md#timing-and-state), [capabilities](DISC_CAPABILITIES.md).

Neither the one-shot CLI nor the persistent console has a managed queue executor. `Stop` reports continuation
as inactive and pauses the device; it does not claim to cancel nonexistent work.
When a recommendation executor is introduced, stop must durably cancel pending
assistant launches even if device connectivity fails. Resume may continue the
native queue but must not revive a cancelled recommendation plan.

### Execution and state

1. Parse intent before opening search/storage. Under the shared device lock,
   connect (or borrow the persistent session), check handshake/firmware and retain
   interleaved events with one reader.
2. Wait only for the remaining stock 2.1-second mutation interval, then read fresh
   state immediately before acting. Unknown/loading or silent reads do not justify
   a blind toggle. Stopped-state resume remains unverified: require a new selection.
3. Return `already_satisfied` when appropriate. Otherwise mark the mutation attempt
   before socket I/O and send once. Observe state/context; never replay after a
   timeout or reconnect.
4. Pause/resume confirmation requires the expected state in the same recording
   context. Assistant previous requires the expected queue position, matching row
   and unchanged membership/mode after a single selection; a restart cannot pass.
   Native next still observes identity change/progress. Same-title copies cannot
   be resolved from title alone. Queue selection legitimately changes the source
   flag to type 0, so confirmation must not require the original artist type 7.

Initial connection refusal is retried within the configured timeout, before any
handshake/mutation. This accommodates the stock listener's delayed reopening;
it is not reconnection or replay of an established operation.

Stock navigation is rate-limited by integer seconds. External controls and EOF
can race the final read; absolute idempotence cannot be guaranteed over a toggle.
A mismatched outcome is uncertain, not grounds for a second corrective toggle.
A future pending-operation queue must prioritize stop over unsent auto-launches;
it cannot retract bytes already sent.

Full `a202 state=2` can mean loading. Empty replies and `0202` timeouts are not
proof of stop. Observed final EOF resets `a103` to zero then sends metadata-free
state 2; subsequent `0202` can be silent. A reconnect without event history leaves
state unknown. Transient state 1 at EOF is not proof of a user pause.
See [EOF evidence](TRACK_END.md).

### Implementation and acceptance

- `device.py`: shared lock, event-preserving sequential client, mutation-attempt
  tracking for selection/mode/control commands.
- `controls.py`: fresh-state control execution; previous uses live queue HTTP
  observations through Controller, without search or a local catalog dependency.
- Unit tests cover RU/EN phrases, title collisions, no-op pause/resume, missing
  search credentials, unknown/loading state, external track change, uncertain
  writes without replay, and progress evidence for previous-to-start.
- Synthetic transport acceptance checks real CLI and Controller dispatch. Firmware
  acceptance additionally covers previous before/after 10 seconds, actual state
  events and native random continuation. Physical audio is a separate observation.

## M2b: source context and continuation

Search answers “which recording starts”; a queue answers “what follows”. Ranked
search alternatives can contain competing versions, copies and other artists;
they must not be treated as a continuation playlist.

### Native queue first

Current track launch uses `play_artist(artist, index, album=album)`: a position in
an artist-scoped album, type 7. Artist requests use the whole artist catalog.

Now-playing album text can be shorter than the full HTTP catalog name, as seen
on the physical player on 2026-09-18. The shared Controller resolves a nonempty
album prefix only against two equal, fresh artist-album listings with exactly one
compatible name, then verifies native queue membership and the requested position.
Ambiguous prefixes remain uncertain. Title/artist equality is not relaxed, and no
selection is retried. See [the confirmation contract](CONTROLLER_API.md#use).
Results and the request journal retain `confirmation.last_observed` (state, source
type, title, artist, album and wire `pos_id`) even when confirmation times out;
`state: null` still means playback was not confirmed, not that it stopped.
Controller tests establish these source memberships; the first Assistant slice
verified the selected track, not audible continuity. See
[artist-scoped playback](LIBRARY_BROWSING.md#browse-and-play).

The first policy is **track → its artist-scoped album; artist → its catalog**.
Read all HTTP `curlist/song` pages after selection, compare the expected membership
and selected row, and report the actual queue/order, source and mode. A failed
post-dispatch check must not trigger an automatic corrective selection.

| Mode | Expected continuation |
| --- | --- |
| 0 — list once | Advance to the end; a selected last track stops afterward |
| 1 — random | Continue within the queue; no non-repetition or next-position guarantee |
| 2 — repeat one | Repeat the current recording |
| 3 — repeat list | Wrap from the final entry to the first |
| 4 — single once | Stop after the selected recording, regardless of queue length |

Natural behavior was originally checked on a short custom queue. The Assistant
acceptance now also checks type-7 EOF, with gapless/folder jump off, using three
six-second generated tracks. Do not promise untested preference behavior or
gapless audible transitions. See [EOF](TRACK_END.md).

Preserve device mode by default and report restrictions. The explicit
`[playback].continuous_context = true` setting sets mode 3 with readback verification.
Opting in authorizes that behavior without a confirmation for each request.
Mode changes persist on the player; expose them and do not restore settings
silently when CLI exits. The default is false, including for older configs.

At an album's end, continuous context wraps to its beginning; it does not add
music from other albums. A one-entry source repeats; an empty source cannot play.
Mode change and track selection are separate mutations: record each outcome,
stop on uncertainty, and never retry or automatically roll back a partial result.
Both phases share one TCP connection; each can dispatch once. Results preserve
the mode phase even when the subsequent selection or queue verification fails.

### Later: Assistant recommendation queues

A separate `QueuePlan` should contain the chosen starting recording, bounded
continuation candidates, selection policy, catalog generation, inclusion reasons
and execution status. Start with the same artist; expansion by genre/similarity
must be an explicit policy. History, likes and embeddings become inputs only
when available. Identical names or device IDs are insufficient to merge recordings
or deduplicate CUE entries across snapshots.

| Object | Owner and role |
| --- | --- |
| Catalog/search features | `library`: snapshots, availability and ranking inputs |
| Continuation plan | `assistant`: request, policy, intended sequence and cancellation |
| Observed device queue | Current session: fresh HTTP rows, source and selected mark |

No verified API writes an arbitrary ordered active queue. A custom playlist is
one candidate backend, but insertion order does not establish playback order and
playlist positions change. Verify order/membership and ownership/lifecycle before
using it; a matching name alone does not establish ownership. See [PLAYLISTS.md](PLAYLISTS.md).

Another backend is a persistent Assistant session that observes completion and
selects the next recording. It must coordinate with native auto-advance: do not
let both independently launch the next track. A possible single-once execution
mode requires explicit opt-in and separate validation. Gaps can occur, and losing
the host ends managed continuation. The current CLI cannot execute after exit.

Persistent execution needs one TCP reader, cancellation on stop/new requests,
suspension on pause, detection of external source changes, and loss of plan
ownership on reconnect. Never issue catch-up launches. A restarted process may
load a plan for display, but must not automatically start music.

### M2b acceptance

- Read actual queue/mode after selecting middle/last entries; verify natural EOF
  in all five modes, not just explicit next.
- Cover one entry, empty sources, overlapping artist/album names, CUE/copies and
  externally replaced queues.
- Preserve mode by default; verify each step separately for explicit continuous
  context, including partial failure after a mode write.
- Stop/pause must not start continuation. Native queues must continue according
  to device mode after Assistant exits.
- Verify type-7 context/EOF in an isolated emulator; record physical behavior and
  audible transitions separately. One successful album launch does not establish
  arbitrary recommendation-queue execution.

## M2c: persistent device session

Implemented on 2026-09-18: keep DISC TCP open while the foreground Assistant
application is running and connection is enabled. The interactive console submits
work to that shared session. One-shot CLI commands retain their existing lifecycle
for scripts/cron. Future voice input can use the same application interface;
local IPC and a separate daemon are not required for this first slice.

### Ownership and lifecycle

- One application owns one device connection, one reader, the state reducer and
  serialized operations. The device ownership lock lasts for the process lifetime.
  Catalog synchronization borrows the session and uses the matching HTTP endpoint.
- Connection state (`disconnected`, `connecting`, `ready`, `reconnecting`) is
  separate from playback (`unknown`, `loading`, `playing`, `paused`, observed
  final stop). Observations and pending work belong to a connection generation.
- Connect performs handshake, V2.57 validation and bounded fresh reads of settings,
  play mode and playback. Queue rows are fetched by `/queue` and playback execution,
  not on every reconnect. A silent `0202` after EOF leaves playback unknown unless
  observed events establish stop; it does not alone mean the link is dead.
- Unexpected EOF/error invalidates connection observations and pending work.
  Reconnect starts with 0.5-second backoff, doubling to 15 seconds with ±20% jitter;
  a session stable for 30 seconds resets the backoff. No remote wake, fake touches
  or device power-policy changes are introduced.
- `/disconnect` disables reconnect and releases TCP for FiiO Control. `/connect`
  enables it asynchronously. The local ownership lock remains until exit. Shutdown
  closes the session without pausing playback, clearing queues or restoring modes.
  Music `Stop` remains a playback intent, distinct from disconnect or exit.
- The configured target is fixed for this process. Exit and restart to change it;
  selectors never migrate to a new connection generation.

### Events and command outcomes

A dedicated thread receives events between commands and during blocking HTTP or
search work. Tagged requests are serialized because the protocol has no request
IDs. Unsolicited updates use the same reducer: state-only deltas preserve metadata,
loading/final-stop observations remain distinct, and duplicate events do not
establish additional listens. Idle observations are bounded current state; active
operations have a bounded event buffer. This is not a listening-history store.

A non-`a202` request timeout retires the connection so a delayed tagged reply cannot
satisfy a later operation. `a202` is also unsolicited and can be silent after final
stop, so that timeout does not retire an otherwise healthy link. Health uses the
reviewed `0105` mode read every 30 seconds when no operation owns the client,
rather than continuous now-playing polling. Physical idle/sleep effects remain
unvalidated. New controls still require a fresh usable playback observation.

Unsent mutations are cancelled across connection generations. Writes that may
have started remain `uncertain`; reconnect restores observation only. Toggles,
navigation, mode changes and selections are never replayed. Each new selection
revalidates source rows. Shared Controller pacing enforces the 2.1-second mutation
interval across console commands and one-shot mode/selection phases. Since
2026-09-19, redundant unconditional operation sleeps are removed: elapsed idle and
preflight time count toward the interval. Fresh connections retain a conservative
initial interval; reads/no-ops do not restart it. Disconnect interrupts persistent
waits. State/catalog checks run after pacing, so a delayed toggle does not use a
pre-wait snapshot. See [Controller timing contract](CONTROLLER_API.md#protocol-and-concurrency-guarantees).

Device-operation results include an operation ID. The [request journal](ASSISTANT_HISTORY.md)
now links it to parsed input, search/selection evidence and observed outcomes.
Pending/interrupted records do not prove that nothing was dispatched. This is
local inspection storage, not an idempotent IPC result service or a replay queue;
a future asynchronous API must define operation lookup and caller retry semantics.

### Startup, one-shot compatibility and acceptance

`run.sh start` starts local Typesense (or checks externally managed remote search),
then connects, syncs, prepares the index and opens interactive input. All device
steps use one application session. `listen` opens the same console using existing
data without Docker startup or automatic sync/index. Search preparation failure
leaves controls available. See the [console commands](ASSISTANT_COMMANDS.md#interactive-console).

Startup and `/sync` compare complete ordered source rows after two fresh equal
catalog reads. Identical content reuses the existing snapshot generation; this
does not skip device observation or claim permanent identity. Startup reuses an
index only when generation/config match and the collection exists with the expected
count. A missing projection is rebuilt. Explicit `/index` always rebuilds.

One-shot `ask`, `sync`, `queue`, offline `search`, `rank`, `index` and local `status`
remain available with their JSON/nonzero-exit contract. Device operations reject
concurrent ownership of the same data directory; they do not forward over IPC.
`up`/`down` still manage Typesense alone. Native queues continue after either
interface exits without a background recommendation executor.

Validation on 2026-09-18:

- 114 prototype tests passed with the full firmware-free suite, followed by a
  focused interrupt/reconnect rejection tests (116 total). Coverage includes idle/slow-work
  events, late replies, scan retention, commands invalidated across generations,
  loss during writes without replay, explicit disconnect and thread cleanup.
- Disposable Typesense acceptance ran `start → sync/index → console` with one
  handshake/socket across commands, reused unchanged snapshots/indexes and rebuilt
  a missing collection. Existing one-shot acceptance also passed.
- Focused generated-media V2.57 acceptance verified shared sync/control/queue,
  unsolicited track changes between commands, observation-only reconnect, final
  EOF with silent `0202` on the same healthy socket, and disabled reconnect after
  explicit disconnect. Run `emulator_check.sh OTA_PATH persistent` to reproduce.

Physical sleep, Wi-Fi recovery, button transitions and competition with FiiO
Control require separate acceptance; emulator success does not establish them.
The [shared Controller API](CONTROLLER_API.md) now owns this session/state core
and verified device operations. Assistant retains its policy and request journal.
Physical playback/session validation and M3 microphone input follow separately.
Arbitrary recommendation-plan execution remains a later increment.


## Explicit previous-row policy (2026-09-18)

The owner selected deterministic previous-track semantics after the emulator
regression exposed the stock restart shortcut. `controller.queue.previous_in_queue`
and `DiscSession.previous_in_queue()` guard a single positional selection with
fresh queue/current-state reads and post-selection verification. Assistant uses
this path for all elapsed positions, including the native 10–12 second restart
interval. It does not send two previous commands or replay an uncertain selection.

First row returns `already_satisfied` with `outcome: queue_start` in every mode.
Random mode uses displayed queue order, not playback history. A predecessor
selection starts playback from paused state. `Client.previous_track()` and
`DiscSession.previous_track()` retain native firmware behavior. The optional
`http=` preflight on `Client.play_queue_index()` preserves its original TCP-only
behavior for existing callers. There is still no atomic device queue revision.
See [emulator regression results](ASSISTANT_EMULATOR_ACCEPTANCE.md).
