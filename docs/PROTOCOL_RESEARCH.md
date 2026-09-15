# DISC protocol research: continuation plan

Updated 2026-09-16. This is the handoff checklist for continuing the research in
another session. Keep its status current when finishing a work item; detailed
contracts and evidence remain in the linked documents.

## Scope and current checkpoint

Priority: stock SNOWSKY DISC functionality for a future locally hosted web remote
(backend + frontend, potentially Docker). Supported emulator profiles are V2.57
and V2.40. Android FiiO Music/M21 is reference material only; it is a different
implementation from FiiO Control and must not define DISC semantics.

Working branch: `codex/disc-protocol-research`. Research checkpoint before the queue
work: `f210645`. Use `git log -5 --oneline` and `git status --short` to identify the
latest checkpoint and any work left uncommitted; do not assume the earlier hash
contains the later queue helpers.

### Completed

- [x] Playback, metadata, seek, modes and favorites: [remote control](REMOTE_CONTROL.md).
- [x] Stock file transfer, HTTP catalog, custom playlist CRUD and network indexing:
  [HTTP API](HTTP_API.md). Playlist CRUD does not yet establish playlist playback.
- [x] Gain, DRE, filter, SPDIF, PEQ read/write and persistence:
  [settings](REMOTE_SETTINGS.md). These checks do not measure DSP output.
- [x] Work-mode and Bluetooth source-codec preference controls, stock/custom theme
  APIs: [modes and themes](REMOTE_MODES_THEMES.md).
- [x] Sanitized FiiO Control iOS capture fixtures, app-version evidence, and
  [Android comparison](M21_COMPARISON.md): [app evidence](FIIO_CONTROL_APP.md).
- [x] Current-queue type-0 selection needs no localized label. TCP/WS helpers
  check fresh bounds; empty/replaced queues and invalid-index recovery tested.
- [x] `0105` reads all five play modes via **`a102`**, not `a105`.
- [x] `0426` has a NULL handler on both DISC profiles. Both empty and `0000`
  requests time out without breaking subsequent reads. Use TCP `0406`, HTTP
  `curlist/song` and `0202` instead. No additional phone capture is needed for
  these two commands.

## Checkpoint completion

- [x] Run the firmware-free suite on the final changes.
- [x] Run **full** disposable integration on V2.57, including the new queue checks.
- [x] Run **full** disposable integration on V2.40.
- [x] Review the complete diff, record validation and remaining limitations here,
  then commit the checkpoint. A local commit is authorized; pushing/publishing is
  not part of this step.

Before this full-regression step, 177 Python tests, 23 JavaScript tests, shell
checks and four shim builds passed. Focused `queue` and `queue-reads` scenarios
passed on both profiles via TCP and WS. These focused results alone are not full
integration or release-gate results.

### Reproduction

Read `AGENTS.md`, [EMULATION.md](EMULATION.md) and [CI.md](CI.md) first. Resolve
`OTA_257` and `OTA_240` below to existing extracted `main_os/ota_v257` and
`main_os/ota_v240` directories on the current machine. Do not download or execute
an unreviewed firmware profile as a substitute.

```sh
docker build -t diskos-qemu-ci docker
docker run --rm --network none -v "$PWD:/repo:ro" diskos-qemu-ci bash /repo/ci/test.sh
CI_SCENARIO=full FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=full FW_VERSION=2.40 bash ci/integration.sh "$OTA_240"
# Focused diagnostics, not substitutes for the full runs above:
CI_SCENARIO=queue FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=queue-reads FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
```

Run firmware integration sequentially to limit resource pressure. Each run uses
generated media, a randomly named Compose stack and disposable volume, and cleans
them up. Leave interactive `diskos-qemu` and `diskos-preview` untouched. Do not
reset all binfmt registrations. Raw captures, firmware, decompilation, generated
screenshots and detailed logs stay ignored; only code/docs/curated fixtures belong
in the commit. `CI_SHOTS` can retain diagnostic screenshots locally.

Known test details: selection and subsequent pause must respect the stock
2.1-second navigation interval. One earlier full-style UI scan preparation failed
before reaching protocol reads; retain screenshots and diagnose the failing stage
instead of declaring the protocol broken. `queue-reads` deliberately prepares its
index using stock TCP scanning; `full` and `queue` still test UI scanning.

## Next research, in priority order

For each item: identify the actual handler and payload first, exercise it on
disposable firmware through TCP/WS where applicable, verify observable readback,
restore state, add useful regression coverage and update the contract. A string
or table entry alone is not a supported capability. Record unsupported commands
explicitly instead of retrying them indefinitely.

