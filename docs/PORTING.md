# Porting another firmware version

This is the reusable process, not a list of addresses to copy. Version-specific
observations belong in [firmware reports](firmware/2.40.md); detailed RE techniques
remain in [RE.md](RE.md) and [ghidra/README.md](../ghidra/README.md).

## Keep four different records

| Record | Purpose |
|---|---|
| `CHANGELOG.md` | Changes actually made to the emulator, grouped by its release/tag. |
| `firmware/inventory/v<version>.json` | Reproducible input facts: versions, ZIP/rootfs hashes, sizes, chunk count. Not an enablement profile or a compatibility claim. |
| `docs/firmware/<version>.md` | Upstream notes, tested/not-tested matrix, findings, failures, evidence and remaining work for that firmware. |
| Shared scripts/tools + this guide | Repeatable methods and regression tests useful for later versions/products. |

Keep development on `2.x`, using short-lived task branches where useful. Do not fork
the entire emulator for every minor firmware. Immutable `v2.40`, `v2.57`, etc. preserve
validated snapshots; `v2.40-r1` means an emulator revision against the same firmware.
Add an Unreleased changelog entry with each meaningful change, then move it into the
release entry when the exact commit passes the release gates. Vendor announcements
must never become "working" emulator features just by copying their changelog.

## 1. Intake and provenance — no execution

Record the original archive name, public vendor release page (when confirmed), main
and recovery versions, ZIP digest, encrypted rootfs integrity and plaintext rootfs
digest. Keep the direct URL in a per-version secret; no ZIP/rootfs in Git or CI artifacts.

`tools/firmware_inventory.py` supports differing version numbers and chunk counts:

```sh
docker build -t diskos-qemu-ci docker
FW_PACKAGE_DIR=/absolute/path/to/SNOWSKY_DISC_update_20260909_v257
FW_ARCHIVE=/absolute/path/to/SNOWSKY_DISC_update_20260909_v257.zip
docker run --rm --network none \
  -v "$PWD:/repo:ro" -v "$FW_PACKAGE_DIR:/package:ro" -v "$FW_ARCHIVE:/package.zip:ro" \
  diskos-qemu-ci python3 -B /repo/tools/firmware_inventory.py /package \
  --archive /package.zip --decrypt-rootfs
```

The tool reads `ota_config.in`, requires a contiguous rootfs sequence, checks encrypted
rootfs chunks against `manifest.sha256`, and verifies those same chunks/config in the
ZIP. It streams OpenSSL output into SHA-256 without writing decrypted files. Kernel/
recovery contents are not checked against the unpacked directory. Signature validation
is **not implemented**: integrity/identity is not proof of vendor authenticity.
`firmware_executed: false` describes this inventory operation, not a version's global status.

Commit the small, reviewed JSON report, never the inputs. Re-inventory a repackaged
archive instead of silently changing a release's recorded hashes.

## 2. Static compatibility, before patches or boot

Use a new, explicitly named work volume; never re-extract over the interactive `/work`.
Use a separate version-named Ghidra project/import, keeping the V2.40 analysis intact.

- Inspect `etc/product_version/version.in`, `etc/os-release`, init scripts and preload paths.
- Hash stock `mq_player`, `mq_ui`, loader and relevant libraries; record ELF machine,
  endianness, ABI/nan2008 flags, load segments and dynamic symbol bindings.
- Locate handlers by source/function-name strings and their xrefs, not old addresses.
  Translate file offsets through ELF load segments; do not assume `+0x400000` universally.
- Confirm the power/reboot confinement and helper wrappers before exercising any power
  operation. qemu-user shares the Docker host kernel; this is not a sandbox for arbitrary firmware.
- Recheck key dispatch, route discovery, framebuffer/input behavior and network listeners.
  ECHO/`fiio_music_mvc` naming can suggest shared ancestry, not device compatibility.

For future runtime profiles, key every patch/probe address by product, firmware version
and **exact stock ELF SHA-256**. Require expected original bytes at the verified offset,
unique anchors where used, and an explicit already-patched state. Unknown builds must
fail closed for operations requiring that patch/probe, not silently reuse another version.
Separate these opt-in runtime profiles from the read-only inventory records.

**Current boundary:** `scripts/lib.sh`, `scripts/patch_keys.sh`, several memory/route
probes, `tools/fetch_firmware.py` and the firmware workflow still target V2.40. An
inventory JSON does not activate V2.57. The current key patch searches a short V2.40
anchor and skips on mismatch; that is not sufficient proof that a new build is supported.
Do not run setup/probes on a new image until the relevant profile work is reviewed.

## 3. Bring-up and regression matrix

Keep fixes in Dockerfile/Compose/scripts/shims, not just a live container. Existing
`ci/integration.sh` demonstrates separate work/SD/container names, generated media,
no published test ports, and guest/loop/volume cleanup. Preserve both versions' state.

Test in this order and record the exact emulator commit and firmware/ELF hashes:

1. Clean config initialization, boot to English UI and confined guest shutdown.
2. Touch/swipes, real button gestures, app assignments, sleep/wake and framebuffer selection.
3. Fresh SD Browse files **and** stock Update now; never seed catalog rows to make a test pass.
4. Generated audio fixtures, format/rate/channel readback and byte-exact PCM where applicable.
5. TCP/HTTP/WebSocket routing, request/reply framing, asynchronous events, controls and reconnect.
6. Upstream change-specific cases, plus repeated boot/clean-volume runs and hosted CI.

Do not infer a scan from a spinner, playback from a log label, a query reply from its
tag alone, or loader interception from the presence of a `.so`. Check the downstream
state/data: catalog records, complete playback snapshots, PCM and actual symbol binding.
For a blocked state machine, instrument runtime values before proposing binary patches.
Never replay a non-idempotent command to compensate for a missing readback.

## 4. Evidence and release

Use explicit labels: **observed** (runtime/data), **inferred** (static analysis),
**upstream-reported**, **not tested**, **unsupported**. A shared code path alone is
not hardware validation; BT/USB/MCU claims need their own evidence.

For every useful finding record: version/ELF hash, hypothesis, command/tool, result,
interpretation and resulting regression test/fix. Keep raw logs/Ghidra projects and
throwaway PNGs ignored; curate relevant screenshots in `docs/images/`, with a version
and scenario in the filename. Do not preserve pages of speculative patches as a recipe.

Promote only after the exact release commit passes firmware-free and relevant firmware
integration checks, all required cases have evidence, and limitations are explicit.
Update the per-version report, STATUS and project changelog; publish only source/notes.
Dependabot PRs retain SHA pins but still need review/tests. Do not move an old release tag.

## V2.57 starting point

Intake is complete; see [2.57 report](firmware/2.57.md). Next: isolated extraction and
stock ELF inventory, then version-aware guarded patch/probe selection. Do not change
the V2.40 rootfs pin or point the existing V2.40 workflow at `FIRMWARE_V257_URL`.
