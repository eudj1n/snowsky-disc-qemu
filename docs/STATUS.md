# Status

_As of this commit._

## Working ✅

- **Firmware unpack** — decrypt + assemble + `unsquashfs` the V2.40 rootfs, sha256-verified.
- **Boot under qemu-user** — `mq_player` + `mq_ui` run; POSIX-mqueue IPC between them works.
- **Full boot to main screen** — splash → first-boot language wizard → main menu carousel.
- **Battery reported healthy** (100%) via stubbed cw2215 sysfs.
- **Touch injection** — inject `input_event`s into the touch stub; tap coordinates mapped
  (180°-rotated). A short press (~0.3 s) is a click; a long press (~1 s) opens the item's
  context menu (select / delete / add-to-playlist) — see [TOUCH.md](TOUCH.md).
- **SD card / File Browser** — drop media into `./sdcard`; it is built into a FAT image exposed
  as `/dev/mmcblk0[p1]` and mounted at `/tmp/sdcard`. The File Browser lists it and is fully
  navigable to the leaf tracks. Verified end-to-end: main menu → **Browse files** →
  `Test Artist` → `Greatest Hits` → the two `.wav` tracks.
- **Reverse engineering** — Ghidra 12 headless on `mq_ui`/`mq_player`; decompiled the touch
  read-callback, boot IPC, and the `mount_storage_dev.c` SD-mount logic.

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

## Not done yet / next

- **Audio path** — drive playback of a test track and check the CS43131 path (audio out is
  not wired to the host; would need an ALSA/PCM stub or capture).
- **Network services** — the emulated `mq_player` does **not** yet bind 12100/12103 (gated on the
  network being up). Next: a `40_network.sh` that adds a dummy `wlan0` + sets
  `NETWORK_MODE=1`/`WIFI_STATUS=1` (this got 12103 answering `GET /api/hi → 200` in an earlier
  throwaway container), then build a "FiiO YMD"-style bridge against the emulator. The protocol
  itself is already reversed and verified against the real device — device control is **auth-free**
  on 12100, and there is **no file-upload command** in the device protocol (see
  [PROTOCOL.md](PROTOCOL.md) and [DEVICE.md](DEVICE.md)).
- **Carousel swipes** — inject motion (intermediate position events over time) so LVGL
  registers drags, to navigate the app carousel and settings.
- **MCU/UART** — the FiiO MCU (`/dev/ttyS*`) is absent; not required to reach/use the main
  screen, but some features (power, keys, charging state) would need a UART stub.
- **Deterministic live-buffer capture** — currently emit all sub-buffers and pick by eye;
  could record the last-flushed buffer from the shim.

See [EMULATION.md](EMULATION.md) for the how/why behind everything above.
