# DISC remote-control contract

This is the local-music contract for a separately hosted web remote. Commands use
stock FiiO Link TCP 12100. The emulator's WebSocket bridge transports the same
records; it does not add firmware capabilities. M21 has not been tested.
See [PROTOCOL.md](PROTOCOL.md) for framing and historical V2.40 probes.

## Commands

All numbers below are ASCII hexadecimal. Length includes the eight header bytes
and counts **UTF-8 bytes**, not characters. Complete examples:

| Action | Record | Meaning / readback |
|---|---|---|
| Toggle play/pause | `0201000C0000` | `a202` state, then fresh `0202` |
| Like current track | `0104000C0001` | Full `a202` with `love: true` |
| Unlike current track | `0104000C0000` | Full `a202` with `love: false` |
| Next | `0201000C0001` | Next entry in the active queue |
| Previous | `0201000C0002` | Previous entry near the start; **restart this track if position >10 s** |
| Seek to 15 seconds | `0103001000003A98` | Eight hex digits of **milliseconds**; `a103` position notifications |
| Repeat the list | `0102000C0003` | Four hex digits of mode; `a102` event and `0501.playMode` |
| Read play mode | `01050008` | `play_mode()` returns 0..4 from **`a102`**, not `a105`; four hex digits |
| Select second catalog entry | `0100001000010001` | Position `0001` (zero-based), then list type `0001` |
| Select third current-queue entry (physical iOS trace) | `0100003b00020000Список воспроизведения` | Index 2, list type 0, observed app-localized queue label; raw form only |
| Select third current-queue entry (client helper) | `0100001000020000` | `play_queue_index(2)` first checks current queue length through `0406`; no label needed in tested emulator |
| Select second album entry | `0100001800010003CI Album` | Position, list type 3, exact UTF-8 album name |
| Play whole album | `010100140003CI Album` | List type 3, name; starts the first album entry |
| Play all indexed songs | `0101000C0001` | List type 1 |
| Select first favorite (V2.57) | `0100001000000006` | Position 0 in built-in favorites |
| Select second custom-playlist track (V2.57) | `0100001800010005{"id":0}` | Track position 1, type 5, playlist position 0; [fresh HTTP preflight required](PLAYLISTS.md) |
| Play custom playlist (V2.57) | `010100140005{"id":0}` | First track of playlist position 0, not SQLite ID |
| Select internal favorite ID 3 (V2.40 diagnostic) | `0100001000030006` | Internal `MY_LOVE.ID`, **not reliably available from the favorites page** |

For all tracks, artists and albums, `0100` takes a **position in the chosen list,
not the `id` returned in a catalog record**. Favorites are version-specific (below).
`0101` takes the list type first, without a position. The tested selection
contexts are all tracks (1), artist (2), album (3) and, on V2.57, custom playlists (5)
and built-in favorites (6). Custom playlists use a [dedicated guarded helper](PLAYLISTS.md),
not the generic named-list helpers.
Artist and album play-all are also exercised over both transports in the emulator. Named artist/album helpers reject empty/NUL-containing names and
limit them to 255 UTF-8 bytes. This is a client bound, not a measured firmware maximum.
`unknown_album` / `unknown_artist` are stock special tokens; they are not the
localized display labels. Named-album acceptance uses real tags, not those fallback tokens.

**Favorites differ between V2.40 and V2.57, despite the same 0306 handshake.**
V2.40 forwards the first field as an internal `MY_LOVE.ID`; V2.57 translates a
network list position to that ID first. The `id`/`songId` returned by `0415` are
**not a reliable substitute** for V2.40's internal ID. A repeated add/remove test
produced wire ID 3 while the read-only database showed `MY_LOVE.ID=4`. A one-off
selection had worked only when those IDs happened to coincide.

