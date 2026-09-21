# DISC and Android M21: related FiiO Link dialects

Comparison date: 2026-09-16. DISC evidence is the stock V2.40/V2.57 emulator work
and physical V2.57 iOS captures in [FIIO_CONTROL_APP.md](fiio-control-app.md).
M21 evidence is the user-supplied Android project's `fiio-link-api.md` (FiiO Music
3.3.1, Android 13; reports live checks in July 2026), its current `BlinkerClient.kt`,
`ApiServer.kt`, and subsequent implementation notes. M21 was **not probed again**
during this comparison. Statements about its server internals come from that
project’s reverse-engineering notes, not a new inspection of the vendor binary.

## Application and API boundaries

The user clarified that the M21 investigation concerns **FiiO Music**, not FiiO
Control. On M21, FiiO Music implements the Link server; the user's Android bridge
adds its own API for library management beyond the stock remote. On DISC, the
server is stock device firmware and **FiiO Control is the observed phone client**.
This comparison concerns those server dialects and does not compare two versions
of the same app or assume identical UI capabilities.

In the Android project, `/api/player/...` and library-management API routes belong
to the custom bridge. The documented `/db`, `/setting`, `/sendToClient` and
`/sendFromClient` on port 6744 belong to FiiO Music's stock HTTP server. Keep these
layers separate when identifying native features or transferring research leads
to DISC. The custom API's features are not evidence of stock Link commands.

## Shared family, different contracts

Both use FiiO Link/BLinker over TCP 12100, four-hex-digit command/length headers,
`0201` transport control, `0103` millisecond seek, `0502` volume, `0202` now-playing,
`a202` nested song JSON and `a103` progress. Both have a single-client limitation.
This is enough to share a normalized remote API, but **not** one unqualified wire
implementation or one set of playback-state constants.

| Concern | DISC | Android M21 / FiiO Music evidence |
|---|---|---|
| Length unit | UTF-8 **bytes**, including header | Java/Kotlin `String.length`: UTF-16 code units, including header |
| TCP startup | Client sends `0599/0000`; reply `a599/0306` | Client uses no `0599`; notes describe server greeting, code immediately calls `refresh()` |
| `a202.state` | 0 playing, 1 paused, 2 stopped | Notes/code use 1 playing, 0 paused; report stale/missing state on track changes |
| `0102` | Set requested play-order value 0..4 | Cycle mode; payload ignored according to RE notes and `cyclePlayMode()` |
| `0104` | Set current-track favorite: 1 add, 0 remove | Toggle current-track favorite; client always sends 1, notes trace through `PlayListManager.M` |
| `a102` | Play-order mode | Also play-order mode, **not** playback state |
| `a103` | Milliseconds; about 1 s ticks in captures, absent while paused | Milliseconds; notes report about 500 ms ticks, absent while paused |
| HTTP | Mongoose 12103: files, catalog, themes, cover | Netty 6744: `/db`, `/setting`, command tunnel and event stream |
| HTTP command/event transport | No native WS route in verified DISC router; emulator WS is our bridge | GET-with-body `/sendToClient`; responses/events via `/sendFromClient` |
| Catalog `0405` | No response on tested V2.57 | Documented working playlist response `a405` |
| Favorites list key | `我的最爱`; paths observed empty | Same key; notes report populated `songPath` |
| Cover commands | HTTP `/image/cover/`; V2.57 `0203` handler is empty | Notes identify `0203`/`0215` as cover operations |
| Database | Stock DISC databases, different tables and schema | `/db` exports greenDAO DB with `SONG`, `EXTRA_LIST_SONG`, `RECORD_SONG`, etc. |

The M21 frame example `041500100000我的最爱` has a declared length of 16 UTF-16
code units but occupies 24 UTF-8 bytes. DISC uses `041500180000我的最爱`. An ASCII-only
smoke test would miss this incompatibility. Supplementary Unicode characters use
two UTF-16 code units: a Python implementation of the Android dialect cannot use
plain `len(text)` as a substitute. Keep DISC's byte-framing tests intact and add a
separate Android framer if implementing M21 support.

