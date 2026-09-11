# Status

_Updated 2026-09-11 after live physical-control tests._

## Working ✅

- **Firmware unpack** — decrypt + assemble + `unsquashfs` the V2.40 rootfs, sha256-verified.
- **Boot under qemu-user** — `mq_player` + `mq_ui` run; POSIX-mqueue IPC between them works.
- **Full boot to main screen** — splash → first-boot language wizard → main menu carousel.
- **Battery reported healthy** (100%) via stubbed cw2215 sysfs.
- **Touch injection** — inject `input_event`s into the touch stub; tap coordinates mapped
  (180°-rotated). A short press (~0.3 s) is a click; a long press (~1 s) opens the item's
  context menu (select / delete / add-to-playlist) — see [TOUCH.md](TOUCH.md).
- **Live interactive viewer** — `./run.sh view` streams the framebuffer to a browser and
  turns clicks/drags into taps/**swipes** (shade pull-down, left→right back), optionally
  composited into a photo of the player. Verified live: menu → tap **Browse files** → swipe
  **back** → menu. See [VIEWER.md](VIEWER.md).
- **SD card / File Browser** — drop media into `./sdcard`; it is built into a FAT image exposed
  as `/dev/mmcblk0[p1]` and mounted at `/tmp/sdcard`. The File Browser lists it and is fully
  navigable to the leaf tracks. Verified end-to-end: main menu → **Browse files** →
  `Test Artist` → `Greatest Hits` → the two `.wav` tracks.
- **Reverse engineering** — Ghidra 12 headless on `mq_ui`/`mq_player`; decompiled the touch
  read-callback, boot IPC, and the `mount_storage_dev.c` SD-mount logic.
- **Local audio** — stock decoder → tinyalsa → PCM capture, with Web Audio in the viewer
  and `./run.sh audio` WAV export. I2S3 card discovery works without audio binary patches.
  Captured samples were checked against the source. See [AUDIO.md](AUDIO.md).
- **Physical controls in the viewer** — Volume −/+, Play / pause, Power / lock. Volume
  single/double/hold gestures use the stock app's assignments; holds include GPIO state
  and repeat/cancel handling. Play/pause, screen sleep/wake and touch blocking were
  verified live. Long Power stops only this guest; Power while off boots it again without
  stopping Docker or the viewer. See [KEYS.md](KEYS.md) for tests and fidelity limits.
- **Stock automatic power-off confinement** — BusyBox's libc `reboot` is intercepted;
  the viewer consumes a shutdown request and stops only the guest. Verified by executing
  guest `poweroff -f`: Docker and the page stayed alive, and Power booted the guest again.
- **Browser output volume** — stock CS43131 attenuation writes now control Web Audio's
  left/right gain. Volume 115 → 114 → 115 produced gain 0.37584 → 0.35481 → 0.37584.
  Raw PCM/WAV exports stay bit-exact before the hardware volume stage.
- **Active framebuffer selection** — the shim records the last buffer written by the UI;
  the viewer no longer has to guess when both buffers changed between polls.

The language choice persists to `sysconfig.db` after the first successful tap, so subsequent
boots go **straight to the main menu** (~24 s), skipping the wizard.

## Screens reached

| | screen |
|---|---|
| ![splash](images/01-splash.png) | Boot splash (SNOWSKY / FIIO OWNED BRAND) |
| ![low battery](images/02-low-battery.png) | Critically-low-battery warning (before the battery sysfs fix) |
| ![language](images/03-language.png) | First-boot language wizard, **English** selected (options stay in their native scripts; the 确定 button is the fallback locale until you confirm) |
| ![main](images/04-main-menu.png) | **Main menu** carousel (Settings / Browse files / Now playing), battery 100%, volume 120 |
| ![files](images/05-file-browser.png) | **File browser** at `/tmp/sdcard` showing the `Test Artist` folder from `./sdcard` |
| ![tracks](images/06-sd-tracks.png) | Two levels in — `/tmp/sdcard/Test Artist/Greatest Hits` listing the `.wav` tracks |

## Current controls — screenshots from 2026-09-11

These are actual emulator/browser captures, not mockups. Permanent copies are in
`docs/images/`; diagnostic captures in ignored `shots/` are not required to reproduce them.

| | Verified screen |
|---|---|
| ![Gesture settings](images/07-key-gesture-settings.png) | Stock **Custom volume settings**: Single press, Double press, Long press. All three assignments were changed through this app and restored to 1 / 0 / 1. |
| ![Long-press assignment](images/08-key-long-press-assignment.png) | Stock **Long press** action selection; **Adjust volume** restored after testing Switch track. |
| ![Physical controls](images/09-viewer-physical-controls.jpg) | Updated viewer with Volume −/+, Play / pause and Power / lock, plus gesture instructions and device status. |
| ![Locked screen](images/10-viewer-screen-locked.jpg) | Power short-click: screen is black, status reports locked, touch requests return HTTP 409. A second click wakes the stock UI. |

Checks passed: **16 Python tests + 7 JavaScript tests**, plus live guest state readback,
browser click/double-click, GPIO holds, settings changes/persistence, DAC gain, and an
off/on cycle. Viewer screenshots were captured from the actual browser page.
The full track/position/gesture matrix and physical-device timing were not exhaustively tested.

## Not done yet / next

- **Additional audio routes** — USB/BT, DSD, and hardware-accurate timing still need separate
  validation. Local PCM works; see [AUDIO.md](AUDIO.md).
- **Network services** — the emulated `mq_player` does **not** yet bind 12100/12103 (gated on the
  network being up). Next: a `40_network.sh` that adds a dummy `wlan0` + sets
  `NETWORK_MODE=1`/`WIFI_STATUS=1` (this got 12103 answering `GET /api/hi → 200` in an earlier
  throwaway container), then build a "FiiO YMD"-style bridge against the emulator. The protocol
  itself is already reversed and verified against the real device — device control is **auth-free**
  on 12100, and there is **no file-upload command** in the device protocol (see
  [PROTOCOL.md](PROTOCOL.md) and [DEVICE.md](DEVICE.md)).
- **Carousel swipes** — ✅ done via the viewer's drag/`/swipe` (intermediate position events
  over time).
- **Power fidelity** — viewer power-off is a deliberate guest-only process stop, not stock
  standby/shutdown policy or its animation. Raw firmware `0x108` is blocked in the viewer
  because it invokes stock shutdown side effects. Automatic poweroff's libc reboot call
  is now intercepted too; hardware-accurate standby/MCU behavior and a security sandbox
  for arbitrary direct syscalls are not implemented. See [KEYS.md](KEYS.md).
- **MCU/UART** — the FiiO MCU (`/dev/ttyS*`) is absent; not required to reach/use the main
  screen; MCU-specific behavior such as charging reports remains unemulated. Physical
  key delivery itself uses `event0`, not UART (see [KEYS.md](KEYS.md)).
- **Other firmware versions / rendering paths** — last-buffer tracking is validated for
  V2.40's framebuffer memcpy path. The viewer retains its old heuristic as a fallback when
  an older shim supplies no marker. Standalone captures still export both raw sub-buffers.

See [EMULATION.md](EMULATION.md) for the how/why behind everything above.
