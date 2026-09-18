# Assistant interpretation, language and speech boundaries

Implemented in the research prototype on 2026-09-18. This supersedes the earlier
merged-input/separate-response language policy. One locale now governs interaction;
interpreters and speech engines have independent provider contracts.

## Pipeline

```text
Typed text ------------------------+
                                   v
WAV file --> Transcriber -> text -> Interpreter(text, context)
Microphone (future) ------^
                                   |
                           validated intention
                                   |
              +--------------------+-------------------+
              |                    |                   |
       music reference       playback control    language change
              |                    |                   |
    catalog resolver/ranker        |             Preferences
              |                    |                   |
    fresh guarded selection ------> Controller         |
              |                    |                   |
              +------------ operation result ----------+
                                   |
                          localized response
                                   |
                         speak? -> Synthesizer -> AudioOutput
```

Text and WAV-file input, the rules interpreter and response generation run today.
Local `whisper.cpp` and macOS `say` adapters implement the speech contracts; the
latter generates explicit sample files. There is no microphone, external service,
automatic reply playback or dialogue loop. See [file speech](ASSISTANT_VOICE.md)
for setup, corpus evaluation and the measured recognition limitations.

## Interpretation

[`interpreter.py`](../research/disc_assistant/assistant/interpreter.py) defines:

```python
async def interpret(text: str, context: InterpretationContext) -> Interpretation:
    ...
```

Context is an immutable value containing the active locale, a cached playback
label (`unknown` when unavailable) and optional music-name hints. It contains no
Controller, socket, database or mutable application session. CLI interpretation
currently receives unknown playback; console interpretation uses cached state,
without a new network query. Hints default to empty; the full library is not sent
to an external provider automatically.

`Interpretation` has status `recognized`, `unrecognized` or `unsupported` and a
validated intention only when recognized:

| Intention | Meaning |
| --- | --- |
| `Intent(query, kind, artist, title)` | Music request; unresolved names remain text, not guessed track IDs |
| `ControlIntent(action)` | Allowlisted pause/resume/stop/next/previous |
| `LanguageIntent(locale)` | Set one installed, valid interaction locale |

The `RuleInterpreter` wraps the existing literal grammar. Local-model and remote
implementations can implement the same protocol and be explicitly injected into
`Application`, console `run` or CLI `main` in Python. Only the rules backend ships;
there is no configurable network endpoint or automatic local/remote fallback.
Each provider identifies its name, version and `local`/`remote` execution through
`ProviderInfo`. Backend adapters should translate their own transport/model failures
to `ProviderUnavailable`; the boundary also maps unexpected backend exceptions to a sanitized provider error.

`interpret_request` bounds input, validates result types and the intention
allowlist, and records provider identity, locale and interpreted status in the
journal. Invalid output, provider unavailability, unsupported requests and
unrecognized text remain distinct. Cancellation propagates; no provider fallback
or device mutation retry follows it. Future adapters must configure bounded
network/model deadlines and return typed results rather than executable text.

The application interprets a natural request exactly once. The launcher does not
parse commands to decide whether search is needed. It prepares search credentials
when available; absence does not block control or language commands. Maintenance
slash commands remain explicit application commands outside natural interpretation.

[`resolver.py`](../research/disc_assistant/assistant/resolver.py) resolves an
interpreted music reference against the current catalog. It can infer artist/title
boundaries from known names. `ranking.rank` accepts an `Intent`, not raw command
text; search and ranking cannot reinterpret the command. Search result IDs remain
snapshot-scoped. Controller preflight and observed playback remain the authority
for execution, regardless of which interpreter supplied the intention.

The console pins connection generation before transcription and a potentially slow interpreter and
checks it before dispatch, then retains the existing check after search. A request
spanning a reconnect is not sent on the new connection. Fresh playback/control
checks still handle changes within the same connection.

## One interaction locale

```toml
[language]
locale = "ru"

[response]
mode = "errors"
```

`locale` selects command syntax, user response templates and the context supplied
to speech providers. Device UI language remains independent and unknown
through the supported remote contract. Music titles, artist names and aliases may
use any language. A Russian command can contain `Linkin Park — Numb`.

The first startup persists the effective locale even when command journaling is
disabled. Precedence is explicit `--language CODE`, then the saved preference,
then configuration, then the built-in `ru` default. The startup override is durable:

