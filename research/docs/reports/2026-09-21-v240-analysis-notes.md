# Deep-analysis playbook

> Historical snapshot preserved during the 2026-09-21 documentation refactor
> from source revision `9bfdbc4`. Dates, results and instructions below describe
> their original checkpoints; they do not authorize new work or define current status.
> Use the [current page](../methods.md) for active guidance.

How to reverse-engineer the Snowsky Disc firmware binaries (`mq_player`, `mq_ui`) and extend
the emulator — written so a **new firmware version** can be re-analysed the same way. Tooling
setup lives in [../research/ghidra/README.md](../../ghidra/README.md); this page is the method + the findings
per direction.

Addresses/layouts below are **V2.40 observations**, not portable constants. For a
second firmware version, start with [PORTING.md](../../../firmware/docs/porting.md) and keep its input and
evidence report separate; do not replace V2.40's pins while investigating another build.

## The two facts that make this tractable

1. **The binaries are fixed-address `EXEC` (not PIE).** Every string/global is at an absolute
   address, so a data reference is a plain `lui/addiu` or a pointer word — no `$gp` games. A
   string at file offset `F` in `.rodata` has vaddr **`F + 0x400000`** (verify per build:
   `vaddr = rodata_vma + (F − rodata_off)`; for V2.40 `rodata_vma=0x6a10b0`, `rodata_off=0x2a10b0`).

2. **The stripped binaries carry their own symbols via zlog.** Almost every function calls the
   logger `FUN_004f550c(cat, "<source/path.c>", <ver>, "<function_name>", <lvl>, <line>, …, fmt, …)`.
   So even with no ELF symbols you get the **source file, function name and line number** of the
   call site. This is the fastest way to map `FUN_xxxx` → what it is: grep the decompilation (or
   strings) for the source paths. Key source files seen:
   `hardware/snowsky_disc/src/echo_key_handler.c`, `process/player/snowsky_disc/src/echo_sys_control.c`,
   `process/ui/mq_ui.c`, `util/src/mount_storage_dev.c`, `control_core/fiio_link/src/fiio_link.c`,
   `http_server_mongoose.c`.

## Workflow (headless Ghidra)

Environment and the one-time arm64-decompiler build are in [../research/ghidra/README.md](../../ghidra/README.md).
Once a project has `mq_player`/`mq_ui` imported+analysed, iterate with the scripts in `research/ghidra/`:

- **`DecFuncs.java <addr…>`** — decompile the function containing each address.
- **`DecAt.java <addr…>`** — same, but if the address is only a *label* (auto-analysis didn't
  make it a function — common for callbacks reached only through a pointer), it disassembles and
  `createFunction`s first. Use this on the target of a function pointer.
- **`RefsTo.java <addr…>`** — list all refs (READ/WRITE/CALL) to a data/code address, with the
  containing function. This is how you follow a runtime-registered callback or find who sets a flag.

Typical trace: find a string → `RefsTo` the string addr → decompile the referencing function →
follow function pointers with `RefsTo`+`DecAt` → find the gate/flag with `RefsTo` on the global.

**Runtime instrumentation (do this before patching a state machine).** Static decompilation alone
whack-a-moles hardware state machines — read the live values with GDB. `research/diagnostics/gdb_probe.sh
<gdb-cmd-file>` boots `mq_ui` + `mq_player` under qemu's gdbstub and attaches `gdb-multiarch`
(arch `mips:isa32r2`, LE). Example `research/ghidra/probe_out_device.gdb` watches the audio output route:
it prints `ctx = *(0x832214)` and `ctx+0x58` at `set_out_device`, showing the value go **0
(NO_OUT_DEV) → 6 (I2S3_OUT)** once card discovery succeeds — the observation that distinguishes
"route never selected" from "format rejected". This is how the audio blocker was actually
understood (belatedly); reach for it first on the remaining directions.

## Direction: physical keys ✅ (viewer controls implemented)

