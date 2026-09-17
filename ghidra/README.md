# Ghidra reverse-engineering helpers

Scripts used to decompile the MIPS UI binaries (`mq_ui`, `mq_player`) from the rootfs.

See [../docs/RE.md](../docs/RE.md) for the deep-analysis playbook (method + findings per
direction: keys, audio, network, touch) and how to re-analyse a new firmware version.

## Reusing the built decompiler + project

Ghidra 12 ships **no prebuilt macOS-arm64 decompiler**, so it was built once (below) and the
project (`mqproj`, with `mq_player` imported+analysed) was created. To reuse them headlessly:

```sh
GH=<ghidra_12.1.3_with_built_decompiler>/support/analyzeHeadless
"$GH" <proj_dir> mqproj -process mq_player -noanalysis \
  -scriptPath <dir-with-only-the-script> -postScript DecFuncs.java 0x004de6fc
```

- Java 21+ works (ran fine on OpenJDK 26 with the usual `sun.misc.Unsafe` warnings).
- Script output is on stdout, prefixed `INFO  <script>>`; slice from the `////////` banner.
- `-noanalysis` reuses the stored analysis; drop it (or omit `-process`) the first time.

## V2.57 SD/auto-scan analysis

The V2.57 SD/auto-scan investigation was reproduced on the Homebrew Ghidra 12.1.3
installation with Java 21; its supplied decompiler worked without a local build.
The manual-build instructions below describe the earlier installation. For this
Homebrew layout, the headless entry point is
`/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless`; `ghidraRun` is the GUI
launcher. Keep project files and binary copies under ignored `work/`.

After importing/analyzing `mq_ui`, the relevant existing helpers are:

```sh
"$GH" <proj_dir> <proj_name> -process mq_ui -noanalysis \
  -scriptPath ghidra -postScript DecAt.java 481d10 481a78 47a994 47cea0 \
  -postScript RefsTo.java 008e1735 008def90 00461c7c
"$GH" <proj_dir> <proj_name> -process mq_player -noanalysis \
  -scriptPath ghidra -postScript DecAt.java 4e5af4 4f3c54 4c34ec
```

The resulting conditions and live acceptance are summarized in
[MEDIA_LIBRARY.md](../docs/MEDIA_LIBRARY.md). Use actual function entries with
`DecAt`; creating a function at a mid-function label can give misleading decompilation.

## The two facts that make xrefs easy

- **`mq_player`/`mq_ui` are fixed-address `EXEC` (not PIE)** — data refs are absolute
  `lui/addiu` or pointer words, no `$gp`. A `.rodata` string at file offset `F` has vaddr
  `F + (rodata_vma − rodata_off)` (V2.40: `+0x400000`).
- **Stripped, but self-symboling via zlog:** most functions call
  `FUN_004f550c(cat,"<src/path.c>",ver,"<func_name>",lvl,line,…,fmt,…)`, so the decompilation
  reveals each function's real source file, name and line. Map `FUN_` → purpose by these strings.

## Scripts here

- `DecFuncs.java <addr…>` — decompile the function containing each address.
- `DecAt.java <addr…>` — like DecFuncs, but disassembles + `createFunction`s first when the
  address is only a label (a callback reached via a function pointer). Use on pointer targets.
- `RefsTo.java <addr…>` — list READ/WRITE/CALL refs to an address with the containing function
  (follow runtime-registered callbacks; find who sets a flag).
