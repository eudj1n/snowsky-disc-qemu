# Changelog

This records changes to **snowsky-disc-qemu**, not features merely announced by the
firmware vendor. Vendor notes and their verification status live in
`docs/firmware/<version>.md`. The supported firmware version is explicit in each release;
emulator-only revisions use `v2.40-r1`, etc. See [the porting guide](docs/PORTING.md).

## [Unreleased]

### Added

- TCP/WS channel-balance helper: stock L20..0..R20 range, packed direction/magnitude
  encoding, readback and SQLite persistence. Disposable tests check center, ±1,
  ±20 and opposite-channel DAC attenuation; add `CI_SCENARIO=settings` for focused
  settings/PEQ regression runs. No firmware patch or physical-audio claim.
- TCP/WS `play_mode()` reads via `0105` with the stock `a102` response tag.
  Add focused `CI_SCENARIO=queue-reads` acceptance for all five modes and `0426`
  response absence, with settings/queue checks after each timeout. Document the
  unassigned DISC `0426` handler and supported queue-read alternatives.
- Current-queue selection helpers for TCP/WS with a fresh queue-length check and
  no localized label. Disposable tests cover label variants, empty/replaced queues,
  stale-index rejection and recovery from a raw out-of-range selector. Add focused
  `CI_SCENARIO=queue` integration runs and a persistent protocol-research checklist
  with validation status and remaining work for session handoff.
- Physical DISC protocol evidence from FiiO Control iOS captures, with sanitized
  fixtures for themes, work modes, codecs, playback/favorites, paused seeks and
  HTTP current-queue selection. Document Android M21 dialect differences and
  current-queue semantics and Android compatibility boundaries.

- Stock USB/local/AirPlay mode and Bluetooth source-codec preference helpers;
  lock-screen HTTP client for system selection and full custom PNG/metadata upload.
  Disposable TCP/WS and direct/proxy tests pin mode persistence, exact image bytes,
  and stock empty-body/activation quirks; document an app traffic-capture checklist.

- Stock HTTP file/catalog/playlist client and disposable direct/proxy acceptance:
  Unicode uploads, directories, progress, playlist lifecycle and network reindexing.
  Physical DISC comparisons include temporary FLAC transfer and current-cover retrieval.
- TCP/WS setting and PEQ helpers with wire validation and readback/SQLite acceptance
  for gain, DRE, filter, SPDIF, user EQ bands and master gain.
- Stock FiiO Link remote-control helpers and TCP/WebSocket acceptance for track
  selection, next/previous, seek, local play modes, albums and built-in favorites.
  Document physical DISC V2.57 comparisons, navigation timing and distinct list schemas.
- Three generated audio fixtures (Unicode WAV and tagged FLAC) for real stock
  album/queue tests, retaining byte-exact audio and storage regression checks.
- Firmware transition and OTA issue checklist: promotion follows validation/release
  preparation; retirement preserves historical releases and research evidence.
- Daily stock OTA catalog monitoring with sanitized version outputs and one
  tracking issue per new main-OS/recovery pair; release preparation and issue
  closure remain manual, with no firmware download or automatic profile changes.
- Optional `DEVICE_BOOT_SCRIPT` for the viewer Power-on action. Empty by default;
  stock startup and `run.sh boot` retain their existing behaviour.

### Fixed

- Replace the three-version FIFO policy with one actively supported, validated
  firmware on `2.x`, plus historical release snapshots without promised backports.
  V2.57 is active; V2.40 runtime/CI cleanup is tracked separately. New vendor
  announcements do not trigger promotion until emulator validation succeeds.
- Remove the obsolete `main` branch and enable automatic deletion of merged PR
  branches; document `2.x` protection and local branch cleanup.
- Refresh the README around the emulator and viewer, with current V2.57 captures;
  reconcile setup, controls and status documentation while retaining dated evidence.
- Preserve literal escapes when registering the MIPS binfmt handler. Raw NULs
  previously truncated its magic and made it intercept i386 executables. Setup
  repairs only that handler and leaves other architecture registrations intact.