See [KEYS.md](../../../emulator/docs/keys.md) for the corrected mapping, implementation, tests and fidelity limits.
Earlier log-based interpretations of play/pause, menu navigation and power were wrong.

Full chain (V2.40), all via [../research/ghidra/README.md](../../ghidra/README.md) scripts:

```
/dev/input/event0 (name "x2000_key", opened O_RDWR)
  └─ echo_start_key_server  FUN_004d9974  (echo_key_handler.c) — opens event%d, spawns:
       └─ echo_loop_key      FUN_004d9840  — read()s 16-byte input_event; if type==EV_KEY(1)
            calls (*DAT_0088cc50)(code, value)
              └─ echo_sys_key_handler  FUN_004de6fc  (echo_sys_control.c) — the dispatcher
```

The dispatcher is registered by `FUN_004e3410` (`DAT_0088cc50 = &echo_sys_key_handler`). It
**gates on `DAT_0082e9c1` (key-enable): if 0, every key is dropped.** Valid key codes are the
**non-standard range `0xFA…0x10D` (250–269)** — which is why standard evdev codes
(KEY_VOLUMEUP=115 …) do nothing. `value`: 1=press, 0=release, 2=repeat.

| code | action (from dispatcher calls, not just log labels) |
|---|---|
| `0x106` / `0x107` | Volume − / + hold/repeat; configurable via `DAT_0082e9d4`, GPIO-gated |
| `0x103` / `0x109` | Screen sleep/wake (`FUN_004dde48` / `FUN_004e0350`) |
| `0x10c` / `0x10d` | Play long/double log labels only; no playback action in these branches |
| `0x108` | Standby/shutdown; includes a path to `poweroff -f`, not runtime-tested |
| `0xfa` | Media play/pause (`FUN_00424b2c(0, 0)`), verified live |
| `0xfb` / `0xfc` | Volume-button + / − single press, configurable via `DAT_0082e9d2` |
| `0x10a` / `0x10b` | Volume-button + / − double press, configurable via `DAT_0082e9d3` |

Power events do exist here. Do not sweep this range blindly: qemu-user shares the
container kernel, and the shutdown path must be confined before testing it.

The dispatcher gates every key on `DAT_0082e9c1` (key-enable): `if (DAT_0082e9c1==0) return 0;`.
Headless it stays 0 (set only by `FUN_004e847c` = `*(char*)(cmd+0x10)` from an IPC/settings
command, and inside settings-apply `FUN_004e3658` — neither fires under emulation), so keys are
read but dropped.

**✅ Enabled by a one-instruction patch** (`emulator/scripts/patch_keys.sh`, run from `10_setup_env.sh`):
the guard loads the flag with `lbu v0,65(s2)` at `0x004de70c` (file off `0xDE70C`); patch it to
`li v0,1` (`0x24020001`) so the flag always reads 1 and the `beqz` at `0x004de720` is never taken.
`s2` (the struct base, set at `0x004de708`) stays valid for the handler's other fields. The
script matches the exact guard bytes (anchor `addiu s2,v0,-5760` = `80e95224`, then `lbu` =
`41004292` → `01000224`), is idempotent, and no-ops on a firmware whose addresses moved.

Inject the codes into `event0` (16-byte `input_event`, `type=EV_KEY`, value 1 then 0).
These are **already-classified gesture codes**: the reader does not classify a 120 ms
press as single/double/long. The viewer now classifies gestures in `viewer/static/keys.js` and
delivers them through `POST /button` / `emulator/runtime/keys.py`, preserving stock assignments.
`fbshim` handles the volume GPIO levels and touch/LCD sleep ioctls; setup supplies the
brightness path. Holds and screen sleep/wake now work. Viewer Power uses a guest-only
host lifecycle, not dangerous event `0x108`. See [KEYS.md](../../../emulator/docs/keys.md) before extending it.

