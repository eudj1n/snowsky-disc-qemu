# Disc Assistant Web

A separate local browser interface to the research Assistant. It uses the viewer's
visual vocabulary (dark violet surfaces, compact controls and a circular player
observation), but does not import viewer/emulator code or require guest firmware.
The configured target may be a physical DISC or an emulator.

## Start

Close the existing Assistant console with `/exit` first: the web service acquires
the same exclusive local ownership lock and keeps one device session. Do not run
FiiO Control against the same single-client device at the same time.

```sh
# Install the runtime, pinned models and service images once.
./experiments/disc_assistant/run.sh setup --all
# Edit the configured device, then start speech/search, sync/index and serve.
./experiments/disc_assistant/run.sh web --bootstrap
# Open http://127.0.0.1:8090 in a browser on this computer.

# Reuse an already running Typesense and existing catalog/index instead:
./experiments/disc_assistant/run.sh web
# A separate configured device/port:
./experiments/disc_assistant/run.sh --config /absolute/path/player.toml web --port 8092
```

Use [the common installer](tts.md) on a new machine. `setup` without
`--all` remains available for text-only use. The web adapter uses existing `aiohttp`. No npm build, CDN, browser speech service or
microphone library is required. `--bootstrap` performs catalog preparation once;
Sync library and Rebuild index remain available on the page. A failed preparation
leaves playback controls usable, with the error in Last result.

The page identifies the configured device key and endpoint. Connect/Disconnect
controls the persistent session; it does not stop music. Closing/reloading the
page does not disconnect the service. Ctrl-C in the serving terminal shuts down
the service and releases ownership, without stopping Typesense, speech services or music. An
accepted operation is allowed to finish before shutdown; uncertain writes are
never replayed. The CLI and one-shot scheduled flows remain available separately.

## Text and microphone

Choose the saved input/reply language. The interface labels are English, while
Assistant command dictionaries and response templates follow the selected locale.

- **Preview** (default): interpret/search; no playback or language mutation.
- **Execute**: dispatch the recognized command once through the existing guarded
  application path, including automatic best-match selection.
- **Transcribe**: audio recognition only, without interpretation or execution.

Type a natural command, or select a microphone and click **Record command**.
Click **Stop & submit** to submit it using the selected mode. **Cancel recording**
discards the input and releases the microphone; it does not send a request.
Recording also ends at the configured `speech.max_seconds` (default 30). This is
single-utterance capture, not voice-activity detection or wake-word listening.

The browser captures PCM through an AudioWorklet at the actual context sample
rate, averages channels, resamples with OfflineAudioContext and uploads 16 kHz,
mono, signed 16-bit PCM WAV. The server revalidates size, format, duration and
payload, then uses the same STT/interpretation/ranking/execution pipeline as CLI
file input. Digital-zero silence is rejected; background-noise or hallucination
rejection is not a solved speech detector.

Web uses **Whisper Server by default**, including when the same configuration selects
CLI STT for one-shot commands. There is no silent CLI fallback. `setup --all`
configures the multilingual model, server endpoint and optional managed lifecycle.
`web --bootstrap` starts the managed stack; plain `web` expects it to be running.
See [speech services and Piper replies](tts.md) for installation,
RU/EN voices, saved response policy and browser sound opt-in.

### Choose the speech engine

The **Speech recognition** selector lists configured STT instances; the default choices are **Whisper Server** and **Sherpa · Russian**
for that browser's next recording. [Speech profiles and adapters](voice-adapters.md)
can add GigaAM or user-defined engines and choose the initial provider. Changing engines restores **Preview**; it never
resubmits existing audio. Selection is saved per device in browser local storage and is captured with
the uploaded audio, so another browser cannot change an in-flight request's engine.
Each result displays its actual provider/model, independently of the current selector.
The selected engine feeds the same Assistant interpretation/search and guarded
Controller path in Preview, Transcribe and Execute. TTS remains independent.

