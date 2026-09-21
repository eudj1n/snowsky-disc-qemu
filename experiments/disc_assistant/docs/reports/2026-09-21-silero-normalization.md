# Silero and TTS normalization integration, 2026-09-21

Scope: optional Silero RU adapter, shared TTS-only normalization and device-free
synthetic listening comparison. No physical playback command was sent. This does
not replace speech-quality, firmware or board-performance acceptance.

## Implementation and provenance

- Silero `v5_5_ru`, Xenia, CPU, two threads, 24 kHz; Torch 2.8.0 / NumPy 2.2.6
  in a separate Python 3.12 environment. Model SHA-256:
  `50081637b602126ee06cb3bc8a744d25651d2da149ee8864b9a379bfdd934437`.
- The resident worker verifies the exact model before loading, rejects unsupported
  locales/voices, bounds WAV output, and is killed/reaped on cancellation/timeout.
- The TTS registry composes every engine with `TextNormalizer`: identity default,
  explicit `ru_numbers`, or optional RUNorm. Original response text is preserved.
  Cache identity includes normalization revision and weights; timing/digests are
  separate from control outcomes. Failed synthesis never retries a player command.
- RUNorm 1.1, Transformers 4.44.2, Torch 2.8.0, CPU/two threads, separate environment.
  Local models: small `24fa466a3818f14c66b6392965e67b9644ed3136`,
  tagger `ce379228483424b9bf7cca3175c7777bd53b2945`,
  kirillizator `b130ae67db4b209babec461767bcd2ace74fe88a`.
  Combined directory digest:
  `361d6f89de21eea29d7ac3f7d026b18feb59da3262475e8256c5bb9eee1ba948`.
  Runtime loads these paths with Hugging Face/Transformers offline mode enabled.
- Adapter code remains MIT. Silero weights retain CC BY-NC-SA 4.0; RUNorm code
  and selected model cards declare Apache-2.0. Models/environments/audio stay outside Git.

## Verification

- Full `./experiments/disc_assistant/run.sh test`: **421 tests, OK, 4 optional skips**,
  60.271 seconds. Log: local `/tmp/disc-silero-suite.log`.
- Focused initial suite: 29 tests, OK, one optional skip. New cases cover original
  text preservation, cache policy changes, bad normalization output preventing
  synthesis, locale handling, model digest rejection before loading, resident
  reuse, malformed IPC, cancellation/timeout cleanup and rejection of concurrent work.
- Real Silero returned nonsilent, validated 24 kHz PCM through the common runtime.
- Real `ReplySynthesizer` delivery returned a cache miss then a cache hit for the
  same Russian reply, retaining its original text and normalization metadata.
  Twelve focused normalization/worker tests passed after final changes; existing
  browser reply/capture JavaScript checks passed. Documentation links/diff checks passed.
- `evaluation.tts_compare`: **18/18 successful WAVs**, six synthetic phrases each
  through Piper, Silero with rule normalization, and Silero with RUNorm. No player
  or application session is created. Browser page renders all 18 audio controls.
  Local artifacts: `/tmp/disc-tts-listening-20260921/{index.html,results.json,*.wav}`.
- Existing web owner restarted with the Silero/rule-normalization profile;
  read-only `/api/state` advertised `silero_ru`, locale `ru`. Existing preferences,
  Piper settings, STT selection and device configuration were preserved.

Initial sandboxed loopback tests failed to bind sockets; the focused and full
runs above used the required local-socket permission. No model fallback was used.

## Observed normalization limitations

Real RUNorm output, kept without corrective tuning:

| Input | Output |
| --- | --- |
| `Громкость 25%.` | `Громкость двадцать пятьпроцента.` |
| `Включаю Ваню Дмитриенко.` | `Включаю ваню дмитриенко.` |
| `Играет Linkin Park — Numb.` | `Играет линкин парк — эн йю эм би` |

Consequently RUNorm remains explicit opt-in. The active Silero profile uses the
dependency-free `ru_numbers` policy, which expands integer percentages correctly
but does not claim contextual declension, Latin-name pronunciation, dates or times.
English names are retained by that policy; their acoustic pronunciation requires
listening evaluation of the selected TTS model.

## Timings, not a model ranking

Single sequential run on the existing macOS host; no repetitions or controlled load:

| Configuration | First phrase, including local preparation | Later five phrases |
| --- | --- | --- |
| Existing Piper HTTP | 572 ms | 315–762 ms |
| Silero + ru_numbers | 2241 ms | 34–132 ms |
| Silero + RUNorm | 5395 ms | 61–406 ms |

Piper uses an already-running external service; Silero/RUNorm start new local
workers. Output lengths and normalization differ. These values prove neither
relative model quality nor equivalent work/real-time performance on ARM boards.
The six examples are synthetic integration inputs, not a representative listening
corpus or independent holdout. Reproduction commands and configuration are in
the [TTS guide](../guides/tts.md).
