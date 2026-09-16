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
- [x] Dedicated V2.57 index/favorites reset, explicit confirmation, preserved
  source/settings/custom lists and recovery limits: [reset contract](LIBRARY_RESET.md).
- [x] Natural EOF observed in all five V2.57 local modes over TCP/WS with
  short WAV/FLAC tracks; final stop versus loading, repeat progress restart and
  silent `0202` after stop: [EOF contract](TRACK_END.md).
- [x] Generated CUE/WAV, DSF and DFF metadata and positional queue/favorite
  selection over TCP/WS; stock identity collisions/losses: [formats](FORMATS.md).
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

## Current checkpoint: idle, reconnect and USB power

LAN discovery checkpoint: `da9e00d`. The remaining local lifecycle investigation
uses no phone/LAN exposure and no edits to the interactive guest.

- [x] Trace independent display, UI inactivity, idle-power and USB-detection paths.
- [x] Observe TCP/WS quiet screen timeout and fresh handshake/readback after reconnect.
- [x] Model V2.57 USB power through stock AW35615/ADC1 detection, not a direct
  memory write or POWER_SAVE override; keep other ADC sensors unavailable.
- [x] Add disposable long `idle` / `idle-usb` scenarios and a short native USB
  check in ordinary full integration.
- [x] Add LAN timeout/reconnect regression; fix cancellation under upstream traffic.
- [x] Finish final focused lifecycle/USB and full V2.57 validation, review diff,
  refresh documentation/screenshots and create the local checkpoint commit.

Details and current validation: [IDLE_POWER.md](IDLE_POWER.md).

## Previous checkpoint completion: LAN discovery

CUE/DSF/DFF checkpoint: `70114b2`; natural EOF: `c3d15c2`;
library reset: `4da1de6`; scan cancellation: `53fb0eb`;
playlist: `392c8bc`; preferences: `274bce4`.
Their validation/failure history remains below.

- [x] Move SACD ISO into separate [issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8).
- [x] Trace V2.57 UDP announcement format and connected-state gate; observe
  physical beacons and compare the address with the user's iPhone search result.
- [x] Run focused disposable `discovery` acceptance: idle, TCP pre/post-handshake
  silence, fresh reads and disconnect recovery.
- [x] Add an opt-in host TCP/HTTP LAN bridge with explicit interface, one-phone
  allowlist, lifetime and unauthenticated-control acknowledgement.
- [x] Run firmware-free checks: 250 Python tests, 23 JavaScript tests, shell
  checks and four shim builds.
- [x] Verify phone-to-emulator discovery/connection and library browsing in an
  explicitly approved, one-phone LAN session.
- [x] Run **full** disposable integration on active V2.57 with discovery acceptance.
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
CI_SCENARIO=library-reset FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=track-end FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=formats FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=discovery FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=idle FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
CI_SCENARIO=idle-usb FW_VERSION=2.57 bash ci/integration.sh "$OTA_257"
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
- [x] **Dedicated library reset:** identified stock `0621/0000` and tested its
  index/favorites loss versus preserved files/settings/custom lists. Focused/full
  acceptance passed; see [reset contract](LIBRARY_RESET.md). Actual app
  sequence remains uncaptured; opening/cancelling confirmation reveals no payload.
- [x] **Natural end of track/list:** all five modes observed over TCP/WS using
  short generated WAV/FLAC tracks, gapless/folder jump off. Automatic transitions,
  final stop, repeat-one/list and random continuation have explicit acceptance;
  see [scope and limitations](TRACK_END.md). Physical timing remains unvalidated.
- [x] **CUE/DSF/DFF metadata and identity:** generated external UTF-8 CUE and
  stereo DSD64 fixtures, queue/favorite positions, shared path/zero track and
  ID/HTTP-mark ambiguity. See [scope and limitations](FORMATS.md).
- [ ] **SACD ISO:** tracked separately in [issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8);
  requires a suitable multi-track test sample; DSF/DFF do not
  establish ISO support. Embedded/multi-file CUE and higher DSD rates remain
  secondary extensions, not covered by the current fixtures.
  Historical V2.40 favorite-position playback remains guarded;
  its missing internal ID is not an active-development requirement.

### 3. Exact app behavior and discovery

