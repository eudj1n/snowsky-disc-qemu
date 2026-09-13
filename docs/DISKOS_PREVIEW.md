# Experimental diskOS preview

## Source-built UI preview

The experimental preview runs diskOS's **GPL-3.0-or-later UI** alongside the verified
stock `mq_player`. It does not run the installer or build/flash a NAND image.
[Issue #1](https://github.com/b0hemia/diskos/issues/1) concerns the installer's image
size limit; that limit does not apply to an extracted rootfs and a separately loaded UI.

The UI is static musl, so `/etc/ld.so.preload` cannot provide its framebuffer ioctls.
`tools/diskos/emu_io.c` is linked with `--wrap=ioctl`: it supplies the emulated
360×360 framebuffer and marks page zero for the viewer. diskOS's own partial
renderer and IPC framing remain unchanged. The stock binaries retain their original
paths and normal fingerprint validation. `scripts/21_diskos.sh` boots the stock
pair first, then replaces only the running UI with `/usr/data/mq_ui`. This is a
warm UI handoff, **not** a validation of diskOS's hardware cold-boot installer.

The launcher invokes QEMU with `-0 mq_ui` to avoid diskOS's argv-normalisation
self-exec loop under binfmt. One source adaptation in the **build copy** is enabled
by `DISKOS_EMU_WARM_PLAYER`: skip the redundant V2.40 startup route reinitialisation
when the backend was already initialised by the stock UI. Without the flag the
upstream logic remains active. Do not reuse this launcher for a cold backend.

The builder archives the exact commit in `tools/diskos/source-revision` from the
local repository. Local edits, untracked files and `config.mk` are not used. Fetch
that commit if it is missing; change the pin only after reviewing and testing the
new source. The build copy retains the emulator adaptation and corresponding source.

Verified with diskOS commit `85a327ca56af2676c850f24ddcba5f34135132d4` and stock **V2.40**:

- Main screen, touch navigation through Library → Songs, and the UI's own SD scan.
- A WAV under a Cyrillic directory/filename is indexed and played. Cyrillic glyphs
  appear as boxes in the supplied diskOS font; this is separate from path handling.
- Stereo 44.1 kHz / 32-bit PCM contains byte-exact periods of the generated WAV.
- Viewer Power off/on returns to diskOS through the dedicated boot script.

Playback control experiment (2026-09-13): a separate container with **no published
ports and no browser clients**, fresh V2.40 state and the same 30-second WAV:

| UI startup | Captured PCM | Result |
|---|---:|---|
| Upstream logic + framebuffer adapter | 9.01 s | Stops when `v2.40 workmode: local-init sent once` appears |
| Warm-player adaptation enabled | 30.15 s including padding | Entire track completes; source waveform verified |

Browser Enable sound only reads PCM into Web Audio; it sends no player command.
The controlled reproduction rules it out as the cause of this interruption.

Known separate limitation: after rebooting with a previously selected track,
selecting that same entry again stopped a control run after about five seconds.
The diskOS start-confirmation timeout/recovery path still needs investigation;
this is not covered by the warm-start timer fix. Resuming through Play/Pause worked.

V2.57, hardware installation, Wi-Fi/BT, USB modes and diskOS's own system-restart
menu are not validated by this preview. In particular, do not interpret the
framebuffer adaptation or successful playback as evidence of safe NAND flashing.

From the repository root (Docker and Compose ≥2.36 required):

```sh
docker build -t diskos-qemu-ci docker

# Use matching, already downloaded official firmware chunks.
export FW_VERSION=2.40
export OTA_DIR=/absolute/path/to/main_os/ota_v240
preview() {
  docker compose --env-file /dev/null -p diskos-preview \
    -f tools/diskos/compose.yaml "$@"
}
mkdir -p work/diskos-preview/sdcard
# Populate with your media, or create our generated test tone (once):
docker run --rm --network none -v "$PWD:/repo:ro" \
  -v "$PWD/work/diskos-preview/sdcard:/fixtures" diskos-qemu-ci \
  python3 -B /repo/ci/fixture.py /fixtures
preview up -d
preview exec -T emu bash /repo/scripts/00_extract_rootfs.sh /ota  # new volume only
preview exec -T emu bash /repo/scripts/10_setup_env.sh
bash tools/diskos/build.sh /absolute/path/to/diskos
preview exec -T emu bash /repo/scripts/21_diskos.sh
preview exec -d emu bash /repo/scripts/40_stream.sh
```

Open <http://localhost:8081>. The usual viewer on 8080 and its `diskos-work` volume
remain separate. This stack publishes only the viewer, not the stock network
services. The viewer's Power start uses `21_diskos.sh` again. Guest lifetime is
four hours by default; override `GUEST_TTL` when creating the preview container.

Build outputs and the copied GPL sources remain under ignored
`work/diskos-preview/`; no diskOS or vendor binaries are committed here. The
upstream builder verifies its musl toolchain download by SHA-256. Keep the copied
source and adapter with any emulation binary you share; it is not a flash payload.

To stop, release this stack's SD mounts first:

```sh
preview exec -T emu bash /repo/ci/cleanup.sh
preview down
```

The named volume preserves its configuration and library. On subsequent starts,
run setup, diskOS boot and viewer commands; omit extraction. `down --volumes`
discards this preview's guest state. Use a separate volume for each firmware.
