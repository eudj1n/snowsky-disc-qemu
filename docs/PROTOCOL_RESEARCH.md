# DISC protocol research: continuation plan

Updated 2026-09-16. This is the handoff checklist for continuing the research in
another session. Keep its status current when finishing a work item; detailed
contracts and evidence remain in the linked documents.

## Scope and current checkpoint

Priority: stock SNOWSKY DISC functionality for a future locally hosted web remote
(backend + frontend, potentially Docker). Active development targets V2.57;
V2.40 is historical and its legacy profile remains temporarily pending cleanup.
Earlier two-version validation below is retained as evidence, not a continuing
requirement. See [the support policy](PORTING.md#support-policy--one-active-firmware).
Android FiiO Music/M21 is reference material only; it is a different
implementation from FiiO Control and must not define DISC semantics.

Working branch: `codex/disc-protocol-research`. Research checkpoint before channel
balance: `09951b8`. Use `git log -5 --oneline` and `git status --short` to identify the
latest checkpoint and any work left uncommitted; do not assume the earlier hash
contains the later balance helper.

### Completed

- [x] Playback, metadata, seek, modes and favorites: [remote control](REMOTE_CONTROL.md).
- [x] Stock file transfer, HTTP catalog, custom playlist CRUD and network indexing:
  [HTTP API](HTTP_API.md). Playlist CRUD does not yet establish playlist playback.
- [x] Gain, DRE, filter, SPDIF, PEQ read/write and persistence:
  [settings](REMOTE_SETTINGS.md). These checks do not measure DSP output.
- [x] Channel-balance contract: `0712` read / `0713` write / `a712` reply,
  L20..0..R20, packed direction/magnitude, opposite-channel attenuation:
  [evidence and reproduction](REMOTE_SETTINGS.md#channel-balance).
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
- [x] Run **full** disposable integration on V2.57, including channel balance.
- [x] Run **full** disposable integration on V2.40.
- [x] Review the complete diff, record validation and remaining limitations here,
  then commit the checkpoint. A local commit is authorized; pushing/publishing is
  not part of this step.

Channel-balance firmware-free checks passed: 180 Python tests, 23 JavaScript tests,
shell checks and four shim builds. Focused `settings` passed on V2.57 via TCP and WS.
These focused results alone are not full integration or release-gate results.

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
CI_SCENARIO=settings FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
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

- [x] **Channel balance:** mapped from stock UI and player handlers. Shared TCP/WS
  helper and tests cover -20, -1, 0, +1, +20, SQLite, per-channel DAC writes and
  restoration. Hardware analog effects remain a separate check.
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

- [ ] Retire the legacy V2.40 runtime/diagnostic profile, manual workflow choice
  and obsolete compatibility branches in a dedicated cleanup. Preserve `v2.40`
  and the research records; choose a final `-rN` snapshot only if later changes
  should be retained. Do not fold this cleanup into protocol research.
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
| Firmware-free | Passed: 180 Python tests, 23 JavaScript tests, shell syntax and four shim builds |
| Focused settings V2.57 | Passed; TCP/WS balance endpoints/center/±1, DAC mirrors, SQLite and settings restoration |
| Full V2.57 | Passed, exit 0; UI scan, audio, controls, TCP/WS remote and queue checks, HTTP, balance/settings, modes/themes, confinement and SD rescanning |
| Full V2.40 | Passed, exit 0; UI scan, audio, controls, TCP/WS remote and queue checks, HTTP, balance/settings, modes/themes and confinement |
| Final review / commit | Reviewed; included in the local checkpoint commit containing this document |

Both full runs passed on their first attempt in this balance checkpoint, on the
current computer. TCP and WS each checked center, ±1 and ±20, with baseline DAC
L/R (12,12), L20 (12,32), R20 (32,12), matching SQLite and unchanged master volume.
All temporary stacks/volumes were removed; the interactive stack was not changed.
The CI image was also rebuilt from the tracked Dockerfile and the firmware-free
suite passed again. Its package inventory matched the pre-existing test image
except for the previously absent `strace`; V2.40 ran in the rebuilt image.
These are local integration results, not hosted release gates; no physical analog
output claim or publication is implied.

**Resume with playback preferences** in section 1. Check the worktree and latest
commit first. Balance is complete; its physical analog effects remain unvalidated.

Detailed local logs for this checkpoint are ignored under `work/http-research/`:
`balance-unit.log`, `balance-unit-rebuilt.log`, `balance-full-v257.log` and
`balance-full-v240.log`.
The prior checkpoint ran on another computer; its local files are not required.
The summary here must remain sufficient to resume even
when those machine-local logs are unavailable. Update results, failure explanations
and the next unchecked item before handing off the session.