- [ ] **Custom-theme metadata save in FiiO Control:** capture upload, then a change
  of only color/overlay settings. Preserve and restore the original custom slot.
  Our verified full-image API already works; empty-body custom POST clears the
  image path. See the [capture checklist](REMOTE_MODES_THEMES.md#fiio-control-capture-checklist).
- [x] **UDP LAN discovery contract:** exact physical payload observed; controlled
  emulator idle/connected/disconnected lifecycle passed. [Details](DISCOVERY.md).
- [x] **Official-app connection to emulator:** iPhone FiiO Control discovered
  the opt-in host LAN bridge, connected and opened the emulator library.
  Broader app compatibility and mDNS remain separate. Existing
  localhost WS bridge is our adapter, not a native stock DISC WebSocket endpoint.
- [x] **Emulator remote connection versus idle power:** screen-off, pause,
  power counters, natural shutdown, explicit local boot and TCP/WS reconnect
  passed, including native USB-power emulation. This is not stock standby or
  remote wake. See [current investigation](IDLE_POWER.md)
  and [earlier failure evidence](CI.md#idle-shutdown-versus-protocol-failure).
- [ ] **Physical iOS background/reconnect:** distinguish the host bridge's
  per-direction timeout from firmware power-off on a real phone. Any renewed
  one-phone LAN session needs fresh, bounded approval; do not reuse the expired
  discovery-test permission or infer Wi-Fi suspend behavior from qemu tests.

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

## Library-reset investigation (2026-09-16)

Static analysis traced admitted `0621` through `414bc0` / slot `83a56c` to
`4f0814`. It drops SONG/MY_LOVE and LIST_SONG_0/3, deletes PLAY_LIST rows 0/3,
but not custom-playlist tables or source files. Broader `0800` was only inspected
statically, never sent. The owner confirms FiiO Control exposes reset, but the
app frame/sequence remains unobserved; it is not needed to establish this firmware
handler. No reset was requested on a physical device.

Initial focused diagnostic passed TCP/WS with paused album playback, one seeded
favorite and a two-track custom list. Read-only SQLite confirmed dropped tables,
preserved custom rows and SYSCONFIG; source bytes were unchanged. Immediate
network catalogs are not all coherent: love/song has total -1, custom/song reports
two tracks but no items, and a202 is empty. An explicit guest restart left tracks
and favorites empty, recreated readable tables and exposed the saved custom list;
subsequent scanning restored three tracks without restoring favorites.

The extended helper run verified runtime still paused, unchanged Wi-Fi/theme
files, scoped PLAY_LIST deletion and TCP scan-only recovery. Its assertion failed
because it compared the entire custom page, including playback `mark` (-1 → 1),
instead of membership: all two entries had already recovered. Final acceptance
compares total/items separately. The same run proved MY_LOVE remains absent after
rescan; negative totals are not suppressed. This is a stock limitation, not a
reason to retry reset or write missing tables directly.

Firmware-free checks passed twice: 213 Python, 23 JS, shell syntax and four shim builds.
Final focused acceptance passed through both transports, including playback of
the preserved custom list after recovery. Full local V2.57 integration passed,
exit 0, on its first attempt in this checkpoint: all earlier scenarios, the new
TCP/WS reset checks, then SD hotplug/Unicode and preference checks. Its disposable
stack/volume were removed. This is local evidence, not a hosted exact-commit
release gate. All changes use tracked CI setup, no new Docker dependency, image
edits or interactive changes. Reviewed and included in the local checkpoint commit.
No viewer UI changed; existing curated screenshots remain the visual reference.

Ignored evidence in `work/preferences/`: `reset-refs.log`, `reset-callers.log`,
`reset-handlers.log`, `reset-scope.log`, `reset-list-scope.log`; initial
`reset-focused.log` / `reset-focused-logs/`; extended `reset-helper.log` /
`reset-helper-logs/`; `reset-unit.log`, `reset-unit-final.log`; final
`reset-final.log` / `reset-final-logs/`; `reset-full.log` / `reset-full-logs/`.

The next item at the reset checkpoint was natural end of track/list (below).
Do not substitute `0800` factory reset for library operations.
Check the worktree and latest commit first. Balance/preference audio effects,
physical custom-list behavior and hardware EOF timing remain unvalidated.

## Natural EOF investigation (2026-09-16)

Traced the V2.57 playlist worker `4524a4`, switch table `6c13f8`, automatic
control `4249fc` and final stop `458e1c`. The indirect switch is incomplete in
Ghidra's decompilation; its table and branches establish dispatch. Runtime tests
use the actual stock decoder and six-second WAV/FLAC files, no seek/next/EOF
injection or speed modification. See [the contract](TRACK_END.md) for addresses,
observed sequences, reproducible fixtures and client implications.

The first focused exploratory run failed at its final `0202` query after mode 0.
Guest logs showed both tracks had played to completion. The subsequent complete
TCP/WS observation established that modes 0/4 send `a103=0` then metadata-free
`a202 state=2`, internal state becomes 3, HTTP queue/mark survive and fresh mode
reads succeed, but `0202` remains silent. This is not accepted from timeout alone.
Follow-up static analysis explains the silence: `41fc70` → slot `83a3d8`
(`4ed618`) → local `4252ac` requires `4537b0()==0`; stop `456200` sets the
underlying context `+0x50` flag to 1. This is independent of status at `+0x48`.
Modes 2/3 replay/wrap with new full metadata and restarted ticks; mode 1 keeps
selecting from the queue beyond three completions without a fixed order claim.

The acceptance oracle requires complete six-second cycles, matching queue
identity/positions, expected per-mode order, terminal sequence or continuing
playback, independent runtime and network readback. The observer now samples
continuing tracks after their first tick, away from the next EOF race, and
observes a two-second quiet tail after stop. Every wait has a bound. Generated
media/list are removed, mode restored and the original three tracks reindexed.
Firmware-free checks passed: 224 Python, 23 JS, shell syntax and four shim builds.
Final focused acceptance passed all ten mode/transport combinations, source
byte verification, restored mode/catalog and disposable-stack cleanup (exit 0).
Full local V2.57 integration passed on its first attempt at this checkpoint
(exit 0), including all ten EOF cases and the subsequent scan-cancel, reset,
SD hotplug/Unicode and preference checks. The deadline failure path was tightened
during review before this run reached EOF: deadline exhaustion now fails rather
than allowing an incomplete quiet tail. The final firmware-free suite passed
again (224 Python / 23 JS / shell checks / four shim builds). Its disposable
stack, volume and generated host fixture were removed. This is local evidence,
not a hosted exact-commit release gate. No branch push is part of the checkpoint.

Ignored evidence under `work/preferences/`: `eof-worker.log`, `eof-navigation.log`,
`eof-stop.log`, `eof-random.log`, `eof-query-refs.log`, `eof-query.log`,
`eof-query-gates.log`, `eof-query-callback.log`; failed exploratory `eof-observe.log` /
`eof-observe-logs/`; complete observation `eof-events.log` / `eof-events-logs/`;
`eof-unit.log`, `eof-unit-final.log`; final acceptance `eof-final.log` / `eof-final-logs/`;
full integration `eof-full.log` / `eof-full-logs/`.
No viewer UI changed; the curated screenshots remain current. Interactive media
and emulator were not touched. Tracked fixtures use existing image dependencies;
no Dockerfile/normal Compose change or ad-hoc image edit is needed.

The next item at the EOF checkpoint was CUE/SACD/DSD metadata and identity
(CUE/DSF/DFF investigation below), not a claim of hardware/DSD audio support.

Historical balance-checkpoint logs are ignored under `work/http-research/`:
`balance-unit.log`, `balance-unit-rebuilt.log`, `balance-full-v257.log` and
`balance-full-v240.log`.
The prior checkpoint ran on another computer; its local files are not required.
The summary here must remain sufficient to resume even
when those machine-local logs are unavailable. Update results, failure explanations
and the next unchecked item before handing off the session.

## CUE DSD investigation (2026-09-16)

Generated original two-track UTF-8 CUE/WAV, tagged DSF and uncompressed DFF
fixtures rather than using private music. Independent host FFprobe recognizes
the two DSD layouts/tags; it is not a CI dependency. Stock scans yield seven
tracks (the original three, two CUE entries and two DSD files). TCP/HTTP catalog
order agrees; selected CUE metadata distinguishes titles/durations but not path
or wire track number. DSF/DFF report source DSD64/stereo/one-bit metadata, not
proof of native DSD/DoP output. [FORMATS.md](FORMATS.md) is the detailed contract.

Static analysis traced CUE insertion `443160`, queue construction `4388a0`,
source-ID lookup `44538c` and now-playing fallback `421c78`. CUE rows have
`IS_M3U=NULL`, which cannot match the lookup's integer equality; its fallback
mixes queue and catalog IDs. Runtime independently proves duplicate `0406` IDs
and a wrong HTTP current-row mark. `MY_LOVE` retains two CUE track ordinals,
but `0415` loses path/track/isCue. Both favorite positions still select the
correct title. No client normalization, DB repair or firmware patch was added.

The initial TCP observation passed. An extended identity run completed the TCP
format/favorite reads but failed while immediately pausing its restored album,
before reaching WS. It violated the known navigation interval; final acceptance
waits 2.1 seconds before both selection and pause, requires matching playing and
paused metadata, and never retries mutation commands. Final focused acceptance
passed both TCP/WS, including current-queue and favorite selection, favorite
removal, restored mode, unchanged fixture hashes and original three-track rescan.
Firmware-free checks passed twice: 232 Python tests, 23 JS tests, shell checks
and four shim builds. Final checks also assert DSF zero padding and CUE NULL flags.
Full local V2.57 integration passed on its first attempt at this checkpoint
(exit 0), including the new format scenario after earlier playback/settings/theme
checks and the subsequent EOF, scan cancellation, library reset, SD/Unicode and
preference checks. The final acceptance additionally asserts CUE `IS_M3U=NULL`;
it passed on both transports in the full run. Disposable stack, volume and host
fixture were removed. This is local validation, not a hosted exact-commit release
gate. Reviewed and included in the local checkpoint commit; no push is implied.

Ignored evidence under `work/preferences/`: `formats-refs.log`,
`formats-static.log`, `formats-identity-static.log`, `formats-id-lookup.log`;
initial `formats-observe.log` / `formats-observe-logs/`; failed extended
`formats-identity.log` / `formats-identity-logs/`; focused `formats-final.log` /
`formats-final-logs/`; `formats-unit.log`, `formats-unit-final.log`; full-run
`formats-full.log` / `formats-full-logs/`. Reproduction does not depend on these
machine-local files. Fixtures and all CI setup are tracked; no image-only edits,
new Docker dependency or interactive emulator/media changes. No viewer UI changed;
existing curated screenshots remain current.

**Deferred format item: SACD ISO**, tracked in
[issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8), requiring a suitable multi-track sample.
Its static decoder branch is mapped, but DSF/DFF are not a substitute. Without
that input, the next independent backlog is exact app behavior/discovery, not
more speculative format-support claims. Embedded/multi-file CUE, CUE seek/EOF
boundaries and hardware DSD output remain outside this checkpoint.

## LAN discovery investigation (2026-09-16)

SACD ISO moved to [issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8)
at the user's request; no ISO was added or marked supported. The next work item
became LAN discovery. See [DISCOVERY.md](DISCOVERY.md) for the wire contract,
exact V2.57 addresses, host tooling, exposure risks and repeatable commands.

Static UDP sender `4da780` sends only literal `SNOWSKY DISC` to multicast
224.0.0.255:12101, not a Link frame or a response to a query. TCP accept in
`4db020` sets connected flag `898950` and suppresses beacons even before a Link
handshake. A fresh disposable focused run passed: four idle beacons (~2.01 s),
silence before/after handshake, fresh settings/protocol reads, then four resumed
beacons after disconnect. No source/settings changes or firmware patch.

Passive physical capture received 15 exact beacons in 30 seconds (~1.84–2.15 s).
The user saw the same device address in iPhone FiiO Control. Their brief physical
connect/disconnect was not precisely aligned with the observer; retain that limit
instead of claiming measured physical suppression. A short mDNS browse saw no
`_fiio._tcp` instance. Static registration `489d70` uses port 12102, with TXT
fields built by `4898a4`; it is not evidence of a TCP-12100 discovery requirement.

Added passive `tools/fiio_discovery.py` and explicit host `tools/lan_bridge.py`.
The latter synthesizes the verified announcement from the selected host interface
and forwards TCP 12100 and direct stock HTTP 12103 to existing loopback ports.
It requires a single allowed phone IP, acknowledgement of unauthenticated control
and a bounded lifetime; default Compose stays localhost-only. No Avahi, WS
translation, arbitrary multicast relay or image-only dependency was introduced.

After explicit approval, the existing V2.57 guest was booted (no SD rebuild) and
the bridge opened for one iPhone. The user confirmed discovery of the emulator's
host address, successful connection and library browsing. Bridge logs independently
showed control and HTTP connections. On confirmed disconnect, announcements
resumed in the host observer and the device returned to the phone's search list.
The bridge was stopped and its LAN listeners checked absent. Normal local guest
was left running; no library reset, file deletion or setting mutation was part
of the manual test. The phone-to-emulator path worked without mDNS advertising.

Firmware-free validation passed: 250 Python tests, 23 JavaScript tests, shell
checks and four shim builds. Bridge tests include byte-exact forwarding,
half-close, disallowed peers, single control owner, HTTP readiness/failure,
connection/readiness race, upstream-failure cleanup and explicit multicast TTL.
The first full run passed discovery and all later scenarios through formats, then
failed the EOF oracle's requirement for an intermediate `a202 state=1` between
tracks. Its trace still shows six seconds/6000 ms, correct next full metadata,
restarted progress and final zero/state-2 stop. Guest logs independently show
natural completion and a decoder-only transition; the precise reason for the
missing wire delta was not established. The oracle now permits that transient
delta to be absent **between** tracks, while retaining duration, order, new
metadata, restarted progress, final-stop and runtime/readback requirements. Two
regression tests cover this valid sequence and retain the terminal pause check.
The original saved failing trace also passes the corrected oracle unchanged.
The failure was not suppressed or retried unchanged. The second full run passed
all five TCP EOF modes (including another transition without state 1), but failed
the fixture's album-restoration pause before reaching WS. That path sent pause
immediately after selection, violating the already documented 2.1-second
navigation interval. It now waits before the single pause command, as the format
scenario already does; no mutation retry was added. The third full run passed
(exit 0): discovery, all existing protocol/settings/format checks, all ten EOF
mode/transport combinations and their restoration, scan cancellation, library
reset, SD/Unicode and preference checks. The final firmware-free suite passed
again (250 Python / 23 JavaScript / shell checks / four shim builds), and Compose
validation passed. Disposable stack, volume and generated host fixture were
removed. This is local validation, not a hosted exact-commit release gate.
Reviewed and included in the local checkpoint commit; no push is implied.

Ignored evidence under `work/preferences/`: `discovery-refs.log`,
`discovery-static.log`, `discovery-state-refs.log`, `discovery-lifecycle.log`,
`discovery-mdns.log`, `discovery-mdns-register.log`; physical observations
`discovery-physical.log`, `discovery-physical-lifecycle.log`; host bridge observations
`discovery-host-bridge.log`, `discovery-phone-disconnect.log`; focused
`discovery-focused.log` / `discovery-focused-logs/`; firmware-free
`discovery-unit.log`, `discovery-bridge-unit.log`, `discovery-unit-final.log`,
`discovery-unit-reviewed.log`, `discovery-unit-verified.log`; failed full
`discovery-full.log` / `discovery-full-logs/`; second failed full
`discovery-full-final.log` / `discovery-full-final-logs/`; third full
`discovery-full-verified.log` / `discovery-full-verified-logs/`. Logs contain local addresses:
do not upload them as CI artifacts. Reproduction uses tracked scripts and does
not depend on these machine-local records. Viewer UI is unchanged.

Next: exact custom-theme metadata-only save in FiiO Control, or the separately
listed remote connection/idle-power lifecycle. Discovery/library browsing does
not validate every app command, Android, mDNS/AirPlay or sleep/wake behavior.
Do not start an automatic LAN service or weaken default network exposure.

## Idle, reconnect and USB-power investigation (2026-09-16)

The owner's physical observation (5-minute Idle poweroff, Sleep off, 2-minute
screen timeout, USB power prevents idle shutdown) prompted a native power model.
The previous viewer cable/sysfs stub did not set the stock USB flag. Traced
AW35615 sink role, sequential ADC initialization and ADC1 thresholds, then added
narrow V2.57-only shim/setup support. The firmware itself now updates its power
gate. Other ADC sensors fail explicitly; no fabricated jack state, USB data,
direct runtime-memory writes, firmware patches or POWER_SAVE override.
See [the complete contract and addresses](IDLE_POWER.md).

Initial quiet TCP/WS experiments passed 135 seconds without application reads,
natural display timeout, fresh handshake/settings/queue reads, remote playback
with the display still off and local physical wake. Separate paused testing
with idle limit 300 demonstrated counter growth despite read-only network polls;
playing and USB power reset that counter. The first natural shutdown run reached
counter 301 on both transports, then the confined power request and guest-scoped
supervisor stop. TCP recovery included retained queue/current metadata; WS
recovered settings/catalog/queue but did not restore current-track metadata.

Failure history and oracle corrections:

- The first strict manual screen-off assertion raced sysfs brightness against
  the player's separately updated screen byte. The fixture now waits for both
  before recording its playing interval; state/counter assertions remain.
- The first USB run passed the entire 310-second plugged interval but failed
  its unplug assertion. Stock removal wakes the display and resets UI activity;
  a counter sampled across that wake is not monotonic. The test now observes
  the transition, explicitly sleeps the display and checks resumed counting.
- The initial power acceptance required full now-playing immediately after
  every boot. The second reboot logged `get list song idx fail!` in stock
  `comm_play_memory`, while catalog/queue reads worked. Recovery now independently
  checks the known metadata-suppression flag on a timeout, fresh settings/mode
  reads, and a **new explicit** selection/play/pause cycle. Queue persistence is
  not a guarantee of resume-memory restoration, and timeout alone never passes.
- A new LAN loopback regression caught nested `wait_for` cancellation hanging
  cleanup under continuous upstream notifications. Direct awaits inside
  `asyncio.timeout` fix it without changing the 120-second per-direction policy.
  Twenty repeated runs of the LAN test file passed after the correction.
- The first full regression reached the new native USB checks, then failed the
  unchanged strict TCP/WS catalog comparison. Logs show TCP accept at 11:44:09.698,
  auto-scan start at .702, TCP close at .766 and scan completion at .791; WS
  connected at 11:44:10.993. SD insertion had queued a delayed auto-scan across
  the two reads. The peripheral fixture now waits for a new scan, stopped worker,
  visible result and exact SD/SQLite/TCP agreement, then dismisses the result.
  It does not retry the comparison until green, change the transport clients,
  disable Auto update or relax equality.
- The second full run passed that comparison, PCM/buttons/settings/formats,
  all ten EOF cases and scan cancellation, then failed library-reset fixture
  cleanup: the newly selected album stayed playing after an immediate Pause.
  That older fixture omitted the known 2.1-second selection-to-pause guard.
  Added the same spacing at its three selection/pause sites, retaining the
  paused-state assertion and sending each toggle only once. Dedicated reset
  acceptance passed TCP/WS after this correction; the third full run passed too.

Final focused `idle` (both phases, TCP/WS), `idle-usb`, dedicated `library-reset`
and the third **full V2.57 integration** passed (exit 0). The full run covered
discovery, peripheral native USB detection, PCM/buttons, TCP/WS queue/files/
playlists/settings/themes, CUE/DSF/DFF, all ten EOF cases, cancellation/reset,
Unicode SD scans and rejected preference setters. Final firmware-free checks:
257 Python, 23 JavaScript, shell checks and four shim builds. This is local
evidence, not a hosted exact-commit release gate.

Evidence remains ignored under
`work/idle/`, `shots/idle*` and local `/tmp/disc-idle-*.log`; do not upload guest
logs or derived binaries. Reproduction is entirely in tracked setup/shim and
`ci/idle_check.py`, selected by `CI_SCENARIO=idle|idle-usb`. Dockerfile dependencies
already suffice, Compose remains localhost-only, and the interactive guest and
physical player are untouched. Phone background/reconnect and hardware timing
are not covered by these emulator tests.

Next: the specific FiiO Control custom-theme metadata-only capture, or a separately
approved physical iOS background/reconnect session. Neither is required to enable
the implemented emulator USB-power model; do not silently open LAN listeners.
