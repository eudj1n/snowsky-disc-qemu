# Disc Assistant commands

Implementation status: **2026-09-18**. The prototype lives in
[`research/disc_assistant/`](../research/disc_assistant/README.md).
Run [`run.sh`](../research/disc_assistant/run.sh) from the repository root; virtualenv
activation is unnecessary. `ask` starts the best match without a choice dialogue.
`rank` explains the same decision without connecting to the device.

## Launcher and maintenance

| Command | Behavior | Device effect |
| --- | --- | --- |
| `./research/disc_assistant/run.sh setup` | Prepare the environment, config and private search key; preserve existing settings | None |
| `./research/disc_assistant/run.sh start` | Start Typesense, connect, sync/index, then open the persistent text console | Read only until a playback command is entered |
| `./research/disc_assistant/run.sh history [ARGS]` | Inspect, export, prune or clear the local request journal | None; offline |
| `./research/disc_assistant/run.sh response [ARGS]` | Show/set speech policy, or reset its default | None; offline |
| `./research/disc_assistant/run.sh locales` | Validate each installed locale pair | None; offline |
| `./research/disc_assistant/run.sh language [CODE\|reset]` | Show/set one interaction locale, or reset to the TOML default | None; offline |
| `./research/disc_assistant/run.sh listen` | Open the persistent console with existing data; no Docker startup or automatic sync/index | Initial handshake and state reads |
| `./research/disc_assistant/run.sh up` | Start local Typesense and await readiness | None |
| `./research/disc_assistant/run.sh down` | Stop Typesense, retaining its index volume | None |
| `./research/disc_assistant/run.sh sync` | Read the catalog twice and publish a consistent SQLite snapshot | Read only; does not start a device scan |
| `./research/disc_assistant/run.sh status` | Show local snapshot/index status | None; offline |
| `./research/disc_assistant/run.sh queue` | Read all native queue pages, selected mark and play mode | Read only; no search/index dependency |
| `./research/disc_assistant/run.sh index` | Rebuild Typesense from SQLite | None |
| `./research/disc_assistant/run.sh search 'Linkin Park Numb'` | Search metadata and show candidates | None |
| `./research/disc_assistant/run.sh --language en rank 'Play Linkin Park — Numb'` | Explain ranking or a control intent | None |
| `./research/disc_assistant/run.sh --language en ask 'Play Linkin Park — Numb'` | Select the best candidate, check fresh rows, dispatch once and verify playback | Starts playback |
| `./research/disc_assistant/run.sh --language en ask 'Pause'` | Execute a state-aware control | See the control table below |
| `./research/disc_assistant/run.sh test` | Run prototype unit tests | None |
| `./research/disc_assistant/run.sh check` | Exercise real CLI/controller/SDK against disposable Typesense and a synthetic player | No physical device used |
| `./research/disc_assistant/run.sh transcribe FILE` | Transcribe PCM WAV with the active locale; return raw and normalized text | None |
| `./research/disc_assistant/run.sh rank --audio FILE` | Transcribe and preview the normal intent/ranking path | None |
| `./research/disc_assistant/run.sh ask --audio FILE` | Transcribe then execute the normal guarded command path | Same as typed `ask` |
| `./research/disc_assistant/run.sh synthesize TEXT --output FILE.wav` | Generate a WAV and provenance sidecar through TTS | None; no speaker output |
| `./research/disc_assistant/run.sh speech-samples DIR [--corpus JSON]` | Generate synthetic inputs for the active locale in a new directory | None |
| `./research/disc_assistant/run.sh speech-check DIR` | Check transcripts against expected intentions; nonzero exit on mismatches | None; no settings changes |
| `./research/disc_assistant/run.sh help` | Show usage | None |

`search` accepts `--limit N` (1–50). `rank` and `ask` accept one quoted string.
They alternatively accept `--audio FILE`, mutually exclusive with text. Speech
requires explicitly configured external engines/models; see
[file input, installation and evaluation](ASSISTANT_VOICE.md).
Default configuration is `~/disc-assistant.toml`; override it with:

