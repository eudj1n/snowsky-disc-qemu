# AGENTS.md

Shared instructions for coding agents continuing this project. Read this, then
`docs/EMULATION.md`. The goal: run the FiiO Snowsky Disc stock firmware under qemu-user
and drive its UI, as groundwork for custom firmware / a sync bridge.

## TL;DR of the current state

Full boot to the **main menu** works, **touch injection** works, and the **SD card / File
Browser** works (drop media in `./sdcard`, browse it to the leaf tracks). The three fixes that
got the UI up (all encoded in `scripts/10_setup_env.sh`): raise **`RLIMIT_MSGQUEUE`**
(`ulimit -q`), stub the **battery** sysfs at 100 %, and set **`LOCAL_IMG_ANIM=0`** to kill
the boot-animation overlay. Touch coordinates are **180°-rotated** and press/release must be
**separated in time** (and a ~1 s hold is a long-press — use ~0.3 s to open a list item). The
SD needs a re-mount after the guest's boot-time umount (`sd_mount()` in `lib.sh`). See
`docs/STATUS.md` for screenshots and what's next.

## How to run

Host: `./run.sh up <…/main_os/ota_v257>` (once) → `./run.sh boot` → `./run.sh tap <x> <y>`.
Screenshots are copied to `./shots/`. For an **interactive** session use `./run.sh view` →
open `http://localhost:8080` (live screen, click=tap, drag=swipe; optional device-photo skin
from `assets/skin.png`) — see `docs/VIEWER.md`; the daemon is `tools/stream.py` /
`scripts/40_stream.sh`. `boot` now keeps the guests alive ~30 min (`GUEST_TTL`) for this. `./run.sh shell` gives a container shell where the
`/repo/scripts/*.sh` pipeline lives. Everything qemu-side runs **inside** the container
(named `diskos-qemu`, `--privileged`); `/work` is a Docker volume holding the extracted
rootfs and runtime state.

To view a captured screen, `Read` the PNGs in `./shots/` (e.g. `boot-b0.png`, `boot-b1.png`).
Because `mq_ui` alternates two sub-buffers, use `emu/fb-live` (0 or 1) to identify
the last-written buffer, or the viewer's `/frame` endpoint. The non-black pixel
count printed by `fb2png.py` is only a fallback heuristic, not evidence of recency.

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
- Start **`mq_ui` first** (creates the `ui` queue), then `mq_player`. Boot waits for
  network listeners, both input devices and a framebuffer flush before capturing;
  use the readiness result rather than a fixed sleep (see `docs/VIEWER.md`).
- Touch: append 16-byte `input_event`s to `/rootfs/dev/input/event1`. Press =
  `ABS_MT_TRACKING_ID=0` / `BTN_TOUCH=1`; release = `TRACKING_ID=-1` / `BTN_TOUCH=0`. The
  read-cb drains all queued events per call, so **inject press → sleep ~1s → release**, else
  LVGL only sees the net (released). The ~1 s hold above is a diagnostic long press;
  use the normal ~0.3 s tap helper for list items. Tap point = `(359-x, 359-y)` of what you see;
  `30_tap.sh` flips it for you.
- The first-boot **language wizard** is gated on the `LANGUAGE` column: it shows only while
  LANGUAGE is out of range (the fresh default is 100). `LANGUAGE` is a **0-based index** (switch
  in mq_ui `FUN_004776e4`): `0 zh · 1 tw · 2 en · 3 ja · 4 ko · 5 es · 6 it · 7 de · 8 pt · 9 ru`.
  `10_setup_env.sh` presets it (`LANG_CODE`, default **2 = English**), which both picks the
  language AND skips the wizard, so a fresh `/work` volume boots straight to the English main menu.
