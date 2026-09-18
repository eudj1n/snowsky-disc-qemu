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
| `./research/disc_assistant/run.sh language [CODES\|reset]` | Show/set saved command dictionaries, or reset to TOML defaults | None; offline |
| `./research/disc_assistant/run.sh listen` | Open the persistent console with existing data; no Docker startup or automatic sync/index | Initial handshake and state reads |
| `./research/disc_assistant/run.sh up` | Start local Typesense and await readiness | None |
| `./research/disc_assistant/run.sh down` | Stop Typesense, retaining its index volume | None |
| `./research/disc_assistant/run.sh sync` | Read the catalog twice and publish a consistent SQLite snapshot | Read only; does not start a device scan |
| `./research/disc_assistant/run.sh status` | Show local snapshot/index status | None; offline |
| `./research/disc_assistant/run.sh queue` | Read all native queue pages, selected mark and play mode | Read only; no search/index dependency |
| `./research/disc_assistant/run.sh index` | Rebuild Typesense from SQLite | None |
| `./research/disc_assistant/run.sh search 'Linkin Park Numb'` | Search metadata and show candidates | None |
| `./research/disc_assistant/run.sh rank 'Play Linkin Park — Numb'` | Explain ranking or a control intent | None |
| `./research/disc_assistant/run.sh ask 'Play Linkin Park — Numb'` | Select the best candidate, check fresh rows, dispatch once and verify playback | Starts playback |
| `./research/disc_assistant/run.sh ask 'Pause'` | Execute a state-aware control | See the control table below |
| `./research/disc_assistant/run.sh test` | Run prototype unit tests | None |
| `./research/disc_assistant/run.sh check` | Exercise real CLI/controller/SDK against disposable Typesense and a synthetic player | No physical device used |
| `./research/disc_assistant/run.sh help` | Show usage | None |

`search` accepts `--limit N` (1–50). `rank` and `ask` accept one quoted string.
Default configuration is `~/disc-assistant.toml`; override it with:

```sh
./research/disc_assistant/run.sh --config /absolute/path/disc.toml ask 'Play Linkin Park'
```

Physical DISC uses its LAN IP, TCP **12100**, HTTP **12103**, and reviewed firmware
**V2.57**. The example's HTTP **12113** is the direct emulator endpoint.
Disconnect FiiO Control before connecting: stock TCP accepts one client.

## Interactive console

After `start` or `listen`, enter music/control phrases directly, without `ask` or
shell quoting. Commands share one device session; events keep updating while
input is idle. `listen` currently means text input, not microphone capture.

| Console command | Behavior |
| --- | --- |
| `/history [ARGS]` | Inspect recent requests, `show ID`, `export PATH`, `prune`, or `clear --yes`; see [history](ASSISTANT_HISTORY.md) |
| `/help` | List text and maintenance commands |
| `/language [CODES\|reset]` | Show/set saved command dictionaries immediately; `reset` restores TOML defaults |
| `/status` | Show connection generation, latest playback observations and local catalog/index state |
| `/connect` | Enable connection/reconnection asynchronously; inspect `/status` for readiness |
| `/disconnect` | Close TCP and disable reconnect; retain the process ownership lock |
| `/sync` | Read the catalog twice; reuse the snapshot if all ordered rows are unchanged |
| `/index` | Rebuild the search projection from SQLite |
| `/queue` | Read the native queue and mode using the shared connection |
| `/search TEXT` | Search metadata without playback |
| `/rank TEXT` | Explain a music ranking or control intent without playback |
| `/exit` | Close the session and release the local ownership lock; keep music and Typesense running |

EOF or Ctrl-C also exits. Search errors leave playback controls available.
`start` reuses a matching index after checking collection existence/count; a
changed snapshot requires rebuilding it. `/sync` alone does not rebuild search.

All existing one-shot commands remain available for scripts and cron. Device
commands fail with a busy lock while the console owns the same data directory,
even after `/disconnect`; use `/exit` first. Offline commands remain available.
There is no local IPC command forwarding. One-shot failures exit nonzero; console
command failures are printed and leave the input loop open. Reconnect restores
observations only and never resubmits a failed command.

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

Literal forms live in [`ru.toml`](../research/disc_assistant/assistant/locales/ru.toml)
and [`en.toml`](../research/disc_assistant/assistant/locales/en.toml). User config:

```toml
[language]
enabled = ["ru", "en"]
```

The TOML value supplies the default. An explicit selection is available without
restarting the console:

```text
/language          # Show enabled, configured and available languages and source.
/language ru       # Accept Russian command forms only.
/language en       # Accept English command forms only.
/language ru en    # Merge both dictionaries.
/language reset    # Remove the saved override and restore the loaded TOML default.
```

Comments above explain the examples; enter only the command itself. For scripts:

```sh
./research/disc_assistant/run.sh language ru
./research/disc_assistant/run.sh language
./research/disc_assistant/run.sh language reset
```

The selection applies immediately to console parsing and ranking and persists
across sessions, including one-shot `ask`/`rank`. Precedence is saved preference,
then TOML, then the bilingual default. Invalid/missing dictionaries and duplicate
codes fail without replacing the previous selection. `/language` also reloads a
preference changed by another process; otherwise an already-open console keeps
its selection until restart. TOML edits require restart.

This selects command dictionaries (including their version phrases), not the
player's UI language or a metadata-language filter. Artist/title text may still
use any language. `/language` and other slash commands stay available in every
selection. Replies/help remain English; microphone recognition is not implemented.
No sync or index rebuild is required.

The bilingual setting is also the default for older configs. Dictionaries merge, allowing mixed
requests such as `Play песню Numb`. `search` continues accepting arbitrary text.
Add `assistant/locales/<code>.toml`, enable its code, and add tests. Example:

```toml
[commands]
play = ["mets", "mets moi"]
pause = ["pause"]
[targets]
artist = ["artiste"]
track = ["la chanson"]
[versions]
live = ["en concert"]
```

Values are literal phrases, not regular expressions. Longest play/target prefixes
win; controls match the entire phrase. Identical forms with the same meaning
merge. Conflicting meanings within a section, unknown keys and invalid files fail
validation. Language order does not establish precedence. Semantic keys are
`commands.play/pause/resume/stop/next/previous`, `targets.artist/track`, and
`versions.live/remix/acoustic/instrumental/demo/karaoke/cover/remaster`.
New forms need no parser changes; new actions require Python implementation.
This is a bounded phrase grammar, not general sentence parsing or inflection.

Version phrases apply to both queries and metadata. Keep English enabled for
English tags such as Live/Remastered alongside Russian commands. Music-name
aliases remain in `aliases.artists/titles`, separate from command forms.
Dictionary edits apply on the next CLI invocation or console restart without
`sync`/`index`.

## Ranking: lexical-v1

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
Results include `request_id` when saved; use `/history show ID` or one-shot
`history show ID` to inspect stages. The journal retains bounded search candidates,
the automatic selection and operation outcomes without treating them as listens.
Use `--source scheduled` before the CLI command for cron attribution. History
inspection/export/clear is not itself journaled. Retention defaults to 90 days and
10,000 completed requests. See [storage, commands and limits](ASSISTANT_HISTORY.md).

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
