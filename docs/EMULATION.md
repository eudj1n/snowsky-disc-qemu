# Emulation deep-dive

How the Snowsky Disc firmware is run without the hardware, and every non-obvious
thing that had to be true before the UI would reach its main screen.

## Stack

```
macOS/Linux host
  └─ Docker (privileged Linux VM)
       └─ qemu-mipsel-static (user-mode)   ← runs the MIPS32 guest binaries
            └─ chroot /work/rootfs         ← unpacked firmware root filesystem
                 ├─ mq_ui       (LVGL GUI, owns POSIX mqueue "ui")
                 └─ mq_player   (audio/backend, owns "player", pushes state to "ui")
```

- **User-mode** qemu (not full-system): we execute the two userland binaries directly;
  there is no guest kernel. Anything the binaries expect from the kernel/drivers we
  fake with sysfs/dev stubs and an ioctl shim.
- `--privileged` is required: qemu-user needs to reserve a large contiguous guest VA,
  binfmt_misc must be writable, and POSIX mqueues must be mountable.

## binfmt_misc — register ONLY mipsel

The guest does `popen()`/`execve()` of other MIPS binaries (`/bin/sh`, `cmd_watchdog`,
`cat …/name`). For those child execs to run, the kernel needs a binfmt_misc handler
that hands MIPS ELFs to qemu.

**Do not** run `qemu-binfmt --reset -p yes` / `multiarch/qemu-user-static --reset`: it
registers *every* qemu interpreter including `qemu-aarch64`, which then intercepts the
host VM's own native arm64 binaries (containerd-shim, unpigz, …) → `exec format error`,
breaking Docker until you restart Docker Desktop. This happened twice.

Instead register a single mipsel entry with a mask that matches MIPS32-LE ELFs and
nothing else (`scripts/10_setup_env.sh`). The mask ignores ELF bytes 6–15 so it matches
busybox (which sets `EI_ABIVERSION`) as well as glibc binaries.

## The ioctl shim (`shim/fbshim.c`)

The guest opens `/dev/fb0` and issues framebuffer ioctls, and reads input-device names.
There is no real framebuffer/driver, so an `LD_PRELOAD`-style shim intercepts `ioctl`:

- `FBIOGET_VSCREENINFO` → report 360×360, yres_virtual 1080, 32bpp, XRGB8888 (R@16 G@8 B@0 A@24)
- `FBIOGET_FSCREENINFO` → smem_len = 360·1080·4, line_length = 1440, visual TRUECOLOR
- `EVIOCGNAME` → return the input device name
- all other `0x46xx` fb ioctls (PAN/BLANK/PUT) → return 0 (no-op)

The shim is **freestanding** (`-nostdlib`, raw MIPS syscalls). A normal glibc-linked
`.so` fails to load because the host toolchain glibc (2.36) ≠ device glibc (2.29):
`cannot open shared object`. Freestanding + no NEEDED entries sidesteps that.

Two gotchas that were fixed:
- **nan2008**: the device loader is `ld-linux-mipsn8`; the shim's ELF `e_flags` must have
  the nan2008 bit or it is rejected. `build_shims.sh` stamps `0x70001407` at offset 36.
- **fd leak**: the shim logged to `/fbshim.log` on every ioctl and never closed the fd.
  Over the boot animation's hundreds of PAN ioctls this exhausted the fd table, and the
  *next* `mq_open("ui")` failed — which looked like an mqueue bug but was fd exhaustion.
  Fixed by closing the log fd (and not logging on the hot path).

It preloads via `/rootfs/etc/ld.so.preload` (a file the guest ld.so reads), **not**
`LD_PRELOAD`: the env var does not survive the guest's `popen()` children, and the path
must resolve inside the chroot.

`/dev/fb0` is a plain file; qemu maps it with `mmap` and the guest draws into it. See
[TOUCH.md](TOUCH.md) / `tools/fb2png.py` for reading it back.