- **SD card / File Browser**: `mq_ui` (`mount_storage_dev.c`) **umounts `/tmp/sdcard` once at
  startup** and expects a hotplug handler to remount the card — which nothing does under
  emulation, so the browser shows nothing. The File Browser **re-scans `/tmp/sdcard` live on
  entry**, so the fix is just to keep the card mounted: `sd_mount()` (`lib.sh`) re-mounts
  `/dev/mmcblk0p1 -o iocharset=utf8` after the boot-time umount (called from `10_setup_env.sh`,
  end of `20_boot.sh`, and `30_tap.sh`). It is **not** a Docker-volume propagation issue and
  needs **no** synthetic netlink uevent — both were dead ends. The card is a real FAT block
  device (`mknod /dev/mmcblk0[p1] b 7 <loop minor>`, not a symlink — the guest's chroot can't
  resolve `/dev/loopN`). Drop media into `./sdcard`; it is rebuilt into the image each setup.
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
  `tools/fb2png.py` (framebuffer → PNG, BGRX + 180° rotation), `tools/stream.py` (live viewer +
  touch/swipe HTTP bridge; served by `scripts/40_stream.sh`, `docs/VIEWER.md`).
- RE: `ghidra/` scripts + notes. Key functions: `mq_ui` main `FUN_004036ec`, touch device
  open `FUN_0055da20`, touch read-cb `FUN_0055db8c`.
- Firmware acquisition + decrypt: `firmware/README.md` (password `fo123`; rootfs and
  six stock binary hashes pinned in `firmware/v<version>.json`).
- Protocol + real-device RE: `docs/PROTOCOL.md` (FiiO Link frames, verified-live 12100 handshake
  `0599…`, the corrected 12103 route mapping — **TCP device control is auth-free**;
  stock file transfer uses separate HTTP, see `docs/HTTP_API.md`), `docs/DEVICE.md`
  (ports/mDNS, no stock debug unlock), `docs/DISKOS.md` (V2.40 builds;
  only the size cap blocks). Network/auth `mq_player` function addresses are in `ghidra/README.md`.

## Conventions

- For another firmware/product, read `docs/PORTING.md` and its `docs/firmware/<version>.md`
  report first. `firmware/inventory/` contains observed inputs, not runtime enablement
  profiles. Keep vendor-reported changes separate from verified emulator features;
  update `CHANGELOG.md` for emulator changes. Never replace V2.40 hashes/addresses blindly.
- Support at most three validated firmware versions (FIFO). Promote only after
  validation and release preparation; a fourth retires the oldest from current
  runtime support and CI. OTA detection alone does not move the window. Preserve
  historical tags, inventories and analysis; see `docs/PORTING.md` for the checklist.
- `FW_VERSION` selects a reviewed runtime profile (default `2.57`, opt-in `2.40`).
  Setup/boot validate product/version and six binary fingerprints before execution.
  Key patch validation normalizes only the permitted instruction, then checks the full
  stock hash and executable PT_LOAD mapping. Read-only key/network/HTTP diagnostics select
  separately verified V2.40/V2.57 addresses by full binary fingerprint (see
  `docs/DIAGNOSTICS.md`); legacy GDB breakpoint files remain V2.40-specific.
- Public-release preparation: `docs/PUBLIC_RELEASE.md`. Keep passwords out of the root
  README and private-project names out of tracked files. Do not change visibility or
  rewrite immutable history without explicit approval. Code/photo license: MIT.
- Default development branch: `2.x`; firmware-based release tags `v2.40`, then
  `v2.40-r1` for emulator fixes against the same firmware. See `docs/CI.md` for pinned
  CI, secret-backed downloads and release gates. Never log a direct firmware URL.
- Full firmware-free suite: `docker run --rm --network none -v "$PWD:/repo:ro"
  diskos-qemu-ci bash /repo/ci/test.sh` after `docker build -t diskos-qemu-ci docker`.
  `ci/integration.sh` uses a fresh disposable Compose stack, never the interactive volume.
- Firmware and anything derived from it (rootfs, `.enc`, `.squashfs`, FiiO binaries, Ghidra
  project, captured `shots/`) are **git-ignored** — never commit firmware. Commit code,
  scripts, docs, and the curated screenshots in `docs/images/`.