```sh
./research/disc_assistant/run.sh --config /absolute/path/disc.toml --language en ask 'Play Linkin Park'
```

Physical DISC uses its LAN IP, TCP **12100**, HTTP **12103**, and reviewed firmware
**V2.57**. The example's HTTP **12113** is the direct emulator endpoint.
Disconnect FiiO Control before connecting: stock TCP accepts one client.

## Interactive console

After `start` or `listen`, enter music/control phrases directly, without `ask` or
shell quoting. Commands share one device session; events keep updating while
input is idle. `listen` currently means text input, not microphone capture.
The prompt identifies the configured `[device].key`, for example
`local-disc-emulator> `. It retains that label while disconnected; `/device`
shows the configured target and cached connection state without a network query.
The key is a user-assigned namespace, not a discovered hardware identity.

| Console command | Behavior |
| --- | --- |
| `/history [ARGS]` | Inspect recent requests, `show ID`, `export PATH`, `prune`, or `clear --yes`; see [history](ASSISTANT_HISTORY.md) |
| `/help` | List text and maintenance commands |
| `/debug [on\|off]` | Show/toggle live request traces for this console session; initially off unless launched with `--debug` |
| `/transcribe FILE` | Recognize PCM WAV and return text; no interpretation or playback |
| `/rank --audio FILE` | Transcribe and preview intention/ranking; no device mutation |
| `/ask --audio FILE` | Transcribe and execute through the normal interpreter and Controller |
| `/clear` | Clear the terminal screen; keep input history, journal and playback |
| `/response [mode none\|errors\|all\|reset]` | Show/set saved speech policy; see [responses](ASSISTANT_RESPONSES.md) |
| `/locales` | Validate each installed command/response catalog |
| `/language [CODE\|reset]` | Show/set the input/output locale immediately; `reset` stores the TOML default |
| `/status` | Show connection generation, latest playback observations and local catalog/index state |
| `/device` | Show the current configuration key, host, TCP/HTTP ports and cached session state; also works while disconnected |
| `/connect` | Enable connection/reconnection asynchronously; inspect `/status` for readiness |
| `/disconnect` | Close TCP and disable reconnect; retain the process ownership lock |
| `/sync` | Read the catalog twice; reuse the snapshot if all ordered rows are unchanged |
| `/index` | Rebuild the search projection from SQLite |
| `/queue` | Read the native queue and mode using the shared connection |
| `/search TEXT` | Search metadata without playback |
| `/rank TEXT` | Explain a music ranking or control intent without playback |
| `/exit` | Close the session and release the local ownership lock; keep music and Typesense running |

In a capable terminal, `prompt_toolkit` provides Up/Down recall, Ctrl-R history
search, Tab completion and history-based suggestions (Right accepts a suggestion).
Ctrl-L clears the screen. Ctrl-C while editing cancels only the current input;
Ctrl-D on an empty input or `/exit` closes the session. Ctrl-C during an operation
still exits without replaying any possible device write. `/help` renders readable
multiline text. Other operation results retain their JSON format.

Completion covers slash commands, `/language` codes, `/response` modes, `/history` subcommands and
command phrases from the active locale dictionary. It follows `/language` changes
immediately. Music-library completion is deferred; completion does not query or
control the player. Suggestions never execute without Enter.

Recall uses up to 1,000 recent interactive journal entries for this device,
respecting journal age/count limits. Truncated/multiline input and history/UI
maintenance commands are excluded. There is no separate history file. With
journaling disabled, recall is session-only; `/history clear --yes` also clears
the editor's history. `/clear` and Ctrl-L never delete journal entries.

Redirected input/output retain plain input and JSON output. `TERM=dumb` uses plain
input too, with readable help when both streams are terminals. In plain mode,
`/clear` returns a `clear_screen` status without terminal escape sequences. EOF
or Ctrl-C exits. Search errors leave playback controls available.
`start` reuses a matching index after checking collection existence/count; a
changed snapshot requires rebuilding it. `/sync` alone does not rebuild search.

