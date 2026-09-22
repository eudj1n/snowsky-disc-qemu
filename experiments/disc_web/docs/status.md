# DISC Web status

Initial implementation on 2026-09-22, branch `codex/disc-web`.

The application provides an independent local server, responsive music UI,
isolated synthetic demo, live library navigation, guarded indexed playback and
playlist editing. RU/EN localization and light/dark/system appearance are
available with browser-local preferences. See [README](../README.md) for exact live/demo
capabilities and launch commands.

The product remains experimental. This checkpoint is not full Controller feature
coverage or physical-device acceptance.

## Initial validation

- Repository firmware-free suite passed in the existing CI Docker image with no
  network and a read-only repository, including the new application tests,
  41 JavaScript tests, shell syntax and all four shim builds.
- The new application boundary tests cover same-origin/token validation,
  duplicate rejection, no automatic connection, stale-generation/busy rejection,
  bounded catalog reads and preserved artist scopes. A real synthetic TCP peer
  checks one session, confirmed pause/volume, idempotent pause and no write after
  disconnect. No physical DISC or interactive emulator volume was used.
- Browser checks cover home/album navigation, demo album playback and queue
  selection, search by artist, and responsive album/expanded-player presentation
  at 390 px.
  Demo actions are presentation checks, not firmware evidence.

## Theme, localization and library editing checkpoint — 2026-09-22

- RU/EN dictionaries cover navigation, status, dialogs, actions and accessible
  names; track/album counts follow language plural rules. Music metadata is not
  translated. Switching languages preserves the current view.
- Light/dark/system appearance uses shared color tokens. The saved theme is
  applied before paint; system changes only affect the automatic choice.
- Indexed album and queue selections preserve original displayed positions,
  scope and expected rows, including after browser filtering. Expired, evicted
  or previous-generation source tokens are rejected.
- Custom playlists support create, rename, track add and member removal through
  public Controller operations. Source-file deletion is not exposed. At this earlier checkpoint, live custom
  playlist playback, seek and all-tracks/favorite indexed playback were gated.
- App checks: 14 Python boundary tests and 7 JavaScript tests passed. Controller
  focused selection/edit checks passed (22 tests). Repository firmware-free run
  passed 428 Python tests, its then-current 41 JavaScript checks and shim builds;
  the subsequent app-only tests include the new preference and source-token cases.
- Ruff and mypy passed. Controller sdist → wheel → isolated installation,
  synthetic TCP session and optional WebSocket imports passed.
- The complete disposable V2.57 `full` integration run passed (exit 0),
  and its temporary containers/volume were removed. `web_session_check` covered:
  indexed album/queue selection, stale displayed-source rejection and verified
  playlist create/add/rename/remove. It uses generated media, not the interactive
  volume or physical DISC.
- Browser verification covers RU/EN, both palettes, preference persistence after
  reload, 390 px home and expanded player, and demo playlist
  create/add/rename/remove with membership readback.

## Everyday playback checkpoint — 2026-09-22

- Public Controller selection now covers complete/indexed custom playlists and
  indexed all-tracks/favorites, with fresh displayed-source and queue checks.
- Seek uses validated duration and the exact displayed track/source. A paused
  device seek remains explicitly unconfirmed until playback yields fresh
  position evidence. No implicit resume or retry is performed.
- Track menus offer play, supported playlist edits, known-album and artist links.
  They retain original source positions after filtering and support keyboard
  navigation. On mobile they appear as a bottom sheet.
- Demo indexed playback retains the complete selected source as its queue;
  demo seek preserves paused/playing state and remains silent.
- New synthetic Controller tests cover final playlist shifts, stale catalogs,
  unknown versions, seek bounds, paused seek and lost-connection no-replay.
  UI checks cover menu navigation, right-click/keyboard access, playlist member
  edits and pointer/keyboard seeking on desktop and at 390 px, in RU/EN and both
  palettes. The current app suite passed 15 Python and 8 JavaScript tests.
- Repository firmware-free validation passed 439 Python tests, 45 JavaScript
  tests, shell checks and all four shim builds. Ruff, mypy and isolated
  Controller wheel installation/synthetic-session checks passed.
- The complete disposable V2.57 `full` run passed (exit 0), including the expanded
  web-session acceptance for catalog/favorites/custom-playlist playback, playing
  seek, paused seek without resume, explicit resume observation and stale-track
  rejection. Temporary containers and volume were removed. No physical DISC or
  interactive emulator volume was used.

## Import and scan checkpoint — 2026-09-22

- The import dialog accepts individual files and directory-picker album folders,
  preserving the root and nested paths. Batches are sequential and stop on an
  unconfirmed item. Limits: 1,000 audio files, 2 GiB minus one byte each; the
  maximum file size is a validated bound, not a throughput acceptance result.
- Transfer has separate receiving/sending/verifying/finished states. The public
  Controller facade requires completed byte count plus a fresh directory entry;
  collisions, stale generations and incomplete staging never dispatch a write.
- Scanning is a separate explicit operation with discovered count. It owns the
  session without interleaved queries, invalidates displayed source tokens and
  refreshes the view after the observed end. Timeout/disconnect is uncertain.
- Demo consumes selected bytes only for presentation: no saved files, changed
  catalog, audio output or device connection. RU/EN and both palettes cover the
  import flow, including skipped file types and uncertain results.
- CUE exploration on a disposable V2.57 stack returned completed byte progress
  but no confirmable directory entry. The operation correctly remained uncertain;
  CUE was excluded from the supported importer. Artwork/CUE and other sidecars
  are explicitly skipped with a count, rather than reported as verified copies.
- Synthetic tests cover private staging cleanup, partial bodies, foreground
  admission, reconnect during staging, duplicate requests, path/size bounds,
  case-insensitive collision and observed scan ownership/no replay.

Validation for this checkpoint: app suite passed 20 Python and 9 JavaScript
tests; repository firmware-free run passed 450 Python and 46 JavaScript tests,
shell checks and four shim builds. Ruff, mypy and isolated Controller package
installation/synthetic-session checks passed. The full disposable V2.57 run
passed, followed by a focused `queue` run covering the final nested-folder upload,
byte equality, collision rejection, explicit scan and fresh index membership.
Both successful stacks were removed. The CUE exploratory run remained a failed
verification, as recorded above; it is not part of the supported import surface.
Browser checks cover folder picking, two identical leaf names in separate disc
folders, skipped sidecars, sequential demo transfer, explicit scan, RU/EN and
light/dark layouts at desktop and 390 px. No physical DISC or interactive
emulator volume was used.

## Next implementation stages

1. File browsing/management and verified artwork/CUE sidecar handling.
2. Extend device settings, cover caching, large-catalog presentation and live
   multi-browser invalidation; integrate optional Assistant through one owner.

Do not expose placeholder settings as functioning controls or use diagnostic
clients to bypass the persistent facade.
