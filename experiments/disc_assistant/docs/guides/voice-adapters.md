# Speech adapters and deployment profiles

The version-1 contracts live in `assistant/voice/contracts.py`; the historical
`assistant/speech.py` imports remain compatible. STT is speech input, TTS is
speech output. Neither receives a Controller, catalog store or executable command.
The existing application interprets and guards recognized text exactly once.

## Adapter, model, profile

An **adapter** calls an engine or service. A **model** supplies compatible weights,
locale/voice and decoding settings. A **profile** selects named adapter instances
and their settings. The same adapter can have multiple instances with different
models; the same configured instance can serve CLI and Web.

A new model in an already supported format usually needs configuration. Another
architecture, engine API or inference transport needs an adapter. In particular,
the bundled Sherpa adapter is the pinned Russian Zipformer implementation, not a
loader for every model supported by sherpa-onnx.

Built-in factories are explicit, lazy imports:

| Adapter ID | Role | Current scope |
| --- | --- | --- |
| `whisper_cpp` | STT | One-shot whisper.cpp executable, configured multilingual model |
| `whisper_server` | STT | Operator-owned whisper.cpp HTTP service |
| `sherpa_onnx` | STT | Owned optional worker, pinned RU Zipformer INT8, CPU |
| `gigaam_server` | STT | Optional native worker protocol; v3 CTC has historical pilot evidence |
| `piper` | TTS | Operator-owned HTTP service, explicitly configured locale-to-voice paths |
| `vosk_tts` | TTS | Owned CPU worker, pinned RU 0.9 multi-speaker model, five voices |
| `silero` | TTS | Owned CPU worker, pinned v5_5_ru, five RU voices; optional normalization |
| `macos_say` | TTS | macOS system voice, file synthesis; no speaker output |

Ordinary imports do not load Torch, ONNX or NumPy. Dependencies and model licenses
belong to each deployment. No plugin or weight downloads occur on a voice request.
GigaAM RNNT/multilingual names are accepted by its existing worker contract, but
have not been quality-tested here. Neither successful contract checks nor a named
profile certify a model's human-speech quality or board performance.

## Configuration

Existing `[speech]` and `[tts]` files work unchanged. Without `[voice]`, CLI keeps
its CLI/server choice, Web defaults to Whisper and offers Sherpa, and configured
Piper handles browser replies. File synthesis retains its legacy macOS default
when no TTS provider is configured. `voice.tts = "none"` explicitly disables both file synthesis and browser replies.

An optional new section selects instances:

```toml
[voice]
stt = "sherpa"             # CLI/file input
web_stt = "sherpa"         # initial browser choice
web_choices = ["whisper", "sherpa", "gigaam"]
tts = "piper"

[voice.providers.gigaam]
kind = "stt"
adapter = "gigaam_server"
label = "GigaAM v3 CTC"
[voice.providers.gigaam.settings]
server_url = "http://127.0.0.1:18123/inference"
model = "~/disc-speech/gigaam-models/v3_ctc.ckpt"
max_seconds = 25
timeout = 120
```

The built-in instance IDs are `whisper_cli`, `whisper`, `sherpa`, `piper`, and
`macos_say`; they obtain settings from the existing sections. GigaAM is explicitly
configured because it needs a separate worker/checkpoint. A named provider table
may replace a built-in instance. Its `settings` table is passed only to its factory;
engine-specific validation belongs to that factory/adapter. Timeout is bounded
by the common contract, and the adapter's declared audio limit also applies.
If `web_choices` is omitted, the legacy Whisper/Sherpa choices plus custom STT
instances are offered. The configured default is included. Unknown IDs, wrong
roles, unsupported contract versions and unsupported locales fail without fallback.

Instead of repeating deployment settings, set an absolute profile path:

```toml
[voice]
profile = "/absolute/path/to/speech-profile.toml"
```

A profile contains only `[voice]` and its subtables. Inline selectors override it;
inline provider/plugin entries replace entries with the same name. Nested profile
includes are rejected. Example files live in
[`assistant/voice/profiles`](../../assistant/voice/profiles): Whisper HTTP,
Sherpa RU CPU, GigaAM native and a custom JSON service.

Profiles are explicit deployment inputs for Mac, Orange Pi, Raspberry Pi or other
hosts. They do not auto-detect hardware, install packages, build binaries or assert
acceleration support. Packaging can install only a chosen profile's engine
requirements and weights. The existing `setup --all` still manages the original
Whisper/Piper bundle; it is not a universal plugin installer. Custom services and
GigaAM must be started explicitly. `services.speech` retains its existing meaning.

Web obtains its selector from the registry. Selection is saved per device in that
browser's local storage, only if the instance still exists in the current choices.
A fresh browser uses `web_stt`. Reload and engine changes start in Preview; no
recording or command is resubmitted. Each result displays its actual provider/model,
independently of the current selector, plus preparation and inference timings.
`cold` means the first successful call in this adapter lifecycle, not proof that an
external HTTP server loaded its weights during that call. Total STT includes local
validation/identity work; HTTP inference timing also includes transport/server wait.

## Implement an adapter

Use `SpeechAdapter` as a convenience base or implement the same contract:

- `contract_version = 1`, immutable `ProviderInfo` and `Capabilities`.
- STT: `async transcribe(Audio, SpeechContext) -> Transcription`.
- TTS: `async synthesize(SynthesisRequest) -> Audio`.
- `async prepare(locale)` is idempotent; `async aclose()` releases owned resources.
- `available()` is a cheap installation/configuration check, not a network health
  guarantee. Construction must not allocate models, clients or start services.
- `evidence(locale)` describes configured model/voice identity; `result_evidence()`
  optionally returns evidence verified by the last successful inference response.
  Both return bounded JSON objects with **no secrets, paths to private recordings,
  credentials or arbitrary server response bodies**.

