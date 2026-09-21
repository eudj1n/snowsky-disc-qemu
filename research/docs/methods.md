# Firmware analysis methods

Use this workflow to investigate a specific fingerprinted stock build. Start with
[firmware porting](../../firmware/docs/porting.md),
[read-only diagnostics](diagnostics.md) and the [current research scope](status.md).
Legacy addresses and earlier interpretations are preserved in the
[V2.40 analysis notes](reports/2026-09-21-v240-analysis-notes.md), including findings
later corrected. They are not a runtime profile for a new build.

## Establish identity before interpreting behavior

1. Inventory the firmware input and full stock ELF hashes; use a separate work
   volume and version-named Ghidra project. Preserve earlier inventories and pins.
2. Check ELF mappings for that build. Convert file offsets using the containing
   segment/section mapping; never assume the historical `0x400000` offset.
3. Locate functions through zlog source paths and function-name strings, then
   follow references and callbacks. Similar names or addresses do not prove equal
   wire semantics or supported capabilities.
4. Distinguish a static handler, TCP admission, observable emulator behavior and
   physical-device evidence. Record failures and unsupported boundaries explicitly.

## Workflow (headless Ghidra)

Environment and the one-time arm64-decompiler build are in [Ghidra setup](../ghidra/README.md).
Once a project has `mq_player`/`mq_ui` imported+analysed, iterate with the scripts in `research/ghidra/`:

- **`DecFuncs.java <addr…>`** — decompile the function containing each address.
- **`DecAt.java <addr…>`** — same, but if the address is only a *label* (auto-analysis didn't
  make it a function — common for callbacks reached only through a pointer), it disassembles and
  `createFunction`s first. Use this on the target of a function pointer.
- **`RefsTo.java <addr…>`** — list all refs (READ/WRITE/CALL) to a data/code address, with the
  containing function. This is how you follow a runtime-registered callback or find who sets a flag.

Typical trace: find a string → `RefsTo` the string addr → decompile the referencing function →
follow function pointers with `RefsTo`+`DecAt` → find the gate/flag with `RefsTo` on the global.

## Runtime evidence and publication

Inspect live state before changing a hardware state machine. Select reviewed
GDB/memory addresses by full binary fingerprint through the diagnostics helpers.
The legacy `research/ghidra/probe_out_device.gdb` is V2.40-specific; do not use it
as a generic probe for the active V2.57 build.

Use disposable emulator resources and generated media for mutable tests. Physical
captures require a deliberately resumed scope; the [PEQ pause](status.md#peq-remains-paused)
continues to apply. Never replay an uncertain mutation to obtain a cleaner result.

Publish current wire facts in the [protocol reference](../../docs/protocol/README.md),
version findings in [firmware reports](../../firmware/docs/README.md), and dated
investigation evidence in `reports/`. Runtime profiles and Controller capability
registries are separate reviewed decisions; a report alone enables neither.