- Prefer editing the pipeline scripts over ad-hoc container commands, so the repo stays the
  source of truth and the work stays reproducible from another machine.
- Screenshots for the docs live in `docs/images/`; throwaway captures go to `shots/` (ignored).

## Likely next tasks (see docs/STATUS.md "Next")

For continuing DISC protocol research, start with `docs/PROTOCOL_RESEARCH.md`:
it records the checkpoint, remaining tasks in priority order and validation status.
Update that document when completing a research item so another session can resume.

Local audio works: `tinyshim` redirects `/proc/asound/cards` discovery to `/etc/asound.cards`
(x2000), so stock firmware selects I2S3_OUT (6), hw:0,3. No audio binary patches.
Capture: `/audio.pcm` + `/audio.fmt`; `./run.sh audio` exports a WAV, and the viewer offers
Enable sound / Replay capture. See `docs/AUDIO.md` for runtime evidence and corrected route
interpretation (`0x10000000` is INPUT). USB/BT and DSD remain unvalidated.

Physical controls now work in the viewer: volume single/double/hold respects the app's
assignments; media play/pause is `0xfa`; `0x103` sleeps/wakes the screen. GPIO, brightness,
touch/LCD stubs and browser DAC gain are implemented. Long Power safely stops only guest
processes; Power while off boots them again (not stock standby/shutdown emulation).
The viewer places translucent pink hotspots over the physical buttons on the photo;
icons appear on hover/focus/press. Gesture shortcuts and alignment live in collapsed
**Debug**. Without a skin, physical controls remain a labelled row. See `docs/VIEWER.md`.
Raw power code `0x108` can invoke `poweroff -f` and is blocked in the viewer — do not sweep
event codes blindly. See `docs/KEYS.md` and the current screenshots in `docs/STATUS.md`.
The stock idle-poweroff path also calls BusyBox `reboot`; `fbshim` blocks the kernel call
and publishes `emu/power-request` for the viewer to stop only this guest. This was tested
with actual guest `poweroff -f` after verifying its dynamic symbol binding to the shim.
`fbshim` observes framebuffer mmap/memcpy and records `emu/fb-live` so the viewer picks
the actual last-written buffer instead of a stale frame when both buffers changed.

Network services now bind 12100/12103: Compose names the real Docker interface `eth1`
(Compose >=2.36), and `scripts/16_network.sh` re-announces its existing address after
the stock netlink detector subscribes. No Wi-Fi DB overrides or network binary patches.
Guest `ip` read queries use stock BusyBox (the standalone ip address dump fails in qemu).
`guest_run()` drops dangerous capabilities; wrappers block automatic OTA/NTP/hwclock
and network reconfiguration. All ports publish only on localhost. Recreate the container
with `docker compose up -d --build`, then boot/view. See `docs/NETWORK.md` for repeatable
probes, `tools/fiio_link.py` for host control. V2.40's active HTTP callback `004b9d38`
has no WebSocket route in table `006c7a50`; unknown URLs return empty 200 via `0048f8f8`.
The bundled mg_dash code is not the active router; the earlier password-gate explanation
was wrong. Reproduce with `tools/inspect_http_routes.py` and `tools/probe_websocket.py`.
An explicit native WS→TCP bridge now serves host `12103/api/websocket`, forwarding
FiiO Link to `emu:12100`; other HTTP paths proxy to unchanged guest `12103`. Host
`12113` bypasses it for stock HTTP diagnosis. The opt-in `wsbridge` Compose profile starts the bridge unprivileged,
read-only, without guest volumes; Dockerfile supplies python3-aiohttp. No firmware patch.
Enable with `docker compose --profile wsbridge up -d wsbridge`; ordinary up/start/boot
do not launch it. CI enables the profile explicitly.
`./run.sh wscheck --control` compares TCP/WS and checks volume/playback (leaves paused).
`http://localhost:12103/bridge/` is a read-only protocol inspector; disconnect it before
another client (stock TCP is single-client). See `docs/WEBSOCKET.md`. LAN discovery
and FiiO Control app compatibility remain unvalidated.

