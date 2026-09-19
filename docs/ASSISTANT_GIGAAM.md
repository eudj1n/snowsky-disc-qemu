# Native GigaAM comparison

Experimental STT provider on `codex/gigaam-stt`, separate from the accepted software
MVP. Whisper remains the default. GigaAM replaces only transcription; the common
interpreter, catalog ranking, Controller and Piper response path are unchanged.

## Install an isolated worker

From the repository root, with Python **3.12**, Git and `ffmpeg` on PATH:

```sh
python3.12 -m venv "$HOME/disc-speech/gigaam-venv"
"$HOME/disc-speech/gigaam-venv/bin/python" -m pip install \
  -r research/disc_assistant/experiments/requirements-gigaam.txt

"$HOME/disc-speech/gigaam-venv/bin/python" -m \
  research.disc_assistant.experiments.gigaam_server \
  --model v3_ctc --model-dir "$HOME/disc-speech/gigaam-models" \
  --threads 4 --download
```

The process stays in the foreground on **127.0.0.1:18123**. Wait for `ready: true`;
Ctrl-C stops it. `--download` explicitly permits initial model installation. Later
starts use the same command without that flag and require an existing checkpoint.
The pinned upstream loader validates its checkpoint checksum; the worker publishes
SHA-256 of the loaded checkpoint and checks the installed Git revision. No download
occurs during inference. Audio is held in a private temporary directory during
recognition and removed afterwards; request bodies are not logged.

The worker uses CPU, FP32 and explicit Torch thread counts. It does not select MPS,
CUDA, ONNX or Docker. The reviewed package revision is
`7447938d791c4f3e643386ee22c33777004293a5`, with Torch/torchaudio 2.8.0. Other Python
packages follow that upstream revision's dependency constraints; preserve `pip
freeze` with a benchmark report. This is an optional environment, not an addition
to ordinary Assistant requirements or `setup --all`.

Supported experiment names: `v3_ctc`, `v3_rnnt` (RU only), `multilingual_ctc`
(RU/EN interaction locales). Only `v3_ctc` has been exercised here. English music
names inside Russian requests remain valid inputs but recognition is measured,
not assumed. A RU-only model rejects an EN interaction locale without fallback.

## Compare without a player

In another terminal, using an existing Assistant setup and the same frozen files:

```sh
./research/disc_assistant/run.sh speech-benchmark \
  --provider gigaam --server http://127.0.0.1:18123/inference \
  --model "$HOME/disc-speech/gigaam-models/v3_ctc.ckpt" \
  --server-threads 4 --server-label native-gigaam-cpu \
  --audio "$HOME/disc-samples/dorn.wav" --locale ru \
  --output "$HOME/bench-gigaam-01"
```

Use `--samples DIRECTORY` instead of `--audio` for existing checksum-bound sample
manifests with reference text/intents. Reports require a new private directory
outside the checkout and preserve frozen recordings. Use those same samples for
the [Whisper benchmark](ASSISTANT_SPEECH_BENCHMARK.md). Models run sequentially;
do not overlap inference or run CPU-heavy tests during timing. First requests and
warmups are recorded separately. Existing-server startup time is not measured.
Unlabelled audio produces transcripts/latency, not accuracy scores. No player,
library synchronization or Typesense is required for this benchmark.

## Select GigaAM in Assistant Web or CLI

Copy your existing config to a separate experiment config and replace its speech
settings (preserve your device, storage, search and TTS configuration):

```toml
[speech]
provider = "gigaam"
backend = "server"
server_url = "http://127.0.0.1:18123/inference"
model = "~/disc-speech/gigaam-models/v3_ctc.ckpt"
catalog_hints = false
timeout = 120
max_seconds = 25

[services]
speech = false
```

`model` must name the same supported `.ckpt` file loaded by the worker; both sides
check SHA-256. Do not point this adapter at a stock GigaAM/Triton endpoint: its
bounded protocol belongs to our experimental worker. Language is the explicitly
selected interaction locale, not a language-detection result. Catalog hints are
unsupported and rejected rather than silently ignored. Input is mono 16-bit PCM
WAV at 16 kHz, at most 25 seconds; Web caps recording accordingly.

```sh
./research/disc_assistant/run.sh --config ~/disc-gigaam.toml --language ru \
  transcribe ~/disc-samples/dorn.wav
./research/disc_assistant/run.sh --config ~/disc-gigaam.toml web --bootstrap
```

`transcribe` does not execute commands. Web preview/transcribe can be used before
explicit execution. Close other device owners before opening Web. The browser
adapter and request journal preserve the selected provider and model evidence.
The worker rejects concurrent requests instead of queuing them. Client timeout
does not interrupt an already running CPU inference; its result is discarded and
there is no automatic retry. The worker never receives device control commands.

`services.speech=false` leaves speech lifecycle to the operator. Start Piper
separately if spoken replies are desired, or leave TTS disabled. `web --bootstrap`
can still prepare Typesense. `setup --all` selects the managed Whisper/Piper bundle
and backs up then updates its config; it is not GigaAM installation. To switch
back, use the original Whisper config. Missing `speech.provider` still means
Whisper, preserving existing installations.

## Native pilot, 2026-09-19

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

The [curated report](../research/disc_assistant/experiments/speech_reports/2026-09-19-gigaam-native.json)
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
