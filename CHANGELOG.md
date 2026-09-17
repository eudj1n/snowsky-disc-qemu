# Changelog

User-facing changes to **snowsky-disc-qemu**, not vendor firmware announcements.
Keep entries short and group related work; protocol details and validation evidence
belong in the linked documentation. Vendor notes live in `docs/firmware/<version>.md`.
See [release and support policy](docs/PORTING.md).

## [Unreleased]

Active firmware: **V2.57**. Local protocol research is finalized in
[issue #10](https://github.com/eudj1n/snowsky-disc-qemu/issues/10); see the
[controller capability summary](docs/DISC_CAPABILITIES.md).

### Added

- Remote playback, seeking, play modes, favorites and guarded queue selection,
  with natural end-of-track/list checks. [Playback](docs/REMOTE_CONTROL.md).
- HTTP file transfer, library browsing and custom playlist management/playback;
  artist-scoped album, genre and folder selection (including captured FiiO Control Play all) and guarded
  bulk playlist additions. [Library](docs/LIBRARY_BROWSING.md).
- Disposable category-deletion checks documenting membership loss, file removal
  and stale references. [Deletion limits](docs/LIBRARY_DELETE.md).
- Library scan cancellation and dedicated index reset with recovery checks;
  reset preserves source files. [Scan](docs/LIBRARY_SCAN.md), [reset](docs/LIBRARY_RESET.md).
- Remote audio settings with verified stock Gain and physical-app filter mapping, channel balance
  and basic PEQ helpers; read-only gapless,
  folder-jump and ReplayGain preferences. [Settings and limits](docs/REMOTE_SETTINGS.md).
- Work-mode/codec preferences and custom wallpaper uploads, including four styles
  and captured color/Date save behavior, with verified safe name limits. System
  themes now support verified opacity, color, style and overlay edits.
  [Modes and themes](docs/REMOTE_MODES_THEMES.md).
- Passive LAN discovery and an opt-in, time-limited bridge for one phone;
  initial FiiO Control connection verified. [Discovery](docs/DISCOVERY.md).
- USB-power emulation that inhibits stock idle shutdown, plus idle/reconnect
  checks. USB data/DAC is not emulated. [Power behavior](docs/IDLE_POWER.md).
- CUE/DSF/DFF metadata and track-selection checks; native DSD output and SACD ISO
  remain outside this coverage. [Formats](docs/FORMATS.md).
- Sanitized physical-app fixtures, focused integration scenarios and optional
  local failure logs, including captured genre browsing/album selection.
  Long power tests run only when relevant. [Testing](docs/CI.md).
- Daily OTA catalog monitoring with tracking issues; no automatic firmware
  download or promotion. Optional viewer Power-on script for custom startup.

### Changed

- Separate emulator, viewer, controller, firmware tooling and research into explicit
  components. Keep root launch commands; media now lives in `emulator/sdcard/` and
  Docker names use `snowsky-disc-qemu`. [Source layout](docs/REPOSITORY.md).

- Support one validated firmware on `2.x`; older versions remain historical
  snapshots without promised backports. Hosted integration now targets V2.57 only.
- Keep immutable `v2.57` as a pre-release and `v2.40` as the historical stable
  release; the eventual stable V2.57 release will use a new tag such as `v2.57-r1`.
- Refresh setup/control documentation and V2.57 screenshots; retire the obsolete
  `main` branch and automatically delete merged PR branches.

### Fixed

- LAN bridge timeout cleanup now releases the control connection even during
  continuous upstream notifications.
- Stabilize library, SD and end-of-track tests around stock asynchronous behavior;
  read-only diagnostics tolerate transient player-process ambiguity.
- Correct MIPS binary-handler registration so it cannot intercept i386 programs;
  setup leaves other architectures' handlers untouched.

Detailed progress, limitations and follow-ups: [protocol research](docs/PROTOCOL_RESEARCH.md).

## [2.57] — 2026-09-13

Main OS **257**, recovery **18**. Reclassified as an immutable **pre-release
snapshot** on 2026-09-16; the tag and commit are unchanged. Entries below describe
that snapshot, not current development. Exact-commit CI evidence is in the
[release notes](https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.57).

### Added

- Viewer headphone, USB-status and SD controls; real guest card eject/insert,
  stock brightness tracking and clearer sleep/off status. USB was status-only.
- Fingerprint-checked diagnostics for V2.40/V2.57, firmware inventory tools and
  a reusable porting/acceptance checklist.
- Guarded V2.57 runtime profile, clean-volume button/reboot checks, MIT license
  and owner-attributed skin photo.

### Fixed

- Live browser audio starts at current PCM and recovers after stalls;
  Replay capture retains historical playback.
- SD reinsertion/remounting, automatic scans and UTF-8 filenames; empty cards
  no longer prevent fresh runtime initialization.
- Idle key polling no longer consumes a CPU core. Viewer startup waits for guest
  readiness instead of a fixed delay; pointer cancellation resets the cursor.
- Diagnostic process selection and SD test ordering no longer confuse worker
  processes or a busy card with an idle fixture.

### Changed

- V2.57 became the default, with V2.40 selectable at publication; existing
  firmware volumes are preserved rather than migrated automatically.
- WebSocket bridge became opt-in; Compose configuration moved to `compose.yaml`.
- Lossless changed-frame streaming and persistent status events reduce polling
  and reconnect automatically after viewer interruptions.
- Shared agent instructions moved to `AGENTS.md`; passwords/private-project
  references removed from public-facing documentation without rewriting history.

At publication, both firmware profiles had validation coverage. Hardware
BT/USB/DSD, MCU behavior and hardware-accurate power were not validated.
Current support and release gates are defined in [CI.md](docs/CI.md).

## [v2.40] — 2026-09-11

Main OS **240**, recovery **17**. Immutable emulator source release, not an
installable vendor firmware package. Both CI workflows passed on `e3aab81`.

### Added

- Stock UI boot, touch/swipes, FAT SD card and library scanning under qemu-user.
- Physical-button hotspots with app-configured volume gestures and guest-only
  power control; PCM capture, WAV export and browser audio with DAC gain tracking.
- Stock FiiO Link TCP control, our WebSocket bridge and a protocol inspector.
- Firmware-free and secret-backed integration CI, pinned build dependencies
  and weekly Dependabot updates without automatic merging.

### Fixed

- Audio-card discovery, scanner SD mount paths and handling of partial playback
  notifications.

### Project and limitations

- Renamed to `snowsky-disc-qemu`; default branch `2.x`, immutable releases,
  localhost-only ports and confined guest reboot/privileged operations.
- Firmware is excluded from Git and CI artifacts. Branch protection was
  unavailable on the private repository's GitHub plan at publication.
- Automatic scanning, native stock WebSocket, phone interoperability and
  hardware USB/BT/DSD/power behavior were not fully supported or validated.

See [STATUS.md](docs/STATUS.md) for current capabilities and evidence.

[2.57]: https://github.com/eudj1n/snowsky-disc-qemu/compare/v2.40...v2.57
[v2.40]: https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40
