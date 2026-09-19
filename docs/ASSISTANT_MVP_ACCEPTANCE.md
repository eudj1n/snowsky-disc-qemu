# Disc Assistant software MVP acceptance

**Decision: accepted on 2026-09-19**, by the owner, within the
[emulator-based software boundary](ASSISTANT_MVP.md). The owner explicitly deferred
physical-device acceptance and platform/speech-quality work, and confirmed that
existing reproducible emulator scenarios are sufficient for closure. No new
regression or audio run was performed for this documentation checkpoint.

## Evidence

Candidate: `48477e8` on `codex/assistant-plan`. The disposable V2.57 run used
manifest v7, generated media, real Typesense and the common Assistant/Controller
execution path. Fresh state/queue reads and instrumented writes independently
checked expected effects.

| Measure | Result |
| --- | --- |
| Planned / submitted / passed | 64 / 64 / 64 |
| Russian / English passed | 35 / 29 |
| Failed / blocked cases | 0 / 0 |
| Cases requiring no device mutation | 19 |
| Observed mutation writes in those cases | 0 |
| Controller tests | 192 passed |
| Assistant prototype tests | 354 passed |
| Shared firmware-free container checks | 365 Python / 37 JavaScript passed |

Coverage includes artist/track/album selection, compilations, scoped/Cyrillic
albums, semicolon artist credits, fuzzy member lookup, RU synonyms, pause/resume/
stop and repeated controls, next/previous before and after the stock restart
boundary, paused/first-row navigation, missing music, negation, compound-command
rejection and locale changes. All declared per-case checks passed.

The [curated machine-readable report](../research/disc_assistant/experiments/acceptance/reports/2026-09-19-emulator-mvp.json)
preserves all 64 outcomes, timings and source/manifest/report hashes. Full local
artifacts remain at `/tmp/disc-pacing-acceptance-20260919/`; these temporary files
are not the only record of the accepted result. The run began on `45590a2` with
its recorded working-tree pacing patch, subsequently committed in `48477e8`.
Later LAN shutdown/test-fixture changes were checked by the final unit suites;
the Assistant/playback execution code matches the accepted candidate.

Example local command latencies: EN/RU pause 76.794/77.175 ms; track selection
324.130/293.273 ms. Rapid EN resume after setup pause took 1999.296 ms because the
remaining stock interval was still enforced. These individual observations are
not a paired speed benchmark or an Orange Pi estimate.

## Reproduce

With the reviewed V2.57 OTA directory already available, from the repository root:

```sh
./research/disc_assistant/run.sh test

docker build -t snowsky-disc-qemu-ci docker
docker run --rm --network none -v "$PWD:/repo:ro" \
  snowsky-disc-qemu-ci bash /repo/ci/test.sh

bash ci/assistant.sh /absolute/path/to/main_os/ota_v257 /tmp/disc-mvp-new-run
```

Choose a **new** report directory. The last command creates disposable guest/search
resources and generated media, captures reports, then removes its containers,
network and volumes. It does not control a physical player. See the
[runner instructions](ASSISTANT_EMULATOR_ACCEPTANCE.md) for prerequisites and case
selection. A future failure is a new regression record; never overwrite this
accepted report or automatically replay a possibly dispatched command.

## Limits and follow-ups

This is acceptance of a known, examined **text-command regression cohort**. It is
not an independent holdout estimate, human microphone accuracy, audible Hi-Fi
validation or acceptance of arbitrary user wording. Screenshots were collected,
but no visual-review claim is needed for the API-observable checks. Earlier failed
runs and the partial physical baseline remain unchanged.

Physical acceptance is tracked in [#23](https://github.com/eudj1n/snowsky-disc-qemu/issues/23).
[Speech quality/performance #24](https://github.com/eudj1n/snowsky-disc-qemu/issues/24) tracks native versus Docker CPU builds,
Orange Pi small timeout, transcript review, representative human recordings,
Piper mixed-name pronunciation and Irina redistribution-license clarification.
These are not prerequisites for this accepted software MVP. Learned execution,
dialogue and hardware promotion remain outside scope.
