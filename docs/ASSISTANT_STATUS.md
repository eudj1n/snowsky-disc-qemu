# Assistant current checkpoint

This is the short continuation index. [The roadmap](ASSISTANT.md) preserves
historical decisions; [MVP acceptance](ASSISTANT_MVP.md) defines completion.
Conversation and local experiments do not replace device evidence.

## Russian voice and previous-track alias, 2026-09-19

The managed RU voice is now **Piper Irina medium**, at the owner's request; EN Alba
is unchanged. Model/config/card checksums stay pinned to the same voice repository
revision. `setup --all` preserves an installed Whisper model unless explicitly
replaced with `--whisper-model`; missing known base/small variants retain their
variant, and missing custom models fail explicitly. A voice-map hash makes Compose
recreate the resident Piper worker when voices change. Update with web stopped:
`setup --all`, then `web --bootstrap`. Previous model assets remain on disk.

Russian `прошлый` / `прошлый трек` now mean the existing guarded previous-track
operation. Negations, compound input and music titles retain their boundaries.
Irina's model card reports an unknown dataset license; product redistribution
clarification remains open, as documented in the TTS guide.

**339 prototype tests pass**. Real Irina synthesis returned nonsilent 22,050 Hz
PCM (saved STT sample converted to 16 kHz) with the expected voice/config hashes.
The isolated install retained its previous Whisper path. No physical-player
command or subjective pronunciation-quality acceptance is claimed by this check.

## Observed Russian STT spelling, 2026-09-19

The owner reports the microphone flow generally works, with better perceived
English recognition; several Russian next commands were transcribed as
`следующий трак` and rejected. This is qualitative feedback, not a measured RU/EN
accuracy comparison. The complete phrase is now a Russian `next` dictionary alias.
No global spelling correction, STT tuning or fuzzy control matching was added.
Raw transcript/command text remain in history; quoted music titles, negation,
compound requests and the selected-locale boundary keep their existing behavior.
**335 prototype tests pass**, including single dispatch and transcript retention.
This is an examined regression case, not new independent acceptance evidence.

## Resident speech and Piper delivery, 2026-09-18

[Common setup and Piper replies](ASSISTANT_TTS.md) are implemented: `setup --all`
installs runtime requirements, pinned Whisper/Piper models and Docker services;
`web --bootstrap` starts them. Web always selects Whisper Server. RU/EN reply
synthesis honors the saved speech policy and explicit browser sound opt-in;
failures and browser-reported delivery are separate journal events, never command
retries. TTS text preparation is an identity hook; automatic transliteration is
deferred pending listening comparison.

Clean installer/service health and real RU/EN Piper WAV output were verified.
Web confirmed Pause against a synthetic peer and then returned Piper audio with
one device write. Two isolated-word Piper → Whisper base checks both misrecognized
the command; retain this limitation rather than treating plumbing as accuracy.
Final verification: **330 prototype tests** plus both JavaScript capture/reply
checks passed. Browser Resume against the synthetic peer reached `Reply played`;
this is browser completion evidence, not a subjective audio-quality assessment.
See the speech guide for evidence boundaries and dependency/model notices.

### Installer certificate follow-up

An owner workstation reported `CERTIFICATE_VERIFY_FAILED` downloading Whisper.
The downloader now explicitly loads pinned certifi roots alongside Python default
trust, with an optional administrator-provided `DISC_ASSISTANT_CA_BUNDLE`. TLS and
hostname verification remain required. **22 focused installer/launcher tests** pass,
including an empty initial trust store, custom/invalid CA bundles and no insecure
retry. Real pinned model-card download and a ranged Whisper model download also
passed with an initially empty CA store, including HTTPS redirects. The previous
330-test full-run checkpoint above remains unchanged.

## Browser input, 2026-09-18

[Disc Assistant Web](ASSISTANT_WEB.md) now provides a separate loopback interface
in the viewer's visual style: text, bounded microphone capture, preview/execute,
locale selection, live observation, response JSON and traces. CLI and web share
`Application`; no viewer or emulator runtime dependency was added. Browser UI and
synthetic HTTP/device checks are verified. The owner also reports microphone
commands successfully played and stopped music on the physical player; quantified
RU/EN acceptance remains pending. **317 prototype tests** and JavaScript capture/encoding checks pass.
Start with `run.sh web --bootstrap` (close the CLI console first).

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
5. **Complete:** optional structured-model source, strict schema/typed arguments,
   original-text spans, bounded loopback transport and prompt/model fingerprints.
   Real Qwen 0.5B comparison: 5/16 RU and 7/16 EN exact positives; 5/9 and 6/9
   undisputed negative activations. It remains shadow-only, excluded from priority.
   **308 prototype tests** passed; real CLI `explain` confirmed no mutation.
   Final shared verification: **353 Python / 37 JavaScript tests passed**.

## Evidence boundaries

- The complete emulator cohort is generated-media regression, not independent
  physical acceptance. Keep unsuccessful earlier runs and source provenance.
- Physical `my-player-text-v2`: 19 RU observations remain frozen. Resume at RU-21;
  RU-20 is the final locale switch. One rejection-only expectation is disputed
  because the text could be a recording title. No numeric MVP limits are agreed.
- No learned execution, dialogue, compound planning, quantified human microphone acceptance, wake-word,
  Raspberry Pi performance or physical audio quality is implied by these increments.
- Personal data, reports, audio, models and firmware-derived images stay outside Git.

See [emulator acceptance](ASSISTANT_EMULATOR_ACCEPTANCE.md),
[physical baseline](ASSISTANT_BASELINE.md), [voice](ASSISTANT_VOICE.md),
[interpretation sources](ASSISTANT_INTERPRETATION_SOURCES.md) and
[issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21).
