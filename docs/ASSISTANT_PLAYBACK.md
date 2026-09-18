# Assistant playback controls and queue

Two increments following ranked text playback, **2026-09-18**. Work remains in
`research/disc_assistant/`. See [commands](ASSISTANT_COMMANDS.md) for available
behavior and [the implementation plan](ASSISTANT.md) for the broader roadmap.
M2a controls and M2b native queue observation/continuation are implemented.

Validation on 2026-09-18: 97 prototype unit tests, 313 shared Python tests and
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
| `previous` | Stock previous; after >10 seconds this restarts the current track |

There is no confirmed absolute pause/play or separate network stop. Controller
uses `0201/0000`, `0201/0001` and `0201/0002`. Never emulate stop through power-off,
library reset, zero volume or seeking to the end. Evidence:
[remote control](REMOTE_CONTROL.md#timing-and-state), [capabilities](DISC_CAPABILITIES.md).

This short-lived CLI has no background queue executor. `Stop` reports continuation
as inactive and pauses the device; it does not claim to cancel nonexistent work.
When a persistent executor is introduced, stop must durably cancel pending
assistant launches even if device connectivity fails. Resume may continue the
native queue but must not revive a cancelled recommendation plan.

### Execution and state

1. Parse intent before opening search/storage. Under the shared device lock,
   connect, check handshake/firmware and retain interleaved events with one reader.
2. Respect the stock timing gate (existing tests use 2.1 seconds), then read fresh
   state immediately before acting. Unknown/loading or silent reads do not justify
   a blind toggle. Stopped-state resume remains unverified: require a new selection.
3. Return `already_satisfied` when appropriate. Otherwise mark the mutation attempt
   before socket I/O and send once. Observe state/context; never replay after a
   timeout or reconnect.
4. Pause/resume confirmation requires the expected state in the same recording
   context. Navigation requires an observed identity change or progress rollback
   for a restart. Same-title repeats and copies cannot be resolved from title alone.

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
- `controls.py`: fresh-state control execution; no search or catalog dependency.
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

Sequence: **M2a controls → M2b observed native queue and explicit mode policy →
M3 microphone**. Arbitrary recommendation-plan execution is a later increment;
it does not block controls, native continuation or first voice input.