**Logging gotcha (important for all directions):** `mq_player`'s zlog config
(`usr/data/fiio/log/zlog_player.conf`) routes only `=INFO/=NOTICE/=WARN/=ERROR/=FATAL` to stdout
and sends **nothing at DEBUG** anywhere (the `=DEBUG>stdout` line is commented; `!DEBUG` goes to
`fiio_player.log` but in practice that file shows only ERROR). Most handler traces (incl.
`key_code: %d`) are **DEBUG and silently dropped** — "no log" ≠ "not executed". To see them,
uncomment `*.* >stdout` (or `=DEBUG>stdout`) in `zlog_player.conf` and reboot; that is how the key
dispatch above was confirmed.

## Direction: local audio ✅ (see [AUDIO.md](../../../emulator/docs/audio.md))

Local CS43131 playback uses **tinyalsa** (`pcm_open`/`pcm_write`), captured by `tinyshim.c`.
The missing prerequisite was card discovery: `get_i2s3_pcm_device` (`FUN_0047670c`) expects
`x2000 - x2000` in `/proc/asound/cards`. Redirecting that read to `emulator/shims/asound.cards` lets
`set_out_device` (`FUN_00474f84`) choose **I2S3_OUT=6**, hw:0,3, through normal firmware logic.
No audio binary patches are required.

GDB confirmed `ctx = *(uint32_t*)0x832214`: `ctx+0x58` was NO_OUT_DEV=0 before discovery.
Its caps entry was empty, but the I2S3 entry at `0x82e010` was already populated. The
`0x10000000` flags and `ctx+0x5c` branches investigated earlier are **input**, not output.
See [AUDIO.md](../../../emulator/docs/audio.md) for the corrected chain, signal validation, WAV export and Web Audio.
Multi-format PCM validated (16-bit/44.1k and 24-bit/96k, faithful). USB-DAC (no USB host under qemu-user), DSD (route identified, needs a .dsf test file) and input remain out of scope — see [AUDIO.md](../../../emulator/docs/audio.md).

## Direction: network / FiiO Link + 12103 auth ✅ (mapped)

Corrected active V2.40 path: `http_server_thread` `FUN_004b9720` listens on 12103,
callback `FUN_004b9d38` uses the 16-entry table `006c7a50`, with no WebSocket route.
Bundled dashboard `FUN_004b2820` / `mg_dash_authenticate` is **not** this listener's router.
Device control is auth-free FiiO Link TCP. Native WS support is an emulator adapter,
not a stock authentication unlock. Reproduce with `research/diagnostics/inspect_http_routes.py` and
`controller/diagnostics/probe_websocket.py`; startup networking is `emulator/scripts/16_network.sh`.
See [WEBSOCKET.md](../../../controller/docs/websocket.md) and [NETWORK.md](../../../emulator/docs/network.md).

## Direction: touch / UI ✅

`mq_ui` main `FUN_004036ec`; touch device open `FUN_0055da20`; read-cb `FUN_0055db8c`; language
switch `FUN_004776e4`. Event grammar + 180° coordinate flip in [TOUCH.md](../../../emulator/docs/touch.md); the live
bridge is [VIEWER.md](../../../viewer/docs/usage.md).

## Re-analysing a new firmware version

1. Inventory the input using `firmware/tools/firmware_inventory.py`; keep a separate record and
   work volume. Do **not** overwrite V2.40's rootfs pin. See [PORTING.md](../../../firmware/docs/porting.md).
2. Import `mq_player`/`mq_ui` into a separate version-named Ghidra project and analyse
   (addresses/layouts may shift); record exact stock ELF hashes before any patch.
3. Re-locate functions by their **zlog source paths / function-name strings** (fact #2 above),
   not by the old `FUN_` addresses — grep the decompilation for e.g. `echo_sys_key_handler`,
   `echo_start_key_server`, `mg_dash_authenticate`. Recompute the string-vaddr offset (fact #1).
4. Confirm the FiiO Link command tags are unchanged (they were stable 2.09→2.40; see
   [DISKOS.md](diskos.md)) before trusting the old protocol map.