The runtime gives each instance a stable event loop across synchronous application
requests. Prepare/inference are serialized per instance; concurrent input is
rejected rather than queued. Cooperative timeout/cancellation awaits adapter
cleanup. Adapters must offload blocking work, honor cancellation and make aclose
idempotent. Python plugins run as trusted application code, not in a security
sandbox: non-cooperative native work needs an owned subprocess such as Sherpa's.
Cancelling an HTTP request cannot stop inference on an external server; its result
is discarded and the request is never automatically replayed.

STT input is validated mono PCM16 WAV at 16 kHz; declare a lower `max_seconds` when
needed. TTS returns mono PCM16 WAV at its native sample rate, checked against the
metadata. Playback/capture are separate contracts. The common boundary rejects
invalid output, wrong locales, inconsistent silence, and unsupported hints.
`Capabilities.locales=None` means an explicit model locale is passed through, not
that all languages were tested. It never enables language auto-detection.
Streaming/VAD/wake words are outside v1; do not overload final transcripts with
partial results.

Register an installed package explicitly in trusted local configuration:

```toml
[voice.plugins]
my_recognizer = "my_speech_package.adapters:create_transcriber"

[voice.providers.my_ru]
kind = "stt"
adapter = "my_recognizer"
label = "My Russian recognizer"
[voice.providers.my_ru.settings]
model = "/models/my-model"
```

The factory takes one settings dictionary and returns an adapter. Alternatively,
embedding applications can use `Registry.register(name, kind, factory)` and pass
that registry to `SpeechRuntime`. Built-in IDs cannot be replaced by a plugin.
Only configured IDs cross the browser API; clients cannot submit module paths.

[`examples/http_speech.py`](../../assistant/voice/examples/http_speech.py) contains
working STT/TTS extension examples for a user's own loopback JSON service. The
matching `custom-json.toml` profile documents registration and payloads. Tests
exercise those examples with synthetic HTTP services, without modifying the core.

A model for a new language enables speech processing only. Full Assistant support
also needs its [command rules and response locale](../reference/locales.md).

## Test multiple implementations

The ordinary suite exercises built-ins with synthetic subprocesses/services and
shared contract tests: identity, formats, locale rejection, cancellation, lifecycle,
no fallback, configuration, custom HTTP plugins and Web routing. It needs no ML
weights. Run `./experiments/disc_assistant/run.sh test`.

For real installed models, use the device-free sequential matrix runner:

```sh
experiments/disc_assistant/assistant/.venv/bin/python -m \
  experiments.disc_assistant.assistant.voice.check \
  --config ~/disc-assistant.toml \
  --provider whisper --provider sherpa \
  --audio /absolute/path/to/fixed-ru.wav --locale ru --repeats 3
```

Repeat `--provider` for configured instances. TTS needs `--text`; supplying both
inputs permits a mixed STT/TTS matrix. Reports include input hashes, provider/model
identity, first/reused-call timings and errors. A failing provider is not retried;
other explicitly requested providers are still checked. The runner never connects
to DISC, interprets commands, plays generated audio or stores recordings. Catalog
hints are disabled for comparability. JSON is printed to stdout; redirect it to a
private location if preserving results. This is an integration probe, not a speech
quality score. Use labelled recordings and separate hardware runs for acceptance.

## GigaAM migration

Code and evidence were selectively ported from commit `40a9bb7` on
`codex/gigaam-stt`; old factory/UI/config branches were not merged. The historical
[native pilot report](../reports/2026-09-19-gigaam-native.md) and its curated JSON
remain distinct from new contract verification.

Use Python 3.12 and ffmpeg for the optional native environment:

```sh
python3.12 -m venv "$HOME/disc-speech/gigaam-venv"
"$HOME/disc-speech/gigaam-venv/bin/python" -m pip install \
  -r experiments/disc_assistant/assistant/voice/requirements/gigaam.txt
"$HOME/disc-speech/gigaam-venv/bin/python" -m \
  experiments.disc_assistant.assistant.voice.adapters.stt.gigaam_worker \
  --model v3_ctc --model-dir "$HOME/disc-speech/gigaam-models" --threads 4
```

The worker now refuses startup if `ffmpeg` is missing from PATH. On macOS,
if no system executable is installed, an isolated alternative is:

```sh
"$HOME/disc-speech/gigaam-venv/bin/python" -m pip install imageio-ffmpeg==0.6.0
"$HOME/disc-speech/gigaam-venv/bin/python" -c 'from pathlib import Path; import sys, imageio_ffmpeg; p = Path(sys.prefix) / "bin/ffmpeg"; p.exists() or p.symlink_to(imageio_ffmpeg.get_ffmpeg_exe())'
export PATH="$HOME/disc-speech/gigaam-venv/bin:$PATH"
```

This package supplies an executable on supported wheel platforms; on other hosts
provide FFmpeg through the system/deployment dependencies. No inference-time
installation or fallback is attempted.

For first installation only, add `--download` explicitly. The worker checks the
pinned upstream revision and serves loopback 18123; the adapter checks the checkpoint
hash and worker revision on every successful response. Torch stays out of the main
Assistant environment. See `gigaam-native.toml` for selection. A client timeout
leaves external inference to finish; it does not restart the worker or retry input.

## TTS normalization and Silero

Every TTS factory is composed with the versioned `TextNormalizer` stage. The
reserved provider setting `normalization` is consumed by the registry before
calling the engine factory. Identity is the compatibility default; `ru_numbers`
and optional offline `runorm` are explicit choices. See [TTS setup and listening
comparison](tts.md#optional-silero-ru) and [normalization](tts.md#pronunciation-boundary).
