# Assistant scenarios against the emulator

The disposable runner verifies Assistant commands against stock V2.57 with
generated media and real Typesense. The [64-case software MVP was accepted](../reports/2026-09-19-mvp-acceptance.md)
on 2026-09-19. Physical acceptance remains separate; this cohort never overwrites
the frozen physical baseline.

## Run

Requires Docker Compose >=2.36, the reviewed V2.57 OTA directory and the existing
`snowsky-disc-qemu-ci` image (`docker build -t snowsky-disc-qemu-ci emulator/docker`).
The first run builds a separate Python 3.12 Assistant image using the prototype's
requirements. Typesense 30.2 runs with a fresh data volume and random test key.

From the repository root:

```sh
bash ci/assistant.sh /absolute/path/to/main_os/ota_v257 /tmp/assistant-run-01
```

The report directory must not already exist. Run selected cases, with optional
screenshots for every case:

```sh
bash ci/assistant.sh /absolute/path/to/main_os/ota_v257 /tmp/assistant-run-02 \
  --case en-pause --case ru-compound --screenshots all
```

Manifest v7 has 64 cases (29 EN / 35 RU). Default screenshots cover unsuccessful cases.
The separate voice-extension suite has 30 cases (18 RU / 12 EN), covering
favorites, now-playing, volume and album/artist search priority, including ten
no-write cases. Select it explicitly; the default remains the accepted baseline:

```sh
bash ci/assistant.sh /absolute/path/to/main_os/ota_v257 /tmp/assistant-voice-01 \
  --suite voice
```

Exit status is zero only when every selected case passes; known failures are not
silently excluded. The fresh guest, search service, network and volumes are removed
on exit. No host ports are published, no personal configuration is loaded, and the
runner's device endpoint is fixed to the disposable `emulator` service.

`results/report.md` and `results/report.json` summarize the run. Individual JSON
files retain setup, measured response, fresh before/after observations, TCP send
tags, checks and screenshot references. `manifest.json`, `provenance.json`, bootstrap
results, isolated SQLite/journal under `runtime/`, image identities, source diff
and guest/run logs preserve reproducibility. Keep this directory private and
outside Git; logs/screenshots can contain firmware-derived content. Screenshots
are evidence awaiting review, not automatic visual assertions.

## Reuse existing infrastructure

[`ci/integration.sh`](../../../../ci/integration.sh) already creates an isolated Compose
stack, disposable work volume and generated media, then boots stock firmware.
[`ci/compose.yml`](../../../../ci/compose.yml) removes host port publishing. Existing
Controller integration checks exercise playback and queue reads on that guest.
Assistant unit tests use synthetic servers. The older
[`emulator_check.sh`](../../emulator_check.sh) checks controls,
queues, EOF and persistent sessions without the complete live search path.

[`ci/assistant.sh`](../../../../ci/assistant.sh) reuses the extraction/setup/boot/cleanup
primitives with a dedicated [test overlay](../../../../ci/assistant.compose.yml).
[`assistant_check.py`](../../../../tests/integration/assistant_check.py) covers the full
text → interpreter → real Typesense → Controller → stock firmware path.
Controller acquires no research dependencies, and this opt-in run is not a default
firmware CI gate. Its pure oracle tests are included in firmware-free CI.

## Scenario execution

1. Generate tagged recordings with explicit identities and known album/artist
   membership, including Cyrillic, shared artist metadata and duplicate editions.
   Use generated audio, not the owner's library. Ordinary control tracks should
   be long enough to avoid accidental EOF; dedicated EOF cases use short tracks.
2. Boot the reviewed firmware, scan, wait for scan completion, then sync and index
   through the actual Assistant. Give each run isolated settings, SQLite, journal,
   Typesense data and credentials. Record code/firmware/index fingerprints.
3. Establish each case's declared precondition, locale and play mode. Keep setup
   operations separate from the measured command. Submit the command through
   `Application.request`, the console's application entry point; do not call the
   parser or Controller action directly in place of the Assistant.
4. Observe fresh state and queue before/after, with bounded waits and timestamps.
   Compare against independently authored expectations and fixture identities,
   never against the Assistant's selected candidate or success status as gold.
   Do not replay uncertain commands. Block dependent cases if setup fails.
