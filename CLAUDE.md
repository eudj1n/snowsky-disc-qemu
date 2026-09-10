# CLAUDE.md

Orientation for a Claude Code session continuing this project. Read this, then
`docs/EMULATION.md`. The goal: run the FiiO Snowsky Disc stock firmware under qemu-user
and drive its UI, as groundwork for custom firmware / a sync bridge.

## TL;DR of the current state

Full boot to the **main menu** works, and **touch injection** works. The three fixes that
made it possible (all encoded in `scripts/10_setup_env.sh`): raise **`RLIMIT_MSGQUEUE`**
(`ulimit -q`), stub the **battery** sysfs at 100 %, and set **`LOCAL_IMG_ANIM=0`** to kill
the boot-animation overlay. Touch coordinates are **180°-rotated** and press/release must be
**separated in time**. See `docs/STATUS.md` for screenshots and what's next.

## How to run

Host: `./run.sh up <…/main_os/ota_v240>` (once) → `./run.sh boot` → `./run.sh tap <x> <y>`.
Screenshots are copied to `./shots/`. `./run.sh shell` gives a container shell where the
`/repo/scripts/*.sh` pipeline lives. Everything qemu-side runs **inside** the container
(named `diskos-qemu`, `--privileged`); `/work` is a Docker volume holding the extracted
rootfs and runtime state.

To view a captured screen, `Read` the PNGs in `./shots/` (e.g. `boot-b0.png`, `boot-b1.png`).
Because `mq_ui` alternates two sub-buffers, the current screen is whichever of `-b0`/`-b1`
looks right / has the higher non-black pixel count printed by `fb2png.py`.

## Hard-won facts (don't rediscover these)

- **NEVER** run `qemu-binfmt --reset -p yes` or `multiarch/qemu-user-static --reset`: it
  registers `qemu-aarch64` and hijacks the host VM's native binaries → Docker breaks
  (`exec format error`), needs a Docker Desktop restart. Register **only** mipsel (the setup
  script does). This bit us twice.
- `mq_open("ui")` returning **EMFILE** is `RLIMIT_MSGQUEUE` exhaustion, **not** fd count.
  Killed guests leak queues into a kernel mqueue instance a `mount -t mqueue` view doesn't
  show. `ulimit -q` fixes it.
- The shim **must** be freestanding (`-nostdlib`, raw syscalls): device glibc is 2.29, host
  toolchain is 2.36, so a normal `.so` won't load. Preload via `/rootfs/etc/ld.so.preload`,
  not `LD_PRELOAD` (env doesn't survive the guest's `popen()` children). ELF must carry the
  **nan2008** flag (`build_shims.sh` stamps it).
- Start **`mq_ui` first** (creates the `ui` queue), then `mq_player`. Boot to a UI screen
  takes ~20–24 s under qemu — wait before capturing.
- Touch: append 16-byte `input_event`s to `/rootfs/dev/input/event1`. Press =
  `ABS_MT_TRACKING_ID=0` / `BTN_TOUCH=1`; release = `TRACKING_ID=-1` / `BTN_TOUCH=0`. The
  read-cb drains all queued events per call, so **inject press → sleep ~1s → release**, else
  LVGL only sees the net (released). Tap point = `(359-x, 359-y)` of what you see;
  `30_tap.sh` flips it for you.
- The language choice **persists** after the first successful Confirm tap, so later boots go
  straight to the main menu (no wizard).
- `/usr/data` is a **separate partition** (empty in the squashfs). Two consequences on a fresh
  rootfs, both handled by `10_setup_env.sh`: (a) it must be **seeded** with the zlog configs
  (`usr/project/config/zlog_{player,ui}.conf` → `usr/data/fiio/log/`) + `usr/project/db/*`, or
  `mq_player` dies at `zlog_init` and never creates `sysconfig.db`; (b) `sysconfig.db` is then
  created on first boot with `LOCAL_IMG_ANIM=1`, so a **priming boot** is needed before the flag
  can be set to 0. State persists in the `/work` Docker volume.
- If `docker run`/`start`/`exec` hangs and a new container is stuck in `Created` (existing ones
  still work), the Docker Desktop VM is wedged — **restart Docker Desktop**, then retry. Give it
  ≥8 GB. This is the same OOM-adjacent failure seen mid-project.
- `fb2png.py` reporting `-b2 non_black_px=0` is normal (only buf0/buf1 are used).

## Where things are

- Emulation pipeline: `scripts/` (numbered). Shared helpers/paths: `scripts/lib.sh`.
- Shim source: `shim/fbshim.c` (fb + input-name ioctls). Diagnostic mq_open interposer:
  `shim/mqshim.c` (only needed if you suspect an attr/errno issue — normally unused).
- Tools: `tools/inject.py` (touch), `tools/uisniff.c` (sniff the `ui` mqueue non-destructively),
  `tools/fb2png.py` (framebuffer → PNG, BGRX + 180° rotation).
- RE: `ghidra/` scripts + notes. Key functions: `mq_ui` main `FUN_004036ec`, touch device
  open `FUN_0055da20`, touch read-cb `FUN_0055db8c`.
- Firmware acquisition + decrypt: `firmware/README.md` (password `fo123`; rootfs sha256 pinned
  in `scripts/lib.sh`).

## Conventions

- Firmware and anything derived from it (rootfs, `.enc`, `.squashfs`, FiiO binaries, Ghidra
  project, captured `shots/`) are **git-ignored** — never commit firmware. Commit code,
  scripts, docs, and the curated screenshots in `docs/images/`.
- Prefer editing the pipeline scripts over ad-hoc container commands, so the repo stays the
  source of truth and the work stays reproducible from another machine.
- Screenshots for the docs live in `docs/images/`; throwaway captures go to `shots/` (ignored).

## Likely next tasks (see docs/STATUS.md "Next")

Audio path (CS43131 / ALSA stub), network services (TCP 12100 raw FiiO Link, 12103 HTTP/WS
— publish container ports), carousel swipe gestures, optional MCU/UART stub.
