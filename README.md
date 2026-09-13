# snowsky-disc-qemu

Emulating the **FiiO Snowsky Disc** (Ingenic X2000, MIPS32) music player from its
stock **V2.40 / V2.57** firmware, under `qemu-user` — booting the real UI to its main screen
and driving it with synthetic touch, entirely without the hardware.

Groundwork for building/testing custom firmware (cf. [b0hemia/diskos](https://github.com/b0hemia/diskos))
and a media-library sync bridge against an emulated device instead of a physical one.

Development branch: **`2.x`**. Releases follow the exact firmware version (`v2.40`;
emulator revisions `v2.40-r1`, etc.). Firmware-free CI and manual secret-backed firmware
integration: **[docs/CI.md](docs/CI.md)**. Firmware/rootfs are never release assets.
First validated source release: **[v2.40](https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40)**.
Project history: [CHANGELOG.md](CHANGELOG.md). New-version workflow and evidence:
[docs/PORTING.md](docs/PORTING.md); [V2.57 compatibility and release gates](docs/firmware/2.57.md).
V2.40 remains the default; select V2.57 explicitly with `FW_VERSION=2.57`.
Release checks cover emulator compatibility; vendor feature announcements are reference
information, not a certification of FiiO's software.

The GitHub project was renamed from `diskos-qemu`. Existing runtime names
(`diskos-qemu` container/image, `diskos-work` volume, `diskos-qemu-ci` test image)
remain unchanged for compatibility; commands below deliberately use those names.

![main menu](docs/images/04-main-menu.png)

_The stock main menu running under qemu — battery 100%, volume 120, app carousel
(Settings · File Browser · Now Playing). Reached by tapping through the first-boot
language wizard via injected touch events._

## What works

Splash → first-boot language wizard → **main menu** → into apps (file browser shows the
SD content), plus working **touch injection**. Full detail + screenshots: **[docs/STATUS.md](docs/STATUS.md)**.
**Local audio capture and browser playback** also work: select a track, enable sound in the
viewer, or run `./run.sh audio` to export `shots/audio.wav`. See [docs/AUDIO.md](docs/AUDIO.md).

## Quickstart

Requires **Docker Engine 28.1+** (macOS or Linux) and **Compose 2.36+** (`eth1` naming).
The firmware is **not** in this repo — get it first:
**[firmware/README.md](firmware/README.md)** (official download page and preparation instructions).

```sh
# 1. point the tool at the OTA chunk directory (…/main_os/ota_v240 of the unzipped firmware)
./run.sh up /path/to/SNOWSKY_DISC_update_.../main_os/ota_v240

# 2. boot to the main screen; PNGs land in ./shots/
./run.sh boot

# 3. tap something (coordinates are what you SEE in the PNG; flipped internally)
./run.sh tap 180 315      # e.g. the Confirm button on the language screen

# 3b. …or drive it interactively in the browser: live screen + click/drag/swipe
./run.sh view             # -> http://localhost:8080  (click=tap, drag=swipe)
./run.sh shell            # or drop into the container to poke around

# stop / teardown
./run.sh stop
./run.sh down             # remove container (keeps the extracted-rootfs volume)
```

`run.sh` builds the container, extracts+verifies the rootfs, applies every fix needed to
reach the main screen, boots the two UI processes, and copies screenshots out.

**Prefer Docker Compose?** The container is also defined in `compose.yaml` (which builds
`docker/Dockerfile`). Set the firmware path once and use compose for lifecycle, `run.sh` for the
pipeline:

```sh
cp .env.example .env      # then edit OTA_DIR to your …/main_os/ota_v240
docker compose up -d --build
./run.sh up               # extracts+sets up (reads OTA_DIR from .env); then boot/tap as above
```

Compose starts only `emu` by default and **publishes on localhost only**: **12100**
(raw FiiO Link), **12113** (direct stock HTTP), UDP **12101** (not a LAN multicast
relay), and viewer **8080**. Try `python3 tools/fiio_link.py`.

The optional `wsbridge` profile adds **12103** (WebSocket→TCP bridge + stock HTTP
proxy) for WebSocket clients and protocol debugging:

```sh
docker compose --profile wsbridge up -d wsbridge
./run.sh wscheck --control
docker compose --profile wsbridge stop wsbridge  # when finished
```

With the bridge enabled, the read-only browser protocol inspector is at
**http://localhost:12103/bridge/**; disconnect it before using another control client.
See [docs/WEBSOCKET.md](docs/WEBSOCKET.md) for verified framing and bridge limits,
[docs/NETWORK.md](docs/NETWORK.md) for network setup. Stock V2.40 itself has no WS route.
(`./run.sh up <dir>` writes `.env` for you.)

> **Why `--privileged`?** qemu-user needs a large contiguous VA reservation, writable
> `binfmt_misc`, and mountable POSIX mqueues. The container registers **only** a mipsel
> binfmt handler — see [docs/EMULATION.md](docs/EMULATION.md) for why not to auto-register all.

## Repository layout

```
run.sh                 host orchestrator (up / boot / tap / capture / diag / shell / stop / down / nuke)
docker/Dockerfile      reproducible environment (qemu-user, mipsel toolchain, tools)
compose.yaml           container definition (builds the Dockerfile) + FiiO Link port mappings
.env.example           OTA_DIR (firmware path) for compose; copy to .env
scripts/               in-container pipeline
  00_extract_rootfs.sh   decrypt+assemble+unsquashfs the firmware (sha256-verified)
  10_setup_env.sh        binfmt, mounts, /dev + sysfs stubs, battery, LOCAL_IMG_ANIM, shim
  20_boot.sh             run mq_ui + mq_player, capture the framebuffer
  30_tap.sh              inject a tap at a screen coordinate, re-capture
  capture.sh 99_stop.sh lib.sh
  40_stream.sh           live viewer + touch/swipe bridge daemon (./run.sh view)
sdcard/                drop media here -> appears as the device's SD card (/tmp/sdcard) in the File Browser
assets/                optional viewer skin (owner's original photo; included)
shim/                  freestanding MIPS ioctl shim (fbshim.c) + build script; mqshim.c (diag)
tools/                 inject.py (touch), uisniff.c (mqueue sniffer), fb2png.py (fb → PNG), stream.py (viewer)
ghidra/                headless decompile scripts + RE notes
firmware/README.md     how to obtain + decrypt the firmware (NO firmware here)
docs/                  STATUS, EMULATION (deep dive), PROTOCOL, TOUCH, images/
AGENTS.md              shared instructions for coding agents continuing this work
```

## Documentation

- **[docs/STATUS.md](docs/STATUS.md)** — what works, screenshots, what's next
- **[docs/EMULATION.md](docs/EMULATION.md)** — the stack + every non-obvious fix (read this first)
- **[docs/TOUCH.md](docs/TOUCH.md)** — touch event format + coordinate mapping
- **[docs/VIEWER.md](docs/VIEWER.md)** — live browser viewer + touch/swipe bridge (`./run.sh view`)
- **[docs/AUDIO.md](docs/AUDIO.md)** — PCM capture, browser sound, WAV export, and card discovery
- **[docs/KEYS.md](docs/KEYS.md)** — physical-button audit, corrected codes, app assignments, remaining work
- **[docs/SETTINGS.md](docs/SETTINGS.md)** — settings storage, confirmed values and configuration without UI navigation
- **[docs/NETWORK.md](docs/NETWORK.md)** — reproducible eth1/network setup (Compose 2.36+), localhost client, safety and live checks
- **[docs/PROTOCOL.md](docs/PROTOCOL.md)** — FiiO Link frames, mqueues, network ports, auth
- **[docs/DEVICE.md](docs/DEVICE.md)** — the real device on the network (ports, mDNS, no debug unlock)
- **[docs/DISKOS.md](docs/DISKOS.md)** — diskOS V2.40 compatibility (build works; only the size cap blocks)
- **[firmware/README.md](firmware/README.md)** — download + decrypt + device facts
- **[docs/RE.md](docs/RE.md)** — deep-analysis playbook (method + findings per direction; new firmware versions)
- **[ghidra/README.md](ghidra/README.md)** — reverse-engineering setup + findings

## Legal / scope

Independent research project; not affiliated with or endorsed by FiiO/SNOWSKY.
This is a source-code emulator release, not firmware to flash onto a device.
Project code and the owner's skin photo are [MIT licensed](LICENSE). Vendor firmware,
branding and firmware UI depicted in screenshots are not relicensed by this project.

For interoperability research and personal customization of a device you own. Firmware is
downloaded by the user from FiiO and is not redistributed here. Flashing modified images to
real hardware is gated by an ECDSA signature the manufacturer controls; this project only
runs the unpacked binaries under emulation.