`Client.play_index(index, 6)` / `WSClient.play_index(index, 6)` read `soc_version`
and allow the positional selector only for 257. V2.40 and unknown versions raise
`ValueError` before any selector is sent. The V2.40 wire example above documents
the internal-ID route, not a usable position-based API. General favorites selection
on V2.40 remains unsupported by these clients; favorites **reading** works.

A raw position-0 selector on V2.40 failed with a nonempty favorites queue and empty
`a202` payload; a known internal ID played the track. V2.40 also briefly emits an
empty `a202` while loading a valid favorites selection. Clients return `{}` for an
empty payload: no snapshot is available yet, and no playing/paused/stopped state
is inferred. Acceptance waits for a full matching snapshot. Other malformed JSON
still raises an error; arbitrary cleared/invalid selection recovery is not established.

The five local modes are **0 list once, 1 random, 2 repeat one, 3 repeat list,
4 single once**. Their names come from the stock playlist worker's switch/log
strings; acceptance verifies setting each value, its event, settings query and
persisted `PLAY_MODE`. V2.57 also has [natural EOF acceptance](TRACK_END.md) for
all five modes on a short WAV/FLAC custom queue over TCP/WS, with gapless/folder
jump off. It does not statistically test randomness or every source/queue type.
Values beyond 4 include other playback backends and are not exposed.

The user's iOS screenshots and `2026-09-15-235540.pcap` match the app's cycle:

| Screenshot | Icon | Value | Intended local behavior |
|---|---|---:|---|
| `IMG_6779.PNG` | Crossing arrows | 1 | Random track order |
| `IMG_6780.PNG` | Loop arrows with 1 | 2 | Repeat the current track |
| `IMG_6781.PNG` | Loop arrows | 3 | Repeat the current list |
| `IMG_6782.PNG` | Single arrow with 1 | 4 | Play this track once, then stop |
| `IMG_6783.PNG` | Two straight arrows | 0 | Play the list in order once, then stop |
| `IMG_6784.PNG` | Crossing arrows | 1 | Return to random order |

The trace starts with `0501.playMode: 1`, then sends `0102` values 2 → 3 → 4 → 0 → 1.
Every change receives a matching `a102`. The screenshot mapping uses the user's
reported ordering; screenshots show 00:00, after the 23:56 capture. Mode meanings
come from the stock worker analysis above; this short capture does not exercise
track/list completion or characterize random selection.

### Timing and state

- Navigation has a stock rate gate. In V2.57 `comm_play_ctrl` calls `4cb284` with
  threshold 1; it accepts only when the difference of **integer seconds is >1**.
  Tests wait 2.1 seconds between track selections/navigation. A dropped command
  has no success acknowledgement. Do not immediately retry it or infer success
  from the TCP/WS write completing.
- Seek truncates milliseconds down to whole seconds for local playback. A paused
  seek keeps the player paused; the next position tick after resume confirms it.
  There is no proven immediate seek acknowledgement or paused-position query.
  The iOS seek capture confirms two batches of four paused seeks, with no position
  or state updates until resume. Last targets 151953 and 216235 ms are followed by
  first ticks at 152000 and 217000 ms respectively. This agrees with whole-second
  progress after resume; the first tick alone is not an exact seek-rounding probe.
  A future remote can show the requested position immediately as pending, retain
  it while paused, and reconcile it with the next `a103`. Do not retry a seek only
  because the player has not acknowledged the paused position.
- `0201/0000` is a **toggle**, not idempotent play/pause. `0203` reaches an empty
  handler in V2.57; physical probes with `0000` and `0001` while paused did nothing.
  No absolute play/pause command is established. Read state first and observe the
  result; a reconnect must never replay an old toggle.
- `a202` is both a response and an unsolicited notification. It can be only
  `{"state":0}`, `{"state":1}` or `{"state":2}`. Merge deltas into known metadata;
  don't replace a full track with an empty object. A full snapshot may initially
  show a stopped/loading state before the later playing event.
- Wire state is **0 playing / 1 paused / 2 stopped**. Internal memory uses a
  different enum (1 playing / 2 paused / 3 stopped). They are not interchangeable.
