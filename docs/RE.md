# Deep-analysis playbook

How to reverse-engineer the Snowsky Disc firmware binaries (`mq_player`, `mq_ui`) and extend
the emulator — written so a **new firmware version** can be re-analysed the same way. Tooling
setup lives in [../ghidra/README.md](../ghidra/README.md); this page is the method + the findings
per direction.

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

Environment and the one-time arm64-decompiler build are in [../ghidra/README.md](../ghidra/README.md).
Once a project has `mq_player`/`mq_ui` imported+analysed, iterate with the scripts in `ghidra/`:

- **`DecFuncs.java <addr…>`** — decompile the function containing each address.
- **`DecAt.java <addr…>`** — same, but if the address is only a *label* (auto-analysis didn't
  make it a function — common for callbacks reached only through a pointer), it disassembles and
  `createFunction`s first. Use this on the target of a function pointer.
- **`RefsTo.java <addr…>`** — list all refs (READ/WRITE/CALL) to a data/code address, with the
  containing function. This is how you follow a runtime-registered callback or find who sets a flag.

Typical trace: find a string → `RefsTo` the string addr → decompile the referencing function →
follow function pointers with `RefsTo`+`DecAt` → find the gate/flag with `RefsTo` on the global.

## Direction: physical keys ✅ (codes found; enable-gate identified)

Full chain (V2.40), all via [../ghidra/README.md](../ghidra/README.md) scripts:

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

| code | action (from log strings / calls) |
|---|---|
| `0x106` (262) | `KEY_VALUE_MENU_DOWN` — menu nav down (Vol-Down key) |
| `0x107` (263) | `KEY_VALUE_MENU_UP_L` — menu nav up (Vol-Up key) |
| `0x103` / `0x109` | play/pause toggle (`FUN_004dde48` / `FUN_004e0350`) |
| `0x10c` (268) | `KEY_VALUE_PLAY_KEY_L` (play, long) |
| `0x10d` (269) | play double-click |
| `0x108` (264) | a mode/screen toggle |
| `0xfa` (250) | silent back/exit action (`FUN_00424b2c`) — **not** power |
| `0xfb`,`0xfc`,`0x10a`,`0x10b` | configurable (branch on `DAT_0082e9d2/d3` — the sysconfig gesture map `KEY_*_CLICK_SLE`) |

**No power key here.** A full sweep of `0xFA…0x10D` logged no POWER/SHUTDOWN/LOCK action — power
is MCU-mediated (`mq_ui` gets `POWER_KEY_EVENT_REPORT`, and the diskOS RE notes power on a GPE
GPIO read via `/dev/mem`), not on `event0`'s `echo_sys_key_handler`. So a power button needs the
MCU/UART stub (`/dev/ttyS0`), which isn't emulated.

The dispatcher gates every key on `DAT_0082e9c1` (key-enable): `if (DAT_0082e9c1==0) return 0;`.
Headless it stays 0 (set only by `FUN_004e847c` = `*(char*)(cmd+0x10)` from an IPC/settings
command, and inside settings-apply `FUN_004e3658` — neither fires under emulation), so keys are
read but dropped.

**✅ Enabled by a one-instruction patch** (`scripts/patch_keys.sh`, run from `10_setup_env.sh`):
the guard loads the flag with `lbu v0,65(s2)` at `0x004de70c` (file off `0xDE70C`); patch it to
`li v0,1` (`0x24020001`) so the flag always reads 1 and the `beqz` at `0x004de720` is never taken.
`s2` (the struct base, set at `0x004de708`) stays valid for the handler's other fields. The
script matches the exact guard bytes (anchor `addiu s2,v0,-5760` = `80e95224`, then `lbu` =
`41004292` → `01000224`), is idempotent, and no-ops on a firmware whose addresses moved.

Then inject the codes into `event0` (16-byte `input_event`, `type=EV_KEY`, value 1 then 0); the
firmware does its own single/double/long-click detection by timing (~0.12 s = single). The viewer
(`tools/stream.py`, [VIEWER.md](VIEWER.md)) exposes `/key?k=menu_up|menu_down|play|play_pause|power`
and page buttons. **Confirmed live:** an injected `0x107` reaches the dispatcher and logs
`KEY_VALUE_MENU_UP_L`; `0x106` → `KEY_VALUE_MENU_DOWN`. Visible UI effect is context-dependent
(the menu carousel is touch/swipe; the physical keys act in the playback/volume context).