## Blocker 1 — frozen splash: `mq_open("ui")` = EMFILE

`mq_ui` creates the POSIX message queue `ui` (`mq_maxmsg=32, mq_msgsize=8192`); `mq_player`
opens it and pushes UI state. Under emulation `mq_open` failed with **EMFILE** ("too many
open files") even though the process had ~8 fds open.

EMFILE from `mq_open` is not only the fd limit — it also fires on **`RLIMIT_MSGQUEUE`**
exhaustion (bytes of POSIX-queue memory per user). Each queue costs `maxmsg·msgsize` =
256 KB. Guest processes killed with SIGKILL leave their queues allocated in the kernel's
own mqueue instance, which a `mount -t mqueue …` view does **not** list, so
`rm /dev/mqueue/*` never freed them. After a handful of runs the limit was blown.

**Fix:** `ulimit -q 268435256` before launching. (qemu-user 7.2's mqueue passthrough is
otherwise correct — verified a clean glibc test binary creates `/dev/mqueue/qt` fine.)

## Blocker 2 — "battery too low, shutting down" screen

With the queue working, the UI left the splash but showed a battery icon and
`电量过低，倒计时关机 / 19S` (battery too low, shutdown countdown). The fuel gauge is read
from `/sys/class/power_supply/cw221X-bat/capacity`; absent, it reads 0%.

**Fix:** create that sysfs tree with `capacity=100, status=Full, …` (`10_setup_env.sh`).

## Blocker 3 — main screen built but never shown (boot animation overlay)

With a healthy battery the UI went *back* to the SNOWSKY splash and stayed. Tracing showed
`mq_ui` actually **built** the main screen (it opened all `main_screen/main_1/*.png` assets)
— but the boot logo animation (`power_on/opening_*.png`, state flag `power_on_ing`) is an
**infinite-loop overlay drawn on top** of it and never auto-clears under emulation (~17
loops observed). The config key `LOCAL_IMG_ANIM` controls it.

**Fix:** `sqlite3 sysconfig.db "UPDATE SYSCONFIG SET LOCAL_IMG_ANIM=0"` → the overlay is
skipped and the real first-boot flow appears: **splash → language wizard → main menu**.

**Catch on a fresh rootfs (two parts):** `/usr/data` is a **separate UBIFS partition** on the
device (`etc/init.d/S21mount_ubifs`) and is *empty* in the squashfs. On hardware the init
scripts `S98FIIO` + `fiio_init.sh` populate it from templates in the read-only rootfs. We
don't run init, so:

1. **Seed `/usr/data`** — most importantly copy the zlog configs
   `usr/project/config/zlog_{player,ui}.conf` → `usr/data/fiio/log/` (and `usr/project/db/*`,
   e.g. `dic.db`, → `usr/data/fiio/db/`). Without the zlog config, `mq_player`'s `zlog_init()`
   fails (`Error: zlog_init`), the backend never starts, and **no `sysconfig.db` is ever
   created** — so on a truly fresh rootfs you're stuck on the splash with an empty
   `usr/data/fiio/db/`.
2. **Priming boot** — even seeded, `sysconfig.db` is created by `mq_player` on first boot with
   `LOCAL_IMG_ANIM=1`. So a throwaway boot creates the DB, then we set `LOCAL_IMG_ANIM=0`, then
   boot for real.

`scripts/10_setup_env.sh` does both automatically. (The language choice and this flag then
persist in the `/work` volume.)

The first-boot **language wizard** is gated on the same DB: it shows only while `LANGUAGE` is
out of range (fresh default 100). `LANGUAGE` is a **0-based index** (switch in mq_ui
`FUN_004776e4`): `0 zh · 1 tw · 2 en · 3 ja · 4 ko · 5 es · 6 it · 7 de · 8 pt · 9 ru`. Setting
any valid value picks the language and skips the wizard; `10_setup_env.sh` presets `LANG_CODE`
(default 2 = English). (Out-of-range codes like 100/102 fall back to Chinese — which is why the
"language index = code − 100" guess was wrong.)

## What mq_player sends at boot

Sniffing the `ui` queue (see `tools/uisniff.c`) shows the backend push these FiiO-Link
frames right after start (there is **no** explicit "show main" command — the transition is
internal to `mq_ui` once the animation is gone):

| tag | value | meaning |
|-----|-------|---------|
| `aa1d` | `0064` | battery = 100 |
| `a634` | 0 | — |
| `aa24` | `{"volume":120,"brightness":20,"dac_filter":1,…}` | settings blob |
| `a102` | 0 | play state |
| `a712` | 0 | — |
| `a620` | `{"SN":"","NB":"","WIFI_MAC":…}` | device info |
| `aa1c` | 0 | — |
| `a202` | `{"state":2}` | player state |

See [PROTOCOL.md](PROTOCOL.md) for the frame format.

## Framebuffer capture

`fb0` = 360×1080×4 (three 360×360 sub-buffers). `mq_ui` does **not** use `FBIOPAN_DISPLAY`;
it alternates drawing to buf0/buf1, so the current screen is the **last-flushed** buffer
(a static screen is not re-flushed, so the other buffer holds a stale frame). `tools/fb2png.py`
emits every sub-buffer and prints each one's non-black pixel count so you can pick the live
one. Pixels are BGRX and the panel is 180°-rotated, so the converter reverses pixel order.

## Ordering / timing

Start `mq_ui` first (creates `ui`), then `mq_player` (retries `mq_open("ui")`). Reaching the
language screen / main menu takes ~20–24 s under qemu — allow ≥24 s before capturing.

## Known noise (harmless)

`WATCHDOG: feed failed`, `adc get voltage failed: Bad file descriptor`,
`gpio_get_value fail`, `Failed to open …/brightness` — all from absent hardware; the
backend keeps running. Note the *ioctl* failures on these devices are harmless, but the
initial **`open("/dev/gpio")` must succeed** or `mq_player` aborts with `failed to open
device` before it inits the DAC / pushes UI state (→ stuck splash). So `10_setup_env.sh`
creates 0-byte stubs for `/dev/gpio`, `/dev/jz_adc_aux_0`, `/dev/jz_watchdog` (open works,
later ioctls fail harmlessly). `/dev/jz_adc_aux_0`'s ADC reads still fail — not needed.

## Troubleshooting

- **`fb2png` prints `…-b2 non_black_px=0`** — normal. There are three sub-buffers; `mq_ui`
  only ever draws to buf0/buf1 (alternating), so buf2 stays black. The current screen is
  whichever of `-b0`/`-b1` has the higher non-black count.
- **`sysconfig.db missing` on the very first `10_setup_env` of a fresh rootfs** — expected
  (see the `/usr/data` catch above); the script seeds `/usr/data` then primes the DB. If it
  still reports missing after priming, check `/work/mq_player.log`.
- **`/work/mq_player.log` = `Error: zlog_init`** — the backend can't init logging because the
  zlog config isn't in `usr/data/fiio/log/`. `10_setup_env.sh` seeds it from
  `usr/project/config/zlog_{player,ui}.conf`; if the seed step didn't run (older checkout),
  `git pull` and re-run, or copy those two files manually.
- **`docker run`/`docker start`/`docker exec` hangs and a new container is stuck in
  `Created`** — the Docker Desktop VM got wedged (often after an earlier OOM or a killed
  `docker` operation left a zombie containerd-shim). Existing containers keep working, but new
  ones won't start. Fix: **restart Docker Desktop**, then `./run.sh up …` again. Give the VM
  ≥8 GB (two qemu-user MIPS processes plus the popen/`cmd_watchdog` children are memory-hungry;
  running out is what wedges it).
