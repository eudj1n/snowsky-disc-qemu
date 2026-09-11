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

- **Audio path** — WIP. The libasound interposer (`shim/asndshim.c`) + CS43131 stubs are
  built and ready; playback triggers but is gated by a chain of hardware-format layers before
  ALSA is reached (format lookup patched; `pcm_control` params is the next gate). See
  [AUDIO.md](AUDIO.md).
- **Network services** — the emulated `mq_player` does **not** yet bind 12100/12103 (gated on the
  network being up). Next: a `40_network.sh` that adds a dummy `wlan0` + sets
  `NETWORK_MODE=1`/`WIFI_STATUS=1` (this got 12103 answering `GET /api/hi → 200` in an earlier
  throwaway container), then build a "FiiO YMD"-style bridge against the emulator. The protocol
  itself is already reversed and verified against the real device — device control is **auth-free**
  on 12100, and there is **no file-upload command** in the device protocol (see
  [PROTOCOL.md](PROTOCOL.md) and [DEVICE.md](DEVICE.md)).
- **Carousel swipes** — ✅ done via the viewer's drag/`/swipe` (intermediate position events
  over time).
- **Physical keys** — ✅ working. Fully reversed (see [RE.md](RE.md)): `event0` → `echo_loop_key`
  → `echo_sys_key_handler`, custom codes **`0xFA–0x10D`** (MENU_UP=`0x107`, MENU_DOWN=`0x106`,
  PLAY=`0x10c`, play/pause=`0x103`; `0xfa` is a silent back/exit — **no power key on `event0`**,
  power is MCU-mediated and unemulated). The dispatcher's key-enable gate
  (`DAT_0082e9c1`, 0 headless) is removed by a one-instruction patch (`scripts/patch_keys.sh`,
  run from `10_setup_env.sh`); the viewer has key buttons that inject into `event0`. Confirmed
  live: injected keys reach the dispatcher (`KEY_VALUE_MENU_UP_L`/`MENU_DOWN` logged). Visible
  effect is context-dependent (menu carousel is touch/swipe; keys act in playback/volume).
- **MCU/UART** — the FiiO MCU (`/dev/ttyS*`) is absent; not required to reach/use the main
  screen, but some features (power, keys, charging state) would need a UART stub.
- **Deterministic live-buffer capture** — currently emit all sub-buffers and pick by eye;
  could record the last-flushed buffer from the shim.

See [EMULATION.md](EMULATION.md) for the how/why behind everything above.
