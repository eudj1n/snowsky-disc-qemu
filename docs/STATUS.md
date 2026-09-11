# Status

_Updated 2026-09-11 after WebSocket route tracing and skin-hotspot UI tests._

## Working ✅

- **Local FiiO Link TCP 12100** — host handshake, settings, indexed library, now-playing
  path, absolute volume and play/pause. Compose provides real `eth1`; startup re-announces
  its IP via netlink. No Wi-Fi DB overrides or network binary patches. HTTP 12103 also
  listens; its active router does not register WebSocket (see investigation below).
  Ports are localhost-only. See [NETWORK.md](NETWORK.md).
- **Manual media-library synchronization** — Settings → Update media lib → Update now
  found all **4 test WAVs**; TCP returned the same four records. Fixed the scanner's extra
  SD gate: the mount source must be guest-accessible `/dev/mmcblk0p1`, not
  `/work/rootfs/dev/mmcblk0p1`. Browse files alone had not exposed this problem.

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

## Network and library checks — 2026-09-11

| Actual browser capture | Result |
|---|---|
| ![Media-library settings](images/11-media-library-settings.jpg) | **Update now / Auto update** in the stock application. The indicator alone is not proof that automatic scanning is enabled or implemented. |
| ![Library scan completed](images/12-media-library-scanned.jpg) | **4 songs scanned**, using the stock scanner after the mount-source fix; all four returned by TCP 0401. |
| ![TCP-controlled playback](images/13-network-playback-paused.jpg) | **01 - Tone A.wav**, selected through TCP from the indexed library, left paused after the play/pause test. The central Play icon agrees with wire state 1 and internal state 2. |

Passed: **28 Python tests + 7 JavaScript tests**, Compose validation, image rebuild /
container recreation, repeated setup/boot and viewer Power-on. The live host check
`python3 tools/verify_network.py --control --start-library` verifies protocol 3.06,
volume **119 → 118 → 119**, the same track's wire state **0 → 1 → 0**, and HTTP 12103.
The test leaves playback paused. Guest memory independently confirmed volume 119,
player state 2 (paused), network-ready=1, Docker IP and dropped dangerous capabilities.
Automatic scanning did not ingest the fifth test file; WebSocket returned 200 instead
of 101. Those are recorded limitations, not passing checks.

## Skin controls and WebSocket findings — 2026-09-11

| Actual browser capture | Result |
|---|---|
| ![Quiet skin hotspots](images/14-skin-hotspots.jpg) | Physical controls on the skin: translucent pink circles, no icons at rest. Power is centered over the top button; Play/pause and the volume rocker are on the right. Gesture shortcuts and alignment are hidden in collapsed **Debug**. |
| ![Hotspot hover](images/15-skin-hotspot-hover.jpg) | Hover reveals the icon and label; focus/pressed feedback remains available. Volume changed **115 → 114 → 115**, with DAC gains **0.37584 → 0.35481 → 0.37584**. |

Passed **37 Python + 10 JavaScript tests**. Live browser clicks verified volume,
Power startup/wake and play/pause (internal state **2 → 1 → 2**, left paused).
Confirmed hover CSS: fill alpha 0.13/icon opacity 0 at rest, 0.32/1 on hover.
Debug expands/collapses; closing it clears alignment mode and its readout.
Automated checks cover keyboard feedback, pointer/blur cancellation, duplicate-click
suppression, a second finger's release and plain/skin HTML generation. Mobile layout
and the no-skin fallback were not visually tested in this session.

**WebSocket diagnosis is complete, but stock WS control does not work:** the active
12103 callback `004b9d38` dispatches a 16-entry HTTP table with no WebSocket route.
Unknown URLs go directly to empty HTTP 200 (`0048f8f8`). `/api/websocket` and a made-up
URL returned the same result. The older explanation involving a dashboard password
was incorrect; the bundled dashboard handler is not connected to this listener.
Read-only route inspection and strict upgrade probes are committed; see
[NETWORK.md](NETWORK.md#websocket-investigation). No binary patch, new dependency,
port or ad-hoc image change was made. Dockerfile/Compose remain unchanged for this step.
The existing viewer startup script applies the UI changes: `./run.sh view`, then reload.

## Not done yet / next

- **Additional audio routes** — USB/BT, DSD, and hardware-accurate timing still need separate
  validation. Local PCM works; see [AUDIO.md](AUDIO.md).
- **Auto update (media library)** — the menu option was inspected/clicked, but adding a
  generated fifth WAV and rebooting did not update the index or start a scan. Its effective
  on/off state and startup/hotplug trigger are not yet established. Manual Update now works.
  The fixture was removed and SD rebuilt; the original four indexed tracks remain.
- **Remaining network work** — optional local WebSocket → TCP bridge (not implemented;
  stock V2.40 has no registered WS route), LAN multicast discovery, Wi-Fi association
  and cloud streaming. Raw TCP works independently. `POST /audio/` is an active HTTP
  route worth investigating separately for file transfer. Automatic OTA/NTP helpers
  are blocked; OTA downloads/installations were not tested.
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