**Logging gotcha (important for all directions):** `mq_player`'s zlog config
(`usr/data/fiio/log/zlog_player.conf`) routes only `=INFO/=NOTICE/=WARN/=ERROR/=FATAL` to stdout
and sends **nothing at DEBUG** anywhere (the `=DEBUG>stdout` line is commented; `!DEBUG` goes to
`fiio_player.log` but in practice that file shows only ERROR). Most handler traces (incl.
`key_code: %d`) are **DEBUG and silently dropped** — "no log" ≠ "not executed". To see them,
uncomment `*.* >stdout` (or `=DEBUG>stdout`) in `zlog_player.conf` and reboot; that is how the key
dispatch above was confirmed.

## Direction: audio (WIP — see [AUDIO.md](AUDIO.md))

Firmware uses **ALSA** (`libasound.so.2`, full `snd_pcm_*`) and opens **`hw:%d,%d`** (kernel-direct,
so an `asound.conf` `file` plugin can't redirect it); the LinuxKit VM has no snd modules. Capture
route: a freestanding **libasound interposer** (`shim/asndshim.c`) that fakes the PCM handle and
appends `snd_pcm_writei` to `/audio.pcm` — **built and ready**, plus `/dev/cs43131*` stubs.

**The LOCAL DAC path is tinyalsa** (`libtinyalsa.so.1`: `pcm_open`/`pcm_write`), not libasound — so
`shim/tinyshim.c` is the local-capture interposer (`asndshim.c` handles the USB/BT libasound path).
Local playback is gated by a **DAC-route state machine** (`set_pcm_config`, `pcm_control.c
FUN_004715fc`) that branches on the output-route mode `*(DAT_00832214+0x5c/0x58)` — a value only a
real initialised DAC holds. Traced gate-by-gate: `audio_track_create` (`FUN_0044f2d4`) →
`FUN_00475348` format lookup (empty caps table; patchable) → `set_pcm_config` route-state machine
(`pcm_control.c:538`, the **blocker**) → `pcm_open`/`pcm_write` (tinyshim, not yet reached). Blind
static patching of the route masks did **not** converge; the fix is to init/instrument the route
mode, not whack branches. Full status + addresses in [AUDIO.md](AUDIO.md). Decoder is
`libavcodec.so.58`. Real-time audio is out (qemu-user can't decode in real time) — capture-then-play.

## Direction: network / FiiO Link + 12103 auth ✅ (mapped)

Function addresses and the auth conclusion are in [../ghidra/README.md](../ghidra/README.md) and
[PROTOCOL.md](PROTOCOL.md): `http_server_thread` `FUN_004b9720` (listen 12103), router
`FUN_004b2820`, `mg_dash_authenticate` `FUN_004af7e0`, token gen `FUN_004ae108`. Device control
is auth-free FiiO Link; there is no file-upload command. To exercise the servers under emulation
they must bind first — see the `40_network.sh` lead in [STATUS.md](STATUS.md).

## Direction: touch / UI ✅

`mq_ui` main `FUN_004036ec`; touch device open `FUN_0055da20`; read-cb `FUN_0055db8c`; language
switch `FUN_004776e4`. Event grammar + 180° coordinate flip in [TOUCH.md](TOUCH.md); the live
bridge is [VIEWER.md](VIEWER.md).

## Re-analysing a new firmware version

1. Re-extract the rootfs (`scripts/00_extract_rootfs.sh`) and re-pin the sha256 in `scripts/lib.sh`.
2. Re-import `mq_player`/`mq_ui` into Ghidra and analyse (addresses **will shift** between builds).
3. Re-locate functions by their **zlog source paths / function-name strings** (fact #2 above),
   not by the old `FUN_` addresses — grep the decompilation for e.g. `echo_sys_key_handler`,
   `echo_start_key_server`, `mg_dash_authenticate`. Recompute the string-vaddr offset (fact #1).
4. Confirm the FiiO Link command tags are unchanged (they were stable 2.09→2.40; see
   [DISKOS.md](DISKOS.md)) before trusting the old protocol map.
