# diskOS on V2.40 — historical findings

This report records the earlier V2.40 build investigation; it is not a statement
about the current upstream release or supported project firmware. The separate
[UI preview experiment](../../../experiments/diskos/docs/preview.md) is preserved with historical, unsupported status.

[diskOS](https://github.com/b0hemia/diskos) is the community custom firmware this project is
groundwork for. We ran its build pipeline (`diskos-installer` 1.0.0) against the stock **V2.40**
rootfs. Result: **V2.40 is structurally and semantically compatible — the only blocker is a
self-imposed size cap.**

## What already works on V2.40 (verified in the build)

- **Version gate** — accepted with `DISKOS_ALLOW_UNTESTED_FW=1`; rootfs recognised as genuine
  (`stock rootfs OK: PRODUCT=SNOWSKY_DISC MAIN_OS_VER=240`).
- **Boot-hook patch** — the `_patch_fiio_init` anchor (`if [ "$COREDUMP_FLAG" == "1" ]; then` +
  `\n    /usr/data/mq_ui &`) is present **exactly once** in V2.40's `usr/project/fiio_init.sh` →
  patches cleanly.
- UI validation, S97 install, embedded `mq_ui`, manifest, dropbear, repack (lzo, `-b 131072`) and
  the full `_validate_squashfs_output` round-trip all succeed.
- Core FiiO Link command tags are **unchanged 2.09 → 2.40** (verified live over 12100 — the
  V2.09 command map still applies; see [PROTOCOL.md](../../../docs/protocol/protocol.md)).

## The blocker (E231 — size cap, not the flash)

```
[5/6] repacking squashfs (stock params: lzo, -b 131072)
BuildError E231: squashfs is 90193920 > 76021760 partition - refusing
```

The V2.40 stock `rootfs.squashfs` grew to ~88 MB; with the diskOS payload the image is ~90 MB,
over the `IMG_SIZE` cap (76 021 760 = 580 NAND blocks).

| version | stock rootfs.squashfs | |
|---|---|---|
| V2.09 | 75 919 360 (72.4 MiB) | pinned, under cap |
| V2.28 | 72 957 952 (69.6 MiB) | pinned, under cap |
| **V2.40** | **88 420 352 (84.3 MiB)** | **+payload → 90 193 920 (86.0 MiB)** |
| `IMG_SIZE` cap | 76 021 760 (72.5 MiB / 580 blocks) | the constraint |

`mtd2` (rootfs slot A) is physically **128 MB**, so 90 MB fits the flash — the cap is the
constraint, not the hardware. Bumping `IMG_SIZE` to 768 blocks (100 663 296) lets the build
**complete** and produces a valid `diskos_public.bin` (round-trip verified).

## Proposed fix (needs maintainer review)

Raise `IMG_SIZE` to fit the larger V2.40 rootfs (still well within 128 MB `mtd2`). Because it
touches the flasher, review: the bad-block reserve inside `mtd2`, the partition boundary /
next-slot assumptions, and whether the recovery/backup path assumes ≤ 580 blocks. Add `240` to
`TESTED_FW` + a `PINNED_ROOTFS` entry only **after** a real flash-test.

Not flash-tested on hardware (stock V2.40 has no UART/root to run the live-preview path first). A
full write-up was prepared as a GitHub issue for `b0hemia/diskos`.

## Emulator findings (2026-09-13)

A source-built diskOS UI at commit `85a327ca56af2676c850f24ddcba5f34135132d4` ran
over the verified stock V2.40 backend in a separate emulator container. This was
a warm UI handoff after stock startup, not the hardware installer/cold-boot path.

- Its static musl UI needs a link-time framebuffer adapter; libc preload does not
  apply. Explicit QEMU argv[0] avoids its self-exec loop under binfmt.
- Touch navigation, the UI's own library scan and playback of a WAV under a
  Cyrillic path worked. The supplied font displayed Cyrillic letters as boxes.
- In a fresh control container without browser clients, the V2.40 startup route
  reinitialisation stopped playback at 9.01 seconds. Skipping that redundant step
  after stock initialisation let the complete 30-second test track play; captured
  stereo 44.1 kHz PCM contained byte-exact periods of the generated waveform.
- Re-selecting a previously selected track after reboot remains a separate open
  issue. V2.57 and hardware installation are not validated by this experiment.

The installer size cap in [upstream issue #1](https://github.com/b0hemia/diskos/issues/1)
does not apply to loading the UI in an extracted emulator rootfs. Build scripts and the
launcher are preserved under `experiments/diskos/`; the
[preview report](../../../experiments/diskos/docs/preview.md) records reproduction, limitations and the
conditions for revisiting its historical/unsupported status.
