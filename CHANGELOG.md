# Changelog

This records changes to **snowsky-disc-qemu**, not features merely announced by the
firmware vendor. Vendor notes and their verification status live in
`docs/firmware/<version>.md`. The supported firmware version is explicit in each release;
emulator-only revisions use `v2.40-r1`, etc. See [the porting guide](docs/PORTING.md).

## [Unreleased]

### Added

- Read-only OTA/ZIP inventory tool with encrypted-chunk integrity checks and streaming
  plaintext rootfs hashing. No guest execution or decrypted firmware files required.
- Public inventory records for V2.40 and V2.57; per-version evidence reports and a
  reusable porting/acceptance procedure.
- V2.57 upstream-change checklist, separated from verified emulator capabilities.

### Firmware compatibility

- V2.40 remains the runnable/CI-validated target.
- V2.57 intake and decryption format verified; boot, ABI/patch compatibility and new
  features **not yet validated**. No V2.40 runtime hash/address was replaced to accept it.

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

[Unreleased]: https://github.com/eudj1n/snowsky-disc-qemu/compare/v2.40...2.x
[v2.40]: https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40