Stock HTTP file/playlist operations and remote settings are documented in
`docs/HTTP_API.md` and `docs/REMOTE_SETTINGS.md`. Use `tools/fiio_http.py` for
`/dir/`, raw-body `/audio/` uploads, `/progress/`, single-path `/file/` deletion and
custom playlists. HTTP 200 is not success; progress can survive deletion. Playlist
headers named `list_id`/`src_list_id`/`dst_list_id` use positions, not database IDs.
Avoid stock batch recursive deletion (it constructs shell commands). `0622/0000`
starts a scan; watch `a60a` start/finish and `a622` counts. Gain/DRE/filter/SPDIF and
PEQ helpers are shared by TCP/WS; filter and EQ network enums differ from SQLite.
The new CI scenarios use only disposable generated media. Never substitute the
broad `0800` factory-reset command for the app's library-reset action.

`docs/REMOTE_MODES_THEMES.md` covers stock work-mode control (Link 1 USB DAC,
8 local, 10 AirPlay), the five `06d3` source-codec preferences, and lock-screen HTTP.
Mode/codec readback does not establish hardware audio. Codec changes reopen the
local player; restore the desired mode afterwards. `tools/fiio_theme.py` uploads
and activates complete custom PNGs: an empty-body custom POST clears its image
path, and `flag-in-use: 0` still clears the previously active theme. System-theme
selection uses a separate source namespace. The capture checklist in that doc
requires HTTP 12103 and TCP 12100; an ordinary HTTP proxy may miss the latter.

Physical iOS captures are summarized in `docs/FIIO_CONTROL_APP.md`; only sanitized
protocol fixtures live in `tools/fixtures/`. Full `a202` snapshots and state-only
deltas coexist; DISC uses 0 playing / 1 paused. Paused seeks have no immediate
position acknowledgement. Current queue is observed via HTTP `curlist/song`, then
TCP `0100` index + type 0 + localized queue label. `play_queue_index()` now reads
the current queue length before selecting without a label; `ci/queue_check.py`
checks label variants and empty/replaced queues (`CI_SCENARIO=queue` for fresh
empty-queue coverage). A raw out-of-range selector can leave `0202` silent until
a valid album is selected again. Never replay stale queue selections. The physical trace ran in random mode
and moved 3 → 11 → 3, so never infer queue position by increment/decrement alone.
`play_mode()` reads `0105` but expects `a102`, not the mechanically derived `a105`.
`0426` has no assigned handler in V2.40/V2.57; retained counter JSON strings do not prove
support. Use `0406`, HTTP `curlist/song` and `0202` instead. The focused
`CI_SCENARIO=queue-reads` verifies both read commands without relying on M21 semantics.
`docs/M21_COMPARISON.md` is reference only: M21's FiiO Music uses UTF-16 length
units, a different state enum and toggle semantics. DISC remains the priority;
do not copy those Android rules into its client.

Manual Update media lib now works too: `sd_mount()` mounts INSIDE chroot so
`/proc/mounts` records source `/dev/mmcblk0p1`, accessible to the scanner. The old
`/work/rootfs/dev/mmcblk0p1` source passed Browse files but failed the scanner's
`access(source)` gate. Four test tracks were scanned and returned over TCP.
V2.57 Auto update is a volatile UI flag (defaults to 1 each restart), triggered by
SD insertion (`aa22`), not by the emulator's boot remount alone. Repeated scans work
after dismissing the result via the OK button background (130,303) and unlocking
the UI; backlight-on may still show a clock lockscreen. Click the Auto text row
(170,141), not its circle. `sd_mount()` primes stock `blkid /dev/mmcblk0p1`: the two
mmc nodes alias one loop device, and cold enumeration otherwise misses the partition
name needed by stock hotplug remounting. Cyrillic add/rename/delete are checked in
`ci/storage_check.py` (V2.57 only). USB export/eject remains unvalidated. See
`docs/SETTINGS.md` and `docs/MEDIA_LIBRARY.md`; do not inject broad netlink broadcasts.
