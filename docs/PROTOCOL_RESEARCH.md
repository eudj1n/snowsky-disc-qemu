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

Working branch: `codex/disc-protocol-research`. Channel balance was committed in
`d823d67`; `08e6098` merges the updated single-active-firmware GitHub/CI policy.
Use `git log -5 --oneline` and `git status --short` to identify the latest
checkpoint and any work left uncommitted. Do not publish this branch implicitly.

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

## Current checkpoint completion: playback preferences

- [x] Trace local callbacks AND the separate network receive gate.
- [x] Add three read-only helpers and reject unsupported writes before I/O.
- [x] Run firmware-free checks: 193 Python tests, 23 JavaScript tests, shell
  checks and four shim builds.
- [x] Run focused `preferences` acceptance on V2.57 via TCP and WS.
- [x] Run **full** disposable integration on active V2.57 (retry passed; first
  failure and focused reproduction recorded below).
- [x] Review the complete diff, record validation and commit the checkpoint.
  Local commits are authorized; pushing/publishing is not part of this step.

Earlier balance-checkpoint validation is retained below as historical evidence,
not a new V2.40 integration requirement.

### Reproduction

Read `AGENTS.md`, [EMULATION.md](EMULATION.md) and [CI.md](CI.md) first. Resolve
`OTA_257` below to an existing extracted `main_os/ota_v257` directory on the
current machine. Do not download or execute
an unreviewed firmware profile as a substitute.

```sh
docker build -t diskos-qemu-ci docker
docker run --rm --network none -v "$PWD:/repo:ro" diskos-qemu-ci bash /repo/ci/test.sh
CI_SCENARIO=full FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
# Focused diagnostics, not substitutes for the full run above:
CI_SCENARIO=queue FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=queue-reads FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=settings FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=preferences FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
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
- [x] **Playback preferences:** gapless/folder jump/ReplayGain have read-only
  `0501` fields. Their local setter tags `0647/0687/0718`, plus artist grouping
  `0648`, CD display `064d` and list mode `064e`, are absent from the V2.57 TCP
  allowlist and rejected over TCP/WS. No public setters; other three reads remain
  unsupported. See [contract and static addresses](REMOTE_SETTINGS.md#playback-preferences-v257).
- [x] **Admission of physical-button and cover/lyrics tags:** `0820/0821/0822`
  and `064b/064c` are also absent from the V2.57 TCP allowlist (static evidence
  only, not five additional runtime tests). Do not implement these as remote
  setters. Local physical assignment behavior is already covered separately.
  Reopen alternate-route research only with concrete app/handler evidence.

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
- [ ] Secondary compatibility: CUE/SACD/DSD metadata and track identity on the
  active firmware. Historical V2.40 favorite-position playback remains guarded;
  its missing internal ID is not an active-development requirement.

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
The owner did not find Gapless/ReplayGain options in FiiO Control (2026-09-16);
no capture is currently needed for those preferences.

## Separate subsequent work

- [ ] Reorganize into emulator/viewer/controller plus shared firmware/research:
  [issue #7](https://github.com/eudj1n/snowsky-disc-qemu/issues/7). The agreed
  migration is separate from this protocol checkpoint; files have not moved.
- [ ] Retire the legacy V2.40 runtime/diagnostic profile and obsolete compatibility
  branches in a dedicated cleanup. The hosted workflow choice is already removed. Preserve `v2.40`
  and the research records; choose a final `-rN` snapshot only if later changes
  should be retained. Do not fold this cleanup into protocol research.
- [ ] Hardware validation: real USB DAC/AirPlay/Bluetooth audio, negotiated codec,
  actual PEQ/filter/balance effects, DSD and physical theme rendering. Emulator
  readback/persistence cannot establish those results.
- [ ] Build the local backend/frontend and Docker packaging. Use one owner of the
  stock single-client TCP connection, centralized event routing, partial-state
  merging, reconnection without replaying mutations, pending paused-seek state,
  refreshed queue identities and firmware-specific capabilities.

## Historical validation: channel-balance checkpoint

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

## Playback-preference investigation (2026-09-16)

The first candidate-write run failed: requesting gapless 1 left SQLite/config/
runtime at 0. Writing the existing default 0 had been a false positive. A second
diagnostic run verified populated callbacks but reproduced the failure. Tracing
TCP reception, rather than patching those callbacks, found the independent
111-tag allowlist at `6d84e0`. Candidate setters were removed.

Final focused acceptance passed on fresh disposable V2.57: three read-only values
match SQLite/config/runtime; six individually identified tags, each requesting a
different valid value, leave all six preferences and volume unchanged over both
TCP and WS. Fresh reads still work after every rejection. Unit tests cover all
allowed read values, malformed/missing JSON and no-I/O rejection of unsupported
operations. Final firmware-free checks passed again: 193 Python tests, 23
JavaScript tests, shell syntax and four shim builds. Full V2.57 integration
passed on retry, exit 0, including the new TCP/WS preference checks after SD
rescanning. These are local results, not hosted exact-commit release gates.

The first full run failed before preferences, in existing `queue_reads_check.py`:
after replacing the paused queue with play-all, `0202` reported state 2 instead
of playing, then timed out. Fresh focused `queue-reads` subsequently passed TCP
and WS, including that transition; no queue behavior was changed to mask it.
The cause is not established. Full retry passed with opt-in `CI_LOGS` capture
of guest logs before disposable cleanup; no queue fix is claimed. One intervening diagnostic run is invalid:
the running shell script was edited, disrupting its read position; never edit
`ci/integration.sh` while it is executing.

Logs for this investigation are ignored under `work/preferences/`:
`focused.log` and `focused-diagnostic.log` (failed candidate-write hypotheses),
`unit-allowlist.log`, `focused-allowlist.log` and `full-v257.log`.
Final unit log: `unit-final.log`. Queue reproduction: `queue-reads-v257-retry.log`
and `queue-logs/`; full retry: `full-v257-retry.log` and `full-retry-logs/`.
The interactive stack, its databases and firmware image were left untouched.
No viewer UI changed, so existing curated screenshots remain current.

**Next research item: custom playlist playback** in section 2, after the current
checkpoint validation/commit. Check the worktree and latest commit first.
Balance and preference protocol contracts are complete; actual DSP and local
preference behavior remain unvalidated.

Detailed local logs for this checkpoint are ignored under `work/http-research/`:
`balance-unit.log`, `balance-unit-rebuilt.log`, `balance-full-v257.log` and
`balance-full-v240.log`.
The prior checkpoint ran on another computer; its local files are not required.
The summary here must remain sufficient to resume even
when those machine-local logs are unavailable. Update results, failure explanations
and the next unchecked item before handing off the session.
