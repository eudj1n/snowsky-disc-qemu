# Disc Assistant research: session handoff

Read the repository-root `AGENTS.md` first. This file applies to
`experiments/disc_assistant/`; it supplements, not replaces, repository conventions.
Conversation may be Russian; **tracked documentation and comments are English**.

## Voice extension and NLU ownership, 2026-09-21

Issue #27 / `codex/assistant-contextual-voice` adds favorites, now-playing,
configurable volume and guarded album/artist context ranking. Read
`../../docs/ASSISTANT_QUICK_GUIDE.md` and the latest status before continuing.
Working NLU now lives in `assistant/nlu`; optional evaluation tools are in
`assistant/nlu/evaluation` and data/references in `assistant/nlu/data`.
Locale TOML stays in `assistant/locales`; command templates contain no training
examples. Learned models remain shadow-only and frozen corpus/report bytes are
preserved. Follow `../../docs/PYTHON_QUALITY_REVIEW.md` for the requested quality
review and possible future Controller extraction; no extraction is performed.

## Product boundary updated 2026-09-19: software MVP accepted

The owner explicitly accepted **software MVP against the stock emulator**, and
confirmed that the existing reproducible 64-case run suffices. Close/retain
[MVP #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21) as completed within
that scope; do not make new audio cohorts, physical hardware or performance
optimization prerequisites for it. Read `../../docs/ASSISTANT_MVP_ACCEPTANCE.md`.

Accepted candidate `48477e8`: 64/64 manifest-v7 text scenarios (35 RU / 29 EN),
19 no-mutation cases with zero observed writes; 192 Controller, 354 prototype,
365 shared Python and 37 JS tests passed. This is known regression acceptance,
not an independent human-speech error bound. No new rerun was needed at closure.

Physical acceptance remains unpassed in [#23](https://github.com/eudj1n/snowsky-disc-qemu/issues/23).
Keep its original 19-RU partial baseline, failures and disputed gold intact; measure
that cohort before agreeing physical thresholds. [#24](https://github.com/eudj1n/snowsky-disc-qemu/issues/24)
tracks speech quality and native/Docker/Orange Pi performance, explicitly deferred.

One action per request, one saved locale and no uncertain mutation replay remain
the product contract. Learned arbitration, fine-tuning, semantic retrieval,
recommendations, dialogue, wake word and dock hardware are later work. Keep the
prototype under experiments until a separately agreed promotion/repository split.

## Browser adapter checkpoint

`assistant/application.py` is the common synchronous service. CLI lives in
`assistant/console.py`; Disc Assistant Web lives in `assistant/web/` and follows
viewer styling without runtime imports. `run.sh web --bootstrap` prepares search
and serves loopback port 8090. One worker owns application/SQLite; the existing
Controller session receives events continuously. No queued/retried mutations,
public/LAN serving, arbitrary slash commands or filesystem upload paths. Browser
recording is bounded PCM capture, explicit stop/submit/cancel; no VAD/wake word.
Web always uses Whisper Server; one-shot CLI can retain its configured CLI
backend. `setup --all` installs the optional managed speech stack and pinned
Whisper/Irina/Alba models outside Git; `web --bootstrap` starts speech and search.
Setup preserves an installed Whisper model unless explicitly replaced. Piper
voice-map hashes trigger worker recreation on voice changes (Irina replaced Denis
on 2026-09-19). Piper replies honor response.speak and explicit per-tab sound opt-in. Delivery
failure never changes/replays a command; cache and journal preserve voice hashes.
`voice/text.py` is the identity TTS-only preparation hook; do not add blanket
transliteration or change frozen samples without a separate pronunciation study.
See `../../docs/ASSISTANT_WEB.md` and `../../docs/ASSISTANT_TTS.md`.
The owner reports physical microphone play/stop success; representative quantified
RU/EN acceptance remains pending. Initial isolated-word Piper → base round trip
misrecognized both commands; do not present this plumbing check as accuracy.

## Where to resume

Software MVP is complete. Pick follow-up #23 or #24 with the owner; the historical
physical/benchmark notes below are not blockers for the accepted software scope.

The fixed command delay is now replaced by shared Controller `MutationPacer`:
wait only for the remaining 2.1-second interval before fresh preflight, with a
conservative initial interval on each new connection and an interruptible live
wait. Reads/no-ops do not reset it; failed mutation attempts do. Do not remove the
stock integer-second gate or reintroduce per-operation sleeps. WS cleanup and LAN
listener shutdown regressions are fixed; current validation is in the status doc.
Orange Pi STT diagnosis is explicitly deferred by the owner: native small exceeded
the benchmark's 120-second request timeout; this does not establish a deadlock,
Docker overhead or a model-quality result.

Orange Pi: the owner confirmed `/proc/self/io` is absent on the current Armbian
kernel, matching the trigger in their Typesense issue #2998. The opt-in
`[typesense].io_accounting_compat` wrapper and diagnostics are documented in
`../../docs/ASSISTANT_TYPESENSE.md`. The owner subsequently confirmed working
search on the board; one voice trace took 13.47 seconds and ended uncertain during
queue verification despite matching artist playback. See current status for
timings and next diagnostic work. Do not infer quantified MVP acceptance or
Docker performance overhead; fallback process I/O metrics are zeros.

Queue guard failures now carry `confirmation.queue` with the actual failing read
and failed fields; see `../../docs/ASSISTANT_QUEUE_DIAGNOSTICS.md`. This is evidence
only, without relaxed guards or retry. Keep initial `last_observed` separate from
the subsequent queue read when diagnosing uncertain playback.

`run.sh speech-benchmark` now compares frozen WAVs in sequential disposable Whisper
servers (beam5/greedy, thread counts, optional existing models). No device or search
access; private output contains reusable samples, hashes and labelled-only scores.
See `../../docs/ASSISTANT_SPEECH_BENCHMARK.md`. The benchmark leaves production decoder/journal
behavior unchanged; command pacing is the separate follow-up above. Initial
352-test and native Docker plumbing checks passed; the owner's base-model latency
pilot is recorded in current status, with transcript quality still unreviewed. The historical Controller WebSocket
cleanup timeout is now fixed; all 28 bridge tests pass (see current status).

The benchmark also accepts `--server http://127.0.0.1:PORT/inference` to use an
existing native server without any Docker/process lifecycle calls. In that mode
one reference model is allowed, `--threads` is rejected and `--server-threads` is
only operator-declared metadata; weights/build/threads are not server-attested.
Restart the external server explicitly between thread/model comparisons.

Start with `../../docs/ASSISTANT_STATUS.md`: current review follow-up and evidence.
The owner authorized five sequential increments, each committed and pushed.

- `../../docs/ASSISTANT_BASELINE.md`: private bound case set (30 RU / 21 EN),
  `baselines/my-player-text-v2/` beneath configured data_dir. Media/gold are frozen;
  physical RU-01–19 are recorded; continue at RU-21 (RU-20 locale switch is last).
  RU-17 rejection gold is disputed because its text could be a recording title;
  retain the original attempt and separate review, not a confirmed defect count.
  Private run context is authoritative. Do not publish personal packet contents.
  CSV observation header is in `evaluation/acceptance/`.
- `../../docs/ASSISTANT_EMULATOR_ACCEPTANCE.md`: owner-proposed next validation
  direction, a disposable full Assistant/Typesense/stock-firmware scenario runner.
  Implemented via `bash ci/assistant.sh OTA_DIR NEW_REPORT_DIR [--case ID]`.
  The current manifest v7 has 64 cases (v4 had 46); the 2026-09-19 pacing
  follow-up passed all 64 in one disposable run (see current status). The initial 36-case run exposed shared-artist retrieval
  and late previous/restart behavior. The 42-case follow-up passed all artist cases;
  Assistant previous now selects the explicit predecessor through Controller.
  First row is a no-op in every mode; random mode means displayed queue order.
  Native Controller previous retains its firmware restart semantics.
  Final focused run: 10/10 (early/late, paused, first row, fuzzy member; RU/EN).
  Shared checks 349 Python / 37 JS; prototype 287. Candidate 6798da0 now passed the full 46/46 manifest-v4 rerun;
  keep the earlier 40/42 and final 10/10 reports separate. Keep this cohort separate from physical
  results; failures must remain visible.
- `library/README.md`: semicolon-separated artist members are a derived projection;
  source artist tags remain exact device selectors. Schema 4 requires `/index`,
  not `/sync`; ranking is lexical-v5 (known artist filtered before top-50). No aggregate person-level queue is implemented.
- `../../docs/ASSISTANT.md`: implementation roadmap and historical increments.
- `../../docs/ASSISTANT_ARCHITECTURE.md`: interpreter/STT/TTS contracts, one saved locale.
- `../../docs/ASSISTANT_INTERPRETATION_SOURCES.md`: independent evidence and shadow boundary.
- `../../docs/ASSISTANT_SHADOW_REPORTS.md`: offline reports, review queue and measured limitations.
- `../../docs/ASSISTANT_NLU_DATA.md`: annotations, frozen corpora and supervised studies.
- `../../docs/ASSISTANT_COMMANDS.md`, `README.md`: current user commands/setup.
- `../../docs/ASSISTANT_LOCALES.md`: community locale/template extension.
- `../../docs/DISC_CAPABILITIES.md`: Controller contract; protocol details stay there.

Current implementation includes persistent sessions/reconnect without mutation replay,
CLI/console and separate web text/microphone input, library snapshots/Typesense, ranking, continuation through native queues,
play/pause/resume/stop/next/previous, localized responses, journal/timing/debug,
file STT (CLI or opt-in resident server with bounded catalog hints) and synthetic speech checks, offline command snapshots and diagnostic models.
The owner has reported live-player playback/controls working. This is not yet a
representative, quantified end-to-end baseline or agreed MVP acceptance.

Independent sources are `literal`, `slots`, `command_model` and opt-in
`structured_model` (loopback service; excluded from diagnostic priority). `/shadow on`
records comparisons; **primary rules retain execution**. `/explain` never searches
or executes. The shared bounded single-action guard also runs with shadow off.
Slot/context improvements beyond that guard remain diagnostic. Score weighting,
learned arbitration and live classifier promotion are not implemented.

`shadow-report` consumes only an explicit history export. It produces private
report/evidence/pending files; reviewed annotations are optional. It never opens
runtime storage, reruns providers, connects to a player, trains or selects a model.
Disagreement is not error. Provider unavailability is not a semantic vote. Reports
separate locale, text/speech, STT fingerprint and source revision. Gold metrics
require explicit reviewed labels; never treat command outcomes or predictions as gold.

The owner-supplied RU synonyms are now live dictionary entries (review stage 2).
Original physical attempts remain frozen. The
requested default-track policy remains a separate decision; current `auto` semantics
remain. Explicit albums now have their own typed intent and native whole/scoped
queues. Physical album-command acceptance is not claimed.

## Ownership and data rules

- `assistant/`: application orchestration, intents, preferences, journal, providers.
- `library/`: device catalog snapshots, retrieval/index projection, ranking support.
- `assistant/nlu/evaluation/`: offline evaluation/training/report tools; optional ML dependencies
  stay outside ordinary Assistant requirements. Runtime portable text scoring needs
  neither Torch nor an embedding encoder.
- Controller is independent of research/emulator/viewer. Use its high-level methods;
  do not duplicate raw frame logic in an application or widen Controller dependencies.
- Keep one selected input/response locale, persisted through existing preferences.
  Language text/templates belong in locale TOML, not locale-specific Python branches.
- Intent and extracted arguments are separate measures. A classifier's play/language
  label without arguments is incomplete, never permission to guess a target.
- Personal histories, audio, annotations, reports and model/cache artifacts stay outside
  Git. Exclusive private export files must not overwrite existing files. Use synthetic
  fixtures in tests. Raw SDK bodies, device paths and credentials are not report fields.
- Keep examined examples in regression. `commands-v2` has 609 rows, manifest name
  `commands-v2.1`; its former test set is now examined regression for new designs.
  `slot_acceptance.json` is implementation acceptance, not an independent holdout.
  Do not silently edit frozen corpora or train/calibrate on test failures.
- Historical study runners and `explain.decide` preserve earlier measurements. New
  source comparison uses a distinct diagnostic policy. Do not rewrite history to
  make new results look independently validated.
- Inspect `git status` and preserve unrelated work. In the 2026-09-18 handoff,
  `docs/firmware/echo-retro-nano.md` is an unrelated untracked owner draft.

## Validation and completion

Use the explicit prototype launcher, not the emulator root `run.sh`:

```sh
./experiments/disc_assistant/run.sh test
./experiments/disc_assistant/run.sh shadow-report --history /tmp/disc-history.jsonl \
  --output /tmp/disc-shadow-report
```

Focused tests use the prototype venv and explicit module imports from repository root.
The firmware-free suite includes synthetic loopback servers and may need sandbox
network permission. No device, Docker or ML download is needed for reporting tests.
Use a physical player only for a deliberate end-to-end acceptance run, not offline
reporting or grammar work. Never replay uncertain mutations to improve a metric.

For each completed increment update the relevant English docs, current roadmap
status and MVP issue checklist. Distinguish implemented, tested with fixtures,
observed on device and accepted against thresholds. The owner explicitly requests a commit and push after each of the five review
increments. Do not include unrelated work or infer permission to release.
