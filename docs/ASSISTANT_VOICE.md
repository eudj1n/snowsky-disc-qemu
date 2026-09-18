# File-based speech prototype

Implemented on **2026-09-18** under `research/disc_assistant/`. This first speech
slice accepts a WAV file, transcribes it locally, then uses the existing interpreter,
ranking and guarded Controller execution. It also synthesizes reproducible input
samples through the same `SpeechSynthesizer` interface reserved for future replies.

## Current scope

| Area | Implemented | Still pending |
| --- | --- | --- |
| Input | Bounded PCM WAV files, explicit active locale, raw transcript and normalized command text | Microphone, resampling/compressed formats, streaming, wake word, voice activity detection |
| STT | Local `whisper.cpp` CLI adapter, explicit model, timeout/cancellation, model fingerprint | Resident model/server, GPU tuning, remote provider, music vocabulary hints |
| TTS | Local macOS `say` adapter, configured voices, WAV and provenance sidecar | Portable Pi/Linux engine, automatic response synthesis and speaker delivery |
| Integration | `transcribe`, `rank --audio`, `ask --audio`, equivalent console commands | Questions, confirmations and dialogue |
| Evaluation | RU/EN synthetic corpora, interpretation comparisons, mismatch reports | Human/noisy recordings, catalog selection evaluation, physical-player speech acceptance |

There is no automatic model download, provider fallback, audio playback or audio
retention in the command journal. `ask --audio` is an explicit playback/control
request; `transcribe`, `rank` and `speech-check` do not dispatch device mutations.
The persistent console still connects normally on startup, even for preview commands.

### Recorded acceptance

The [2026-09-18 report](../research/disc_assistant/assistant/voice/evaluations/2026-09-18.json)
retains model and sample hashes, source expectations, recognized text and actual
intentions. On macOS 26.6 arm64 with Milena/Samantha at 175 words/minute:

| Multilingual model | Russian | English |
| --- | --- | --- |
| `base` | 3/6 | 3/6 |
| `small` | 4/6 | 4/6 |

`small` passed pause, next, language switching and rejection of non-command text
in both languages. Artist/track text still differed: examples include Russian
`Линкин Парк` versus the authored `Linkin Park`, and English `Lincoln Park` or
`Nom` versus `Numb`. The Russian mixed-name synthesis itself may affect recognition;
this experiment does not isolate STT from TTS pronunciation quality. No alias or
expected-output changes were made to turn these mismatches into passing cases.
The small-model pass measured roughly 0.84–1.28 seconds per transcription on this
host, including subprocess/model startup. These are a few sequential samples,
not a latency benchmark or Pi estimate.

The owner-requested [base/small comparison rerun](../research/disc_assistant/assistant/voice/evaluations/2026-09-18-base-small-comparison.json)
used those exact saved WAVs and model hashes, without resynthesis or changes to
the corpus, interpreter or device configuration. It confirmed the same outcomes:

| Model | RU cases passed | EN cases passed | Median RU STT | Median EN STT |
| --- | --- | --- | --- | --- |
| `base` | 3/6 | 3/6 | 347 ms | 302 ms |
| `small` | 4/6 | 4/6 | 960 ms | 861 ms |

This is one sequential pass per model/locale, with subprocess/model startup
included and no controlled cache state. Base was about 2.8 times faster in this
pass but additionally failed Russian language switching and English pause.
Both models still failed the authored artist/track reference expectations.
The metric is expected-intention/reference agreement, not word error rate or
measured catalog selection: Cyrillic transliteration versus a Latin canonical name
counts as a mismatch even when an alias could resolve it later. This tiny synthetic
set does not justify replacing small on quality grounds. Base remains an explicit
lower-latency option; test representative human speech and catalog aliases next.

An additional native STT → interpreter → Controller test sent exactly one pause
to the synthetic TCP DISC peer and received a confirmed paused outcome, using
one handshake. No physical player or real microphone was used. **216 prototype
tests pass**, covering speech validation, errors, cancellation, preview/execution,
locale changes, reconnect protection, corpus checks and the existing text path.