5. Save per-case input, result, expected/observed outcome, latency and evidence in
   a new run directory. Provide JSON plus a readable report and selected-case
   execution. New attempts retain old failures. No scheduler or autonomous loop
   is required; an agent or developer starts and reviews each run.

## Evidence and verification boundaries

- Read the player after the operation through the shared Controller session.
  The DISC TCP connection is single-client: a second simultaneous observer must
  not compete with Assistant. `DiscSession.snapshot()` and console `/status`
  expose cached observations; they are not by themselves fresh readback. Use
  fresh requests/event sequence evidence and record observation age.
- Use HTTP queue membership and current recording/position/mode to verify the
  requested effect. A reported `confirmed` may still describe an effect that
  fails the scenario, such as restarting the current track when the expectation
  is the previous recording. Keep response confirmation and scenario outcome
  separate. Distinguish pause from EOF and transient loading.
- Fresh Controller readback is separate from the Assistant response, but shares
  its protocol implementation. For ambiguous state, use the existing reviewed
  guest diagnostics as a second evidence source; keep them firmware-profiled.
- Capture the current framebuffer through emulator runtime primitives, using
  `emu/fb-live`, for mismatches or explicitly visual checkpoints. UI screenshots
  are review artifacts; do not claim automated visual verification merely because
  an image exists. Account for screen sleep, lockscreen and refresh latency.
  Avoid viewer dependencies and pixel-perfect assertions for ordinary playback.
- No-change cases need state/position/queue continuity. Missing
  `mutation_attempted` is unknown, not false. Proving no write requires separate
  command/event instrumentation; stable screenshots alone cannot prove it.

The runner instruments the existing persistent client without changing Controller:
recorded sends cover the measured command only, and new `a103` events establish
progress while playing. Paused DISC can stop progress events; those observations
explicitly label position as retained, with its event timestamp and fresh paused
state readback. TCP tags establish whether playback writes were attempted; they
do not constitute a full network capture. The runner does not exercise HTTP writes.
It opens the stock Now-playing page during unscored setup so screen artifacts can
show track/state. Screen identity is manually reviewed, not inferred from the tap.

## Add a scenario

Edit [`assistant_scenarios.json`](../../../../tests/fixtures/assistant_scenarios.json), with
an explicit new case ID, locale, command, setup track/state/progress and expected
effect, statuses and mutation policy. Track keys refer to synthetic metadata in
the same file, generated by [`assistant_fixture.py`](../../../../tests/fixtures/assistant_fixture.py).
Accepted duplicate editions must be listed before running. Supported effects are
`track`, `artist`, `paused`, `playing`, `next`, `previous` and `unchanged`.
The extension manifest, [`assistant_voice_scenarios.json`](../../../../tests/fixtures/assistant_voice_scenarios.json),
adds `favorite`, `volume` and `now_playing` effects and reuses the baseline's
generated tracks. Its setup can establish favorite state and volume before the
measured request; fresh readback verifies both independently of the reply.
Previous/next expectations use fresh sequential-queue neighbors. Setup always
selects the declared recording anew through Controller; setup failures block that
case, while later cases establish their own prerequisites. New effects need an
oracle implementation and regression tests before being added to this vocabulary.
Interpretation details remain in the request journal; the first runner evaluates
response contracts and observed device effects, not a separately scored slot corpus.

Initial coverage: track/artist selection, pause/resume/stop and repeated controls,
next/previous, absent music, negation and compound rejection, RU/EN locale handling.
Freeze the case contract before execution. Keep known disagreements visible:
the original "previous" versus restart discrepancy is retained in earlier reports; a phrase such as
"turn on the light" may be a song query, so rejection-only gold is disputed.
Do not train or tune on a case and keep calling it independent acceptance.

## Relationship to the physical baseline

Report emulator and physical results separately. Emulator runs can establish
functional control effects without a person listening. They do not establish
physical DAC/Bluetooth output, analog quality or physical firmware timing.
Retain a smaller physical smoke suite and hardware-specific checks.

The active physical run remains incomplete. Its private manifest and original
evidence are unchanged; do not replace its remaining cases with emulator results.
See [baseline status](physical-baseline.md) and [MVP acceptance](../reference/mvp.md).

## Dated results

[Development checkpoints](../reports/2026-09-19-emulator-checkpoints.md) preserve
initial failures and successive manifest results. The accepted MVP and subsequent
30-case extension have separate evidence in [current status](../status.md).
