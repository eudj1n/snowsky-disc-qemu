# Changelog

This records changes to **snowsky-disc-qemu**, not features merely announced by the
firmware vendor. Vendor notes and their verification status live in
`docs/firmware/<version>.md`. The supported firmware version is explicit in each release;
emulator-only revisions use `v2.40-r1`, etc. See [the porting guide](docs/PORTING.md).

## [2.57] - unreleased

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

- V2.40 remains the runnable/CI-validated target.
- V2.57 clean boot, stock scan, TCP/WS, local PCM, basic physical controls and reboot
  shim binding validated locally and in hosted CI on `0202310`; V2.40 regression also
  passed. Upstream feature acceptance remains **not tested**;
  no `v2.57` release yet. V2.40 pins remain separate and unchanged.

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

[2.57]: https://github.com/eudj1n/snowsky-disc-qemu/compare/v2.40...2.x
[v2.40]: https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40
