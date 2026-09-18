# Speech input and file-based experiments

Current browser entry point: [Disc Assistant Web](ASSISTANT_WEB.md) records a bounded
microphone utterance and uses this same WAV/STT pipeline. Historical file-only
measurements below do not establish human microphone accuracy.

Implemented on **2026-09-18** under `research/disc_assistant/`. This first speech
slice accepts a WAV file, transcribes it locally, then uses the existing interpreter,
ranking and guarded Controller execution. It also synthesizes reproducible input
samples through the same `SpeechSynthesizer` interface now used for Piper replies.
The measurements below preserve the earlier macOS sample/model cohorts.

## Current scope

| Area | Implemented | Still pending |
| --- | --- | --- |
| Input | Bounded files/browser microphone WAV, explicit locale, raw transcript and normalized command text | Compressed uploads, streaming, wake word, voice activity detection |
| STT | Local `whisper.cpp` CLI and resident server; web always uses server; explicit model and bounded processing | GPU tuning, remote provider, human microphone acceptance |
| TTS | Local Piper service/browser replies and macOS `say` file adapter, configured voices and provenance | Hardware/Pi performance and human voice-quality acceptance |
| Integration | `transcribe`, `rank --audio`, `ask --audio`, equivalent console commands | Questions, confirmations and dialogue |
| Evaluation | RU/EN synthetic corpora, separate interpretation and catalog-selection checks | Quantified human/noisy recordings and physical-player speech acceptance |

Runtime requests never download models or switch providers implicitly. The explicit
`setup --all` installer downloads pinned assets. Browser reply playback is opt-in;
raw audio is not retained in the command journal. `ask --audio` is an explicit playback/control
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

Current follow-up: evaluate representative human recordings and music-name
pronunciation. Browser capture and Piper reply delivery are now implemented.
The owner reports microphone play/stop working on a physical player; this does
not replace the pending quantified RU/EN cohort.

## Install and configure

For the current web runtime, use [common speech setup](ASSISTANT_TTS.md):

```sh
./research/disc_assistant/run.sh setup --all
./research/disc_assistant/run.sh web --bootstrap
```

This installs the ordinary runtime, model assets and CPU Docker services. Web
uses Whisper Server only. Optional `--whisper-model small` selects the larger
model explicitly; otherwise setup preserves an installed model and uses base only
for a fresh configuration. Piper supplies RU/EN replies and
sample generation; its native audio is explicitly converted to 16 kHz for saved
STT sample files. No host CMake build is needed for the managed stack.

### Alternative manual CLI installation

The lightweight CLI dependencies are unchanged. The STT adapter invokes an external
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

Without `--catalog`, the report compares validated intentions, normalizing case/whitespace in string
fields. It does not require exact transcription punctuation, use the expected text
as a recognition prompt, access a media catalog, execute commands or apply settings.
Music reference fields must match the authored expectation; equivalent music
selection is measured separately with `--catalog` (below). Actual
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

## Catalog selection evaluation

`speech-check DIR --catalog` adds read-only catalog resolution, retrieval and
ranking after STT and interpretation. It requires a current Typesense projection
and an explicit target for every music case. It never opens a device connection,
executes controls or changes language in response to a sample. As with other CLI
commands, the explicit global `--language CODE` option persists the test locale.

```sh
./research/disc_assistant/run.sh index
./research/disc_assistant/run.sh --language ru speech-check /tmp/disc-samples-ru --catalog
```

New bundled corpora include `selection` on music cases. For existing WAV manifests,
use an overlay rather than regenerating audio or editing hashes:

```sh
./research/disc_assistant/run.sh --language ru speech-check /tmp/disc-samples-ru --catalog \
  --expectations research/disc_assistant/assistant/voice/samples/ru-selections.json
```

Overlay shape:

```json
{"version":1,"locale":"ru","selections":{
  "artist":{"kind":"artist","artist":"Linkin Park"},
  "track":{"kind":"track","artist":"Linkin Park","title":"Numb","album":"Meteora"}
}}
```

The bundled target is the synthetic `Meteora` recording. For a real catalog,
author a separate overlay with the intended actual album, or `null` for explicitly
expected absence. Do not derive targets from the search's selected result. Target
matching normalizes case/whitespace only; aliases cannot change the expected
identity. Identical artist/title/album duplicates remain metadata-equivalent,
not proven identical audio or permanent track IDs.

