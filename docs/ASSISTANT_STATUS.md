# Assistant current checkpoint

This is the short continuation index. [The roadmap](ASSISTANT.md) preserves
historical decisions; [MVP acceptance](ASSISTANT_MVP.md) defines completion.
Conversation and local experiments do not replace device evidence.

## Review follow-up, 2026-09-18

The owner authorized these five increments in order, with a separate commit and
push after each. External review is input for comparison, not a specification.

1. **Complete:** frozen `6798da09b692f047449fcc068a4c79db3e73f432`
   passed **46/46** manifest-v4 emulator cases (23 RU / 23 EN),
   fresh API/queue checks and mutation instrumentation. Local evidence:
   `/tmp/disc-review-stage1-46`. One paused-predecessor screenshot was manually
   inspected; the other screenshots remain unreviewed.
2. **Complete:** literal-v3/shared guard, compound credits, quoted references
   and requested RU synonyms. **291 prototype tests passed**. New emulator cases:
   **7/8 initially**, then **1/1** after correcting the new duplicate-edition gold
   to the existing alphabetical tie policy. Original report is preserved.
   Manifest v6 has 54 cases; no full-54 run is claimed.
3. **Complete:** typed album intent, snapshot ranking and guarded complete/scoped
   native album playback. **10/10 focused emulator cases**, **296 prototype tests**,
   **350 shared Python / 37 JS tests** passed; 12 focused tests additionally cover
   the new session helper and oracle (including two new session tests and one new
   oracle test). Manifest v7 has 64 cases; no full-64 result is claimed.
4. **Complete:** known-artist prefilter promoted after synthetic comparison
   (3/5 to 4/5). Schema 4 requires `/index`; split/join remains off. Optional
   resident STT and catalog hints implemented. Matched base decoder comparison:
   CLI 318 ms / resident 226 ms median; hints improve exact intentions 12/24 to
   18/24 on 12 repeated synthetic samples. **301 tests and 6/6 emulator cases**
   passed. See [comparison details](ASSISTANT_REVIEW_EVALUATION.md).
5. **Pending:** structured local-model evidence as an optional shadow source,
   validated typed arguments and comparative reports; primary rules retain execution.

## Evidence boundaries

- The complete emulator cohort is generated-media regression, not independent
  physical acceptance. Keep unsuccessful earlier runs and source provenance.
- Physical `my-player-text-v2`: 19 RU observations remain frozen. Resume at RU-21;
  RU-20 is the final locale switch. One rejection-only expectation is disputed
  because the text could be a recording title. No numeric MVP limits are agreed.
- No learned execution, dialogue, compound planning, microphone/wake-word,
  Raspberry Pi performance or physical audio quality is implied by these increments.
- Personal data, reports, audio, models and firmware-derived images stay outside Git.

See [emulator acceptance](ASSISTANT_EMULATOR_ACCEPTANCE.md),
[physical baseline](ASSISTANT_BASELINE.md), [voice](ASSISTANT_VOICE.md),
[interpretation sources](ASSISTANT_INTERPRETATION_SOURCES.md) and
[issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21).