Install Sherpa once using the [optional environment installer](../evaluation/sherpa-onnx.md#prepare).
Its default location is `~/disc-speech/sherpa-onnx`. The ordinary Assistant virtualenv
does not need ONNX/NumPy: it starts the worker with the optional environment's Python.
The model is loaded on the first submitted recording and remains resident until
the web service stops. Paths/threads and the initial page selection can be configured
under the existing `[speech]` table (do not create a second table):

```toml
web_backend = "sherpa" # optional; the unchanged default is "whisper"
sherpa_root = "~/disc-speech/sherpa-onnx"
sherpa_python = "~/disc-speech/sherpa-onnx/.venv/bin/python"
sherpa_threads = 2
```

Use Russian as **Command & reply language** for this model. With another language,
the page disables Sherpa recording and the server rejects submitted audio before
inference. Choose Whisper explicitly to use another language; no automatic fallback
or locale remapping occurs. Names embedded in Russian commands may still be English.
This greedy model does not receive catalog hints, even when Whisper hints are enabled.

Sherpa verifies its pinned engine version and model hashes in its isolated worker.
The ordinary speech timeout includes first loading; cancellation or timeout stops
and reaps the worker without replaying the recording. A later explicit request may
start a fresh worker. Closing the browser still lets an already accepted application
request finish, as before; it is not a cancel button for a possibly sent command.
An unavailable model/engine leaves text input and explicit Whisper selection usable.

Enable **Enable spoken replies on this browser**, then select **All available
replies** to hear successful controls as well as errors. The default saved policy
is **Errors only**. Text remains visible regardless. Speech plays on this computer,
not on DISC; Stop voice or a new recording cancels it. Dialogue remains disabled.

Allow microphone access in the browser and, when requested, in OS privacy
settings for that browser. Use `http://127.0.0.1:8090` or `http://localhost:8090`
on the same computer. Browser capture requires a secure context; localhost is
supported. Remote LAN serving/HTTPS setup is deliberately outside this slice.
See [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)
and [browser capture permissions](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

## Application boundary and diagnostics

`assistant/application.py` owns the common service previously defined in
`console.py`. `console.py` re-exports `Application` for existing callers. The web
adapter is `assistant/web/server.py` plus bundled static assets. Application work
and SQLite stay on one worker thread. Controller continues collecting events
independently. HTTP accepts at most one active request and rejects concurrent
commands with 409 instead of queuing stale work.

HTTP endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/state` | Cached device/library/preferences, per-process page token and last result |
| `GET /api/events` | SSE observations (about once per second), bounded trace events and results |
| `POST /api/command` | Natural text + mode, or an allowlisted UI action |
| `POST /api/audio?mode=…&engine=whisper\|sherpa` | Bounded WAV body and explicit engine; never an arbitrary filesystem path |
| `POST /api/reply?request_id=…` | WAV for the current eligible response; no arbitrary text |
| `POST /api/reply-status?request_id=…&outcome=…` | Browser-reported delivery evidence, separate from execution |

UI actions are connect, disconnect, sync, index, queue, a validated locale and
response mode (`none`, `errors`, `all`).
Natural text cannot invoke slash administration, exports or arbitrary file reads.
The server binds only 127.0.0.1, validates Host/Origin/fetch site and requires the
page token on POST. It provides no CORS, remote authentication or public API.
Multiple pages observe the same owner/locale; a running command blocks new ones.
SSE reconnect only restores observation; HTTP writes are never automatically
retried. If a response is lost, inspect Last result and live device state first.
Last result is memory-only and resets when the service restarts; the journal is
persistent. SSE drops oldest diagnostics for slow consumers and is not an audit
log. Detailed response JSON and request traces are collapsible on the page.

Requests use journal source `web`; recognized text, intent/search evidence,
outcome, model provenance and timing use the existing journal. Raw uploads are
not retained. Whisper receives only validated WAV and the selected locale/catalog hints.
Piper delivery events append to the request without changing its execution outcome. Do not commit recordings, histories or personal reports.

## Validation and remaining acceptance

The original browser-input increment passed **317 prototype tests**. Current
speech-service verification is recorded in [the checkpoint](../status.md). Automated checks cover synthetic DISC text preview/execution/idempotence, audio
preview/execution, locale persistence, invalid input, cross-origin/token/host
rejection, busy rejection, browser-loss completion without replay, device changes
during recognition and SSE events. JavaScript checks cover PCM encoding, channel
mixing, duration limits and capture stop. Run:

```sh
./experiments/disc_assistant/run.sh test
node experiments/disc_assistant/assistant/web/test_audio.mjs
node experiments/disc_assistant/assistant/web/test_reply.mjs
```

Browser inspection confirmed viewer-style rendering and Preview → Execute Pause
against a synthetic peer, with the observed playback changing to paused. These
checks do not establish microphone recognition quality or physical playback.
The owner subsequently reported successful microphone commands that played and
stopped music on a physical player. This is manual end-to-end evidence, not a
quantified RU/EN cohort. A representative comparison of recordings, model settings
and actual device outcomes remains pending. No MVP error threshold
or Raspberry Pi performance claim follows from this implementation.
