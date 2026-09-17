# Porting another firmware version

This is the reusable process, not a list of addresses to copy. Version-specific
observations belong in [firmware reports](firmware/2.40.md); detailed RE techniques
remain in [RE.md](RE.md) and [research/ghidra/README.md](../research/ghidra/README.md).

## Keep four different records

| Record | Purpose |
|---|---|
| `CHANGELOG.md` | Changes actually made to the emulator, grouped by its release/tag. |
| `firmware/inventory/v<version>.json` | Reproducible input facts: versions, ZIP/rootfs hashes, sizes, chunk count. Not an enablement profile or a compatibility claim. |
| `docs/firmware/<version>.md` | Upstream notes, tested/not-tested matrix, findings, failures, evidence and remaining work for that firmware. |
| Shared emulator/controller/research code + this guide | Repeatable methods and regression tests useful for later versions/products. |

Keep development on `2.x`, using short-lived task branches where useful. Do not fork
the entire emulator for every minor firmware. Firmware-based immutable tags preserve
validated snapshots; `v2.40-r1` means an emulator revision against the same firmware.
Add a Current changelog entry with each meaningful change, then move it into the
release entry when the exact commit passes the release gates. Vendor announcements
must never become "working" emulator features just by copying their changelog.

## Support policy — one active firmware

Adopted 2026-09-16, replacing the three-version FIFO policy. Actively support
**one firmware version for this product/hardware revision**: the latest version
validated in the emulator. Development follows FiiO releases on `2.x`; historical
versions are frozen snapshots, not maintenance branches. No backports or ongoing
integration coverage are promised for them.

An OTA announcement creates a research candidate, not a supported version.
Investigate the candidate in a task branch and a separate work volume. Keep the
existing active version until the candidate passes compatibility checks; never
replace a working version merely because a higher version number appeared.

At each transition:

1. Preserve the previous firmware's final validated snapshot as a source tag/release
   before removing its support code. An existing release can serve as that snapshot;
   if later changes should be included, publish the next unused `-rN` revision after
   exact-commit validation. Never move an existing tag.
2. Validate the candidate, document evidence/limitations and switch the active
   profile/default in the support PR. Release gates are firmware-free checks plus
   full integration for the firmware being released, on the exact release commit.
3. Retire old runtime profiles, version-specific patch/diagnostic branches and
   downloader/workflow choices together. Preserve shared tools and useful generic
   tests; do not maintain old-version compatibility solely for a historical release.
4. Preserve inventory records and version-specific research as historical evidence,
   with a link to the last validated release. Never delete users' firmware or work
   volumes as part of retirement. Old snapshots still require separately obtained
   firmware; upstream download availability is not guaranteed.
5. Record the transition in STATUS, the firmware report and CHANGELOG, then close
   the OTA tracking issue manually after transition/release preparation is complete.

Releases need not wait for the next FiiO update: useful emulator improvements may
ship against the current firmware. The next vendor release is a handoff point,
not the only opportunity to publish. Historical releases normally remain intact;
deleting any published release/tag requires explicit owner approval.

**Current transition:** V2.57 is active. V2.40's historical `v2.40` release remains;
its runtime/diagnostic profile is still present until a separate cleanup task
removes it. Hosted integration runs only V2.57. This change does not remove those files
or rewrite past validation results. V2.40 is no longer an ongoing release gate.

The OTA monitor does not promote or retire firmware automatically. See
[OTA.md](OTA.md) for issue tracking and [CI.md](CI.md) for release gates.

## 1. Intake and provenance — no execution

Record the original archive name, public vendor release page (when confirmed), main
and recovery versions, ZIP digest, encrypted rootfs integrity and plaintext rootfs
digest. Keep the direct URL in a per-version secret; no ZIP/rootfs in Git or CI artifacts.

`firmware/tools/firmware_inventory.py` supports differing version numbers and chunk counts:

```sh
docker build -t snowsky-disc-qemu-ci docker
FW_PACKAGE_DIR=/absolute/path/to/SNOWSKY_DISC_update_20260909_v257
FW_ARCHIVE=/absolute/path/to/SNOWSKY_DISC_update_20260909_v257.zip
docker run --rm --network none \
  -v "$PWD:/repo:ro" -v "$FW_PACKAGE_DIR:/package:ro" -v "$FW_ARCHIVE:/package.zip:ro" \
  snowsky-disc-qemu-ci python3 -B -m firmware.tools.firmware_inventory /package \
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

**Implemented boundary:** `firmware/v<version>.json` holds runtime profiles for V2.40
and V2.57, separate from inventory JSON. `firmware/profile.py` checks product,
main/recovery metadata and six binary hashes before setup/boot. Key patch validation
normalizes only the permitted instruction, then checks the full stock hash, original
bytes and executable PT_LOAD address mapping. Unknown builds fail closed.
Key/network/HTTP-route diagnostics use separately verified addresses for both builds,
selected by full binary fingerprint; unknown builds fail closed. See
[DIAGNOSTICS.md](DIAGNOSTICS.md). Legacy GDB breakpoint files remain V2.40-specific.

Static extraction without execution, into a **new** research volume (not `snowsky-disc-work`):

```sh
docker run --rm --network none -v "$PWD:/repo:ro" \
  -v "$FW_PACKAGE_DIR:/package:ro" -v snowsky-static-v257:/study \
  snowsky-disc-qemu-ci python3 -B -m firmware.tools.firmware_static /package \
  /repo/firmware/inventory/v2.57.json /study/rootfs
```

This checks encrypted manifests and the committed plaintext digest before native
`unsquashfs`; it refuses an existing destination and never runs guest code. The volume
contains proprietary firmware, stays local, and must not be uploaded. Runtime extraction
also refuses an existing rootfs and checks contiguous chunks and pinned plaintext size/hash.

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
6. Targeted cases for upstream changes that affect emulator interfaces, shims or patches,
   plus repeated boot/clean-volume runs and hosted CI.

The release scope is emulator compatibility, not full vendor-software acceptance.
Keep the vendor changelog as reference; testing every upstream feature is not a gate.
Require extra cases for emulator-dependent behavior and reproduced regressions.

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

Static comparison, guarded profiles and the first clean baseline are complete; see
[2.57 report](firmware/2.57.md). Select `FW_VERSION=2.57` for a disposable integration
run; V2.57 is the default and V2.40 remains available explicitly for local historical
work until cleanup. Hosted firmware dispatch uses only the active profile/secret.
Release gates validate emulator compatibility on the exact candidate
commit; they do not certify every vendor feature or physical-device behavior.
