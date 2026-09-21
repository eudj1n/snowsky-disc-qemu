# GigaAM native pilot, 2026-09-19

Preserved from commit `40a9bb7` on `codex/gigaam-stt`; these are historical
measurements, not a new run after adapter migration. See the
[current adapter guide](../guides/voice-adapters.md).

Host: **Apple M2 Max, 32 GiB RAM**, native CPU with four threads per engine.
GigaAM `v3_ctc` / Torch 2.8.0 was compared with whisper.cpp 1.9.4 / multilingual
`ggml-base.bin`, CPU/BLAS, `-ng -nf -nlp`. Seven synthetic RU recordings (Milena,
including English artist/title names) and digital silence were frozen once.
Each profile received one warmup and three measured repeats. The GigaAM group ran
before the Whisper group; inference was not concurrent. These are pilot results,
not randomized hardware trials or human microphone accuracy.

| Native profile | Median STT | p95 STT | Measurements |
| --- | --- | --- | --- |
| GigaAM v3 CTC | 278.825 ms | 291.381 ms | 21 speech requests |
| Whisper base, beam 5 | 242.384 ms | 260.555 ms | 21 speech requests |
| Whisper base, greedy | 210.215 ms | 219.349 ms | 21 speech requests |

Silence is excluded from these latency aggregates. All requests completed without
transport/model errors. GigaAM process peak RSS was approximately **1.83 GiB**,
including startup/model loading; Whisper peak RSS was not measured. Timers exclude
initial reference-file hashing. A separate first CLI invocation recorded 694 ms
for “следующий трек”, including that hash and trace work, so the table is not a
promise of browser end-to-end latency.

GigaAM recognized pause, next and language switching, and returned “включи линкин
парк” for the artist request. The unchanged search/ranking pipeline resolved that
to **Linkin Park** against a synthetic snapshot and real disposable Typesense.
Whisper's “лингин парк” also resolved to the correct artist. This illustrates why
exact transcript/argument agreement alone is not the selection metric.

The difficult recordings remain visible: GigaAM reduced the Linkin Park/Numb
request to “включи”, and the new Ivan Dorn recording to “включи  о”; neither
selected the expected music. Whisper also missed Numb, while beam 5 preserved
“Включи Иван Дорн!” and selected the artist. Catalog checks used only the first
measured repetition, three music targets, existing test aliases and generated
metadata. No player was connected and no command executed. Digital silence
produced an empty GigaAM response and a music marker from Whisper; the common live
pipeline rejects digital silence before either provider.

The [curated report](../../evaluation/speech_reports/2026-09-19-gigaam-native.json)
preserves all 75 requests (including warmups), transcripts, hashes, timings,
dependencies and nine catalog previews. Private frozen WAVs/raw reports remain
under `/tmp/disc-gigaam-*`; no audio/model artifacts enter Git. The native CLI and
its journal recorded the GigaAM provider and verified model evidence successfully.

Validation: the full prototype suite passed **361 tests** before the final
installer/journal/Web regression additions; the subsequent focused suites passed
20 installer/adapter tests and then all nine GigaAM tests. Shared firmware-free
checks passed **365 Python / 37 JavaScript** tests, and both Assistant Web audio/
reply JavaScript test files passed. These overlapping counts are not additive.
The final Web check used a synthetic DISC peer and the real adapter protocol:
transcription selected GigaAM, while a mismatched worker revision caused zero
device mutation writes. No browser microphone or real-device acceptance is claimed.

**Decision:** keep GigaAM optional and Whisper as the default. Compare held-out
human recordings and `multilingual_ctc` next, then evaluate ONNX/platform work if
quality justifies it. RNNT, multilingual, MPS, ONNX and board performance were not
tested. This increment does not change accepted MVP scope or implement fine-tuning.

Upstream: [GigaAM](https://github.com/salute-developers/GigaAM),
[pinned source](https://github.com/salute-developers/GigaAM/tree/7447938d791c4f3e643386ee22c33777004293a5).
