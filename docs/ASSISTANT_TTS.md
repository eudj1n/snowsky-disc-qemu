# Local speech services and Piper replies

The desktop web path is **microphone → Whisper Server → Assistant → Controller →
localized response → Piper → browser audio**. Web always uses Whisper Server;
one-shot CLI/file workflows may still explicitly select the CLI STT backend.
Piper is an optional `SpeechSynthesizer`, independent of interpretation and player
control. Audio plays on the computer running the browser, not through DISC.

## One installation command

Prerequisites: **Python 3.11+ and running Docker with Compose** (Docker Desktop on
macOS). These system prerequisites are installed by the owner. From the checkout:

```sh
./research/disc_assistant/run.sh setup --all
# Then edit ~/disc-assistant.toml: device.key, host and TCP/HTTP ports.
./research/disc_assistant/run.sh web --bootstrap
# Open http://127.0.0.1:8090
```

For an existing custom config, pass `--config /absolute/path/player.toml` before
`setup` and `web`. Close another Assistant console/web owner first. Installation
itself never connects to a player or starts containers.

`setup --all` performs the following:

1. Creates/reuses the prototype venv; installs runtime and optional speech setup/
   sample-conversion dependencies. Generates missing config/search credentials.
2. Downloads multilingual Whisper **base**, Piper **RU Denis medium** and
   **EN Alba medium**, their ONNX configuration and model cards. URLs use fixed
   repository revisions and every asset has a checked SHA-256 in
   [`models.json`](../research/disc_assistant/assistant/voice/services/models.json).
3. Builds CPU-only Whisper Server **v1.9.4** and Piper **1.4.2** images; pulls the
   existing Typesense image. No host CMake, Piper Python environment or GPU is needed.
4. Updates only `[speech]`, `[tts]` and `[services]` for this bundle. Other settings
   and comments survive; the original TOML is saved beside it as
   `.before-speech-<id>` with private permissions before atomic replacement.

To choose the larger multilingual model explicitly:

```sh
./research/disc_assistant/run.sh setup --all --whisper-model small
```

Base is the default desktop smoke-test option, not a quality recommendation.
See [the measured base/small comparison](ASSISTANT_VOICE.md). Repeating setup
reuses verified model bytes, preserves search keys and updates the configured
model choice. A checksum mismatch stops installation rather than overwriting
unknown local files. First installation needs network access, image-build time
and disk space; subsequent command processing is local. Models/cards live under
`<storage.data_dir>/speech`, outside Git. Setup is not a complete transitive
lockfile: OS image tags and package dependency resolution can still change.

`setup` without `--all` retains the lightweight text-only setup. Offline NLU
training/embedding experiments are separate optional environments and are not
installed by this runtime command.

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
  ./research/disc_assistant/run.sh setup --all
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
./research/disc_assistant/run.sh speech-up
./research/disc_assistant/run.sh speech-down
# Existing search-only lifecycle:
./research/disc_assistant/run.sh down
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

`voice/text.py` is the TTS-only text preparation point, currently `identity-v1`.
No automatic transliteration is enabled. Future locale pronunciation dictionaries
may turn a mixed-script music name into an appropriate spoken form, after paired
listening checks. Keep `response.text`, search input, catalog tags and command
history unchanged. Bump preparation provenance when rules change; evaluate artist
names, abbreviations and titles separately. TTS corrections are not search aliases
and must not alter frozen speech evaluation inputs silently.

## Dependencies and model notices

[Piper](https://github.com/OHF-Voice/piper1-gpl) is GPL-3.0; its dependency license
is distinct from the repository's MIT code. The pinned model cards identify
[Denis data as CC0](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ru/ru_RU/denis/medium/MODEL_CARD)
and [Alba data as CC BY 4.0](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_GB/alba/medium/MODEL_CARD).
These cards also describe fine-tuning ancestry. Dataset labels alone are not a
blanket license conclusion for every artifact. Preserve downloaded cards and
review engine, dependencies, model lineage and attribution before distributing
a hardware/product image. A separate process does not remove license obligations.

## Validation checkpoint, 2026-09-18

A clean `/tmp` configuration completed `setup --all`; both Docker healthchecks
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