### 1. Settings useful to the remote

- [ ] **Channel balance:** identify getter/setter, sign/range/units, verify left,
  center and right values and restoration. Request a short app capture if static
  analysis cannot establish the mapping.
- [ ] **Playback preferences:** investigate gapless (`0647`), ReplayGain (`0718`),
  folder jump (`0687`), artist grouping (`0648`), CD/track display (`064d`) and list
  interaction (`064e`). These are leads, not validated remote setters.
- [ ] **Physical-button assignments:** `0820`, `0821`, `0822` remote control of
  single/double/hold assignments; verify against the already tested physical
  controls and restore original assignments.
- [ ] Cover/lyrics preferences (`064b`, `064c`): establish local read/write
  semantics separately from any online retrieval.

### 2. Library and playback edge cases

- [ ] **Custom playlist playback:** establish supported selection route and
  identity after create/rename/add/remove; CRUD alone is already covered.
- [ ] **Cancel indexing:** determine nonzero `0622` behavior, progress/events and
  the resulting partial index. Do not reinterpret this as library reset.
- [ ] **Dedicated library reset:** identify the actual app command and scope.
  Test reset only against disposable state. `0800` is a broader factory reset
  and is not a substitute. Merely opening/cancelling confirmation reveals no
  reset payload.
- [ ] **Natural end of track/list:** verify all five modes, automatic transitions,
  final state, repeat-one/list, single-once and random behavior with short generated
  tracks. Explicit next/previous tests do not establish end-of-track behavior.
- [ ] Secondary compatibility: CUE/SACD/DSD metadata and track identity, and a usable
  V2.40 favorites selection path (generic favorite-position playback is currently
  guarded because V2.40 expects an internal ID absent from the page).

### 3. Exact app behavior and discovery

- [ ] **Custom-theme metadata save in FiiO Control:** capture upload, then a change
  of only color/overlay settings. Preserve and restore the original custom slot.
  Our verified full-image API already works; empty-body custom POST clears the
  image path. See the [capture checklist](REMOTE_MODES_THEMES.md#fiio-control-capture-checklist).
- [ ] **LAN discovery and official-app compatibility:** establish discovery
  packets/advertisements, then connect FiiO Control to the emulator. Existing
  localhost WS bridge is our adapter, not a native stock DISC WebSocket endpoint.

The user can capture TCP 12100 and HTTP 12103 from FiiO Control/Surge on iPhone.
Ask for a specific short action sequence only when it resolves a concrete unknown;
avoid repeating already established mode/codec captures. Existing capture evidence
is indexed in [FIIO_CONTROL_APP.md](FIIO_CONTROL_APP.md).

## Separate subsequent work

- [ ] Hardware validation: real USB DAC/AirPlay/Bluetooth audio, negotiated codec,
  actual PEQ/filter/balance effects, DSD and physical theme rendering. Emulator
  readback/persistence cannot establish those results.
- [ ] Build the local backend/frontend and Docker packaging. Use one owner of the
  stock single-client TCP connection, centralized event routing, partial-state
  merging, reconnection without replaying mutations, pending paused-seek state,
  refreshed queue identities and firmware-specific capabilities.

## Validation log for this checkpoint

| Check | Result |
| --- | --- |
| Firmware-free | Passed: 177 Python tests, 23 JavaScript tests, shell syntax and four shim builds |
| Full V2.57 | Passed, exit 0; UI scan, audio, controls, TCP/WS remote and queue checks, HTTP, settings, modes/themes, confinement and SD rescanning |
| Full V2.40 | Passed, exit 0; UI scan, audio, controls, TCP/WS remote and queue checks, HTTP, settings, modes/themes and confinement |
| Final review / commit | Reviewed; included in the local checkpoint commit containing this document |

Both full runs passed on their first attempt at this checkpoint. The queue-test
cleanup now waits 2.1 seconds before pausing after selection, matching the known
stock rate gate; both full runs exercised that final test code. Temporary stacks
and volumes were removed. These are local integration results, not hosted release
gates; no hardware-audio claim or publication is implied.

**Resume with channel balance**, then the remaining playback preferences in
section 1. Check the worktree and latest commit first. No checkpoint validation
item remains open; later research items above are deliberately unchecked.

Detailed local logs for this checkpoint are ignored under `work/http-research/`:
`checkpoint-final-unit.log`, `checkpoint-full-v257.log` and
`checkpoint-full-v240.log`. The summary here must remain sufficient to resume even
when those machine-local logs are unavailable. Update results, failure explanations
and the next unchecked item before handing off the session.
