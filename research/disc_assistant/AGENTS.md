# Disc Assistant research: session handoff

Read the repository-root `AGENTS.md` first. This file applies to
`research/disc_assistant/`; it supplements, not replaces, repository conventions.
Conversation may be Russian; **tracked documentation and comments are English**.

## Product boundary agreed on 2026-09-18

The MVP is the implemented end-to-end path **command input → interpretation →
execution on DISC**, meeting explicitly accepted error limits. Text and existing
file-based speech input are supported entry points. One action per request; no
compound planning, conditional/delayed actions, confirmation dialogue or choice UI.
A missing recording is a legitimate result, not an invitation to invent a match.

The owner chose **measure the current baseline first, then agree numeric thresholds**.
Do not invent an allowed error percentage or call the MVP accepted from unit tests,
synthetic speech or interpreter-only accuracy. Count correct device outcomes and
unintended actions separately; expose failures, abstentions and uncertain outcomes.
See `../../docs/ASSISTANT_MVP.md` and
[MVP issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21).

Improvements/replacements of individual stages are follow-up tasks, not an endless
expansion of this MVP: microphone/wake word, live TTS, learned selection, semantic
retrieval, fine-tuning, recommendations, dialogues and Raspberry Pi/hardware acceptance.
Keep this prototype under research until a separate promotion/split decision.

## Where to resume

Start with `../../docs/ASSISTANT_STATUS.md`: current review follow-up and evidence.
The owner authorized five sequential increments, each committed and pushed.

- `../../docs/ASSISTANT_BASELINE.md`: private bound case set (30 RU / 21 EN),
  `baselines/my-player-text-v2/` beneath configured data_dir. Media/gold are frozen;
  physical RU-01–19 are recorded; continue at RU-21 (RU-20 locale switch is last).
  RU-17 rejection gold is disputed because its text could be a recording title;
  retain the original attempt and separate review, not a confirmed defect count.
  Private run context is authoritative. Do not publish personal packet contents.
  CSV observation header is in `experiments/acceptance/`.
- `../../docs/ASSISTANT_EMULATOR_ACCEPTANCE.md`: owner-proposed next validation
  direction, a disposable full Assistant/Typesense/stock-firmware scenario runner.
  Implemented via `bash ci/assistant.sh OTA_DIR NEW_REPORT_DIR [--case ID]`.
  Manifest v4 has 46 cases. The initial 36-case run exposed shared-artist retrieval
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
CLI/console, library snapshots/Typesense, ranking, continuation through native queues,
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
- `experiments/nlu/`: offline evaluation/training/report tools; optional ML dependencies
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
./research/disc_assistant/run.sh test
./research/disc_assistant/run.sh shadow-report --history /tmp/disc-history.jsonl \
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
