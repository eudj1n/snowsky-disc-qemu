# Disc Assistant MVP boundary and acceptance

Owner decision, **2026-09-18**: the MVP is a working end-to-end process from a
received command through interpretation to execution on the physical DISC, with
an agreed acceptable error level. **Measure the baseline first; agree numeric
thresholds afterwards.** Implemented features and accepted product quality are
separate checkpoints.

The [MVP tracking issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21)
carries the implementation/acceptance checklist. Local session handoff is
[`research/disc_assistant/AGENTS.md`](../research/disc_assistant/AGENTS.md).

## Included path

- Text in the CLI/console, or an audio file through the existing STT adapter.
- One selected locale used for input and response, persisted between sessions.
- One supported action with validated arguments: music selection, playback control
  or a local language-setting command. No compound-command planner or dialogue.
- Library retrieval/ranking where required, then high-level Controller execution
  with fresh selection checks and observed outcome. Local language changes do not
  require a device mutation.
- Persistent device session, bounded reconnect behavior and no uncertain mutation replay.
- Text response, correlation/timing and local decision evidence for diagnosis.

Most of this path is implemented and the owner has reported successful physical
playback/controls. File speech tests and source comparisons also exist. A frozen,
representative physical-device baseline and numerical acceptance have **not** been
completed. Shadow-report accuracy concerns interpretation, not device success.

The [first physical-player baseline](ASSISTANT_BASELINE.md) now has a private
frozen 51-case text packet bound to the synchronized catalog and owner phrasing.
Live preflight, execution and acceptance remain pending; audio/failure-scenario
coverage still needs a later extension.

## Baseline and acceptance checklist

1. Freeze an explicit single-action command set, expected complete intentions and
   expected device outcomes, covering RU/EN separately and text/file speech separately.
   Include ordinary successes, absent music, non-commands, unsupported/compound input
   and failure scenarios. Record the device/library/locale/STT versions and fixture
   assumptions. Reviewed shadow disagreements help find cases, but are a biased
   sample; include ordinary agreements and independently collected user phrasing.
2. Measure the current executing path on the real player with this set. Separate
   correct confirmed outcomes, incorrect actions/selections, legitimate no-action
   results, unintended mutations on negatives, technical failures and uncertain
   observations. Preserve denominators and latency distributions by input/locale.
   Do not count a timeout as proof that nothing played; use observation/evidence.
3. Review the baseline with the owner and agree explicit thresholds for successful
   outcomes and unintended device actions separately. Include minimum coverage and
   the policy for uncertainty/technical failures; never improve a rate by dropping them.
4. Freeze an acceptance set and run the agreed candidate against those thresholds.
   If the baseline informed tuning, it is regression, not fresh acceptance evidence.
   Record any device state changes and do not automatically replay uncertain commands.
5. Close the MVP only after this end-to-end gate passes and instructions are reproducible.

Numbers are deliberately pending the baseline, per owner decision. Unit tests,
synthetic STT, source agreement and offline exact-intent scores are supporting
checks; none substitutes for the device-outcome gate.

## Follow-up work outside MVP

After this boundary is accepted, open separate tasks to improve or replace stages:
real microphone/VAD/wake word, spoken response playback and portable TTS, learned
source arbitration/calibration, encoder fine-tuning, music semantic retrieval,
recommendations/history enrichment, online providers, dialogue/compound commands,
Raspberry Pi resource acceptance and physical dock/audio hardware. These tasks
must preserve the typed contracts and be compared against the established baseline.
A production package/repository move is a separate decision, not an automatic part
of every experiment or a prerequisite for the current research MVP.
