# Local speech services and synthesized replies

The desktop web path is **microphone → Whisper Server or Sherpa → Assistant → Controller →
localized response → normalizer → configured TTS → browser audio**. Web defaults to Whisper Server;
the [optional Sherpa RU selection](web.md#choose-the-speech-engine) uses its own local worker.
one-shot CLI/file workflows may still explicitly select the CLI STT backend.
Piper is an optional `SpeechSynthesizer`, independent of interpretation and player
control. Audio plays on the computer running the browser, not through DISC.

## One installation command

Prerequisites: **Python 3.11+ and running Docker with Compose** (Docker Desktop on
macOS). These system prerequisites are installed by the owner. From the checkout:

```sh
./experiments/disc_assistant/run.sh setup --all
# Then edit ~/disc-assistant.toml: device.key, host and TCP/HTTP ports.
./experiments/disc_assistant/run.sh web --bootstrap
# Open http://127.0.0.1:8090
```

For an existing custom config, pass `--config /absolute/path/player.toml` before
`setup` and `web`. Close another Assistant console/web owner first. Installation
itself never connects to a player or starts containers.

`setup --all` performs the following:

1. Creates/reuses the prototype venv; installs runtime and optional speech setup/
   sample-conversion dependencies. Generates missing config/search credentials.
2. Preserves an installed Whisper model (uses multilingual **base** on a fresh
   configuration), and downloads Piper **RU Irina medium** and
   **EN Alba medium**, their ONNX configuration and model cards. URLs use fixed
   repository revisions and every asset has a checked SHA-256 in
   [`models.json`](../../assistant/voice/services/models.json).
3. Builds CPU-only Whisper Server **v1.9.4** and Piper **1.4.2** images; pulls the
   existing Typesense image. No host CMake, Piper Python environment or GPU is needed.
4. Updates only `[speech]`, `[tts]` and `[services]` for this bundle. Other settings
   and comments survive; the original TOML is saved beside it as
   `.before-speech-<id>` with private permissions before atomic replacement.

To choose the larger multilingual model explicitly:

```sh
./experiments/disc_assistant/run.sh setup --all --whisper-model small
```

Base is the default for a configuration without a selected model, not a quality
recommendation. An existing installed model/path is preserved unless
`--whisper-model` explicitly selects a replacement. If a configured base/small file
is missing, setup downloads the same variant into managed storage. A missing custom
model requires restoring the file or explicitly selecting a replacement.
See [the measured base/small comparison](voice.md). Repeating setup
reuses verified model bytes and preserves search keys. A checksum mismatch stops installation rather than overwriting
unknown local files. First installation needs network access, image-build time
and disk space; subsequent command processing is local. Models/cards live under
`<storage.data_dir>/speech`, outside Git. Setup is not a complete transitive
lockfile: OS image tags and package dependency resolution can still change.

`setup` without `--all` retains the lightweight text-only setup. Offline NLU
training/embedding experiments are separate optional environments and are not
installed by this runtime command.

### Upgrade the Russian voice

The managed RU voice changed from Denis to **Irina** on 2026-09-19. Stop the web
process, update the checkout, run `setup --all`, then `web --bootstrap`. Existing
Whisper selection is preserved; EN Alba is unchanged. The old Denis assets are
retained locally. A hash of the voice mapping participates in the Piper container
configuration so Compose recreates the resident worker when its voices change;
ordinary unchanged starts do not reload it. No STT or pronunciation rules are
changed by selecting this voice.

## Download certificates

The installer loads the pinned `certifi` public CA bundle in addition to Python's
platform/default trust. This avoids relying on an initialized CA store in a
standalone Python installation. Certificate-chain and hostname verification stay
enabled; model SHA-256 validation is a separate check. See
[Python TLS contexts](https://docs.python.org/3/library/ssl.html#ssl.create_default_context)
and [certifi](https://github.com/certifi/python-certifi).

If an older checkout fails at `Downloading ggml-base.bin` with
`CERTIFICATE_VERIFY_FAILED`, update the checkout and rerun `setup --all`. It
installs the explicit CA dependency before downloading; already verified models
are reused. The pip upgrade notice is unrelated to model download TLS.

For a trusted HTTPS-inspecting proxy whose CA is not in public/default trust,
obtain its PEM CA bundle from your administrator and pass it explicitly:

```sh
DISC_ASSISTANT_CA_BUNDLE=/absolute/path/trusted-proxy-ca.pem \
  ./experiments/disc_assistant/run.sh setup --all
```

This adds trust only for the model downloader; it does not change pip or Docker
trust settings. Invalid bundles fail closed. The installer never retries with
certificate verification disabled and never installs a certificate from a failed
connection automatically.

## Service lifecycle

`web --bootstrap` starts the managed speech stack when `[services] speech=true`,
then prepares Typesense/catalog/index and opens the web service. Plain `web`
reuses running services and saved data. Speech startup failure leaves text input
available; it does not silently switch to another engine.

```sh
./experiments/disc_assistant/run.sh speech-up
./experiments/disc_assistant/run.sh speech-down
# Existing search-only lifecycle:
./experiments/disc_assistant/run.sh down
```

Closing the page/Assistant service does not stop music or Docker services. The
speech stack is the separate Compose project `disc-assistant-speech`, with no
emulator mounts, privileges or LAN bindings. Fixed loopback ports are **18119**
(Whisper `/inference`, `/health`) and **18121** (Piper `/synthesize`, `/health`).
Port 18120 remains reserved for the optional structured-model experiment.
Stop any manually started server occupying these ports before `speech-up`.

External speech services remain possible with `[services] speech=false`, explicit
loopback endpoints, installed model paths and matching voice fingerprints. Piper's
endpoint here is our small adapter, not the upstream optional HTTP server API.
The managed bundle installs RU/EN only. Adding another text locale does not install
a voice: explicitly supply its model/config, worker locale mapping and
`[tts.models]` entry. A missing voice is reported; no fallback language is spoken.

## Browser delivery

On the web page, explicitly enable **Enable spoken replies on this browser**.
This unlocks the browser audio context through a user gesture and resets on page
reload. The saved **Speak** setting controls eligibility:

- **Errors only** (default): successful pause/play commands remain quiet.
- **All available replies**: synthesize every nonempty eligible response.
- **Nothing**: keep text responses, without speech.

The setting is the same persisted preference as `/response mode none|errors|all`.
Only the submitting page requests speech after a result; SSE updates, opening
another tab and reload never autoplay old results. **Stop voice**, a new command,
recording or page closure cancel obsolete browser audio. Recording stops speech
before microphone capture; there is no simultaneous full-duplex conversation or
acoustic echo cancellation claim. The music player is not muted/ducked for TTS.

The server accepts only the current response ID, checks `response.speak`, and
synthesizes its stored text/locale. It rejects superseded results, concurrent
synthesis and arbitrary caller-provided synthesis text. Synthesis failure is a
separate delivery error: a confirmed command stays confirmed and is never replayed.
Journal events record synthesis timing/cache/model fingerprints and browser-reported
playback outcome. A browser completion report does not prove a human heard audio.

Piper models remain resident. A bounded in-memory response cache (8 entries,
16 MiB) includes text, locale, provider, voice/config hashes and pronunciation
policy revision. Audio is not retained in the request journal. Native mono PCM
sample rates are preserved for web playback (both bundled voices use 22,050 Hz).
Explicit `synthesize`/`speech-samples` files target STT's 16 kHz PCM through SoXR
HQ conversion and record the original audio provenance. No compressed upload
support was added.

## Pronunciation boundary

`voice/text.py` defines the asynchronous `TextNormalizer` boundary and composes
it with every registered TTS adapter, including custom factories. Input is the
spoken copy only: `response.text`, search input, catalog tags and command history
remain unchanged. The default is `identity`; opt in per TTS provider:

```toml
[voice.providers.my_voice.settings.normalization]
mode = "ru_numbers"
```

Legacy Piper configuration also accepts `[tts.normalization] mode = "ru_numbers"`.
Modes:

- `identity`: preserve text exactly, for compatibility and paired comparisons.
- `ru_numbers`: dependency-free Russian nominative cardinal numbers 0..999999 and
  integer percentages (`25%` → `двадцать пять процентов`). Other locales pass
  through. Embedded names such as `U2`/`blink-182`, leading-zero identifiers,
  signed values, decimal numbers, dates, times and fractions remain unchanged.
  This is deliberately not general grammatical inflection or transliteration.
- `runorm`: opt-in RUNorm 1.1 small pipeline, resident in its own Python process.
  Russian only; other locales pass through. Upstream also normalizes abbreviations
  and transliterates Latin names; this can change pronunciation incorrectly.

Normalization errors stop audio delivery without fallback or command replay.
Normalized output is bounded to 4000 characters (providers may impose lower limits).
The response cache includes normalization mode/revision and model digest. Result
metadata includes normalization time, changed flag and text digest, not an extra
copy of private response text. Original response policy and browser opt-in still apply.

## Optional Silero RU

The `silero` factory hosts the reviewed `v5_5_ru` model in a separate, reusable
CPU worker. It supports `aidar`, `baya`, `kseniya`, `xenia`, `eugene`, native mono
PCM at 8/24/48 kHz, and configurable `put_accent`/`put_yo`. The supplied profile
selects Xenia, 24 kHz, two CPU threads and `ru_numbers`. Locale `en` is rejected;
select Piper explicitly for English replies. There is no implicit TTS fallback.

From the repository root, install explicitly using Python 3.12:

```sh
python3.12 -m experiments.disc_assistant.assistant.voice.silero_setup
```

The installer creates `~/disc-speech/silero/.venv`, downloads the 138 MiB model,
checks the pinned SHA-256 and preserves existing matching files. A mismatched
existing model is rejected rather than overwritten. No downloads occur on replies.
Torch/NumPy do not become application dependencies. Select this profile in your
existing configuration (use the absolute path to your checkout):

```toml
[voice]
profile = "/absolute/checkout/experiments/disc_assistant/assistant/voice/profiles/silero-ru-cpu.toml"
```

Restart the existing web owner once. In the browser choose Russian, enable spoken
replies, and choose **All available replies** when testing successful responses.
First synthesis includes model loading; later calls reuse the process. Timeout
or cancellation kills/reaps the owned worker; no text is replayed automatically.

## Optional Vosk TTS

The `vosk_tts` factory supports the pinned `vosk-model-tts-ru-0.9-multi`, separately
from Vosk STT and the Sherpa recognizer. Its five speaker IDs are `0`, `1`, `2`
(female) and `3`, `4` (male), as declared by the model's `speaker_id_map`. Names
from older Vosk releases are not assumed to identify the 0.9 voices.

```sh
python3.12 -m experiments.disc_assistant.assistant.voice.vosk_setup
```

Installation uses a separate `~/disc-speech/vosk-tts/.venv`, vosk-tts 0.3.61,
ONNX Runtime 1.23.2 and the reviewed 746.5 MiB archive. The installer verifies its
SHA-256, safely extracts it, and checks every model/dictionary/config/tokenizer and
model-card hash. Existing mismatched files are rejected, not overwritten.
`--archive /absolute/path/model.zip` reuses an already downloaded matching archive.
Models and environments remain outside Git; requests never download anything.

Select the [Vosk CPU profile](../../assistant/voice/profiles/vosk-ru-cpu.toml) with
`voice.profile`, then restart the existing web owner. It selects speaker 2 and
`ru_numbers`; change `speaker_id` to an integer from 0 to 4. The adapter accepts
an explicit `SynthesisRequest.voice` override as the corresponding string ID.
It supports Russian replies only and never switches language or engine implicitly.
For first-load headroom, set `timeout = 120` in the existing `[tts]` table too;
the browser response deadline also caps the entire call.
The mixed phrase `Играет Linkin Park — Numb.` failed in the upstream phoneme map
(`KeyError: u`). The adapter reports an explicit synthesis failure; it does not
silently delete names or switch to another model.

Both ONNX networks explicitly use CPU execution, two intra-op threads by default,
one inter-op thread and sequential execution. The worker loads local reviewed
files directly into the pinned Vosk `Synth` interface rather than using upstream
model discovery/download. Output is native mono 16-bit PCM at 22,050 Hz. Model,
voice, file hashes, ONNX version, normalization and runtime timings are recorded.
Cancellation and timeout reuse the shared owned-worker cleanup contract.

To compare every voice, add the
[all-voices profile](../../assistant/voice/profiles/vosk-voices-ru.toml) to the
listening command below and append
`--provider vosk_0 --provider vosk_1 --provider vosk_2 --provider vosk_3 --provider vosk_4`.
The comparison finishes all phrases for one provider and closes its runtime
before loading the next; five voices do not keep five model copies in memory.
The existing live web TTS choice is not changed by the comparison tool.

Vosk TTS code, the 0.9 model README and its bundled BERT card declare Apache 2.0.
Keep both model cards with distributions; the adapter code remains MIT. No board
performance or music-name pronunciation acceptance is inferred from this integration.
See [the integration report](../reports/2026-09-21-vosk-tts.md).

## Optional RUNorm

Install the heavier normalizer separately; it is not needed for `ru_numbers`:

```sh
python3.12 -m experiments.disc_assistant.assistant.voice.runorm_setup
```

This installs three pinned upstream snapshots (small normalizer, tagger,
kirillizator) under `~/disc-speech/runorm/models`, plus a separate `.venv`. The
installer records a digest over weights/tokenizers/configuration in `models.json`;
the worker verifies it before loading and sets Hugging Face/Transformers offline
mode. The optional [RUNorm profile](../../assistant/voice/profiles/silero-runorm-ru.toml)
selects Silero with RUNorm instead of rule normalization. For a custom installation,
set normalization `python`, `models`, `model_sha256`, `threads`, and `timeout`.
The outer TTS/response timeout still caps the entire normalization-plus-synthesis call.

The real integration probe produced `двадцать пятьпроцента` for `25%` and
`эн йю эм би` for `Numb`. These are preserved observations, not corrected reference
labels. RUNorm remains opt-in; see [the dated report](../reports/2026-09-21-silero-normalization.md).

## Device-free listening comparison

Generate six synthetic replies using existing Piper and the two optional profiles:

```sh
experiments/disc_assistant/assistant/.venv/bin/python \
  -m experiments.disc_assistant.evaluation.tts_compare \
  --profile experiments/disc_assistant/assistant/voice/profiles/silero-ru-cpu.toml \
  --profile experiments/disc_assistant/assistant/voice/profiles/silero-runorm-ru.toml \
  --provider piper --provider silero_ru --provider silero_runorm \
  --output /tmp/disc-tts-listening-new
python3 -m http.server 8092 --bind 127.0.0.1 --directory /tmp/disc-tts-listening-new
```

Open `http://127.0.0.1:8092`. Output includes WAVs, a listening page and `results.json`
with fingerprints, normalization policy and timings. `--text` accepts explicit
synthetic/custom text; keep private outputs outside Git. The tool never creates an
Application, opens Controller, or changes a player. Differences in preprocessing,
transport and runtime mean these timings are not an isolated model benchmark.

## Dependencies and model notices

Project/adapters remain MIT. Downloaded models and optional dependencies retain
separate licenses: Silero `v5_5_ru` uses
[CC BY-NC-SA 4.0](https://github.com/snakers4/silero-models/blob/master/LICENSE).
MIT licensing of this repository does not relicense those weights or remove their
noncommercial condition. They are external optional downloads, not tracked assets.
RUNorm's code and the three selected model cards declare Apache-2.0; preserve the
upstream cards downloaded alongside its models. See [RUNorm](https://github.com/Den4ikAI/runorm).

[Piper](https://github.com/OHF-Voice/piper1-gpl) is GPL-3.0; its dependency license
is distinct from the repository's MIT code. The pinned model cards identify
[Irina data license as Unknown](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ru/ru_RU/irina/medium/MODEL_CARD)
and [Alba data as CC BY 4.0](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_GB/alba/medium/MODEL_CARD).
These cards also describe fine-tuning ancestry. Dataset labels alone are not a
blanket license conclusion for every artifact. Preserve downloaded cards and
review engine, dependencies, model lineage and attribution before distributing
a hardware/product image. A separate process does not remove license obligations.

## Irina checkpoint, 2026-09-19

The voice migration and previous-track aliases pass **339 prototype tests**.
A real managed install preserved the existing Whisper path and produced an Irina
response at 22,050 Hz, with matching pinned voice/config hashes and a nonsilent
PCM payload. The explicit CLI sample was converted to 16 kHz with provenance.
Listening preference and music-name pronunciation remain human checks; this does
not replace or rewrite the earlier Denis sample results below.

## Validation checkpoint, 2026-09-18

The initial Denis/Alba bundle in a clean `/tmp` configuration completed `setup --all`; both Docker healthchecks
passed on macOS arm64. Real RU/EN Piper responses returned nonsilent 22,050 Hz WAV.
A web Pause against the synthetic DISC peer was confirmed, followed by successful
Piper WAV delivery, with exactly one device write. Browser inspection also verified Resume and `Reply played`.
**330 prototype tests** plus JavaScript capture and reply-delivery checks passed.
This checks plumbing, not
physical audio quality or Raspberry Pi performance.

An additional synthetic round trip deliberately retained both failures: Whisper
base recognized Piper's isolated `Пауза` as `База!` and `Pause` as `Purse.`. Do not
count this as successful recognition or infer human-microphone accuracy from it.
The original sample/measurement report is in the local `/tmp/disc-piper-validation`
validation directory; no personal audio is tracked. Voice preference and mixed-name
pronunciation still need human listening and a larger controlled comparison.
