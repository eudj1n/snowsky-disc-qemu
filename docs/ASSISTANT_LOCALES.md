# Contributing Assistant locales

New locales for existing command meanings and user responses require TOML files,
not Python registry edits. Files are discovered by name. The contributor validator
checks completeness, within-locale phrase conflicts and template parameters before a locale is
used with a device.

## Add a locale

1. Copy `research/disc_assistant/assistant/locales/en.toml` to `<code>.toml`
   in the same directory.
2. Copy `research/disc_assistant/assistant/locales/replies/en.toml` to
   `replies/<code>.toml`.
3. Translate the literal command phrases and response templates. Keep all semantic
   keys. Update response metadata `code`, `name` (English display name) and
   `native_name` (local display name).
4. Validate the files, add representative parsing/response tests, then enable the
   new locale explicitly. Restart a running console after installing/editing files.

Use a lowercase language tag: `fr`, `de`, `pt-br`, for example. It must match both
filenames and `[locale].code`. Installing a locale does not change the active locale. A contribution should contain both complete files, with no English
placeholder translations unless the wording is intentionally shared.

Example response metadata:

```toml
[locale]
code = "fr"
name = "French"
native_name = "Français"

[messages]
"playback.paused" = "Lecture en pause."
"playback.started" = "Lecture de {title} — {artist}."
"language.changed" = "La langue est maintenant le français."
```

This fragment illustrates the format; copy and translate the **entire** reference
file. Partial response catalogs are rejected; there is no silent English fallback.

## Command dictionary rules

Each semantic key maps to a nonempty array of literal phrases. All of these keys
are required by the contributor validator:

| Table | Keys |
| --- | --- |
| `commands` | `play`, `pause`, `resume`, `stop`, `next`, `previous`, `set_language` |
| `targets` | `artist`, `track` |
| `versions` | `live`, `remix`, `acoustic`, `instrumental`, `demo`, `karaoke`, `cover`, `remaster` |

Values are phrases, not regexes. Case and repeated whitespace are normalized;
play/target prefixes prefer the longest phrase. Controls match a complete phrase.
The current grammar requires whitespace between play/target prefixes and the
music query. Write and test natural forms that fit this grammar; languages needing
other segmentation or inflection require an explicit parser enhancement.

Within a table, one normalized phrase cannot map to different meanings. The
application loads one locale at a time; each contributed locale is validated
independently. It does not need to share a combined grammar with other locales.
The locale version phrases express query constraints. Common metadata labels are
recognized separately through `library/version_markers.toml`, regardless of input locale.

Artist/title aliases belong to user configuration, not the command dictionary.
Do not translate music metadata or add device protocol values to locale files.
Existing internal parser tests may use partial dictionaries, but a contributed
locale must cover the full supported vocabulary.

Optional `[language_names]` entries map target locale codes to names in the current
language, for example `en = ["anglais"]` in French. `commands.set_language` supplies
the switching prefix, such as `change la langue en`. Codes and installed English/native
display names work as targets without extra registry entries. Keep names unambiguous;
adding a translated name for a new target to existing locales is optional.

Common recording labels also remain explicit query constraints across locales:
`Включи Linkin Park — Numb live` requires a live edition even in Russian mode.
Locale-specific version phrases extend those shared labels. A missing requested
edition is not silently replaced with a studio recording.

## Response template rules

The keys and allowed parameters are defined by `MESSAGE_FIELDS` in
[`responses.py`](../research/disc_assistant/assistant/responses.py). The complete
[English catalog](../research/disc_assistant/assistant/locales/replies/en.toml) is
the copyable reference; Russian is another complete example.

Only `playback.started` and `playback.track_changed` accept parameters. Both require
`{title}` and `{artist}`. Translators may reorder them and surrounding words.
All other templates take no parameters. Use `{{` and `}}` for literal braces.

Unknown/missing keys, missing parameters, attribute/index access, conversions,
format specifiers, empty templates and control characters are rejected. Templates
must be single-line plain text of at most 1,000 characters. No executable code,
HTML, ANSI escapes, conditions or locale-specific device logic is allowed.
Rendered text is capped at 2,000 characters, matching journal retention.
The loader does not currently implement plural rules or grammatical inflection.
Avoid templates requiring them; adding those features is a separate contract change.

Preserve meaning, especially for uncertainty and partial support: a selected song
is not proof of playback, a timeout is not proof of failure, and Stop currently
pauses while retaining the queue. Do not make a translated message ask a question
or promise confirmation: dialogue is reserved and disabled. Speech policy is
application configuration, not a translator-controlled field.

## Validate and test

From the repository root, after the prototype's normal `run.sh setup`:

```sh
# No config, device connection, search server or credentials required.
research/disc_assistant/assistant/.venv/bin/python -m research.disc_assistant.assistant.responses
# Validate a specific locale, or several independent locale pairs.
research/disc_assistant/assistant/.venv/bin/python -m research.disc_assistant.assistant.responses fr
research/disc_assistant/assistant/.venv/bin/python -m research.disc_assistant.assistant.responses ru en fr
# Prototype regression suite, including synthetic local network fixtures.
./research/disc_assistant/run.sh test
```

`run.sh locales` or console `/locales` also validates installed files using the
normal configuration. Validation lists locale metadata and the number of response
templates. It does not establish translation quality; a fluent speaker should
review phrasing and representative commands.

Add tests alongside
[`test_responses.py`](../research/disc_assistant/assistant/tests/test_responses.py)
and [`test_languages.py`](../research/disc_assistant/assistant/tests/test_languages.py).
Cover natural play/artist/track commands, each control, version markers, casing,
multiword forms and a localized success/uncertain response. These tests should use
synthetic data and require no physical player. The completeness test automatically includes all installed
locales; no runtime Python change is needed.

Select one locale for both input and output:

```text
/language fr
/response mode errors
```

Completion discovers the new filenames automatically. Changing locale updates
commands and responses together. It does not restrict music metadata or switch
the player UI. See the [response contract](ASSISTANT_RESPONSES.md) for persistence,
speech eligibility and reserved dialogue semantics.
