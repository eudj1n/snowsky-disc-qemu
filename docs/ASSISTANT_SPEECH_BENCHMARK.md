# Fixed-audio Whisper comparison

`speech-benchmark` compares the existing beam-size 5 / best-of 5 decoder with
greedy / best-of 1, using configurable CPU thread counts (default 2 and 4).
Production defaults are unchanged. There is no DISC connection, search, journal,
catalog hints or TTS in the benchmark.

The pinned server accepts beam/best-of per request; threads are a startup option.
By default each model/thread pair gets a sequential, temporary Docker server with an ephemeral
loopback port and a read-only model mount. Both decoders share that server; their
order alternates across cases/repeats. Existing services/config are untouched.
Owned containers are removed on success, failure or Ctrl-C. Abrupt kill/power loss
may leave `disc-stt-bench-*` containers; inspect that prefix before manual cleanup.

## Run

For Docker mode, prerequisite: existing `setup --all` installation, local image
`disc-assistant-whisper:1.9.4`, and an installed model. No downloads or builds occur
in the benchmark. Run on the board being measured, from `experiments/disc_assistant`.
Avoid concurrent voice requests/CPU-heavy work; record cooling, power and other
workload separately. The tool does not automatically measure throttling or swap.

For an existing mono 16-bit PCM WAV at 16 kHz, at most 30 seconds:

```sh
./run.sh speech-benchmark --audio ~/disc-samples/command.wav --locale ru \
  --output ~/disc-benchmark-01 --threads 2 4 --repeats 3 --warmup 1
```

Repeat `--audio PATH` for more recordings in the same locale. This input has no
reference labels: the report includes transcripts and latency, **not accuracy**.
`--locale` defaults to the TOML locale, not a saved database preference. Relative
paths resolve from the caller's directory.

Existing generated `speech-samples` manifests supply checksums and reference
text/intents. Pass one locale directory or a parent containing RU/EN directories:

```sh
./run.sh speech-benchmark --samples ~/disc-samples \
  --output ~/disc-benchmark-corpus-01 --threads 2 4 --repeats 3
```

If no recordings exist, create a synthetic plumbing sample using installed Piper:

```sh
./run.sh speech-up
./run.sh --language ru synthesize 'Включи Иван Дорн' --output ~/disc-sample-ru.wav
./run.sh speech-benchmark --audio ~/disc-sample-ru.wav --locale ru \
  --output ~/disc-benchmark-01
```

Synthesis selects/persists RU as usual. Use unused output names. Synthetic samples
do not replace microphone recordings for product accuracy evaluation.

## Existing native server (no Docker)

Use `--server` for an already running whisper.cpp HTTP server. The benchmark makes
**no Docker or process-management calls** in this mode. Python dependencies from
`run.sh setup` are sufficient; `setup --all` is not required. A native server must
be installed/launched separately. For a CPU comparison with our Docker settings:

```sh
whisper-server -m /path/to/ggml-base.bin --host 127.0.0.1 --port 8080 \
  -t 4 -ng -nf -nlp
```

Keep it running in another terminal, then from `experiments/disc_assistant`:

```sh
./run.sh speech-benchmark --audio ~/dorn.wav --locale ru \
  --server http://127.0.0.1:8080/inference \
  --model /path/to/ggml-base.bin --server-threads 4 \
  --server-label whisper.cpp-v1.9.4-native-cpu \
  --output ~/bench-dorn-native-t4
```

Use the **same model file loaded by the server**. `--model` can be omitted when
the TOML model already matches it. The hash identifies that reference file; this
mode cannot attest the model actually loaded by an external server. Image ID and
architecture are null, startup is excluded/unmeasured, and execution is explicitly
`external_server`. The first-request flag means first request in this benchmark,
not cold server startup. All other input freezing, transcript and summary behavior
is shared with Docker mode.