```sh
./research/disc_assistant/run.sh --language en listen
./research/disc_assistant/run.sh --language ru ask 'Включи Linkin Park — Numb'
```

```text
/language ru
Переключи язык на английский
Switch language to Russian
/language reset
```

Natural language changes use the current language's command syntax and the same
settings handler as `/language`. A successful change is acknowledged in the new
language. `/rank`/one-shot `rank` can preview a language intent without applying it.
An executed audio transcription passes through this same handler. `/language` with no
arguments reloads the saved value; reset stores the current TOML default.

Open consoles keep their locale until a settings command reloads preferences or
the console restarts. In-flight requests use their captured configuration. There
is no language auto-detection, mixed command-language mode or independent response
language. `/response` controls only `none|errors|all` speech eligibility. Help and
technical diagnostics remain English; localized user feedback is `response.text`.

Metadata version labels are separate from command language. The library's
[`version_markers.toml`](../research/disc_assistant/library/version_markers.toml)
recognizes recording conventions such as `Live` and `Remastered` even when Russian
is active. The locale's version phrases describe requested constraints; they also
extend metadata recognition for localized labels. No sync/reindex is needed for a
locale switch. Lexical version markers remain heuristics, not recording identity. This behavior
is recorded as `lexical-v2`; journal context also pins the metadata-marker hash.

Common recording labels also remain explicit query constraints across locales:
`Включи Linkin Park — Numb live` requires a live edition even in Russian mode.
Locale-specific version phrases extend those shared labels. A missing requested
edition is not silently replaced with a studio recording.

## Migration and storage

The existing schema-2 settings table stores `language.locale` and `response.mode`.
No catalog/history rewrite or schema bump is required. Migration and startup
resolution occur in one SQLite transaction; validation failure preserves old keys.
Existing configuration files are read compatibly and are never rewritten.

For configuration, explicit `[language].locale` is preferred. Without it, the first
entry of legacy `[language].enabled` supplies the locale; legacy `[response].language`
is used only when no input language exists. With neither, use `ru`.

For saved settings, existing `language.locale` wins. Otherwise the first legacy
`language.enabled` entry wins over the old response locale. Without an input list,
use `response.preferences.language`, then the configured locale. Speech mode is
migrated independently. Both canonical keys are written before the legacy keys
are removed. Explicit `--language` takes precedence over legacy locale selection.

Example: saved input `["ru", "en"]` and response `en/all` become locale `ru`, mode
`all`. The policy deliberately preserves the primary input language. `/language en`
is the explicit way to choose English afterwards. Multiple codes in `/language`
and `/response language` now fail with guidance; they do not create divergent settings.
Corrupt locale/mode values can be repaired with `language reset`/`response reset`.

## Speech provider contracts

[`speech.py`](../research/disc_assistant/assistant/speech.py) defines independent
asynchronous protocols:

| Contract | Input | Output |
| --- | --- | --- |
| `Transcriber.transcribe` | `Audio`, `SpeechContext` | `Transcription(text, locale, no_speech)` |
| `SpeechSynthesizer.synthesize` | `SynthesisRequest(text, context, voice)` | `Audio` |
| `AudioCapture.record` | Maximum recording duration | `Audio` |
| `AudioOutput.play` | `Audio` | Completion or failure |

`Audio` includes bytes, media type, sample rate and channel count. `SpeechContext`
contains locale, request ID and optional music vocabulary. Locale is explicit
context, not a prohibition on foreign artist/title words. A transcription cannot
implicitly switch the application locale. Providers report `no_speech` separately
from failures and preserve cancellation. They share `ProviderInfo` and
`ProviderUnavailable`; capture/output implementations remain independent of engines.

The future response-delivery layer must check `response.speak` before synthesis, record
synthesis and playback delivery separately, and cancel obsolete audio as needed.
An audio failure cannot turn a confirmed device command into a playback failure or
trigger a replay. Current code records generated text/eligibility only; it does
not claim any audio was delivered. Concrete file adapters now run through
`voice/backends.py`: local CLI STT and macOS file TTS, with validated WAV input,
bounded subprocess execution and cancellation. `voice/samples.py` generates and
evaluates explicit per-locale corpora without device commands. Portable TTS,
format conversion, streaming, voice capability discovery and representative
human-speech latency/quality evaluation remain future work.

Dialogue stays disabled: `interactive` is false and `dialogue.enabled=true` is
rejected. These interfaces do not add questions, pending confirmations or choices.