- Natural final stop sends zero `a103`, then state-only `a202` with state 2.
  Fresh `0202` subsequently times out in the tested V2.57 modes 0/4, while mode
  reads and the retained HTTP queue still work. A timeout alone is **not** a
  stopped-state detector; see [EOF lifecycle and client implications](TRACK_END.md).
- No request IDs exist. Use one reader, serialize queries, route incoming frames
  by tag, and allow asynchronous transitions. The diagnostic clients intentionally
  discard pending notifications before queries; use `event()` without a query to
  observe pushes. They are not a production multi-browser state service.

The same seek capture contains a full `a202` about 54 ms after the initial `0202`,
with `state: 1`, before any control commands. Paused state therefore does not
itself prevent querying the current track. Earlier captures' initial silence
remains unexplained; a missing/uninitialized track context is a hypothesis, not
a confirmed cause. See [app evidence](FIIO_CONTROL_APP.md#ios-paused-seek-and-play-order-capture-2026-09-15).

## Physical iOS playback and favorite capture

The user's `2026-09-15-234648.pcap` confirms selection with `0100/00000001`,
then pause → resume → pause using three identical `0201/0000` commands. Selection
pushes a full `a202` snapshot initially reporting state 2, followed by state-only
notifications with state 0. Each play/pause transition produces **two identical
state-only notifications** (1, then 0, then 1). Position ticks advance in 1000-ms
steps, stop during the captured pause, and continue after resume. Consumers must
accept repeated state updates and retain metadata across state-only deltas.

While paused, `0104/0001` then `0104/0000` each produce a full `a202` for the same
track, with `love` false → true → false and state remaining 1. These commands set
the favorite flag of the **current track**; they are not a toggle or a general
track-ID API. The trace does not show a favorites-list refresh or durability
across restart. Existing disposable integrations independently check add/remove
against the built-in favorites list.

The app's initial `0202` again has no captured response; after selection it sends
no more `0202` queries. Thus the trace proves asynchronous full snapshots and
deltas during playback, not that a fresh `0202` query succeeds in that state.
No firmware patch or new handshake is needed to receive these pushes. See
[capture details](FIIO_CONTROL_APP.md#ios-playback-and-favorites-capture-2026-09-15)
and the [sanitized fixture](../tools/fixtures/fiio_control_ios_460_playback.json).

## Data schemas for the remote

### Current queue in the stock iOS app

The 2026-09-16 physical capture opens an album using `0101`, type 3 and the album
name, then reads `GET /song_category_tree/` with `type: curlist/song`. Its 15-row
response has `pos`, `name`, `author`, `count`, `total-num: 15` and `mark-pos: 0`.
This is a different schema from TCP `0406`; no `0406` or `0426` is sent by the app.
The HTTP album page and queue page contain identical records in identical order
in this capture. It does not establish that album and queue always share order.

Choosing the third queue row sends the exact byte-counted frame in the command
table above. DISC reports `playerflag: 0`, `playing_num: "3/15"`, nested
`song.pos_id: 3`, and the matching song. This capture alone did not establish
whether the Russian label was required. Subsequent disposable emulator checks
below establish the label-free helper. Generic `play_index()` still rejects type 0;
use the dedicated method with its bounds check.

Initial `0501.playMode` is 1 (random). Next moves **3 → 11**, previous returns
**11 → 3**; response song names/artists match the corresponding HTTP queue rows.
Use device-reported position; do not infer next/previous by arithmetic. This
single return does not prove a general shuffle-history algorithm. The queue is
not fetched again after selection/navigation, so its old `mark-pos: 0` is a
snapshot, not a live current-position field. `playing_num` and `pos_id` update
in full `a202` pushes; their positions are one-based, while HTTP `pos` and selector
indices are zero-based. Next's full snapshot arrives about 1.73 s after the command,
with old-track ticks in between: do not infer completion from a write or a tick.

See [capture details](FIIO_CONTROL_APP.md#ios-current-queue-capture-2026-09-16)
and the [sanitized fixture](../tools/fixtures/fiio_control_ios_460_queue.json).

### Validated current-queue helper

`Client.play_queue_index(index)` and `WSClient.play_queue_index(index)` select a
zero-based position in the **current** queue. They validate the integer, query
TCP `0406` for the current total, reject an empty queue or index outside that
total, then send `0100` with index + type 0 and **no label**. A failed queue read
sends no selector; there is no automatic mutation retry. No full queue download
is needed to obtain its total.

Disposable tests compare Russian, absent and arbitrary labels after rebuilding
the same two-track album queue. All select its second track. Full `a202` reports
`playerflag: 0`, one-based `pos_id`/`playing_num`; a fresh HTTP `curlist/song` read
reports the same queue entries and zero-based `mark-pos` of the selected row.

The test replaces a three-track queue with a two-track album. The helper rejects
old index 2 before sending a selector; valid index 1 now selects the second track
of the **new** queue. It does not preserve an old queue identity. A queue can also
change between the length query and the selector: stock Link has no revision token
or atomic compare-and-select operation. UI code must refresh its queue when the
source changes and confirm the resulting track through events/readback.

The raw out-of-range probe deliberately bypasses this guard in the disposable
guest. The HTTP queue remains readable, but `0202` stops returning a full snapshot
(the tested raw query times out). Re-selecting a valid album restores current-track
responses, then the helper works again. A fresh empty queue returns zero entries
over TCP/HTTP and ignores the raw type-0 selector without a playback response.
These are protocol/state behaviors, not proof that the physical player crashes.
They provide one reproducible cause of a silent `0202`; they do not establish why
the user's earlier captures started in that state.

`ci/queue_check.py` exercises both TCP/direct HTTP and WS/proxied HTTP, restores the
original play mode and leaves playback paused. `CI_SCENARIO=queue` runs it with
fresh-empty checks in an isolated generated-media stack. The full integration
pipeline runs the populated-queue checks after existing remote-control acceptance.

Validation on 2026-09-16: the focused `CI_SCENARIO=queue` scenario passed on fresh
V2.40 and V2.57 guests through both transports, including empty queues, all three
label variants, replacement, invalid-index behavior and recovery. The firmware-free
suite passed 174 Python tests, 23 JavaScript tests, shell checks and four shim builds.
These runs validate the queue scenario; they are not a new full integration or
release-gate result. Existing interactive containers and the physical DISC were
not used for these checks.

### Remaining queue-related reads: `0105` and `0426`

`0105` is a read of the play-order mode, not a playback-state query or a toggle.
Its response is `a102000C0000` through `a102000C0004`, using the same mapping as
`0102`: list once, random, repeat one, repeat list, single once. Both clients expose
`play_mode()` and explicitly expect `a102`; deriving `a105` from the request tag
would discard the actual response and time out. `0501.playMode` remains the mode
field in the complete settings snapshot.

V2.57 static evidence: `0105` table entry at `00838d80` points to wrapper
`0041fc50`, callback slot `0083a3d4` points to `004ed5f8`, and `0042b10c` reads the
mode with `00450d18` and sends `a102` through `004ddaec`. The latter formats the
four-digit hexadecimal value. Addresses are specific to the fingerprinted V2.57
binary, not portable to V2.40.

`0426` must not be advertised as a supported DISC counter query. The V2.57
parser recognizes it, but its dispatch-table entry at `00838e80` has a NULL
handler. The binary retains a `curlistlength`/`songposition` JSON serializer at
`004d88dc`; no direct references to that function were found in the saved Ghidra
analysis. Dispatcher `00420130` looks up the table and returns without invoking
anything for a NULL handler. Data-segment addresses above use the ELF PT_LOAD
mapping (file offset + `00410000`), not the text segment's + `00400000` mapping.
Those strings alone do not demonstrate a working service.

The separately fingerprinted V2.40 binary also has a NULL `0426` handler, at
table entry `0082d510`; its `0105` entry `0082d410` points to `0041c540` and
`0406` entry `0082d508` points to `0041c620`. These values were read through the
ELF segment mapping from the disposable guest's binary.

`ci/queue_reads_check.py` checks `04260008` and `0426000C0000` with bounded waits,
then verifies settings and HTTP queue on the same connection. It also checks all
five modes with repeated `0105` reads, ensuring pause and selected track remain
unchanged, and covers queue replacement. `CI_SCENARIO=queue-reads` additionally
starts with an empty queue for both TCP and WS. The normal full integration run
executes its populated-queue scenarios.

Validation on 2026-09-16: `CI_SCENARIO=queue-reads` passed on fresh V2.40 and
V2.57 guests over TCP and WS. In each transport, both `0426` forms timed out with
an empty queue, during playback, while paused, and after replacement/selection;
subsequent settings and HTTP queue reads succeeded. All five `0105` mode values
were read twice without changing the selected track or pause state. Original mode
was restored and playback left paused. Firmware-free checks passed 177 Python
tests, 23 JavaScript tests, shell checks and four shim builds; later changes to
test preparation passed syntax checks and both targeted runs. These initial runs
were focused checks; subsequent full-regression results are recorded in the
[continuation plan](PROTOCOL_RESEARCH.md#validation-log-for-this-checkpoint).
The physical DISC was not probed for these reads.

The focused run uses stock network indexing to avoid coupling these reads to UI
navigation. An earlier UI preparation attempt failed before reaching the reads;
early selector/pause probes also exposed the existing navigation rate gate. The
final test respects the 2.1-second interval before selection and subsequent pause.

For the remote, use `0406` for queue entries/count, HTTP `curlist/song` for its
zero-based `mark-pos`, and `0202` for current-track metadata and one-based
`pos_id`/`playing_num`. These are separate snapshots; refresh after source changes.
**Mixed CUE queues are an exception to trusting the mark:** duplicate wire IDs
can make HTTP highlight the wrong row. CUE `song_track` and favorites flags are
also lossy; see [format identity findings](FORMATS.md). Keep ordered rows, not an
ID-keyed map, and never deduplicate a queue by `songId`.
Do not keep polling an unsupported `0426` or interpret its timeout as an empty
queue. The diagnostic clients discard old notifications before a query; a future
production backend still needs one event reader, since unsolicited `a102` and the
read response have the same tag and no request identifier.

### List schemas

List replies have four hex digits of total count followed by a JSON array. Request
successive pages using the number of entries already received, until it reaches the
total. A page may contain fewer entries than the total; the physical library test
had 1,221 tracks. Counts and positions are bounded by the wire's four-hex-digit fields.

| Request | JSON entry fields observed |
|---|---|
| `0401` tracks; `0413` named album tracks | `id`, `title`, `artist` |
| `0402` artists; `0403` albums | `count`, `name` |
| `0406` active queue | `songId`, `flag`, `itemName`; `itemInfo` may be absent |
| `0415` built-in favorites | `id`, `songId`, `songPath`, `songName`, `artistName`, `isCue`, `track`, `isSacd` |

The accepted `0415` name on V2.57 is the literal **`我的最爱`**, even with the UI
preset to English: payload `0000我的最爱`, full record `041500180000我的最爱`.
A favorite entry's `songPath` was empty; do not promise paths for every catalog entry.

`0405` was recorded as a playlist query in older V2.40 notes. Both a fresh V2.57
emulator and the physical V2.57 DISC returned **no reply** in this investigation.
This is not evidence that the connection failed or that all playlist functionality
is unavailable. Built-in favorites are independently exercised through `0415` and
list type 6. General custom playlists were subsequently verified via HTTP catalog
and TCP/WS type-5 selection; see [PLAYLISTS.md](PLAYLISTS.md).

### Now playing (`0202` → `a202`)

The `song` field is a JSON **string containing JSON**, which the Python clients
already decode. Observed fields:

- `id`, `pos_id`, `song_name`, `song_file_path`.
- `song_duration_time` in milliseconds; `song_sample_rate` in Hz;
  `song_encoding_rate` is sample bit depth; `song_channel` is channel count.
- `song_bit_rate` was 1411 for both 16-bit/44.1-kHz stereo WAV and FLAC; this is
  insufficient evidence of the file's compressed bitrate. Do not label it that way.
- `song_artist_name`, `song_album_name`, `song_style_name`, `song_track`.
- `is_sacd`, `is_cue`, `is_dsd`, `is_m3u`, `m3u_file_path`.

V2.57 [CUE/DSF/DFF tests](FORMATS.md) verify source metadata and positional
selection. Two CUE tracks can share both path and `song_track: 0`; DSF/DFF report
DSD source rate/bit depth, not proof of native DSD output. SACD ISO is unvalidated.

Outer fields include `state`, `love`, `playerflag`, `playing_num` (e.g. `2/3`) and
`work_mode` (`LOCAL`). Some missing string values are the literal `"(null)"`.
Position arrives separately as `a103` with eight hex digits of milliseconds.
A folder-selected physical track and the same indexed album track had different
IDs; do not assume an ID is stable across contexts. `pos_id` is one-based in these
snapshots, while the selection command takes a zero-based position.

Cover retrieval and custom playlist CRUD were investigated subsequently in
[HTTP_API.md](HTTP_API.md), with [remote settings/PEQ](REMOTE_SETTINGS.md) in a
separate contract. Battery notifications over TCP and streaming audio to the browser
remain unvalidated. Raw physical metadata/captures stay
in ignored `work/`; no private addresses or real music-library contents are fixtures.

## Official app UI evidence

User-provided FiiO Control screenshots for DISC (2026-09-15) show capabilities beyond
the tested playback contract. Screenshots confirm exposed controls, not completed
operations, command payloads or emulator support. Private screenshots remain outside
tracked fixtures.

Follow-up file/playlist/scanner results are in [HTTP_API.md](HTTP_API.md);
settings/PEQ are in [REMOTE_SETTINGS.md](REMOTE_SETTINGS.md).

| App screen | Evidence and remaining work |
|---|---|
| Wi-Fi transfer | Folder creation, FLAC upload/progress and single-file deletion verified on emulator and physical V2.57. PNG upload byte-verified in V2.57 emulator; folder import can compose these operations. |
| Work mode | USB DAC/local/AirPlay control transitions and persisted enums tested; actual hardware audio remains separate. See [modes](REMOTE_MODES_THEMES.md). |
| Local playback | Catalog/play-all, HTTP custom playlist lifecycle and V2.57 TCP/WS custom-list selection are tested; see [playlist coverage](PLAYLISTS.md). |
| PEQ | User-preset selection, frequency/gain/Q, master gain, readback and SQLite persistence tested in emulator. Actual DSP response remains unmeasured. |
| Settings | Network indexing, gain, SPDIF, filter, DRE, channel balance and five Bluetooth source-codec preferences tested in emulator. Dedicated V2.57 [library reset](LIBRARY_RESET.md) is tested separately; negotiated codec and physical audio effects remain unvalidated. |
| Lock screen / cover | Physical V2.57 current-cover JPEG; emulator checks general PNG upload, five stock themes and custom lock-screen PNG/metadata. See [theme quirks](REMOTE_MODES_THEMES.md#lock-screen-http). |

Custom playlist operations use `GET/DELETE /song_category_tree/`,
`POST /custom_list_cmd/` and `POST /add_custom_list/`. The lack of a TCP `0405`
reply does not prevent this HTTP functionality.

## Reproduce and evidence

`ci/remote_control.py` runs the same acceptance scenario over TCP and the optional
WS bridge, inside the disposable integration stack. It requires the three generated
tracks from `ci/fixture.py`: one Unicode WAV plus two tagged FLACs. All carry the
same deterministic waveform, retaining the byte-exact PCM check. The stock UI scans
them; tests do not fabricate song database rows or modify firmware memory.

The scenario checks index selection, metadata, next/previous, previous-to-start,
playing/paused seek, five modes, album/artist selection and play-all, queue, built-in
favorites reading (selection on V2.57; rejection before sending on V2.40), and a
physical play/pause notification. Favorites are temporarily added/removed
using stock `0104` (`0001` add / `0000` remove), only on generated disposable media.
Playback is left paused and the original mode restored. Memory probes are read-only
and select addresses by full binary fingerprint.

```sh
# Includes the remote scenario alongside existing audio, peripherals and storage checks:
bash ci/integration.sh /absolute/path/to/main_os/ota_v257
FW_VERSION=2.40 bash ci/integration.sh /absolute/path/to/main_os/ota_v240
# Manual commands, e.g. on an explicitly selected physical device:
python3 tools/fiio_link.py --host PLAYER_IP --play-index 0 --list-type 3 --name 'Album name'
python3 tools/fiio_link.py --host PLAYER_IP --seek-ms 15000
python3 tools/fiio_link.py --host PLAYER_IP --next
```

Manual CLI output is a snapshot, not an acceptance assertion: transitions can
still be in flight. Allow the stock navigation interval between calls.

Physical DISC V2.57, 2026-09-15: protocol 0306; album position selection, next,
previous, previous-to-start, album play-all, five mode values, seek while paused
(resume tick 16000 ms), and empty `0203` behavior confirmed. `0405` timed out too.
Volume was unchanged, initial random mode restored, and the original track was
left paused in its indexed album context (initially it was stopped in folder context).
This is physical DISC evidence, not M21 compatibility or a firmware-port result.

Local validation completed on 2026-09-15:

- Firmware-free suite: **150 Python tests and 23 JavaScript tests**, shell syntax
  checks and all four MIPS shim builds passed.
- Fresh disposable **V2.40 and V2.57** integrations passed, including the remote
  scenario over both TCP and WebSocket, byte-exact audio, peripherals and confinement.
  V2.40 verifies the favorites-selection guard; V2.57 verifies favorites selection
  and the full repeated-scan/Unicode storage scenario.
- Temporary test containers and volumes were removed. Existing interactive stacks
  were retained. These are local results, not a hosted-CI run.

### Static V2.57 routes

The fingerprinted `work/re257/mq_player` matches `firmware/v2.57.json`. Decompile
with existing `ghidra/DecAt.java` / `DecFuncs.java`; retain derived output ignored.

| Tag | Wrapper / callback | Local handler |
|---|---|---|
| `0201` | `41fd70` / `4ed84c` | `42a198`; navigation `4249fc`, gate `4cb284` |
| `0102` | `41fd90` / `4ed8d0` | `42ae00`; mode switch in worker `4524a4` |
| `0103` | `41fed0` / `4edc9c` | `42a738` (milliseconds → whole seconds) |
| `0100` | `41fef0` / `4edd58` | `429008` (position + 1) |
| `0101` | `41ff10` / `4ede38` | `429500`; album `428644` |
| `0203` | `41fdf0` / `4ed9cc` | Empty handler |
| `0104` | `41fdb0` / `4ed908` | `42b144` (current-song favorite) |

V2.40's `0100` callback is `4e4c88` → `42399c`; the favorites branch at `423b80`
uses ID lookup when the network-format flag at `88cb78` is set. It lacks V2.57's
`4edd58` position-to-favorite-ID conversion. This difference was checked against
the pinned V2.40 binary, not inferred from an address offset.

Parser `4d61f8` splits `0100`/`0103` into two four-digit fields; `0101` and named
queries have one four-digit field plus a string. These are **V2.57** addresses;
do not substitute them into V2.40 diagnostics.
