# Status

_As of this commit._

## Working ✅

- **Firmware unpack** — decrypt + assemble + `unsquashfs` the V2.40 rootfs, sha256-verified.
- **Boot under qemu-user** — `mq_player` + `mq_ui` run; POSIX-mqueue IPC between them works.
- **Full boot to main screen** — splash → first-boot language wizard → main menu carousel.
- **Battery reported healthy** (100%) via stubbed cw2215 sysfs.
- **Touch injection** — inject `input_event`s into the touch stub; tap coordinates mapped
  (180°-rotated). Verified end-to-end: tap Confirm on the wizard → main menu → tap an app →
  file browser (with the test SD content).
- **Reverse engineering** — Ghidra 12 headless on `mq_ui`/`mq_player`; decompiled the touch
  read-callback and boot IPC.

The language choice persists to `sysconfig.db` after the first successful tap, so subsequent
boots go **straight to the main menu** (~24 s), skipping the wizard.

## Screens reached

| | screen |
|---|---|
| ![splash](images/01-splash.png) | Boot splash (SNOWSKY / FIIO OWNED BRAND) |
| ![low battery](images/02-low-battery.png) | Low-battery shutdown (before the battery sysfs fix) |
| ![language](images/03-language.png) | First-boot language wizard (简/繁/EN/日 + 确定) |
| ![main](images/04-main-menu.png) | **Main menu** carousel (设置 / 文件浏览 / 正在播放), battery 100%, volume 120 |
| ![files](images/05-file-browser.png) | File browser opened by tapping the center app (`/tmp/sdcard`) |

## Not done yet / next

- **Audio path** — drive playback of a test track and check the CS43131 path (audio out is
  not wired to the host; would need an ALSA/PCM stub or capture).
- **Network services** — expose/exercise TCP 12100 (raw FiiO Link) and 12103 (HTTP/WS) from
  the host; build the "FiiO YMD"-style bridge against the emulator instead of hardware.
- **Carousel swipes** — inject motion (intermediate position events over time) so LVGL
  registers drags, to navigate the app carousel and settings.
- **MCU/UART** — the FiiO MCU (`/dev/ttyS*`) is absent; not required to reach/use the main
  screen, but some features (power, keys, charging state) would need a UART stub.
- **Deterministic live-buffer capture** — currently emit all sub-buffers and pick by eye;
  could record the last-flushed buffer from the shim.

See [EMULATION.md](EMULATION.md) for the how/why behind everything above.
