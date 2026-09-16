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
  [HTTP API](HTTP_API.md).
- [x] V2.57 custom-playlist whole-list and indexed playback over TCP/WS,
  guarded by fresh HTTP name/track reads: [playlist contract](PLAYLISTS.md).
- [x] V2.57 cooperative scan cancellation, partial replacement index and full-scan
  recovery over TCP/WS: [scan lifecycle](LIBRARY_SCAN.md).
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

## Current checkpoint completion: scan cancellation

Playlist checkpoint: `392c8bc`; preference checkpoint: `274bce4`.
Their validation/failure history remains below.

- [x] Trace `0622`, stop/reset timing, buffered-row flush and finish events.
- [x] Add one-shot cancellation preserving pending events and no-retry coverage.
- [x] Run firmware-free checks: 209 Python tests, 23 JavaScript tests, shell
  checks and four shim builds.
- [x] Run focused `scan-cancel` acceptance via TCP/WS (initial 512-file fixture).
- [x] Run **full** disposable integration on active V2.57, including the final
  1024-file fixture and earlier cancellation trigger (first positive progress).
- [x] Review the complete diff, record validation and create the local checkpoint
  commit. Pushing/publishing is not part of this step.

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
CI_SCENARIO=playlists FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=scan-cancel FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
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

- [x] **Custom playlist playback:** `0100`/`0101`, type 5 plus decimal JSON
  `{"id":<list position>}`. Fresh HTTP preflight checks expected name and track
  bounds; TCP/WS tests cover ID gaps, rename/add/remove, empty and stale positions.
  Position/name checks are not atomic identity: serialize edits and never replay.