## What this resolves or usefully narrows

1. **Paused progress:** both implementations stop progress ticks on pause. The
   M21 notes support our distinction between a pending seek and confirmed progress;
   DISC's own capture is the direct evidence that its last paused seek takes effect
   by the time playback resumes. No new paused-position query is established.
2. **Missing/stale current track:** Android notes describe conditional `a202` pushes
   during changes made on the player. Its client queries `0202` after a backward
   position jump over 3 s, and every 10 s of active progress as a fallback. This is
   a useful recovery design, **not an explanation proven for DISC's initial silence**.
   The last DISC trace already establishes successful `0202` on pause.
3. **Queue identity:** Android uses `0406` plus `0426` (`curlistlength`,
   `songposition`), but its API prefers matching the current song ID against the
   fetched queue because the counter can become stale. This is a lead for DISC;
   cross-context DISC IDs are not universally stable.
4. **Metadata and paths:** Android's DB export supplies paths, history and richer
   tags that ordinary `a401` track pages omit. This does not establish `/db` on
   DISC or make greenDAO tables interchangeable with DISC's database. CUE identity
   needs path plus track/segment information; one file path can contain many tracks.
5. **Connection ownership:** the Android client explicitly closes its blocking
   socket on stop, uses one reader and synchronized writes, and declares readiness
   only after parsing a frame. These practices fit the single-backend remote
   design for both products.

The Android client's 1600-ms no-tick watchdog is a product-specific heuristic.
Copying it to DISC would risk mistaking delayed delivery or a disconnected stream
for pause. Normalize explicit DISC state events, keep connection health separate,
and do not replay toggles after reconnecting. Similarly, a fallback metadata poll
must not discard concurrent notifications as the current diagnostic query helper
does; a production backend needs centralized event routing.

## Leads requiring DISC verification

- Followed up for DISC: `0105` reads play mode via `a102`; `0100` type 0 selects
  the current queue. `0426` counters remain an Android feature, not a supported
  DISC read. See [DISC results](../../../docs/protocol/remote-control.md#remaining-queue-related-reads-0105-and-0426).
- `0407`, `0427`–`042a`: recent tracks, composer/year/sample-rate/format categories.
- `0408` with offset and folder key: Android folder listing and device-defined order.
- `0511`: Android settings command; do not replace DISC's individually verified setters.
- `0445`: Android favorite-related mutation with uncertain flag semantics in the
  API document; do not guess a DISC meaning or probe it as a read operation.

None of these sources establishes a DISC library-reset command, generic file
rename/download, Bluetooth negotiated-codec reporting, or custom-theme save rules.
The M21 HTTP service's reported busy-loop bug is another reason not to auto-enable
its AIDL service for a remote; prefer the existing Wi-Fi mode. This bug was measured
in the supplied project, not reproduced here, and should be rechecked by app version.

## Documentation caveats and implementation boundary

The older Android control plan labels `a102` as playback state; the newer API
document, implementation notes and `handleFrame()` correctly treat it as play mode.
`State.playing` also retains an outdated comment mentioning `a102`. The API document
leaves favorite semantics partly unresolved; `toggleLove()` and the API's wait for
`love != before.love` show the later implementation's toggle contract. Folder type
4 is excluded by an early provider note but tried as a checked fallback in the
newer API implementation: do not promote that early table to a universal rule.

For a future web remote, select an explicit device/app profile before mutations:
DISC V2.40, DISC V2.57, or Android FiiO Music version. Each profile owns framing,
startup, state decoding, play-mode/favorite semantics, list types and library
transport. Share normalized actions and UI state above those profiles. Same port,
similar headers or a familiar command tag are insufficient compatibility checks.
This comparison adds no M21 runtime support and changes no files in the source
Android project.