## [2.57] — 2026-09-13

SNOWSKY DISC emulator source release; main OS **257**, recovery **18**.
V2.57 is the default, with V2.40 regression coverage. Exact-commit CI links are
recorded in the [release notes](https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.57).

### Added

- Viewer headphone, USB charging and SD controls on the lower edge of the skin,
  including plug/card visuals and actual guest SD eject/insert with media-preservation
  checks. USB is a charging stub only; headphone toggling controls browser audio.
- Viewer screen luminance follows the stock shade brightness setting via SSE.
  Volume continues to use stock buttons/menus and the existing DAC gain path.
- Off/sleep status is centered on the dark screen. Normal-on status and usage hints
  are hidden; Replay capture is in Debug. No extra brightness/volume controls.

- V2.40/V2.57 key, network and active HTTP-route diagnostics selected by exact binary
  fingerprint, with checked read-only guest-memory translation. Clean integration
  cross-checks diagnostic state against TCP, sysfs and SQLite; V2.57 adds a `POST /image/`
  route to the active table (17 entries, still no stock WebSocket route).

- Read-only OTA/ZIP inventory tool with encrypted-chunk integrity checks and streaming
  plaintext rootfs hashing. No guest execution or decrypted firmware files required.
- Public inventory records for V2.40 and V2.57; per-version evidence reports and a
  reusable porting/acceptance procedure.
- V2.57 upstream-change checklist, separated from verified emulator capabilities.
- Opt-in V2.57 runtime profile, exact-build guarded key patches, non-overwriting
  extraction and version-selected secret-backed integration. Existing address-based
  diagnostics reject unknown builds instead of reading unrelated memory.
- Clean-volume physical-button checks and dynamic reboot-shim binding verification.
- MIT license and owner-attributed skin photo; public-release preparation checklist.

### Fixed

- Run the independent SD-peripheral integration before playback selects a track.
  Hosted V2.40 correctly rejected a busy-card eject after the playback probes;
  rebooting alone did not establish an idle-card fixture. Busy-card rejection and
  media-preservation assertions remain enabled.
- Enable sound now joins current PCM instead of replaying accumulated capture from
  byte zero, which could mean minutes of service silence. Live playback rejoins after
  stalls; Replay capture retains historical playback. Debug distinguishes live/replay
  and zero-signal silence.
- Diagnostic PID selection excludes forked worker children that briefly inherit
  `mq_player` argv, avoiding intermittent ambiguity during SD integration probes.
- SD remount preparation now explicitly probes the partition with stock `blkid`.
  The two emulated mmc aliases previously left only the whole-card name in its
  cache, so a stock insertion event could unmount the card without restoring it.
  V2.57 integration checks repeated automatic scans, UI result/lock gates and
  Cyrillic additions, renames and deletions against SD, SQLite and FiiO Link.
- Idle physical-key polling no longer burns a CPU core under QEMU. The framebuffer
  shim waits 5 ms only after an empty read of the `event0` file stub; queued keys,
  touchscreen reads, rendering and PCM delivery keep their existing paths.
- Viewer startup no longer blocks controls for a fixed 26-second pause. Boot waits for
  guest input/framebuffer readiness and network listeners, then remounts the SD card.
  The screen cursor now indicates tap/drag interaction and resets on pointer cancellation.
- SD image creation now explicitly uses UTF-8, matching guest mounts and preserving
  Cyrillic directory/file names on hosts whose FAT default is ISO-8859-1.
  Clean integration now scans and decodes a generated WAV under a Cyrillic path,
  with an exact source/card byte comparison before scanning.
- Fresh setup with an empty `sdcard` directory now completes runtime initialization;
  placeholder-only cards previously aborted setup before seeding `/usr/data`, causing
  `zlog_init` failures and viewer boot errors.

### Changed

