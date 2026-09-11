# Ghidra reverse-engineering helpers

Scripts used to decompile the MIPS UI binaries (`mq_ui`, `mq_player`) from the rootfs.

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
  0-based index (`0 zh · 1 tw · 2 en · …`); see `CLAUDE.md`.

### `mq_player` network / auth (12100 + 12103)

Located by disassembling `/usr/bin/mq_player`. String xrefs on this stripped PIC-MIPS binary only
resolve **after** auto-analysis, and the router/callback are reached through pointer tables, so
static xrefs don't link them — these were read from the decompiled bodies:

- `FUN_004b9720` = `http_server_thread` — `listen` on 12103 (`0x2f47`).
- `FUN_004b2820` = the `/api/*` + `/fs` router.
- `FUN_004af7e0` = `mg_dash_authenticate` — the dashboard auth (`config+8==0` → guest level 9;
  else `(*config->fn)(user,100,pass)` → level; level>0 → token).
- `FUN_004ae108` = the 20-char random `access_token` generator (`/dev/urandom` → alnum).
- `FUN_004d9974` = `get_input_event` — opens `/dev/input/event%d` and matches names via
  `EVIOCGNAME`; under emulation this is the loop that hangs `mq_player` until `x2000_key` (event0)
  **and** the touch device (event1) both resolve. The FiiO Link / library dispatch and full
  conclusion are in [../docs/PROTOCOL.md](../docs/PROTOCOL.md).

## Tooling on this machine

Ghidra **12.1.3** is installed at `~/Library/ghidra/ghidra_12.1.3_PUBLIC` (11.4.2 also present).
The `mq_player`/`mq_ui` decompilation was done headless from a scratch project; nothing about the
project is committed (firmware-derived — see the repo `.gitignore`). To reproduce, import the two
binaries from `/work/rootfs/usr/bin/` and re-run the scripts above.