`--server-threads 4` and `--server-label` are optional **operator declarations** for
the report. They do not set threads or verify the binary/backend; an omitted
thread declaration is unknown (`null`). `--threads` is rejected with `--server`
instead of pretending to sweep threads through HTTP. Multiple `--model` arguments
are also rejected: the tool never calls a model-loading endpoint.

To compare two threads, restart the native server yourself with `-t 2`, then run
the same frozen inputs with `--server-threads 2` and a new output directory. Use
the same whisper.cpp revision, model bytes, CPU/GPU backend and other server flags
before attributing a difference to Docker. The server must implement our pinned
multipart `/inference` contract, including `beam_size`/`best_of`; alternate
OpenAI-compatible endpoints are not supported by this adapter.

Only explicit loopback URLs such as `127.0.0.1` or `::1` are accepted. No shutdown,
restart, model loading or external-service cleanup happens, including on errors.
The two decoding profiles still vary per request. Avoid concurrent clients while
measuring; the endpoint does not provide isolation from other workloads.

## Models and quantization

The configured model is used unless `--model` is supplied. Repeat it to compare
up to four existing files against the identical frozen audio:

```sh
./run.sh speech-benchmark --samples ~/disc-samples \
  --model ~/disc-models/ggml-base.bin \
  --model ~/disc-models/ggml-base-q5_0.bin \
  --output ~/disc-benchmark-models-01
```

The quantized file must already exist. The tool does not quantize/download it.
Treat quantization as an experiment, not guaranteed speed or quality parity; see
[whisper.cpp quantization](https://github.com/ggml-org/whisper.cpp#quantization).
The report records model/grammar hashes, Docker image ID/architecture (when managed), threads and decoder
settings. The mounted model is operator-bound; the HTTP API does not attest loaded
weights. A model change during a group excludes that group's rows from summaries.

## Outputs and interpretation

The output must be a new private directory outside the checkout. Files are private
and are never overwritten:

- `manifest.json` and numbered WAVs freeze inputs; reuse this directory with
  `--samples` on another machine or for another run.
- `run.json` captures initial settings/identity.
- `rows.jsonl` incrementally records transcripts, errors, timings, reference
  comparisons, repeat/locale/profile IDs, first-request and warmup flags.
- `report.json` contains final status, rows, failures and per-profile/per-locale
  summaries. Partial/interrupted reports are distinct from completed runs.

Timings measure adapter plus local HTTP inference, excluding interpretation,
device execution and TTS. Model hashing happens before timed requests. Server
startup is separate. Explicit warmup and first-server-request rows are excluded
from warm median, nearest-rank p95 and median real-time factor (STT/audio duration).
With small cohorts p95 is effectively a maximum, not a stable estimate.

Errors remain in attempt counts and labelled denominators, not successful latency
samples. Corpus `text` supplies normalized exact-transcript comparison; `expected`
supplies normalized interpreter-intent/slot comparison. Unlabelled quality scores
are null. Expected answers are never fed to Whisper; no device success is claimed.
The historical `experiments/speech_compare.py` is unchanged; this is a new cohort.

## Validation

Native arm64 Docker smoke check used one saved synthetic RU WAV and base, two
thread counts, both decoders, one warmup and one measured repeat: eight successful
transcription responses, two containers cleaned up. This verifies execution and
reporting, not Orange Pi speed or recognition quality. Tests cover frozen input,
hash mismatch, labels, warmup/cold exclusions, errors, startup cleanup and default
decoder preservation. Compare several actual recordings before choosing defaults.

Existing-server mode was also exercised against a native whisper.cpp v1.9.4 CPU
binary using a saved synthetic RU WAV: four successful responses, both decoders,
server still running after the benchmark. Only the test harness stopped its own
process. Synthetic HTTP tests prohibit all Docker/process-management calls, check
error reports and unknown thread metadata, and reject ambiguous sweeps/nonlocal
URLs. These are implementation checks, not Orange Pi speed or quality acceptance.