- [x] **Cancel indexing:** `0622/0001` stops cooperatively, leaves a partial
  replacement index and emits the same `a60a/0005` as a full scan. Idle cancel
  does not clear the catalog; a new scan resets stop and rebuilds the full index.
  See [contract and tests](LIBRARY_SCAN.md). Not a library-reset command.
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
- [ ] **Remote connection versus idle power:** observe screen-off, pause,
  power counters, shutdown and safe wake/reconnect. The CI display-time fixture
  isolates protocol tests; it does not implement stock standby or remote wake.
  See [failure evidence](CI.md#idle-shutdown-versus-protocol-failure).

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
That run had no retained guest logs, so its cause cannot be proved retrospectively.
The playlist checkpoint below reproduced the same symptom with logs showing
stock shutdown, not a malformed selector. Full retry passed with opt-in `CI_LOGS`
capture of guest logs before disposable cleanup; no queue fix is claimed.
One intervening diagnostic run is invalid:
the running shell script was edited, disrupting its read position; never edit
`ci/integration.sh` while it is executing.

Logs for this investigation are ignored under `work/preferences/`:
`focused.log` and `focused-diagnostic.log` (failed candidate-write hypotheses),
`unit-allowlist.log`, `focused-allowlist.log` and `full-v257.log`.
Final unit log: `unit-final.log`. Queue reproduction: `queue-reads-v257-retry.log`
and `queue-logs/`; full retry: `full-v257-retry.log` and `full-retry-logs/`.
The interactive stack, its databases and firmware image were left untouched.
No viewer UI changed, so existing curated screenshots remain current.

## Custom-playlist investigation (2026-09-16)

Type 5 is a stock branch of admitted `0100`/`0101`, not a new HTTP endpoint.
Ghidra confirmed JSON `id` is translated by SQL OFFSET into `LIST_ID`. The
initial focused test failed before playback because it assumed insertion order;
adding catalog positions 2 then 0 returned the opposite order. Tests now verify
membership separately and use fresh `custom/song` ordering. Playlist operations
use no firmware patch, direct DB write or command sweep (the later CI display
fixture is separate test setup, documented below).

Focused helper acceptance passed on TCP and WS: playlist position 0 mapped to
SQLite LIST_ID 1, both whole-list and index selection matched track metadata,
queue order and mark. Rename/add/remove and deletion-induced position shifts
worked; stale names/positions, empty lists and out-of-range tracks were rejected
before playback. Generated lists were removed, original mode restored, playback
left paused on a valid album and source media checked byte-for-byte.
Final unit suite including CI-fixture and PID-discovery guards passed (206 Python, 23 JS,
shell checks and four shim builds).
Final full local integration passed, exit 0, including nonzero playlist position,
an index made stale by track removal, all preceding protocol/audio/control checks,
settings/modes/themes, confinement, SD rescanning and preference rejection tests.
The disposable stack/volume were removed. These are local results, not hosted
exact-commit release gates. No physical-device or natural-end claim is made.

The first full playlist run failed **before** the playlist stage, at the previous
queue-reads transition. Retained logs show screen-off, `release_local!`, network
teardown and watchdog stop, followed by `g_fiio_local is null!` on selection.
The subsequent test-fixture change keeps V2.57's display on (`LIGTH_ON_TIME=7`),
with the guest stopped for the DB update and read-only fingerprinted UI validation
after boot. It changes neither interactive defaults nor `POWER_SAVE`; all playlist
mutations themselves still go through stock HTTP/Link. See the
[idle-shutdown analysis](CI.md#idle-shutdown-versus-protocol-failure).
Do not claim that all remote sleep/wake behavior is fixed by this CI isolation.

With the display fixture, full integration passed both queue-read transports,
all extended playlist cases, settings and modes/themes, but stopped in the SD
delete-rescan setup: read-only `PlayerMemory` enumeration found two matching PIDs.
It did not send the removal event to an ambiguous process. A main-thread `popen`
fork can inherit both comm and argv; the retained logs alone do not prove which
two processes were observed. Discovery now re-enumerates on ambiguity at most ten
times (50 ms intervals), still fails closed if ambiguity persists and never
retries a mutation. Synthetic tests cover transient/persistent/missing PIDs.
The subsequent full validation passed as recorded above; no guest-state mutation
was replayed to obtain that result. Interactive firmware/settings/media were not
modified. All changes to the disposable fixture are encoded in CI scripts and
the CI Compose overlay; no new image dependency or ad-hoc image edit was needed.

Ignored evidence lives in `work/preferences/playlist-*.log` and corresponding
`playlist-*-logs/`: static `playlist-select.log`, `playlist-identity.log`,
`playlist-position.log`; failed initial `playlist-focused.log`; passed
`playlist-helper.log`; final `playlist-unit-final.log`; full `playlist-full.log`.
CI fixture follow-up: `playlist-awake-unit.log`, `playlist-awake.log` and
`playlist-awake-logs/`; static power/display analysis: `power-*.log`.
Final follow-up: `playlist-final-unit.log`, `playlist-final.log` and
`playlist-final-logs/`.
No viewer UI changes or screenshot refresh are needed for this protocol addition.

## Scan-cancellation investigation (2026-09-16)

Static V2.57 analysis identified admitted `0622` → `4f0550` → `42e18c` and the
cooperative stop flag `85fbdc`, reset at scan start/end. Network worker `42c050`
sends start before the reset; cancelling on a first positive progress event avoids
that known ordering window. The parser flushes pending rows on stop. SONG is
dropped/rebuilt at scan start, so cancellation is not rollback.

Initial focused acceptance passed on both transports with 512 added WAVs and
three original tracks. TCP cancellation at count 455 ended with 508 rows, WS at
314 ended with 397, both with normal `a60a/0005`. TCP, HTTP and SQLite agreed on
the partial catalog. Idle cancel changed no catalog and produced no scan events;
the stop flag cleared on the subsequent scan. Each full recovery restored 515
rows, source bytes were unchanged, and removing generated files/reindexing restored
the original three. No direct DB/memory writes or firmware patches were used.

The first fixture left only seven tracks unprocessed on TCP, an unnecessarily
tight timing margin. Final acceptance uses 1024 generated WAVs and sends cancel
on the first positive count (not after count >=8). It still requires a running
worker and a genuinely partial result; it never retries a scan/cancel to obtain
one. Full local V2.57 integration passed with the final fixture: both cancellation
requests followed count 1, TCP ended with 167/1027 rows and WS with 31/1027.
Each subsequent full scan restored 1027; fixture cleanup restored the original
three. Later SD hotplug/Unicode and preference scenarios also passed, and the
disposable stack/volume were removed. This is local evidence, not a hosted release
gate. Firmware-free suite passed: 209 Python, 23 JS, shell checks and four shim builds.

Ignored evidence: `work/preferences/cancel-static.log`, `cancel-handler.log`,
`cancel-worker.log`; `cancel-focused.log` and `cancel-focused-logs/`;
`cancel-unit.log`; `cancel-full.log` and `cancel-full-logs/`.
No viewer UI changed; existing curated screenshots remain current. The
interactive stack/media remain untouched. Fixtures are part of tracked CI, not
ad-hoc image edits; Dockerfile and normal Compose need no new dependency/option.

**Next research item: dedicated library reset** in section 2. Cancellation
validation is complete. Do not substitute `0800` factory reset for library operations.
Check the worktree and latest commit first. Balance/preference audio effects,
physical custom-list behavior and natural end-of-list remain unvalidated.

Historical balance-checkpoint logs are ignored under `work/http-research/`:
`balance-unit.log`, `balance-unit-rebuilt.log`, `balance-full-v257.log` and
`balance-full-v240.log`.
The prior checkpoint ran on another computer; its local files are not required.
The summary here must remain sufficient to resume even
when those machine-local logs are unavailable. Update results, failure explanations
and the next unchecked item before handing off the session.