Next: evaluate representative human recordings and music-name matching, add a
portable TTS adapter for Linux/Pi, then microphone capture and reply delivery.

## Install and configure

Python dependencies are unchanged. The STT adapter invokes an external
[`whisper-cli`](https://github.com/ggml-org/whisper.cpp/tree/v1.9.4/examples/cli).
The exercised build is **whisper.cpp v1.9.4**, CPU-only. The following source build
requires Git, CMake and a C/C++ compiler. Run it outside this repository:

```sh
mkdir -p "$HOME/disc-speech"
git clone --depth 1 --branch v1.9.4 https://github.com/ggml-org/whisper.cpp.git "$HOME/disc-speech/whisper.cpp"
cmake -S "$HOME/disc-speech/whisper.cpp" -B "$HOME/disc-speech/whisper.cpp/build" -DGGML_METAL=OFF -DWHISPER_BUILD_TESTS=OFF
cmake --build "$HOME/disc-speech/whisper.cpp/build" --target whisper-cli -j 4
bash "$HOME/disc-speech/whisper.cpp/models/download-ggml-model.sh" small "$HOME/disc-speech"
```

Use a **multilingual** model, not an `.en` model, for Russian input. Both `base`
and `small` were exercised; neither has passed the entire small synthetic corpus.
Models are replaceable configuration, not bundled application assets. Model files
can be hundreds of megabytes; keep them outside the checkout.

Add the following to your existing Assistant TOML, substituting your absolute
executable path. `model` also accepts `~`; executable paths must be absolute or
an executable name available on `PATH`.

```toml
[speech]
whisper_executable = "/absolute/path/disc-speech/whisper.cpp/build/bin/whisper-cli"
model = "~/disc-speech/ggml-small.bin"
timeout = 120
max_seconds = 30
rate = 175

[speech.voices]
ru = "Milena"
en = "Samantha"
```

On macOS, inspect installed voices with `say -v '?'`. Voice names must be installed
on that machine. The adapter uses `/usr/bin/say` with file output, never speakers.
`rate` is the synthesis rate in words per minute. Other operating systems can use
file transcription, but this initial TTS adapter explicitly reports unavailable.

`timeout` is 1–600 seconds per speech provider invocation; default 120.
`max_seconds` is 1–120; default 30. WAV input is limited to 8 MiB and must be
**16-bit PCM, 16 kHz, mono**, with a complete, nonempty data payload. The application
rejects other formats rather than silently converting or truncating them. Generated
samples already use the required format. No new Docker service is needed.

## Use it

From the repository root, generate a single test file:

```sh
./research/disc_assistant/run.sh --language ru synthesize 'Пауза' --output /tmp/disc-pause.wav
./research/disc_assistant/run.sh --debug transcribe /tmp/disc-pause.wav
./research/disc_assistant/run.sh --debug rank --audio /tmp/disc-pause.wav
```

The output path and its `.wav.json` sidecar must not already exist. The sidecar
records text, locale, provider/OS version, voice, rate, WAV format/duration/hash
and synthesis timing. Existing recordings are never overwritten. An interrupted
write may leave a partial artifact; choose a new output path for the next run.

To execute the recognized command on the configured device:

```sh
./research/disc_assistant/run.sh ask --audio /tmp/disc-pause.wav
```

Close an existing console before one-shot `ask`, as with typed commands. Inside
the persistent console, use its existing connection:

```text
/debug on
/transcribe "/tmp/disc-pause.wav"
/rank --audio "/tmp/disc-pause.wav"
/ask --audio "/tmp/disc-pause.wav"
```

Only `ask` executes. Previewing a language-switch recording does not change the
locale; executing it uses the normal preference handler and replies in the new
locale. The transcription retains its original input locale. STT never auto-detects
or silently changes Assistant language. Spoken slash commands are not accepted as
administrative commands: all recognized speech enters the natural interpreter.

Inputs with spaces must be quoted. Relative audio/corpus/output paths passed via
`run.sh` resolve against the directory where the launcher was called. The returned
`transcription` includes raw `text`, `command_text`, `locale`, provider, audio hash
and format, and `transcription_ms`. Only surrounding whitespace and final sentence
punctuation (`. ! ?` and their full-width equivalents) are removed for command input.
Names, transliteration, synonyms and grammar are not silently corrected. Raw text
is retained so this normalization can be inspected, including titles with punctuation.

## Reproducible samples and evaluation

```sh
./research/disc_assistant/run.sh --language ru speech-samples /tmp/disc-samples-ru
./research/disc_assistant/run.sh --language ru speech-check /tmp/disc-samples-ru
./research/disc_assistant/run.sh --language en speech-samples /tmp/disc-samples-en
./research/disc_assistant/run.sh --language en speech-check /tmp/disc-samples-en
```

Each generation requires a **new directory**. It creates six WAV/sidecar pairs
and `manifest.json`, covering controls, artist/track requests, a language change
and non-command text. A partial generation is marked incomplete and cannot be
evaluated as a complete corpus. Checks verify file hashes and the active locale.
`speech-check` returns JSON and exits 1 on any mismatch/provider error, 0 only when
every case passes. Redirect stdout to retain a report; debug events go to stderr.

The report compares validated intentions, normalizing case/whitespace in string
fields. It does not require exact transcription punctuation, use the expected text
as a recognition prompt, access a media catalog, execute commands or apply settings.
Music reference fields must match the authored expectation; equivalent music
selection through catalog aliases needs a separate ranking evaluation. Actual
recognized text, expected/actual intent and STT timing remain visible per case.
Synthetic voices exercise the pipeline; these scores do not measure human speech
accuracy or prove suitability for unattended operation.

Community corpora live in
[`assistant/voice/samples/`](../research/disc_assistant/assistant/voice/samples/).
For a new locale, add a `<locale>.json` file with `version: 1`, `locale`, and 1–100
`cases`. Each case needs a unique safe filename `id`, source `text` and an
`expected` object: `{"status":"recognized","intent":{...}}` or
`{"status":"unrecognized"}`. Intents use the existing dataclass fields from
[the architecture contract](ASSISTANT_ARCHITECTURE.md#interpretation). Generation
checks those expectations against the interpreter before synthesis. A custom corpus
can be selected with `speech-samples DIR --corpus FILE.json`.

Add its voice to `[speech.voices]`. If the locale code differs from the STT engine
language code, configure a mapping under `[speech.stt_languages]`, for example
`en-us = "en"`. Never map to `auto`; unsupported languages fail explicitly. These
are deployment settings, not locale-specific Python branches. Adding command and
reply dictionaries still follows [the locale guide](ASSISTANT_LOCALES.md).

## Execution, storage and failure boundaries

Subprocesses receive an argument array, never shell code. WAV/model paths and
synthesized text cannot add executable flags; synthesis text is read from a private
temporary file. Timeouts/cancellation terminate and reap the child before deleting
temporary input/output. Engines run once per request; model loading is included in
STT latency. GPU use and decoding temperature fallback are disabled for this slice.

No usable speech, invalid audio/output and unavailable providers have distinct
localized responses. Digital all-zero PCM is rejected before STT. This is **not**
a general silence/noise detector: other nonspeech audio can still be hallucinated
by a model. Result types, locale, length and control characters are checked before
interpretation; the existing allowlisted intent boundary remains authoritative.

Console execution pins connection generation before transcription and checks it
after interpretation. A reconnect during STT cannot dispatch the stale command.
Fresh Controller checks still run before mutations. Recognition, synthesis or
output failure never causes automatic command replay.

The journal stores `[audio]` as the request input, audio hash/format/duration,
provider/model evidence, transcript, normalized command, interpreter/search results
and timing. It does not copy input audio or persist its source path. Audio placeholders
are excluded from persistent terminal recall. Explicit synthesis/corpus commands
save artifacts only at the requested destination. Model hashes are cached by path,
size and modification time within the process; historical journals are unchanged.

`response.speak` remains eligibility only. Manual sample synthesis is independent
of it. Before automatic replies, add a delivery layer that checks `speak`, manages
interruptions and records synthesis separately from actual playback. Microphone,
TTS output, online engines, dialogues and Pi deployment remain separate milestones.
