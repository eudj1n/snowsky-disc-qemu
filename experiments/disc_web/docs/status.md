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
  public Controller operations. Source-file deletion is not exposed. Live custom
  playlist playback, seek and all-tracks/favorite indexed playback remain gated.
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

## Next implementation stages

1. Add reviewed persistent seek and playlist playback with honest
   pending/uncertain UI; extend scoped track selection where supported.
2. Upload, scan/progress and file management with operation-specific verification.
3. Extend device settings, cover caching, large-catalog presentation and live
   multi-browser invalidation; integrate optional Assistant through one owner.

Do not expose placeholder settings as functioning controls or use diagnostic
clients to bypass the persistent facade.