All existing one-shot commands remain available for scripts and cron. Device
commands fail with a busy lock while the console owns the same data directory,
even after `/disconnect`; use `/exit` first. Offline commands remain available.
There is no local IPC command forwarding. One-shot failures exit nonzero; console
command failures are printed and leave the input loop open. Reconnect restores
observations only and never resubmits a failed command.

### Terminal appearance

By default, the prompt is bold cyan, input yellow, results green, errors red,
uncertain outcomes yellow and history suggestions muted/italic. Customize these
roles in your existing TOML configuration, then restart the console:

```toml
[terminal]
color = true
prompt = "ansicyan bold"
input = "ansiyellow"
result = "ansigreen"
error = "ansired bold"
warning = "ansiyellow bold"
debug = "ansibrightblack"
suggestion = "ansibrightblack italic"
```

Styles use [prompt_toolkit style syntax](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/styling.html):
ANSI palette names or HEX colors such as `#44aaff`, with optional `bold`, `italic`
or `underline`. ANSI colors follow your terminal's palette; the terminal controls
font family and font size. `[terminal].color = false` or `NO_COLOR=1` disables
colors. Formatting affects only terminal presentation; stored journal data and
JSON returned to scripts stay unchanged. JSON keys/values are not individually
highlighted in this first theme; each result uses its status color.

## Music requests

| English / Russian example | Meaning |
| --- | --- |
| `Play Linkin Park` / `Включи Linkin Park` | Whole artist when its name or alias matches |
| `Play artist Linkin Park` / `Включи исполнителя Linkin Park` | Explicit artist, including fuzzy matching |
| `Play Linkin Park - Numb` / `Включи Linkin Park — Numb` | Explicit artist/title pair; spaces around the separator are required |
| `Play Linkin Park Numb` / `Включи линкин парк намб` | Known artist prefix plus title; Cyrillic examples use configured aliases |
| `Play Numb` / `Включи Numb` | Best matching recording, potentially across artists |
| `Play track Numb`, `Play song Numb` / `Включи трек Numb`, `Включи песню Numb` | Explicit track, even when an artist has the same name |
| `Play Linkin Park - Numb live` | Require a live/concert edition marker in title or album |
| `Play Linkin Park - Numb remix` | Require a remix; never silently substitute the ordinary recording |
| `Play artist AC - DC` | Explicit artist preserves the dash as part of its name |
| `Play Stop` / `Включи трек Пауза` | Music titles, not control commands |

For an exact artist/title name collision, an unqualified request selects the
artist; use `track` to override. Matching ignores case and repeated whitespace.
Protocol calls preserve stock names. Command languages are independent of the
player's UI language. Automatic transliteration is not implemented.

## Playback controls

Use the forms for the active locale (`/language en` or `/language ru`).
These work without Typesense, a search key or a catalog/index. `rank 'Pause'`
returns the intent offline; `ask 'Pause'` connects to the device.

| English / Russian | Behavior |
| --- | --- |
| `Pause` / `Пауза`, `Приостанови` | Toggle only from confirmed playing; already paused sends nothing |
| `Resume` / `Продолжи` | Toggle only from confirmed paused; already playing sends nothing |
| `Stop`, `Stop music` / `Стоп`, `Останови музыку` | Pause while preserving position and native queue; report this explicitly, not as hardware stop |
| `Next`, `Next track` / `Следующий`, `Следующий трек` | Send stock next once and observe the actual result |
| `Previous`, `Previous track` / `Предыдущий`, `Предыдущий трек` | Stock previous: after >10 seconds it restarts the current track |

Neither interface has an Assistant-managed continuation executor: `Stop` reports assistant
continuation as inactive. It does not clear the native queue, seek to zero or
power off. A later `Resume` can continue the native queue. Arbitrary queue-plan
cancellation belongs to the future recommendation executor.

Unknown/loading state or a silent now-playing read blocks blind controls.
Stopped-state resume is unverified; use an explicit music selection. Toggle is
not atomic with its state read: external button presses and EOF can race it.
Unconfirmed writes are reported as uncertain and never retried. A restart requires
observed progress rollback; an unchanged title alone cannot confirm navigation.
See the [playback contract](ASSISTANT_PLAYBACK.md).