- `FindText.java <regex…>` — search defined strings using case-insensitive Java
  regular expressions and list referencing function addresses. Read-only; it does
  not discover undefined strings or text in external JSON resources. For example,
  use `-readOnly -postScript FindText.java 'FAST_LL|SLOW_PC'` on V2.57 `mq_ui`,
  then `DecAt.java` at the reported function entries. UI translations also live
  in `/usr/project/config/ui/set_menu/others.json`; see
  [Gain/filter evidence](../docs/REMOTE_SETTINGS.md#gain-and-filter-labels-v257).
- `TouchDump.java` — the original touch-string finder (below).

## Setup notes (Ghidra 12.x)

- Ghidra 12 ships no prebuilt macOS-arm64 decompiler; build it once from
  `Ghidra/Features/Decompiler/src/decompile/cpp` with
  `make ghidra_opt ARCH_TYPE="-arch arm64"` and copy `ghidra_opt` to
  `os/mac_arm_64/decompile` (needs `pkg-config` + `capstone` from Homebrew).
- Ghidra 12 dropped Jython — scripts must be **Java** `GhidraScript`s (these are).
- Run the script from a directory containing **only** the `.java` you want; Ghidra
  compiles the whole scriptPath as one OSGi bundle, so an unrelated broken `.java`
  in the folder makes yours fail to load.
- For PIC MIPS, string cross-references only resolve **after** auto-analysis has run
  (the constant-reference analyzer builds the `%hi/%lo` refs). Import+analyze first,
  then `-process … -noanalysis` for repeat runs.

## Import

```sh
GH=<ghidra>/support/analyzeHeadless
"$GH" <proj_dir> <proj_name> -import /work/rootfs/usr/bin/mq_ui -overwrite
```

## `TouchDump.java`

Finds the input/touch strings (`/dev/input/event%d`, `cst816t`, `SCREEN_ROT`, …), lists
their code cross-references, and decompiles the referencing functions. This is how the
touch read-callback (`FUN_0055db8c`) and the device-open function (`FUN_0055da20`) were
located.

```sh
"$GH" <proj_dir> <proj_name> -process mq_ui -noanalysis \
  -scriptPath <dir-with-only-this-script> -postScript TouchDump.java
```

## `DecFuncs.java`

Decompile arbitrary functions by address (pass addresses as script args):

```sh
"$GH" <proj_dir> <proj_name> -process mq_ui -noanalysis \
  -scriptPath <dir> -postScript DecFuncs.java 0x0055da20 0x0055db8c
```

## Key findings

- `mq_ui` main is `FUN_004036ec` (logs `process/ui/mq_ui.c`): sets up the 360×360 display,
  finds the `cst816t` event device, registers `FUN_0055db8c` as the LVGL indev read-cb, and
  runs the UI refresh loop.
- `FUN_0055da20` opens `/dev/input/event%d` (`O_RDWR|O_NONBLOCK`).
- `FUN_0055db8c` is the touch read-cb — event grammar + coordinate scaling documented in
  [../docs/TOUCH.md](../docs/TOUCH.md).
- Language switch (first-boot wizard) is in `mq_ui` `FUN_004776e4` — the `LANGUAGE` column is a
  0-based index (`0 zh · 1 tw · 2 en · …`); see `AGENTS.md`.

### `mq_player` network / auth (12100 + 12103)

Located by disassembling `/usr/bin/mq_player`. String xrefs on this stripped PIC-MIPS binary only
resolve **after** auto-analysis, and the router/callback are reached through pointer tables, so
static xrefs don't link them — these were read from the decompiled bodies:

- `FUN_004b9720` = `http_server_thread` — `listen` on 12103 (`0x2f47`).
- `FUN_004b9d38` = **active** HTTP callback; table `006c7a50` has 16 routes and no
  WebSocket. Unknown URLs call `0048f8f8` (empty 200).
- `FUN_004b2820` = bundled dashboard `/api/*` + `/fs` code, **not delegated to by
  the active 12103 listener**. Its presence misled earlier auth/WebSocket conclusions.
- `FUN_004af7e0` = `mg_dash_authenticate` — the dashboard auth (`config+8==0` → guest level 9;
  else `(*config->fn)(user,100,pass)` → level; level>0 → token).
- `FUN_004ae108` = the 20-char random `access_token` generator (`/dev/urandom` → alnum).
- `FUN_004d9974` = `get_input_event` — opens `/dev/input/event%d` and matches names via
  `EVIOCGNAME`; under emulation this is the loop that hangs `mq_player` until `x2000_key` (event0)
  **and** the touch device (event1) both resolve. The FiiO Link / library dispatch and full
  conclusion are in [../docs/PROTOCOL.md](../docs/PROTOCOL.md).

### Physical-key handler (event0) — `echo_sys_control.c`

Traced with `RefsTo`/`DecAt` (full write-up + code table in [../docs/RE.md](../docs/RE.md)):

- `FUN_004d9974` `echo_start_key_server` — opens `/dev/input/event%d`, spawns the reader.
- `FUN_004d9840` `echo_loop_key` — reads 16-byte `input_event`; on `type==EV_KEY` calls
  `(*DAT_0088cc50)(code,value)`.
- `FUN_004de6fc` `echo_sys_key_handler` — the dispatcher; registered by `FUN_004e3410`.
  **Key codes are the custom range `0xFA…0x10D`** (not evdev standard): `0xfa`=media
  play/pause, `0xfb/0xfc`=single volume +/−, `0x10a/0x10b`=double volume +/−,
  `0x107/0x106`=held volume +/− (GPIO-gated), `0x103/0x109`=screen sleep/wake,
  `0x108`=standby/shutdown. `0x10c/0x10d` only log. Volume gestures honor app assignments;
  see [../docs/KEYS.md](../docs/KEYS.md) for corrected semantics and runtime evidence.
  Gated by `DAT_0082e9c1`
  (key-enable, 0 under emulation) — the guard `lbu v0,65(s2)` at `0x004de70c` is patched to
  `li v0,1` by `scripts/patch_keys.sh` so keys dispatch (see [../docs/RE.md](../docs/RE.md)).

## Tooling on this machine

Ghidra **12.1.3** is installed at `~/Library/ghidra/ghidra_12.1.3_PUBLIC` (11.4.2 also present).
The arm64 decompiler build + the imported `mqproj` project live in a session scratchpad (not
committed — firmware-derived, see the repo `.gitignore`). To reproduce on a fresh machine, build
the decompiler once (below), import the two binaries from `/work/rootfs/usr/bin/`, analyse, and
run the scripts above.
