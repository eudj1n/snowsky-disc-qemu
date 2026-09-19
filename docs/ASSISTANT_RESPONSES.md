# Assistant user responses

Implemented in the research prototype. The Assistant adds localized user feedback
to existing operation results; Controller remains responsible for device state and
verified operations. File STT and explicit sample TTS now run through
[speech adapters](ASSISTANT_VOICE.md). Optional [Piper browser delivery](ASSISTANT_TTS.md)
is implemented; dialogue remains disabled.

## Response contract

A confirmed pause with default settings includes:

```json
{
  "action": "pause",
  "status": "confirmed",
  "response": {
    "code": "playback.paused",
    "text": "Воспроизведение приостановлено.",
    "language": "ru",
    "speak": false,
    "interactive": false
  }
}
```

Existing fields such as `operation_id`, `state`, `mutation_attempted` and
`request_id` retain their meaning. This example omits them for clarity.

| Field | Meaning |
| --- | --- |
| `code` | Stable, language-independent meaning; consumers must not parse translated text |
| `text` | Plain localized text, or `null` when no user-facing message is appropriate |
| `language` | The active interaction locale, shared with input; independent of player UI |
| `speak` | Whether an audio adapter may speak this response; not evidence of audio delivery |
| `interactive` | Reserved for future dialogue; always `false` in this implementation |

`system.no_message` has `text: null`, `speak: false` and no translation template.
Successful maintenance/inspection commands use it, including `/help`, `/status`,
`/queue`, `/response`, `/history`, `/sync`, `/index` and `/rank`.
Their diagnostic payloads remain available. Unrecognized commands, no matches and
failures have localized messages. Debug help and technical diagnostics remain
English; the active locale governs command interpretation and user-facing `response.text`.
Successful language changes receive confirmation in the new locale.

Console and one-shot CLI requests use the same response policy. JSON includes the
text even when `speak` is false. TTY help/clear/exit retain their existing presentation;
no audio is produced. Parsed application errors also emit structured JSON in the
one-shot CLI, alongside existing stderr diagnostics and a nonzero exit status.
Configuration/argument errors before a valid application context may have only a
technical diagnostic. History inspection stays outside journaling so clearing or
exporting history does not reinsert requests.

## Preferences

```text
/response
/language en
/response mode none
/response mode errors
/response mode all
/response reset
```

Equivalent offline commands:

```sh
./research/disc_assistant/run.sh language en
./research/disc_assistant/run.sh response mode errors
./research/disc_assistant/run.sh response reset
```

| Mode | Speech eligibility |
| --- | --- |
| `none` | No replies eligible; text remains available for debugging |
| `errors` | Errors, unknown commands, no match, interrupted or uncertain results only |
| `all` | Every nonempty user response, including successful playback controls |

`scheduled` and `startup` sources always have `speak: false`, regardless of mode.
Use `run.sh --source scheduled --language en ask "Pause"` for an explicitly scheduled request.
`interactive` describes dialogue behavior, **not** the interactive console source.

The initial defaults are Russian interaction and `errors` mode. They can be set in
TOML:

```toml
[language]
locale = "en"

[response]
mode = "errors"

[dialogue]
enabled = false
```

`/response` saves `response.mode` in the existing Assistant settings table.
Language is stored once as `language.locale`; `/language` updates input and output
together. `/response reset` restores the configured speech mode and preserves locale.
Saved values override TOML; startup `--language CODE` overrides and persists locale.
Invalid values preserve settings. Older split-language settings migrate atomically;
see [architecture and migration](ASSISTANT_ARCHITECTURE.md).

Preferences are scoped to the application data directory. No library sync or
index rebuild is needed. An open console reloads preferences through settings
commands; TOML changes require restart. `/response language` is no longer supported.

Setting `dialogue.enabled = true` is rejected explicitly. The reserved field does
not enable questions, choices, confirmations, pending requests or extra player
commands. Best-match playback remains automatic.

## Outcome accuracy and future adapters

Templates are chosen from verified result status and outcome, never from the
requested action alone. An unconfirmed launch uses `command.uncertain` even if a
track was selected. `not_sent`, an already-satisfied control and a confirmed
change have distinct messages. Previous-track restart is distinguished from a
track change. Stop describes the current Assistant policy honestly: pause while
preserving position and queue. Missing track metadata uses a generic success
message rather than guessing a title.

Playback templates use observed metadata first, then selected metadata where
available. Values are inserted as plain text, with control characters removed
and lengths bounded; they are never evaluated as templates. Translations cannot
issue commands, change the execution policy or enable dialogue.

The journal stores the exact generated response in the result and records the
response language, speech policy, contract version and template hash in request
context. Preference-change events record the newly selected template context.
This records generation/eligibility only, not display or playback delivery.
History made before this increment remains readable without response fields.

The [speech provider contracts](ASSISTANT_ARCHITECTURE.md#speech-provider-contracts)
now have file and resident-service adapters. Explicit sample synthesis bypasses
response policy and does not claim that a reply was spoken. Web consumes `text`,
`language` and `speak` through Piper, with separate synthesis and browser-reported
playback events. Delivery failures never rewrite execution outcomes or trigger
command retries. Future dialogue support must add a request-bound
pending state, expiry and explicit transitions before any response can set
`interactive: true`. A boolean alone is not a dialogue state machine.

See [adding locales](ASSISTANT_LOCALES.md), the
[command reference](ASSISTANT_COMMANDS.md) and [journal](ASSISTANT_HISTORY.md).

Audio failures use `speech.no_speech`, `speech.invalid` and `speech.unavailable`
before interpretation/execution. These distinguish an empty/digital-silence result,
invalid audio/provider output, and unavailable processing. Raw provider diagnostics
are not inserted into localized templates. The existing command response is used
after successful transcription; no second execution policy is introduced.