- V2.57 is now the default in Compose, setup/extraction tools and CI entry points.
  V2.40 remains explicitly selectable; existing rootfs volumes are never migrated
  or overwritten. `run.sh up` preserves firmware/volume settings in `.env` when
  updating the OTA path.
- Release acceptance covers emulator compatibility and regressions. FiiO's feature
  changelog remains reference information, outside the mandatory emulator test suite.
- Confirmed the public V2.57 source page in the runtime profile and release documentation.

- Renamed the root Compose configuration to `compose.yaml`; updated CI paths and
  documentation references.

- WebSocket bridge is opt-in through the `wsbridge` Compose profile. Default startup
  and `run.sh start/boot` leave it off; integration CI explicitly enables it, and
  `run.sh down/nuke` still clean up an enabled bridge. Viewer and direct TCP/HTTP
  remain available without it.

- Viewer image streaming now encodes and sends changed RGB frames at the existing
  capture rate, with cached full PNG refreshes every 15 seconds while idle. It
  preserves lossless pixels, verifies buffer-marker consistency, handles lock/wake,
  and reconnects images after stream errors or viewer-server recovery.
- Viewer power/screen status now uses a persistent SSE connection with change-only
  snapshots, idle heartbeats and automatic reconnection instead of one JSON request
  per second. Diagnostic `/device.json` remains available.
- Shared coding-agent instructions moved to `AGENTS.md` without a duplicate file.
- Root README omits the OTA password; references to private projects removed from
  current documentation. Existing immutable history has not been rewritten.

### Firmware compatibility

- V2.57 is the default; V2.40 is selected explicitly with `FW_VERSION=2.40`.
  Both have separate validated profiles, guarded patches and diagnostics.
- V2.57 clean boot, stock scan, TCP/WS, local PCM, basic physical controls and reboot
  shim binding passed the initial hosted baseline; subsequent SD/viewer/audio fixes
  have local evidence. Firmware-free CI passed on `5a73883`. Final release requires
  both firmware integrations and firmware-free CI on the exact release commit;
  historical baseline results do not replace that gate.
- Vendor feature announcements are not emulator validation claims. Hardware BT/USB/DSD,
  MCU behavior and hardware-accurate power remain outside the validated scope.

## [v2.40] — 2026-09-11

Firmware target: SNOWSKY DISC main OS **240**, recovery **17**. Immutable source release,
not an installable vendor firmware package. Both CI workflows passed on `e3aab81`.

### Added

- Stock UI boot under qemu-user, touch/swipes, FAT SD card and stock library scanning.
- Physical-control hotspots with app-configured volume gestures and guest-only power lifecycle.
- Local tinyalsa PCM capture, WAV export and browser audio with DAC gain tracking.
- Stock FiiO Link TCP plus an explicit native WebSocket bridge and browser protocol inspector.
- Firmware-free CI and a secret-backed clean-volume integration workflow; 67 Python
  tests, 10 JavaScript tests and four cross-compiled shims.
- Pinned Debian/toolchain, Docker Engine/Compose and Node.js 24 actions; weekly
  SHA-preserving Dependabot PRs, without automatic merging.

### Fixed

- Audio card discovery and the scanner's guest-accessible SD mount source.
- Playback checks now distinguish state-only `a202` notifications from full metadata
  snapshots, without retrying control commands.

### Project / safety

- Repository renamed to `snowsky-disc-qemu`; default branch `2.x`, immutable releases.
- Local runtime names retained for existing state. Ports remain localhost-only;
  dangerous guest capabilities/helpers and reboot paths are confined as documented.
- Firmware is not committed or uploaded as an artifact. Branch protection remains
  unavailable on the private repository's current GitHub plan.

### Known limitations

Automatic media scanning, native stock WebSocket, LAN/phone-app interoperability,
USB/BT/DSD and hardware-accurate power behavior are not fully supported/validated.
See [STATUS.md](docs/STATUS.md) for scope and evidence.

[2.57]: https://github.com/eudj1n/snowsky-disc-qemu/compare/v2.40...v2.57
[v2.40]: https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40
