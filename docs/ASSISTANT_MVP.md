# Disc Assistant software MVP: accepted scope

**Accepted on 2026-09-19.** The owner explicitly changed the completion boundary
from physical-device acceptance to the software path running against the stock
DISC emulator, and confirmed that the existing reproducible scenarios are
sufficient. No additional audio cohort or repeat of the completed run is a closure
requirement. [MVP issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21)
tracks this completed scope; the [acceptance report](ASSISTANT_MVP_ACCEPTANCE.md)
records evidence and limits.

## Completion criterion and result

Receive one command, interpret it, resolve music when needed, execute through the
Controller on stock V2.57, and verify the actual device/queue outcome independently
of the Assistant's selected candidate. One action and one selected locale per
request; uncertainty never permits automatic mutation replay.

The agreed emulator regression scope is manifest v7: **64/64 cases passed**
(35 RU / 29 EN), with all declared checks satisfied. All **19 no-mutation cases**
had **zero observed mutation writes**. These are finite-cohort acceptance results,
not a statistical upper bound on errors for arbitrary speech or devices.

The prototype includes CLI, persistent console, web text/microphone input,
Whisper adapters, Piper replies, library snapshots/search/ranking, controls and
native queues, locale dictionaries, history and diagnostic traces. The 64-case
end-to-end cohort uses **text input**. Existing speech/web/TTS checks and owner
observations are supporting evidence, not a claim that all 64 cases used audio or
that human speech accuracy has been accepted.

## Deferred acceptance and improvements

- [Physical-device acceptance #23](https://github.com/eudj1n/snowsky-disc-qemu/issues/23):
  preserve the original partial physical baseline and collect a separate current
  candidate cohort, diagnose physical queue uncertainty, then agree physical
  success/error thresholds after measurement.
- [Speech quality and platform performance #24](https://github.com/eudj1n/snowsky-disc-qemu/issues/24): representative human RU/EN input,
  native/Docker and Orange Pi comparisons, TTS pronunciation and remaining latency
  work are separate from software MVP closure. See the linked follow-up in the
  [acceptance report](ASSISTANT_MVP_ACCEPTANCE.md).
- Learned source arbitration, semantic retrieval, fine-tuning, recommendations,
  wake word/VAD, dialogue/compound planning and dock hardware remain later roadmap
  work. Promotion from research or a repository split is a separate decision.

## Original physical baseline is preserved

The 2026-09-18 definition required physical DISC acceptance, with a baseline before
numerical threshold agreement. That physical work is **deferred, not passed**.
The private `my-player-text-v2` packet contains 51 planned text cases and 19 recorded
RU observations, including misses, an uncertain confirmation, a wrong previous
result and one disputed expectation. Do not rewrite or combine those records with
new software results. The [physical worksheet](ASSISTANT_BASELINE.md) remains the
historical evidence and future resumption guide.

Keep personal exports/audio/library data and firmware-derived captures outside
Git. The curated [software acceptance summary](../experiments/disc_assistant/evaluation/acceptance/reports/2026-09-19-emulator-mvp.json)
contains only generated-fixture case IDs, outcomes, timings and provenance hashes.