## Language dictionaries

The application uses one active locale for command interpretation, user responses
and speech provider context. Russian and English are installed; the default
is Russian. Music names and aliases remain unrestricted by locale.

```toml
[language]
locale = "ru"
```

```text
/language          # Show/reload the saved locale and available codes.
/language ru       # Russian commands and responses.
Переключи язык на английский
Switch language to Russian
/language reset    # Store the configured TOML default.
```

Both natural changes and `/language` use the same preference handler. Confirmation
uses the new locale. `/rank Switch language to Russian` (while English is active)
is a preview and does not save the change. `/language ru en` is no longer supported;
`/response language` is replaced by `/language`. Speech policy stays under `/response mode`.

```sh
./research/disc_assistant/run.sh --language en listen
./research/disc_assistant/run.sh language ru
./research/disc_assistant/run.sh language reset
```

The startup flag is persisted. Saved `language.locale` wins over TOML when no flag
is supplied. Initial defaults are persisted too, independently of request journaling.
Old input lists migrate using their first entry; old separate response language is
used only without an input selection. See the full [migration contract](ASSISTANT_ARCHITECTURE.md#migration-and-storage).

Literal command/target/version phrases live in `assistant/locales/<code>.toml`.
Language-switch prefixes use `commands.set_language`; optional `language_names`
map locale codes to names spoken in the current language. Locale codes and installed
English/native display names are also recognized as language targets. Prefixes use
longest match; controls match whole phrases. No general sentence parsing or inflection
is implied. Slash commands are available independently of the locale.

Recording metadata markers such as Live/Remastered are recognized independently
of input locale. Requested version phrases use the active dictionary; the library's
metadata marker table additionally prevents a locale change from hiding known
live/remastered labels. Personal artist/title aliases remain separate.

For a new locale, follow the [contribution guide](ASSISTANT_LOCALES.md). Full
command/response catalogs need no runtime Python registry edit. The independent
[interpreter and speech contracts](ASSISTANT_ARCHITECTURE.md) allow later local or
remote engines without changing the execution pipeline.

Common recording labels also remain explicit query constraints across locales:
`Включи Linkin Park — Numb live` requires a live edition even in Russian mode.
Locale-specific version phrases extend those shared labels. A missing requested
edition is not silently replaced with a studio recording.

## Ranking: lexical-v2

Version 2 separates metadata version markers from the active command locale;
weights and automatic best-match policy are unchanged.

Scores are explainable heuristics, **not probabilities**. Quality needs evaluation
on a fixed personal-library query set.

| Factor | Policy |
| --- | --- |
| Explicit known artist | Exclude other artists |
| Exact names/aliases | Check the complete SQLite snapshot, outside the search top-k limit |
| Artist/title pair | 75% title similarity, 25% artist similarity |
| Single track or artist | Normalized word similarity using `SequenceMatcher` |
| Typos | Retrieve up to 50 Typesense candidates with token dropping disabled; minimum title similarity 0.60, or title 0.55 + artist 0.72 for a pair; artist-only minimum 0.80 |
| Explicit version | All requested markers are mandatory |
| Unrequested version | Penalty 12; remaster-only penalty 2. Metadata heuristic, not proven recording provenance |
| Ties | Artist, album, title, then snapshot ordinal; no random choice |
| History/likes/popularity | Not collected or used yet |

`rank` exposes `score`, `evidence`, `ranking_policy` and retrieval information.
`retrieval.truncated=true` means fuzzy retrieval was limited to the returned pool.
Absence of version tags does not establish studio origin or audio quality.

## Execution and results

Music selection reads fresh `artist/song` or `artist/album/song` twice, compares
membership, and verifies the final row through Controller. Cached search positions
are never sent directly. Indistinguishable copies select the first current row
and report `metadata_equivalent_rows`; this does not establish permanent identity.

| Status | Meaning |
| --- | --- |
| `ranked` / `not_found` | Ordered music candidates / no usable match; no playback dispatch |
| `planned` | Offline control intent; no device access |
| `playing` | Music launch verified through matching state, metadata and source type 7; not an audible-output test |
| `confirmed` | Control outcome observed; see `outcome` and `state` |
| `already_satisfied` | Fresh state already meets the control request; no mutation |
| `observed` | Read-only native queue and mode; `playback_known=false` when current state is unavailable |
| `not_sent` | Preflight/connection/state failed before dispatch |
| `uncertain` | A write may have happened, but its required result was not confirmed; no retry |

`not_sent`/`uncertain` produce a nonzero one-shot exit code, as do
configuration/parsing and stale-index errors. After a changed snapshot, run
`index` (or `/index`) again. A manual repeat is a new
request and may restart a recording. Device operations share a data-directory
lock, not a lock against external controllers. There is no atomic device revision.
One-shot events are retained within each operation. The console continuously
reduces events throughout its session; listening history is not collected.

## Request journal

Console requests and one-shot application commands are journaled by default in
`assistant.sqlite3`, including invalid phrases and search/operation failures.
Results include `request_id` and `timing.total_ms`, even with journaling disabled.
Use `/history show ID` or one-shot `history show ID` to inspect saved requests;
an ID alone does not imply persistence. The journal retains bounded search candidates,
the automatic selection and operation outcomes without treating them as listens.
Use `--source scheduled` before the CLI command for cron attribution. History
inspection/export/clear is not itself journaled. Retention defaults to 90 days and
10,000 completed requests. See [storage, commands and limits](ASSISTANT_HISTORY.md).

### Timing and live debug traces

```text
/debug on
/rank Включи Макс Корж
/debug off
```

`/rank` diagnoses interpretation and matching without starting playback. A capable
terminal displays trace lines in the `debug` color. The switch is session-only;
it does not change saved preferences, journal collection or speech policy.

Pass the global `--debug` flag before the application command:

```sh
./research/disc_assistant/run.sh --debug listen
./research/disc_assistant/run.sh --debug rank 'Включи Макс Корж'
```

One-shot commands and redirected consoles send traces to **stderr**; one-shot
stdout remains the JSON result. Each `[trace]` line contains a JSON object with
`request_id`, `phase`, `observed_at`, `elapsed_ms` and bounded `payload`. These are
application stages, not raw transport packets or Python stack traces. Debug is
available without persistent journaling; output errors do not replay operations.

`timing.total_ms` measures a traced application request with a monotonic clock,
through response construction, including earlier journal/debug overhead. It excludes
launcher/Python startup, input editing, final result persistence and terminal output.
It is also returned for failed requests and unjournaled history commands. Blank
input, startup banners/status and failures before request creation are outside
this measurement. Per-event `elapsed_ms` is cumulative, not a stage duration.

Search traces include snapshot track/artist counts, resolved intent, local artist
and exact-track matches, the actual Typesense query when needed, retrieval counts
and candidates remaining after filtering/scoring. They help distinguish an absent
exact metadata/alias match, zero retrieval results and rejected retrieved candidates;
they do not prove that an artist is absent from the device's unsynchronized files.

## Queue and remaining work

A track request selects a position in its artist-scoped album; an artist request
selects the artist catalog. `ask` now verifies and returns the native queue;
`queue` reads it independently. `continuation` describes mode policy, not proof
that the player is currently playing. Native continuation depends on play mode:
list once stops at the end, single once stops after this recording, repeat one
repeats it, random stays within the queue, and repeat list wraps.

Default configs preserve device mode. To explicitly enable continuous context:

```toml
[playback]
continuous_context = true
```

For music requests this sets persistent repeat-list mode (3) before selection.
`mode_change` reports its own outcome; a later selection failure does not roll it
back. Controls never change mode. Empty sources cannot launch; one-track contexts
repeat. No host process is needed for native continuation after CLI exit.
See [the queue contract](ASSISTANT_PLAYBACK.md). Search alternatives are not a playlist.

Volume, standalone album/genre/playlist requests, arbitrary recommendation queues,
history/likes/lyrics requests, microphone input and choice dialogues remain deferred.
A Controller method does not by itself establish an Assistant text command.
