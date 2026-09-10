# diskos-qemu

Emulating the **FiiO Snowsky Disc** (Ingenic X2000, MIPS32) music player from its
stock **V2.40** firmware, under `qemu-user` — booting the real UI to its main screen
and driving it with synthetic touch, entirely without the hardware.

Groundwork for building/testing custom firmware (cf. [b0hemia/diskos](https://github.com/b0hemia/diskos))
and a "FiiO YMD"-style sync bridge against an emulated device instead of a physical one.

![main menu](docs/images/04-main-menu.png)

_The stock main menu running under qemu — battery 100%, volume 120, app carousel
(Settings · File Browser · Now Playing). Reached by tapping through the first-boot
language wizard via injected touch events._

## What works

Splash → first-boot language wizard → **main menu** → into apps (file browser shows the
SD content), plus working **touch injection**. Full detail + screenshots: **[docs/STATUS.md](docs/STATUS.md)**.

## Quickstart

Requires Docker (macOS or Linux). The firmware is **not** in this repo — get it first:
**[firmware/README.md](firmware/README.md)** (FiiO forum download + `fo123` decrypt info).

```sh
# 1. point the tool at the OTA chunk directory (…/main_os/ota_v240 of the unzipped firmware)
./run.sh up /path/to/SNOWSKY_DISC_update_.../main_os/ota_v240

# 2. boot to the main screen; PNGs land in ./shots/
./run.sh boot

# 3. tap something (coordinates are what you SEE in the PNG; flipped internally)
./run.sh tap 180 315      # e.g. the Confirm button on the language screen
./run.sh shell            # or drop into the container to poke around

# stop / teardown
./run.sh stop
./run.sh down             # remove container (keeps the extracted-rootfs volume)
```

`run.sh` builds the container, extracts+verifies the rootfs, applies every fix needed to
reach the main screen, boots the two UI processes, and copies screenshots out.

> **Why `--privileged`?** qemu-user needs a large contiguous VA reservation, writable
> `binfmt_misc`, and mountable POSIX mqueues. The container registers **only** a mipsel
> binfmt handler — see [docs/EMULATION.md](docs/EMULATION.md) for why not to auto-register all.

## Repository layout

```
run.sh                 host orchestrator (build / up / boot / tap / shell / down)
docker/Dockerfile      reproducible environment (qemu-user, mipsel toolchain, tools)
scripts/               in-container pipeline
  00_extract_rootfs.sh   decrypt+assemble+unsquashfs the firmware (sha256-verified)
  10_setup_env.sh        binfmt, mounts, /dev + sysfs stubs, battery, LOCAL_IMG_ANIM, shim
  20_boot.sh             run mq_ui + mq_player, capture the framebuffer
  30_tap.sh              inject a tap at a screen coordinate, re-capture
  capture.sh 99_stop.sh lib.sh
shim/                  freestanding MIPS ioctl shim (fbshim.c) + build script; mqshim.c (diag)
tools/                 inject.py (touch), uisniff.c (mqueue sniffer), fb2png.py (fb → PNG)
ghidra/                headless decompile scripts + RE notes
firmware/README.md     how to obtain + decrypt the firmware (NO firmware here)
docs/                  STATUS, EMULATION (deep dive), PROTOCOL, TOUCH, images/
CLAUDE.md              orientation for Claude Code sessions continuing this work
```

## Documentation

- **[docs/STATUS.md](docs/STATUS.md)** — what works, screenshots, what's next
- **[docs/EMULATION.md](docs/EMULATION.md)** — the stack + every non-obvious fix (read this first)
- **[docs/TOUCH.md](docs/TOUCH.md)** — touch event format + coordinate mapping
- **[docs/PROTOCOL.md](docs/PROTOCOL.md)** — FiiO Link frames, mqueues, network ports
- **[firmware/README.md](firmware/README.md)** — download + decrypt + device facts
- **[ghidra/README.md](ghidra/README.md)** — reverse-engineering setup + findings

## Legal / scope

For interoperability research and personal customization of a device you own. Firmware is
downloaded by the user from FiiO and is not redistributed here. Flashing modified images to
real hardware is gated by an ECDSA signature the manufacturer controls; this project only
runs the unpacked binaries under emulation.
