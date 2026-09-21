# Optional sherpa-onnx comparison environment

This experiment prepares native CPU recognition independently of the running
Assistant. It does not load user configuration, connect to DISC, start services,
change Whisper/Piper settings or download anything during recognition.

The first candidate is
`sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16`, from
[the sherpa developer's model repository](https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16).
It is a Russian streaming transducer with INT8 encoder/joiner and FP32 decoder
(about 29 MB of weights). It is distinct from the older **offline** small Russian
Zipformer dated 2024-09-18. Do not combine their scores or model files.

The installer pins the model repository revision and checks every downloaded
file against SHA-256, including two upstream demonstration WAVs. Those WAVs are
plumbing inputs, not our command corpus or a speech-quality holdout.

## Prepare

Use Python 3.11+ on macOS ARM64 or Linux ARM64, from the repository root:

```sh
python3 -m experiments.disc_assistant.evaluation.sherpa_setup
```

The default directory is `~/disc-speech/sherpa-onnx`; `--root /absolute/path`
selects another directory outside the checkout. Setup creates its own `.venv`,
installs sherpa-onnx 1.13.8 and the comparison dependencies, and saves
`installed-requirements.txt` and `model-provenance.json`. Direct dependencies are
pinned; the saved pip freeze describes the actual platform installation, not a
universal lockfile. Downloaded files and reports stay outside Git.

Setup reuses matching models and refuses to overwrite mismatching model files.
TLS verification remains enabled. A hard interruption can leave a `.partial`
download; inspect and remove that individual partial before retrying. Existing
Assistant configuration, virtualenv and model storage are not migrated.

## Verify recognition

### Browser microphone comparison

From the repository root, start the separate local lab:

```sh
~/disc-speech/sherpa-onnx/.venv/bin/python \
  -m experiments.disc_assistant.evaluation.speech_web
# Open http://127.0.0.1:8091
```

Defaults use the installed native `~/disc-speech/whisper.cpp/build/bin/whisper-server`
and `~/disc-speech/ggml-small.bin`. Override with `--whisper-binary PATH` and
`--whisper-model PATH`; `--root`, `--threads` (default 2), and `--port` (default
8091) are available. The binary/model must already exist; there are no automatic
downloads or production config reads. Both providers are resident CPU processes.
The lab starts its own Whisper on an ephemeral loopback port, not the Assistant's
existing service. Ctrl-C stops the web lab and both owned inference processes.

In a browser with microphone support (Chrome or Safari on this computer):

1. Open the address above and allow microphone access when recording.
2. Click **Записать фразу**, speak, then **Завершить запись** (30-second limit).
3. Listen back, then click **Сравнить модели**. Both receive the same PCM WAV.
4. Read each transcript and time; save **Скачать WAV** and **Скачать отчёт** if
   wanted. The JSON includes the audio SHA-256 and model/decoder provenance.

You can also upload an existing PCM16 mono 16 kHz WAV. The lab uses Russian for
both models, no catalog vocabulary or expected transcript, and never interprets
or executes player commands. Model order alternates on each explicit comparison;
inference is sequential. First requests are labelled. Timings include local
transport, exclude model loading, and do not measure live streaming latency.
No quality score or automatic winner is assigned.

Audio/results stay in transient memory unless downloaded explicitly. Neither
microphone audio nor transcripts are logged or written to Assistant storage.
Whisper's owned process runs in a private temporary directory which is removed
on normal shutdown. Closing a tab lets an already submitted comparison finish;
it does not permit overlapping inference or trigger a retry. A failed/timed-out
provider is stopped and requires restarting the lab. Host/origin/token checks,
loopback binding, bounded WAV uploads and one active comparison are enforced.

### File-based runner

From the repository root (no activation needed):

```sh
~/disc-speech/sherpa-onnx/.venv/bin/python \
  -m experiments.disc_assistant.evaluation.sherpa_benchmark \
  --audio ~/disc-speech/sherpa-onnx/sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16/test_wavs/0.wav \
  --output ~/disc-speech/sherpa-onnx/smoke-01 --threads 2 --repeats 1
```

Each output directory must be new. `manifest.json` and numbered WAVs freeze the
inputs; `rows.jsonl` preserves each transcript/error, and `report.json` records
platform, engine, model hashes, load time and warm processing time. First requests
and explicit warmups are excluded from warm summaries. Exit status indicates
runner/provider completion, not transcript accuracy. Unlabelled audio has no
accuracy score.

## Compare identical commands

Use an existing Russian `speech-samples` directory (or a previous benchmark's
frozen manifest), or repeat `--audio` with explicit mono 16-bit PCM 16 kHz WAVs,
each at most 30 seconds:

```sh
~/disc-speech/sherpa-onnx/.venv/bin/python \
  -m experiments.disc_assistant.evaluation.sherpa_benchmark \
  --samples ~/disc-samples/ru --output ~/disc-speech/sherpa-onnx/ru-01 \
  --threads 2 4 --warmup 1 --repeats 3

./experiments/disc_assistant/run.sh speech-benchmark \
  --samples ~/disc-speech/sherpa-onnx/ru-01 \
  --output ~/disc-speech/whisper-ru-01 --threads 2 4 --repeats 3
```

The second command requires the existing Assistant/Whisper setup; see
[Whisper benchmark](speech-benchmark.md), including its native-server mode.

This runner uses a streaming model on complete files, with 300 ms of zero padding
to flush its context. It measures file-processing throughput, **not** microphone
endpointing or first-token latency. Greedy sherpa and Whisper beam/greedy are
distinct decoding profiles. Native sherpa versus Docker Whisper confounds engine
and deployment; use native Whisper on the same machine for that comparison.
Model loading is separate from warm STT time. RAM, thermals and sustained load
are not measured by this first runner.

Russian commands containing English artists/titles, short controls, background
music, silence and actual microphone recordings need explicit evaluation. An
empty transcription remains visible; do not equate nonempty output with speech.
The model does not cover our English command locale; mixed RU/EN manifests are
rejected. No reference text, catalog hints or hotwords are fed to recognition.
Frozen reference text/intents use the existing benchmark's exact normalized
agreement metrics, not WER or actual catalog-selection success.

CPU suitability on Orange Pi must be measured on the particular board. No NPU
runtime, RKNN conversion, VAD, T-one or new TTS voice is installed by this setup.
The file runner remains separate from the application. The main web interface now
supports an [explicit Sherpa provider](../guides/web.md#choose-the-speech-engine)
with subprocess ownership, cancellation and the existing guarded execution path.

The [2026-09-21 smoke record](../reports/2026-09-21-sherpa-environment.md)
preserves the initial macOS installation/inference check and its limits.