Reports separate `transcription_match`, `interpretation_match` and music
`selection_passed/selection_total`. In catalog mode each music case passes when
its selection agrees, even when its recognized spelling differs. Non-music cases
still compare intentions. Aggregate `passed/total` therefore combines command
interpretation and music selection; it is not STT accuracy. Per-case
`failed_stage` identifies transcription errors, rejected/non-music interpretation,
search errors, empty retrieval or wrong/filtered ranking. It identifies where
agreement failed, not the root cause of a recognition error. STT and search/rank
milliseconds are separate; raw text, actual intent and selected evidence remain
visible. A changing catalog/index aborts the run to avoid mixed generations.

The transliterated projection is schema version 2. **Run `/index` or `run.sh index`
once after this upgrade**; an otherwise unchanged library does not need `/sync`.
Changes to aliases or the transliteration table also invalidate the index.

Next experiments now include semantic intent matching, phonetic/embedding name
retrieval and optional intent-classifier training. See
[the comparison plan and acceptance criteria](ASSISTANT_NLU_RESEARCH.md).

### Recorded catalog comparison

The [catalog selection report](../research/disc_assistant/assistant/voice/evaluations/2026-09-18-catalog-selection.json)
uses the same saved WAVs, native whisper.cpp base/small and seven synthetic catalog
rows, including other-artist, live and duplicate distractors. After native STT,
the identical transcripts are replayed against the archived lexical-v2 commit
and both lexical-v3 configurations, each with its own rebuilt index.

| Search policy | Correct music selections |
| --- | --- |
| Archived lexical-v2, no aliases | 0/8 |
| Lexical-v3, no aliases | 2/8 |
| Lexical-v3 with explicit observed aliases | 7/8 |

These are four distinct music WAVs evaluated with two STT models, not eight
independent recordings. The experimental aliases are `Lincoln Park` for
`Linkin Park`, and `Nom`/`намп` for `Numb`; they are recorded in the report and
were **not added to user configuration or default runtime rules**. Base's fused
Russian `лингин парбнамп` remains unresolved. Without the title alias, small's
`Линкин Паркнамп` is rejected rather than launching the whole artist.

Small resolves all four music cases only in the alias-tuned comparison; this
is in-sample tuning, not general voice accuracy. It motivates the broader model
comparison instead of indefinitely adding transcript-specific aliases.
Validation: **224 prototype tests** and disposable real Typesense/SDK plus
synthetic-device acceptance pass. No physical player was used.

## Optional resident STT and catalog vocabulary

The CLI backend remains the default. To retain a model between requests, build the
`whisper-server` target from the same reviewed whisper.cpp version and start it
explicitly with the same installed multilingual model:

```sh
whisper-server -m /absolute/path/ggml-base.bin --host 127.0.0.1 --port 18119 -ng -nf -nlp
```

```toml
[speech]
backend = "server"
server_url = "http://127.0.0.1:18119/inference"
model = "/absolute/path/ggml-base.bin"
catalog_hints = false
```

Assistant never starts, reloads or downloads a server/model. The endpoint must be
an explicit loopback IP; redirects and environment proxies are disabled. Responses
are bounded, locale/task checked, and timeout/unavailability never falls back to
another backend. Use a dedicated service whose loaded model matches `speech.model`: the
recorded file digest is operator configuration, not remote attestation.

`catalog_hints = true` supplies at most 64 names / 800 characters from up to 512
rows of the current device snapshot, including semicolon artist members. The
projection is deterministic, opt-in and shared by CLI/server adapters. Logs record
snapshot, digest, count and truncation. This is vocabulary bias, not a transcript
replacement or an expected answer. It can help names and also bias recognition.
Empty hints are sent explicitly on every server request to avoid prompt carryover.
New locales use their reply metadata's English language name to validate server
`verbose_json` language; ensure it matches the installed Whisper language.

See [measured review comparisons](ASSISTANT_REVIEW_EVALUATION.md) and the two
reproducible experiment modules. These measurements do not change the default
base/small choice, microphone status, or physical acceptance.
