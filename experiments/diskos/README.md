# diskOS preview — historical, unsupported

Preserved source for the V2.40 warm UI handoff experiment. See
[the report and reproduction instructions](docs/preview.md) for
historical results, known bugs, source provenance and conditions for returning
to active experimental status.

- `source-revision`: exact reviewed diskOS commit; no tracking of upstream HEAD.
- `build.sh` / `prepare.py`: archive that commit from a local checkout, adapt only
  the build copy and compile its UI with `emu_io.c`.
- `boot.sh`: boot the stock backend, then hand off to the diskOS UI. Requires the
  isolated preview flag and V2.40; never changes stock binary fingerprints.
- `compose.yaml`: opt-in preview container/volume and localhost viewer on 8081.

Generated binaries, the adapted GPL upstream source and a copy of the MIT
adapter/license stay in ignored `work/diskos-preview/`. The normal emulator and
viewer do not launch this experiment. No firmware, installer or flash image is
included. The current layout migration has not revalidated firmware execution.
