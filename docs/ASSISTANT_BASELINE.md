# Physical-player baseline: preparation and operator worksheet

**Deferred follow-up as of 2026-09-19:** this partial physical baseline is
preserved in [issue #23](https://github.com/eudj1n/snowsky-disc-qemu/issues/23).
It is not a blocker for the [accepted software MVP](ASSISTANT_MVP_ACCEPTANCE.md).
The preparation notes and original candidate gaps below are historical; synonyms,
album intents and explicit predecessor navigation have since been implemented.
Do not rewrite the frozen private packet or append a changed candidate as if it
were the original run.

Prepared **2026-09-18**. The owner confirmed physical `my-player`, text RU/EN
first, supplied six artist/title targets and natural Russian command variants,
and authorized binding from the synchronized library. The concrete private packet
is now frozen: **30 RU / 21 EN cases**, with complete expected typed intentions
and device-outcome predicates. **The physical run is in progress.** The initial generic
matrix below remains a template; use the bound private packet for this run.
This supports [MVP issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21)
and the [baseline-first acceptance policy](ASSISTANT_MVP.md).

Current checkpoint: RU cases 01–19 have evidence recorded privately. Fourteen
meet their functional expectations; two requests were missed, one confirmation
was uncertain, and one previous-track request retained the current recording.
The remaining case has disputed rejection-only gold: the owner correctly noted
that its apparent nonmusic target could be a song title. Preserve the original
attempt and review annotation; do not report it as an established Assistant defect.
RU extensions, the final RU locale switch and the EN block remain pending.
Raw interpretation/journal auditing and threshold agreement are also pending.
The next operator case is RU-21; RU-20 changes locale and remains last in its block.

The owner proposed [emulator scenario automation](ASSISTANT_EMULATOR_ACCEPTANCE.md)
to reduce manual work. The opt-in end-to-end Assistant runner is now implemented.
Emulator observations are a separate cohort, not replacement
evidence for this frozen physical baseline.

## Owner input needed

- Confirmed: physical `my-player`, text-first RU/EN scope.
- Completed: six owner-supplied artist/title pairs were bound from the local
  read-only SQLite snapshot; all were found. No live connection was opened.
- Two targets have two catalog editions. Unqualified requests accept either
  listed edition for this run, without claiming audio/byte equivalence. One target
  has compound artist metadata; the requested name and actual metadata stay distinct.
- Completed: owner phrasing is retained in a separate cohort. English variants
  are authored translations/cases, not independently supplied English utterances.
- During the live run, observe the player/sound and record the actual outcome.
  API success alone cannot establish the physical result. No firmware flashing,
  microphone purchase or hardware modification is required.

## Bound private packet checkpoint

The active packet is `baselines/my-player-text-v2/` beneath the configured Assistant
`storage.data_dir`, outside Git. It contains `manifest.json`, `SHA256SUMS`, `RUN.md`,
`run-context.json` and prefilled `observations.csv`. The 51 case IDs, commands,
expected current typed contract and recording bindings have been checked without
calling an interpreter or sending commands. Manifest SHA-256:
`c42101b5103750ce57a801a5ae024b60d02c361366a3b6d7fafc7210599b03d4`.
Version 1 was preparation only; use version 2 with complete typed expectations.

The snapshot has 792 tracks and was observed on 2026-09-17. Its head/index generation
and signature match the current configuration locally; this does not prove the
physical catalog or firmware is still unchanged. Fill the separate run context
after live preflight. Run shadow off for this baseline; enabling shadow defines a
separate latency condition. Locale-switch cases remain last in each locale block.
Do not modify the frozen manifest when filling observations or run context.

Owner proposals beyond currently implemented behavior are explicit gaps:

- Add play verbs `играй` / `запусти`, stop synonym `хватит`, previous `назад`, next
  `вперед`. Desired positive results are recorded; no dictionary tuning preceded
  this baseline. Both existing and unfamiliar formulations remain in the run.
- Make an omitted music qualifier mean track. The current typed contract uses
  `auto`; this baseline preserves that representation while recording whether the
  requested track actually resolves. The policy change is not silently installed.
- Add `альбом` as an explicit play target. The current Assistant intent contract
  has no album kind. This is a capability gap, **not a negative gold example** or
  a silently supported command. It is excluded from this executable cohort and
  must remain visible in coverage; adding it needs a separate implementation.

Expansion after this baseline must be tested as a new candidate against retained
regression and fresh acceptance data. Complex/multi-action commands remain outside
MVP scope; playing an album would still be a single action.

## Freeze before execution

Create a private run directory outside Git. Resolve every placeholder below and
save the concrete manifest with complete expected intentions/device outcomes.
Do not freeze unresolved names or derive expected results from `/rank` predictions.
Read-only library checks establish that recordings exist; the owner establishes
which recordings/editions are acceptable. Reject an ambiguous binding before running.

Bind `A1`, `A2` to two artists and `T1`, `T2`, `T3` to three recordings with
artist/title/album. `T3` must have a unique title in this snapshot. Bind `MISSING`
to a deliberately absent title, verified absent before testing. Bind `NATURAL_PLAY`
per locale to an owner-authored request for T1. Existing familiar phrases are
regression; new owner phrasing is still not representative independent acceptance
on its own. Every case must contain one requested action.

Record Git commit/dirty state, player model and firmware version, device key,
locale, library/index generation/signature, expected targets, current play mode,
continuous-context setting, aliases and response settings. Do not copy API keys,
`.env`, credentials or unrestricted configuration dumps. Record shadow enabled/
disabled and model snapshot identities if enabled; keep them fixed for the run.
Shadow changes latency, so its timing is not the default shadow-off baseline.
Freeze the manifest bytes/hash before commands are submitted. Thresholds remain
unset until the owner reviews the measured baseline.

## Setup and execution

Use the existing interactive console so one connection owns the player. Disconnect
FiiO Control/other controllers first. Perform any required sync/index **before**
freezing the library snapshot, and wait for scanning to finish. Then capture:

```text
/device
/status
/queue
/language ru
```

Keep the device accessible and use a comfortable listening volume. For deterministic
next/previous cases, select sequential playback in the device UI before the run,
record it, and use a queue with at least three distinct recordings. Do not infer
random-mode next/previous positions from arithmetic. If a prerequisite cannot be
established, mark the case blocked; do not reinterpret its expectation afterwards.

Run one case at a time, with no competing control input. For no-change/negative
cases use a recording well away from natural EOF so normal queue progression
cannot be confused with a requested transition. Establish each listed
precondition, let state settle, then submit its exact command **once**. Setup and
`/status`/`/queue` commands are not scored samples; retain their request IDs when
useful. Do not paste an entire block into the console because later cases may
otherwise run from the wrong state.

After the result, note the command's request ID and check the actual track/state
on the device and through `/status`. For an uncertain reply, observe first, without
repeating the command. Record response status and device outcome separately. Keep
the original attempt even if a later explicit recovery/retry is performed; retries
are separate records and never replace a failure in the denominator.

## Proposed text cases (20 per locale)

This matrix is a draft specification; curly-braced references must be substituted
with the frozen catalog values and reviewed before the first run. Expected `play`
intentions retain the literal query and the requested auto/artist/track distinction;
catalog resolution to a particular recording is a later, separately scored stage.
Controls carry their matching action; language carries the requested target locale.
Negated/non-music/compound inputs are expected to reject without an executable intent.

| ID | Russian command | English command | Precondition and expected physical/local outcome |
| --- | --- | --- | --- |
| 01 | Включи исполнителя {A1} | Play artist {A1} | A different artist is playing; play a recording by A1 in its native queue |
| 02 | Включи исполнителя {A2} | Play artist {A2} | A different artist is playing; play a recording by A2 |
| 03 | Включи {T1.artist} — {T1.title} | Play {T1.artist} — {T1.title} | Another recording is playing; play an accepted T1 edition |
| 04 | Включи {T2.artist} — {T2.title} | Play {T2.artist} — {T2.title} | Another recording is playing; play an accepted T2 edition |
| 05 | Включи трек {T3.title} | Play track {T3.title} | Another recording is playing; play uniquely identified T3 |
| 06 | Включи {T1.artist} {T1.title} | Play {T1.artist} {T1.title} | Another recording is playing; resolve and play T1 from an auto query |
| 07 | {NATURAL_PLAY.ru} | {NATURAL_PLAY.en} | Another recording is playing; owner-intended T1 plays; unsupported wording counts as missed intent, not edited gold |
| 08 | Пауза | Pause | Playing well away from natural EOF; same recording becomes paused |
| 09 | Пауза | Pause | Already paused; remains paused with no unnecessary mutation |
| 10 | Продолжи | Resume | Paused; same recording resumes from retained position |
| 11 | Продолжи | Resume | Already playing; remains playing, no restart or unnecessary mutation |
| 12 | Следующий трек | Next track | Sequential queue, nonfinal item; play the reviewed next recording from the fresh queue |
| 13 | Предыдущий трек | Previous track | Sequential queue, nonfirst item; play the reviewed previous recording; establish precondition separately |
| 14 | Стоп | Stop | Playing; pause, preserving position and queue (current documented stop semantics) |
| 15 | Стоп | Stop | Already paused after stop; remain paused, no restart or unnecessary mutation |
| 16 | Включи трек {MISSING} | Play track {MISSING} | Playing; legitimate not-found response, no replacement/stop/queue change |
| 17 | Включи свет в комнате | Play the room lights | Playing; reject non-music target, no mutation (an interpreter failure may still leave the device unchanged) |
| 18 | Не ставь музыку на паузу | Do not pause the music | Playing; reject negated request and keep playing |
| 19 | Включи {T1.artist} и затем останови музыку | Play {T1.artist} and then stop music | Playing; reject the compound request before any partial execution |
| 20 | Переключи язык на английский | Switch language to Russian | Last case of locale block; change/persist Assistant locale, no player mutation |

Run RU/EN as separate blocks with explicit `/language ru` or `/language en` before
each. Case 20 intentionally changes the locale; do not let it silently affect later
cases. Preserve the original preferred language for restoration after observation.
The matrix is not a statistically sufficient error-bound estimate. It is a first
structured baseline including known commands and targeted failure classes.
Reported speech, unsupported controls, disconnected/stale-index behavior and
file-speech cases need separate reviewed extensions before broad MVP acceptance.
Do not tune rules or aliases between cases; any change defines a new candidate/run.

## Operator observations

Use the CSV header in
[`evaluation/acceptance/observations.template.csv`](../experiments/disc_assistant/evaluation/acceptance/observations.template.csv).
Copy it outside Git. One row is one submitted attempt; case IDs are locale-qualified,
for example `ru-03`. Record unsubmitted blocked cases too, with no request ID.

- `response_status`: exact Assistant status, such as playing/confirmed/uncertain/error.
- `mutation_attempted`: reported value or unknown, not inferred from silence.
- `physical_outcome`: correct / incorrect / unchanged / uncertain / not_observed.
- `interpretation_outcome`: correct / wrong_action / wrong_arguments / rejected /
  unavailable / not_reviewed, from explicit expectation versus retained parsed evidence.
- `case_outcome`: success / wrong_action_or_selection / false_activation /
  missed_command / technical_failure / uncertain / blocked. Only reviewed agreement
  of required interpretation and device/local behavior qualifies as success.
  For negative cases, unchanged device state does not make a wrongly accepted
  intention correct. Distinguish false interpretation from actual unwanted mutation
  in the separate columns rather than relabeling all acceptance as physical action.
- `actual_track`/`notes`: observed title/artist/edition or ambiguity; retain position,
  queue and timestamps in referenced evidence where needed. Timing comes from the
  command result/journal; human observation delay is not system response latency.

After the block capture `/status`, `/queue`, and export once to a new private path:

```text
/history export /tmp/disc-baseline-history.jsonl
```

Do not clear history or publish personal exports in the issue. Keep the manifest,
worksheet and export together. A correct physical result with an uncertain API
confirmation remains explicitly uncertain in confirmation metrics; never hide that
case or assume the timeout means the command did nothing.

## Analysis and next step

Report planned/submitted/blocked counts first, then per-locale success, missed
commands, wrong actions/arguments, unintended physical mutations, technical failures
and uncertainty with explicit denominators. Do not combine text and speech into one
headline percentage. Review end-to-end latency separately from shadow-source timing.
Freeze thresholds only after reviewing this baseline with the owner. If behavior is
subsequently tuned against these examples, retain them as regression and prepare a
fresh acceptance set. No run or MVP acceptance is claimed by this preparation.
