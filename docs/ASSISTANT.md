# Disc Assistant: implementation plan

Start with the [current checkpoint](ASSISTANT_STATUS.md) for active work and evidence.

Checkpoint: **2026-09-18**. The desktop prototype in
[research/disc_assistant](../research/disc_assistant/README.md) now includes catalog
import, SQLite snapshots, Typesense search, single-locale text commands (Russian or English), explained
ranking and bounded Controller playback. `rank` previews the ordering; `ask`
automatically launches the best candidate. The owner explicitly deferred a
choice/confirmation dialogue. File-based voice input and synthetic sample generation
are implemented; microphone capture, spoken reply delivery, listening history and
a browser UI remain pending. See [voice setup and evaluation](ASSISTANT_VOICE.md)
and the [command table](ASSISTANT_COMMANDS.md).
The [interpreter, speech and locale architecture](ASSISTANT_ARCHITECTURE.md) is now
implemented. It supersedes the merged-language/separate-response policy recorded
in the historical increments below.
The [command catalog and explanation preview](ASSISTANT_COMMAND_CATALOG.md) are
also implemented; learned classification remains diagnostic while the live
interpreter uses rules. The [reviewed-data workflow and v2 model comparison](ASSISTANT_NLU_DATA.md) are
implemented. [Independent sources, argument extraction and optional shadow comparison](ASSISTANT_INTERPRETATION_SOURCES.md)
are now implemented; independent human review and learned execution remain pending.
The MVP accepts one action per request; compound planning and dialogues are deferred.
The current device contract is [DISC capabilities](DISC_CAPABILITIES.md).

The current [MVP boundary and acceptance gate](ASSISTANT_MVP.md) is tracked in
[issue #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21): command input
through execution on the device. The owner chose to measure the baseline first,
then agree error limits; later component improvements are separate tasks.
[Offline shadow reports and review queues](ASSISTANT_SHADOW_REPORTS.md) are now
implemented. They support interpretation analysis, not physical-device acceptance.

The [physical baseline](ASSISTANT_BASELINE.md) is in progress, with RU-01–19
recorded privately and one disputed expectation kept separate. The owner proposed
[repeatable Assistant scenarios against the emulator](ASSISTANT_EMULATOR_ACCEPTANCE.md)
as the next validation direction. The opt-in runner is implemented with synthetic
media, real Typesense, independent readback and per-case reports; its regression
results remain separate from physical acceptance. The initial 36-case run exposed
multi-artist retrieval and late previous/restart semantics. Library now projects
semicolon-separated artist membership for search/ranking while preserving stock
selectors; existing snapshots require `/index`, not another sync. The regression
manifest has 46 cases; current measurements are in the emulator acceptance document.
Assistant previous now uses explicit guarded predecessor selection at every elapsed
position. First row is a no-op; native Controller previous semantics are unchanged.
This supersedes the restart behavior described in historical increments below.


Explicit album requests now have a separate typed intent, snapshot ranking and
verified whole/scoped native playback. See the [command contract](ASSISTANT_COMMANDS.md#album-selection).

## Goal and first deliverable

Build **Disc Assistant**, a text and voice interface that runs on a computer and
controls a physical SNOWSKY DISC through the existing controller. This is the
software foundation for a possible **Disc-hub** dock. Keep development in this
repository for now; splitting repositories is deferred.

The first end-to-end deliverable accepts typed commands, finds music in the
device's actual catalog and starts the selected artist or recording. Then add
microphone recording by button and speech recognition using the same command
pipeline. Initial examples:

- `Включи Linkin Park` — play the named artist.
- `Включи Linkin Park — Numb` — play a particular recording.
- `Включи линкин парк намб` — resolve spoken aliases and imperfect transcription.
- Multiple plausible recordings — rank deterministically and launch the best match;
  expose the reasons through `rank`. A choice dialogue is deferred by owner decision.
- Missing music or an unavailable player — explain the result without guessing.

The computer sends control messages; DISC plays its own media. Audio can leave
DISC through its existing wired output or Bluetooth. FiiO documents LDAC
transmission, but successful codec-preference readback does not establish an
actual LDAC connection, bitrate or hardware audio quality. Physical simultaneous
Wi-Fi control, Bluetooth playback and charging need a separate observation.
See [remote modes](REMOTE_MODES_THEMES.md) and [idle power](IDLE_POWER.md).

## Component boundaries

The prototype lives in `research/disc_assistant/`, with separate `assistant/`
and `library/` packages. Their names below describe responsibilities, not root-level
production packages. Keep the experiment isolated until implementation and
acceptance justify promotion into the main [repository layout](REPOSITORY.md).
Promotion is a separate reviewed step, not an automatic move after scaffolding:

| Component | Responsibility |
| --- | --- |
| Existing `controller/` | Device discovery, protocol transports, catalog/state reads and guarded device operations |
| Proposed `library/` | Catalog synchronization, internal identities, history, enrichment, search indexing and candidate retrieval |
| Proposed `assistant/` | Intent parsing, dialogue context, clarification, ranking policy and execution orchestration |
| Proposed `assistant/voice/` | Microphone capture, speech boundaries, speech-to-text and later wake-word activation |
| Assistant application service/UI | Own the device session, coordinate components and present text, recording controls, candidates and execution status |

These are ownership boundaries, not a requirement for separate services. Start
with one application process, SQLite and a separate local Typesense process.
Create modules as needed rather than scaffolding empty subsystems.

```text
Text input -----------------------+
                                  v
Microphone -> speech-to-text -> Assistant -> structured intent
                                  |                |
                                  v                v
                            Library/search -> candidates -> ranking
                                  |                         best match
                            SQLite + Typesense                  |
                                                               v
DISC catalog/events -> application session -> fresh selection -> Controller
                              |                                  |
                              +-> history                        v
                                                           Physical DISC
```

Controller must remain independent of assistant, library, emulator, viewer,
firmware and research. Library search/domain code must be usable offline; its
device adapter uses controller through the application's shared session. The
assistant UI does not depend on emulator viewer internals. Use explicit package
imports and module entry points; keep component tests with their component and
cross-component acceptance under `tests/`.

## Data ownership and persistence

SQLite is the application's durable store. The device remains authoritative for
its current catalog, favorites and playlists; our database records observations
of those resources. Locally collected history and external annotations belong
to the application. Typesense is a derived index that can be rebuilt from SQLite.

| Dataset | Stored information and lifetime |
| --- | --- |
| Device and synchronization state | Application device key, observed identity/version, endpoint, snapshot generation, timestamps and completeness |
| Catalog observations | Literal metadata, source scope, available track discriminators and snapshot membership |
| Favorites/playlists | Device-observed state, read time and unresolved membership where identity is insufficient |
| Listening history | Playback observations, commands, observed intervals, disconnect gaps and attribution confidence |
| Application preferences | Explicit local likes/choices, kept distinct from device favorites and inferred preferences |
| Enrichment | Aliases, lyrics or descriptions, external identifiers, source, retrieval time and matching confidence |
| Search projection | Searchable fields, availability, selected preference aggregates and index/schema generation |

Use a configurable application data directory outside the source checkout:
the platform application-data location for `disc-hub`, with an explicit override
for development and later deployment. Store SQLite, Typesense persistence and
downloaded models in appropriate data/cache locations. Document exact paths and
backup/restore procedures during implementation. Back up durable data; make
indexes reproducible. Keep personal catalogs, credentials, recordings and logs
out of Git. Audio recording retention is off by default; diagnostic retention
must be explicit. Tests use synthetic or sanitized fixtures.

### Assistant preferences

`assistant.sqlite3` alongside `library.sqlite3` owns the versioned
`settings(key, value_json, updated_at)` table. It stores one `language.locale` and
an independent `response.mode`. Input interpretation and responses use the same
locale; startup `--language`, `/language` and a natural language-switch intention
share the persistent setting. Initial defaults are saved on first startup too.
Migration prefers the first legacy input language over the old response language.
See [precedence and migration](ASSISTANT_ARCHITECTURE.md#migration-and-storage).
Settings are scoped to the data directory; invalid changes preserve old values.

Keep infrastructure configuration (device endpoints, storage paths, search secrets)
in TOML/environment. Add future mutable preferences through validated named keys
and explicit schema migrations; do not turn settings into arbitrary runtime flags.
Catalog refresh/reindex cannot erase preferences. Back up both databases. This
initial preference increment did not persist requests. Schema 2 now adds the
[request/decision journal](ASSISTANT_HISTORY.md) while preserving settings;
listening intervals remain separate later work.

Validation: 125 prototype tests and the firmware-free project suite (313 Python /
37 JavaScript) pass. Preference tests cover reopen, precedence/reset, immediate
console parsing, one-shot parity, invalid selections and database-version guards.
No device command or firmware change is required for language selection.

### Synchronization and identity

1. Connect to a deliberately selected device and inspect its reported version;
   compatibility comes from `soc_version`, never the emulator's `FW_VERSION`.
2. Read all catalog pages into a staging snapshot. Track counts, failures and
   observed changes while fetching. Never publish a failed partial fetch as an
   empty catalog or delete history because a page was missing.
3. Publish a locally completed generation in SQLite, then update the search
   projection. Expose index lag and rebuild failed projections. Publishing is
   locally atomic; the device does not provide an atomic catalog revision.
4. Refresh explicitly, after observed library changes and on reconnect as needed.
   A catalog refresh reads existing data; it does not start a firmware media scan.
   If a scan is in progress, postpone publication/selection until a stable read
   is possible. Do not start scans, reset the library or edit files implicitly.

Assign internal keys to library entries. Keep device IDs, paths and list positions
as observations, not interchangeable permanent identities. Reconcile snapshots
using available metadata and source context; retain uncertainty rather than
merging ambiguous entries. An endpoint IP alone is not a durable device identity.

CUE entries may share paths and IDs; duplicate names and different editions must
remain distinct. Do not promise identity continuity after arbitrary renames or
rescans when the protocol cannot establish it. Preserve orphaned history and
annotations until a match can be established. See [formats](FORMATS.md).

A search result carries an internal key and snapshot provenance. Before playback,
resolve it against fresh device rows, verify its identity/context and use the
current position. A cached Typesense ID or offset is never a playback selector.

## Search and the Typesense evaluation

Evaluate Typesense as the first search backend, behind a small library search
interface. Record the tested server version and schema. SQLite remains necessary
for durable records and event history; SQLite full-text search alone does not
provide all the typo handling and ranking proposed here.

Start with title, artist, album and explicit aliases. Add device availability and
edition/version information where present. Preserve stock names for protocol
calls while maintaining normalized search fields separately. Do not split literal
collaborating-artist names into new device selectors.

Typesense supplies typo tolerance, prefix search, field weights, filters and
sorting. Its [Songs Search example](https://typesense.org/docs/guide/reference-implementations/songs-search.html)
demonstrates a MusicBrainz catalog and UI patterns, not synchronization with DISC
or listening-history collection. Use the patterns; do not import a global catalog
as though those recordings were available on the device.

`линкин парк` and `Linkin Park` need deliberate alias/transliteration handling;
ordinary edit-distance tolerance does not establish their equivalence. A match
score is not a calibrated confidence probability. Tune retrieval/ranking against
labeled examples. Current policy automatically selects the best candidate;
interactive ambiguity resolution is deferred. Search engines may relax queries by
dropping tokens: for automatic playback, do not let that silently discard a
requested artist, title or version. Inspect/configure this behavior explicitly.

Search intent determines field priority. Exact-title selection should favor title
and artist; a quoted lyric search should use lyrics. Personal preference must not
override an explicit recording request. Start with lexical retrieval; evaluate
semantic or hybrid search against the same labeled baseline before enabling it.

### Planned embedding snapshots

Precompute embeddings for library search documents, including names, aliases and
later verified lyrics/enrichment. Keep these derived artifacts in `library`,
outside the checkout alongside application data; the assistant consumes the
search interface. Phrase-level documents preserve more context than a collection
of isolated word vectors. Command dictionaries remain responsible for supported
actions and explicit constraints.

An embedding snapshot should record its source catalog generation, input-content
hashes, normalization/chunking version, model identifier and immutable revision,
vector dimension and distance metric. Reuse cached vectors only when both content
and the full embedding pipeline signature match. Reuse of identical text vectors
must not merge distinct recordings/CUE rows or establish identity across rescans.
Maintain a separate mapping from vectors/chunks to each current snapshot entry.

Build changed documents in staging and publish a complete search generation only
after validating its mapping and model signature. A model change rebuilds vectors;
a failed build leaves the previous complete projection available subject to the
existing freshness checks. History/likes remain separate ranking features rather
than forcing every play event to rebuild semantic vectors.

For voice input, transcribe once, parse the command, embed its search portion with
the matching model, and combine lexical and vector candidates. Preserve exact
artist/title/version constraints and fresh Controller selection after retrieval.
An optional bounded query-vector cache may use normalized text plus the pipeline
signature; it must never cache a playback position or skip execution checks.
Lexical search stays available when the embedding model/index is unavailable.

Precomputation avoids embedding the entire catalog per query; it does not remove
speech recognition or query-embedding latency. Compare lexical and hybrid top-1
quality, incorrect launches, cold/warm median/p95 latency, build/update time and
RAM on the desktop before choosing a model or moving to Pi. Snapshot persistence
and cache reuse are planned; no embeddings, model downloads or vector schema are
implemented in the current slice.

Typesense keeps its index in memory. Measure index size, build time, query latency
and RAM on the actual catalog, separately from speech/embedding model resources.
Do not infer Pi suitability from desktop performance or the large public demo.
References: [Search API](https://typesense.org/docs/30.2/api/search.html),
[system requirements](https://typesense.org/docs/guide/system-requirements.html).

## Intent, voice and execution

Use a typed internal request: action, artist/title candidates, hard constraints,
ranking preferences and optional dialogue context. The first action allowlist is
play artist or play recording. An LLM is optional; neither a parser nor a model
should generate unchecked protocol frames or arbitrary executable operations.

The rules interpreter loads the active `assistant/locales/<locale>.toml`.
`interpret(text, context)` returns a validated music, control or language intention;
local-model/remote implementations can use the same contract. The resolver and
ranker consume that intention without parsing again. Metadata version conventions
are recognized independently of the interaction locale. See the
[architecture contract](ASSISTANT_ARCHITECTURE.md) and [locale guide](ASSISTANT_LOCALES.md).

For artist playback, use guarded `play_artist(artist, http=http)`. For a recording
in a named artist album, resolve fresh rows and use
`play_artist(artist, index, album=album, http=http)`. Unknown/reserved labels and
unsupported names require an explicit supported path or a clear refusal, not an
invented selector. Preserve the limitations in [library browsing](LIBRARY_BROWSING.md).

The current CLI exposes connection/catalog freshness, the requested text, ranked
artist/album/title candidates, score components and the selected playback outcome.
There is no pending-choice state or reusable confirmation token. `ask` executes
one best-match request; `rank` only explains. If dialogue is added later, its
responses must belong to a particular request, expire on cancellation/replacement
and be revalidated before execution.

The file-based STT/TTS slice now precedes microphone work; it provides synthetic
corpora and explicit `transcribe`, `rank --audio` and `ask --audio` commands.
Recorded quality gaps and setup are in [ASSISTANT_VOICE.md](ASSISTANT_VOICE.md).
Next add microphone recording by button before continuous listening. Select the input,
bound recording duration, detect end of speech and reject silence. Evaluate a
multilingual speech model on Russian commands containing English music names.
Show the transcript so recognition errors can be separated from search errors.

Typesense [Voice Query](https://typesense.org/docs/30.2/api/voice-search-query.html)
accepts an audio clip and uses its transcription for search. The documented
example uses English-only `ts/whisper/base.en` and 16 kHz, 16-bit WAV input. It does
not itself implement our command dialogue or execution checks. Prefer a separate
speech-to-text adapter so intent parsing happens before search and models can be
changed independently. Built-in Voice Query can be compared as an experiment;
verify available multilingual models rather than assuming the example supports
Russian. Local speech inference is the initial target; external inference is an
explicit deployment option, not an automatic fallback.

Wake-word detection for `Фиио`, spoken replies and conversational follow-ups come
after the button-driven pipeline. Test wake-word misses and false activations with
music playing. The computer does not automatically receive a clean reference copy
of DISC's audio for echo cancellation.

### Device language and the interaction locale

Read-only static verification on **2026-09-17**, against the fingerprint-matched
V2.57 `mq_player`, found no usable language getter in the reviewed network paths:

- `0501` builds settings at `424e8c`; serializer `4d82b4` emits `a501` fields
  without a language field. Its unnamed string at `6d7c54` is `rgb`, not language.
- The database language is loaded into byte `83a779`. Initialization callback
  `4eb47c` includes it as `language` in `aa24`, then calls sender `4ddaec` with
  destination **1**. That destination sends only to the local UI message queue;
  destination 0 is TCP and 2 sends to both. This local snapshot must not be
  confused with the remote settings response.
- Local dispatch entry `8389c8` maps `0615` through wrapper `4146e0` and callback
  slot `83a4d0` to `4eea20`, a no-op returning zero without a reply. The associated
  setter `0665` maps through `414700` / `83a4d4` to `4eea28`, which updates the
  language byte and persists configuration item 14. Neither `0615` nor `0665`
  occurs in the separate 111-command TCP allowlist at `6d84e0`.
- The fingerprinted 17-entry HTTP route table has no dedicated language/settings
  endpoint. This is not a claim that diagnostic file/log access could never expose
  an incidental language value; such access is not a supported current-language API.

Reproduce the static checks with the existing `inspect_link_commands` and
`inspect_http_routes` diagnostics and read-only Ghidra `DecAt`/`RefsTo` scripts
described in [diagnostics](DIAGNOSTICS.md) and the
[Ghidra workflow](../research/ghidra/README.md). No speculative tags or language
setters were sent. With the owner's authorization, the interactive guest was
started using `20_boot.sh` directly, without setup. Product/version and all six
binary fingerprints passed validation. A fresh TCP handshake returned `0306`;
two successive `0501` reads reported `soc_version=257` and the same 23 field names,
with no language/locale field. Read-only SQLite reported `LANGUAGE=2` before and
after boot. No language-switch experiment or physical-device network check is
claimed; filesystem access inside the emulator is not physical-device API access.

Consequently, device locale is **unknown through the supported remote contract**.
Keep the Assistant interaction locale independent of it.
`Включи Linkin Park` in Russian mode and `Play Linkin Park` in English mode map
to the same intention. Test both locales and foreign music names within speech; do not force an English-only model based on a presumed device locale.
Choose one interaction locale explicitly; persist it for command interpretation,
responses and future speech-provider context. A future verified device-locale getter may supply a default,
but must not silently override the saved interaction locale.

### Device session rules

- M2c implements a persistent connection owned by the foreground Assistant
  application through `start`/`listen`. One-shot commands remain available for
  scripts and cron; see [persistent session ownership](ASSISTANT_PLAYBACK.md#m2c-persistent-device-session).
- Own one TCP connection and one reader in the application service. Serialize
  requests and route replies/events centrally; do not give each UI, catalog worker
  or voice request its own connection. FiiO Control can compete for the stock
  single-client connection. The prototype uses a dedicated receiver and central reply/event routing,
  preserving the Controller diagnostic client for its existing callers.
- Pair HTTP and TCP with the same selected device. Use documented physical ports;
  emulator adapter/proxy ports are separate configuration.
- Preserve partial state updates. Duplicate notifications do not create additional
  plays. Empty now-playing responses do not mean stopped, and a timeout alone does
  not establish disconnection or playback completion.
- Respect stock command pacing and verify the selected recording and state after
  sending. Report unconfirmed execution as uncertain; do not automatically retry.
- On reconnect, discard pending mutations, handshake and refresh state. Never
  replay an old selection or toggle. No remote power-on capability is assumed.
- Pause/resume uses observed state and the documented toggle semantics;
  no unverified absolute play/pause command is introduced.

The two playback increments are specified in the
[playback and queue plan](ASSISTANT_PLAYBACK.md): M2a adds index-independent
pause/resume, explicit pause-preserving-position stop semantics, and stock navigation;
M2b reads the actual native queue and makes continuation/mode policy explicit.
Track search candidates are not a continuation playlist. Album/artist context
comes first; an arbitrary assistant-managed recommendation queue requires a
separately validated execution strategy and, potentially, a persistent session.
Both increments now have prototype implementations. Controls and read-only `queue`
bypass search/index dependencies. Neither interface has an Assistant-managed continuation
plan to cancel. `playback.continuous_context=true` explicitly permits a separately
verified persistent repeat-list mode change before selection; default configs
preserve mode. Arbitrary queue plans and their cancellation remain future work.

These rules follow [DISC capabilities](DISC_CAPABILITIES.md),
[remote control](REMOTE_CONTROL.md) and [track completion](TRACK_END.md).

## Shared Controller API

Implemented after the request journal on 2026-09-18. The common
[Controller API](CONTROLLER_API.md) now owns the persistent receiver/session,
partial-state reduction, scan guards, bounded HTTP pagination, state-aware controls,
mode readback, final selection verification and native queue observations.
`DiscSession` exposes immutable normalized snapshots/results and named operations
for a software remote without raw-tag handling. Controller imports no research,
Assistant, emulator or firmware modules.

Assistant uses thin configuration/ownership adapters and shared Controller
operations. It retains language parsing, catalog snapshot reconciliation, search,
ranking, automatic-match policy, Stop-as-pause semantics, continuous-context
opt-in and the request journal. One-shot CLI and existing journal/output contracts
remain supported. A Controller session contains no personal storage path or search
configuration; the application supplies ownership locking.

The synthetic TCP test peer deliberately retains raw tags as independent protocol
fixtures. A future backend shares one session across Assistant/remote adapters;
separate processes still cannot compete for the stock single-client connection.
No HTTP/IPC service or full web remote is added by this extraction. Existing
diagnostic TCP/WS/HTTP APIs remain unchanged; the persistent facade is currently
TCP-only with an explicitly bounded playback surface.

## History, preferences and external enrichment

Design event storage early, then add personalized selection after basic playback
works. Record user intent, command dispatch, confirmed playback and observed
listening intervals separately. Do not count a command as a completed listen,
count repeated state events twice, or fill disconnected time with assumed plays.
Track skips only when evidence supports that attribution. Seeking is not elapsed
listening. Completion must follow observed firmware behavior; retain partial or
unknown sessions when evidence is insufficient.

The implemented [request journal](ASSISTANT_HISTORY.md) assigns one request ID
before parsing and records source, original/normalized text, parsed intent or
failure, catalog/index generations and policy versions. It retains bounded search
and ranking candidates with scores/reasons, marks the automatic selection, and
links operation IDs/outcomes. Unknown phrases remain available for later intent
analysis; the current grammar does not invent unsupported intentions. Metadata
and snapshot provenance keep old records interpretable. Export, explicit clearing
and bounded retention are available. Microphone audio is not retained.

An automatic best match is the algorithm's decision, not an explicit user like.
Scheduled commands are distinct from manual requests; search or dispatch does not
prove listening. Keep these signals separate before deriving preference features.

Keep raw events so derived play counts and preference rules can be recalculated.
Keep device favorites, assistant-only likes and inferred preferences separate.
For a request such as `Включи любимое из Linkin Park, что давно не слушал`, resolve
the artist, filter favorites and availability, then rank by last observed listen.
Explain missing history as unknown; it does not prove a track was never heard.
Use simple transparent rules before training a recommendation model. Typesense can
rank using supplied features or vectors; collecting behavior and defining the
policy remain ours. See [personalization](https://typesense.org/docs/guide/personalization.html).

Add lyrics through an optional enrichment adapter after metadata search works.
Store provider, external recording/work ID, language, retrieval time, provenance
and matching confidence. Respect the chosen source's storage/use terms. Lyrics
stay separate from firmware metadata and audio files. Match a composition to its
recordings carefully; unresolved external matches must not overwrite local tags
or merge studio/live/CUE entries. External outages must leave local search usable.
Provider/model selection remains deferred; use the planned embedding snapshots
above for the hybrid-search experiment.

## Implementation milestones and acceptance

Each milestone produces a usable increment. The first desktop prototype ends at
M3; later milestones extend it and do not block the first end-to-end result.

| Milestone | Work | Exit evidence |
| --- | --- | --- |
| M0: session and catalog | Shared device session; SQLite migrations; complete paginated snapshots; internal identities | Synthetic fixtures and a read-only physical catalog import; interrupted sync preserves the last complete snapshot; no personal data committed |
| M1: text search | Local Typesense index; field weights, aliases, filters; minimal text UI | Labeled exact/typo/Cyrillic/duplicate/missing queries; measured ranking and resources; index rebuild from SQLite works |
| M2: text-to-playback | Bilingual intents, explained automatic best-match ranking, fresh selection and outcome verification; dialogue deferred | Artist/recording launch; deterministic ranking; absent explicit versions and stale sources rejected; disconnect never replays commands |
| M2a: playback controls | State-aware pause/resume, explicit Assistant stop semantics, next/previous; no search dependency | Repeated requests, unknown/loading/EOF states, external transitions and uncertain writes; no toggle replay; previous-to-start behavior |
| M2b: native queue and continuation | Read actual album/artist queue after selection; preserve mode by default, explicit opt-in continuous mode | Type-7 natural EOF, five modes, middle/last/single entries, external queue changes and per-operation results for mode + selection |
| M2c: persistent device session | One foreground application owns TCP and event/state routing; interactive console plus retained one-shot CLI; explicit connect/disconnect and bounded reconnect | Repeated commands use one connection; events arrive without commands; disconnect cancels unsent mutations; reconnect refreshes state without playback replay; explicit disconnect suppresses reconnect |
| M3a: file speech — implemented | PCM WAV input, local whisper.cpp STT, macOS sample TTS, per-locale corpora and debug/journal integration | 216 prototype tests; real synthetic RU/EN evaluation exposes music-name failures; STT through Controller verified with a synthetic TCP peer |
| M3b: microphone — pending | Button recording, speech boundaries, transcription into the same pipeline | Human/noisy recordings, live microphone trials, silence rejection and latency/resource evaluation |
| M4: personal selection | Event reconciliation, favorites mirror, observed-history aggregates | Repeated events, seeks and gaps do not inflate history; favorite/recency requests behave as documented; exact requests remain exact |
| M5: enrichment and hybrid search | Optional lyrics provider, provenance, phrase search; versioned embedding snapshots with incremental cache reuse and lexical/vector retrieval | Correct recording links; measured quality/latency against lexical baseline; interrupted rebuild/model changes cannot mix generations; usable lexical search during model/provider outages |
| M6: hands-free input | Wake word, cancellation and optional spoken clarification | False activations and misses measured in quiet and with music; button input remains available |
| M7: Pi deployment | Run the same service on Raspberry Pi 5; microphone setup, startup and data persistence | Repeat desktop cases; measure latency, memory, temperature and noise; test Wi-Fi commands during LDAC playback and charging |

Before M1/M3 tuning, assemble a fixed labeled evaluation set from representative
library entries: Russian/English names, transliterations, duplicate editions,
overlapping artist/album names, absent tracks and silence/noise for voice. Keep
personal evaluation material local and commit only synthetic equivalents. Reserve
cases not used for tuning. Report top-1/top-k retrieval, wrong automatic launches,
clarification rate and per-stage median/p95 latency. Set numerical targets after
the baseline; do not promise response times before measuring the host and model.

Acceptance must include event-only deltas, final-stop silence, changed catalog
positions, partial sync, index lag, CUE identity collisions and reconnect. Start
physical playback with deliberately selected media and bounded volume; acceptance
does not require library deletion/reset or playlist mutation. Verify device
metadata/state and separately observe actual audio for hardware claims.

Firmware-free component tests cover parsing, identity, synchronization and event
logic. Typesense integration uses a disposable local index. Firmware acceptance
uses generated media and disposable emulator stacks, following the existing
[test-selection policy](CI.md#test-selection-policy); emulator results do not
establish microphone quality, physical Bluetooth audio or Wi-Fi sleep behavior.

## Hardware horizon and deferred decisions

Available boards: Raspberry Pi 4B, Raspberry Pi 5, owner-described Orange Pi Zero
3w and Zero 2w, and Raspberry Pi Zero 2 W. Confirm exact Orange Pi variants, RAM
and OS support before deployment decisions. Pi 5 is the first migration target;
evaluate Pi 4B or smaller boards after measuring the workload. A compact board
with speech inference on another host remains an optional arrangement.

A future Disc-hub may initially provide USB-C charging, microphone, controls and
an enclosure while DISC sends audio directly to an LDAC receiver. A 4.4 mm audio
path, analog electronics, mechanical docking, integrated amplifier/speakers and
audio measurements are later hardware work. LDAC support is not a lossless or
end-to-end Hi-Fi guarantee. See [FiiO transmitter documentation](https://www.fiio.com/newsinfo/1111812.html)
and [Sony LDAC description](https://www.sony.co.jp/en/Products/LDAC/).

Also deferred: repository split, cloud accounts/music services, a general chat
assistant, autonomous destructive commands, comprehensive web-remote features,
multi-user recommendations and an always-listening production appliance.

The first **M0/M1 subset** now runs under `research/disc_assistant/`. It exposes
`sync`, `status`, `index` and `search`; setup and tests are in its
[guide](../research/disc_assistant/README.md). It preserves literal album-scoped
rows and duplicate multiplicities, publishes snapshots atomically in SQLite and
rejects lagging search indexes. That initial checkpoint used a short diagnostic session; M2c below adds the
persistent event-routing application. Internal identities
are snapshot-scoped; cross-snapshot reconciliation remains unimplemented.

Validation covers synthetic paginated TCP/HTTP catalogs with a real Typesense
30.2 server and official Python SDK 2.0.0: exact, typo, Cyrillic alias, album,
duplicate/CUE and missing queries; index rebuilding and stale-index rejection.
These are functional checks, not a personal-library ranking/resource benchmark.
Read-only CLI import/status passed against the interactive guest’s empty catalog;
a subsequent nonempty physical V2.57 import also passed using temporary storage.
The initial `a60a/0010` notification had exposed an overly broad scan guard;
classification now uses the verified scan payloads instead of the whole status tag.
The owner then confirmed the desktop flow works against the physical player:
`sync → index → search`. The first read-only slice is accepted for further
prototype development. At that checkpoint, all 39 prototype unit tests passed; the existing
firmware-free project checks and disposable Typesense acceptance also passed.
No media scan or playback was triggered by the prototype.

This does not complete every original M0/M1 goal: cross-snapshot identity
reconciliation, a browser UI and measured search/resource
baselines remain open. Functional physical search is owner-confirmed; ranking
quality has not been measured on a fixed labeled personal-catalog evaluation set.

## Text-command increment, 2026-09-18

The owner changed the immediate interaction policy: **launch the best available
match automatically; add selection dialogue later**. The implemented increment adds:

- `rank 'Включи …'` / `rank 'Play …'`: complete-snapshot exact/alias matching and
  bounded fuzzy retrieval, with deterministic scores, version rules and tie breaks.
- `ask '…'`: the same ranking followed by one guarded Controller artist/track launch.
  The local snapshot is checked against two fresh artist-scoped reads; the final
  Controller HTTP preflight checks identity as well as bounds. Reordering computes
  a fresh position. Indistinguishable copies use the first current matching row
  and report their multiplicity, not a permanent identity claim.
- A per-data-directory device-operation lock, one sequential playback event reader
  retaining unrelated notifications across queries, and no automatic mutation
  retry/reconnect. Result states distinguish not-sent, playing and uncertain.
- A [command table](ASSISTANT_COMMANDS.md) describing actual CLI/text commands,
  ranking factors, result semantics and deferred operations.

History, favorites and popularity are not included in ranking without observations.
Version penalties are metadata-label heuristics, not an audio-quality or release
identity claim. Lexical scores are not probabilities. See the command document for
weights, thresholds, retrieval limits and deterministic tie rules.

Unit/transport fixtures cover bilingual commands, aliases, fuzzy matches, version
constraints, stale/reordered source rows, interleaved scan events, metadata/state
deltas and uncertain writes without replay. Disposable Typesense acceptance uses
real Controller TCP/HTTP clients and a synthetic player for best-match artist,
recording and requested-live launches. At the text/control checkpoint, 97 prototype tests passed, including
language selection/merging, multiword forms, dictionary validation, controls without
search, actual queue observation and partial mode/selection failures. A read-only
`rank` query against the owner's existing physical-library snapshot returned the
requested recording via its explicit Cyrillic aliases. This validates the software
path and one live-data ranking case; physical `ask` playback and a labeled
personal-library ranking benchmark remain pending.

M2a/M2b validation also passed on a disposable V2.57 guest: actual controls,
previous-to-start after ten seconds, queue continuation after CLI disconnect,
and natural type-7 EOF across all five modes with generated six-second tracks.
The shared firmware-free suite passed 313 Python / 37 JavaScript tests alongside
the 97 prototype tests. Physical controls/continuation acceptance remains pending;
see [playback validation](ASSISTANT_PLAYBACK.md).

## Persistent-console increment, 2026-09-18

M2c now provides `run.sh start`: start/check Typesense, connect once, synchronize,
prepare search and keep an interactive text console open. `listen` skips startup
sync/index and uses existing data. Direct music/control phrases and maintenance
commands share one session with a continuously running reader. Connection loss
invalidates pending work and permits observation-only reconnect; explicit
`/disconnect` disables it. `/exit` leaves native playback and Typesense running.

The previous one-shot flow remains supported for scripts and cron. Device commands
require exclusive ownership of the same data directory; offline operations remain
independent. This original M2c checkpoint did not include local IPC or durable
history. The later request-journal increment below adds inspection storage;
listening-history collection and IPC remain separate work. See the [session contract](ASSISTANT_PLAYBACK.md#m2c-persistent-device-session)
and [console command table](ASSISTANT_COMMANDS.md#interactive-console).

Unchanged catalog snapshots are reused only after two full equal network reads.
Startup checks the matching search collection/count and rebuilds missing indexes;
explicit `/index` rebuilds on demand. Search outages leave controls available.

Validation: 114 prototype tests passed alongside the full 313 Python / 37
JavaScript project suite; subsequent focused interrupt/reconnect rejection tests bring the
prototype total to 116. Disposable Typesense acceptance verifies one handshake and
socket across startup and console commands, snapshot/index reuse and missing-index
recovery. Focused disposable V2.57 acceptance verifies idle track-change events,
shared sync/control/queue, reconnect without mutation replay, silent final-stop
reads on a healthy connection, and explicit disconnect remaining disconnected.
No new physical playback/session acceptance is claimed.

## Request-journal increment, 2026-09-18

Implemented next at the owner's request, before shared Controller API extraction:

- Private Assistant SQLite schema 2 preserves settings and adds request/event
  tables. Requests commit before parsing, with source/session/device attribution.
- Parsing, catalog/index/rule versions, bounded retrieval/ranking candidates,
  automatic best-match selection and operation IDs/outcomes remain separate evidence.
- Invalid phrases, search failures, stale indexes, not-sent/uncertain execution and
  interrupted/pending requests remain inspectable. No mutation is replayed.
- Console and one-shot paths share collection; `--source scheduled` labels cron
  requests. Automatic preparation is marked `startup`. Commands for recent/detail
  inspection, JSONL export, pruning and explicit clearing are available offline.
- Default retention is 90 days / 10,000 completed requests, with configurable
  collection and limits. Preferences/catalog survive history clearing.

See the [journal contract](ASSISTANT_HISTORY.md). This does not implement listening
interval reconciliation, favorites-derived preferences or personalized ranking.

The subsequent shared Controller extraction is now implemented; see
[the API boundary](CONTROLLER_API.md). Next: physical session/playback acceptance
and representative ranking evaluation, followed by microphone input or a remote
adapter over this shared session. Recommendations and repository promotion remain
separate subsequent work.

## Interactive terminal increment, 2026-09-18

`start`/`listen` now use `prompt_toolkit` in capable terminals: history recall and
search, suggestions, slash-command/language-dictionary completion, screen clearing
and readable multiline help. Recall reuses the existing request journal with its
retention and device namespace; disabled journaling uses session-only history.
Ctrl-C cancels editing; an interrupted operation still exits without replay.
One-shot commands and redirected input/output retain JSON output; dumb terminals
use plain input. Controller and playback behavior are unchanged. See the
[interactive command reference](ASSISTANT_COMMANDS.md#interactive-console).

Validation: 154 prototype tests (including ten terminal/history regression tests)
and the 330 Python / 37 JavaScript firmware-free project suite pass. A real PTY
with a synthetic TCP peer verifies completion, history suggestions, multiline help,
screen clearing and input cancellation without reconnecting. No firmware/runtime
behavior changed; no new physical playback acceptance is claimed.

The terminal also supports configurable prompt/input/result/error/warning and
suggestion colors via `[terminal]`, with a `NO_COLOR` override. Terminal formatting
does not alter command parsing, journal evidence or redirected JSON. Font family
and size remain terminal-application settings.
The prompt displays `[device].key`; `/device` reports configured endpoints and
cached session state, including while disconnected. It performs no network query
or target switch. Connected/disconnected command coverage and the 154-test
prototype suite pass.


## Localized response increment, 2026-09-18

Historical checkpoint: the later interpreter refactor below replaces independent
input/response languages with a single locale.

Implemented a common response layer for console and one-shot requests. Results
retain their operation evidence and add `response.code/text/language/speak/interactive`.
Confirmed, already-satisfied, uncertain, not-sent, interrupted and invalid requests
receive distinct localized feedback. Maintenance results can have no user-facing
text. This does not change best-match selection or retry device mutations.

RU/EN templates live in `assistant/locales/replies/`. Persistent response language
and speech mode (`none`, `errors`, `all`) are independent of accepted command
languages; scheduled/startup requests are always silent. The journal records
responses plus template provenance. `interactive` remains false and enabling
`[dialogue]` is rejected until a request-bound dialogue state machine exists.
No TTS, microphone input or spoken-delivery tracking is implemented.

Community locales require command and response TOML catalogs, with automatic
filename discovery and validation of full coverage, literal phrase conflicts and
safe template parameters. See the [response contract](ASSISTANT_RESPONSES.md) and
[locale contribution guide](ASSISTANT_LOCALES.md). Console `/response` and `/locales`
and equivalent one-shot commands expose settings and validation.

Next: physical use feedback and ranking evaluation, then a microphone/voice adapter
consuming the same response contract. Dialogue, listening-derived recommendations
and promotion out of research remain separate work.

Validation: 173 prototype tests pass, including contributed-locale loading,
response policies, CLI/console/journal parity, preference recovery and template
validation. Disposable acceptance with synthetic TCP/HTTP peers and real
Typesense also passes. No firmware or physical-device behavior was changed.


## Interpreter and single-locale refactor, 2026-09-18

Implemented an asynchronous interpreter protocol, a local rules backend and a
common validation boundary for injected local/remote providers. Interpretation
runs once; catalog resolution and ranking consume its typed result. The launcher
no longer interprets text. Connection generation is pinned before interpretation
so a slow backend cannot dispatch a stale request after reconnect.

Input and response language now share one persisted locale. `/language CODE`,
`--language CODE` and natural language switching update the same setting; success
is acknowledged in the new locale. Legacy settings/configuration have a defined
migration path; old files and journal records are not rewritten. `/response` retains
only speech mode. Music names and recording-version metadata stay independent of
command language. Community locale catalogs now include language-switch syntax.

Added independent STT, TTS, microphone capture and audio-output protocols with
explicit audio formats, locale/request context and provider identity. There are no
concrete speech or remote-model backends, automatic fallbacks or dialogue changes.
See [ASSISTANT_ARCHITECTURE.md](ASSISTANT_ARCHITECTURE.md) for the current contract.

Next: language-specific ranking/interpretation evaluation, then a concrete
microphone/transcription adapter using these boundaries. Physical acceptance,
TTS delivery, dialogue and recommendations remain separate increments.


Validation: 192 prototype tests pass. Disposable real-Typesense/synthetic-player
acceptance passes; a real launcher smoke check verifies durable `--language`,
natural switching and rejection of another locale's command syntax. Tests cover
provider substitution, invalid output, unavailability/cancellation, single-pass
interpretation, reconnect rejection, settings migration and independent metadata
version labels. Controller and firmware code are unchanged; no microphone,
external-model or physical speech acceptance is claimed.

## Request timing and debug traces, 2026-09-18

Traced application responses now include `timing.total_ms` and `request_id`,
including failures and requests with journaling disabled. History commands have
timing without recording themselves. Timing uses a monotonic clock and ends at
response construction, before final persistence/output; launcher startup and input
editing are excluded. Saved outcomes retain the timing without a schema change.

`/debug [on|off]` controls live structured traces for the current console session;
global `--debug` enables them for `start`, `listen` or a one-shot application command.
CLI/redirected traces use stderr, preserving one-shot JSON stdout. Terminal traces
have a configurable color. Debug output failures do not interrupt/replay actions.
Search diagnostics expose snapshot size, resolved intent, local matches, actual
Typesense queries and retrieval/filtering counts, without collecting raw packets
or SDK exception bodies. See [commands](ASSISTANT_COMMANDS.md#timing-and-live-debug-traces).

Validation: 202 prototype tests pass, covering monotonic timing, saved outcomes,
disabled journals, errors, history clearing, session-only toggles, bounded and
escaped trace output, stdout/stderr separation, output failures and local/search
matching diagnostics. Controller and firmware are unchanged. Physical diagnosis
of the reported artist lookup remains to be done against the owner's catalog.

## File speech increment, 2026-09-18

Implemented M3a before microphone capture: `transcribe FILE`, `rank --audio FILE`
and `ask --audio FILE`, plus console equivalents. A local whisper.cpp adapter
transcribes validated PCM WAV into the existing single-locale interpreter path.
The console pins connection generation before STT; no replay or administrative
slash-command dispatch follows recognition. Traces/journals now record provider,
model/audio hashes, transcript and timing, without copying source audio.

The local macOS `say` TTS adapter generates explicit WAV/metadata artifacts.
`speech-samples` creates per-locale corpora, and `speech-check` compares intentions
without catalog/device access or settings changes. Community additions use data
files and deployment voice/language mappings. Automatic response TTS delivery is
still pending even though the reusable synthesis backend now exists.

Validation: 216 prototype tests pass. Real whisper.cpp v1.9.4 CPU inference on
synthetic RU/EN corpora gives 3/6 per locale with base and 4/6 with small; music
name accuracy remains unresolved. A real synthesized Russian pause went through
STT and Controller to a synthetic TCP peer with exactly one mutation and a
confirmed result. See [setup, evidence and limitations](ASSISTANT_VOICE.md).
The report is tracked; generated WAVs, downloaded models and external engine
builds are outside the repository. No physical-player speech acceptance is claimed.

Remaining: representative human/noisy recording evaluation and music-name
resolution, portable TTS, microphone/VAD, resident inference/latency tuning,
automatic response synthesis/output and cancellation, then Pi deployment.
Dialogue, recommendations, listening history and online providers remain deferred.

### Base versus small comparison rerun

At the owner's request, reran both models against the same twelve saved synthetic
WAVs, with unchanged hashes/expectations and isolated temporary preferences. Base
again passed 3/6 per locale; small passed 4/6. Median STT durations were 347/302 ms
for base (RU/EN) versus 960/861 ms for small. Base was faster but lost a control or
language-switch case in each locale; both retain music-name/reference mismatches.
This is one sequential pass, not a controlled latency or human-speech benchmark.
See the [comparison evidence and interpretation limits](ASSISTANT_VOICE.md#recorded-acceptance).
No runtime code, user configuration or physical-player state changed.

## Catalog speech evaluation and matching increment, 2026-09-18

Implemented `speech-check --catalog` with explicit expected selections and separate
transcription, interpretation and selection outcomes. It pins one catalog/index
and performs no device operations. Existing sample manifests accept a separate
expectation overlay; bundled new corpora include synthetic target metadata.

Lexical-v3 adds data-defined Cyrillic transliteration, catalog-backed fuzzy artist
boundaries and conservative recovery of fused artist/title spellings. Literal
names outrank aliases/projected spellings. The projection covers artist/title/album
spellings and fingerprints the table. Rebuild using `/index` once after upgrading;
no catalog rescan is needed solely for this change. STT transcripts are preserved.
See [commands](ASSISTANT_COMMANDS.md) and [evaluation](ASSISTANT_VOICE.md#catalog-selection-evaluation).

At the owner's request, the next language-understanding work now compares intent
embeddings, phonetic/name matching, Typesense hybrid and Natural Language Search,
and a small trained intent classifier. This comparison moves ahead of microphone
work; optional semantic retrieval no longer waits for lyrics enrichment in M5.
[The research plan](ASSISTANT_NLU_RESEARCH.md) defines provider boundaries,
held-out evaluation, rejection, model/snapshot provenance and deployment criteria.
These model-backed approaches are planned, not enabled. Hand-authored aliases
remain an optional baseline, not the assumed final solution.

Validation: 224 prototype tests and disposable real Typesense/synthetic-device
acceptance pass. Fixed music samples give 0/8 correct selections for archived
lexical-v2, 2/8 for lexical-v3 without aliases, and 7/8 with aliases tuned to these
observations. Those eight decisions reuse four WAVs across base/small and a
seven-row synthetic catalog; they do not establish generalization. See the
[recorded catalog comparison](ASSISTANT_VOICE.md#recorded-catalog-comparison).


## Read-only embedding and hybrid experiment, 2026-09-18

Completed the first comparison from the expanded NLU plan in
[`experiments/nlu`](../research/disc_assistant/experiments/nlu/README.md): 182
RU/EN authored phrases, fixed train/development/test partitions, calibrated intent
exemplar matching, reusable model/text vector cache and disposable real Typesense
lexical/vector/hybrid track retrieval. Requirements/model download are explicit
and isolated; Assistant runtime dependencies and defaults are unchanged.

Vector candidates improve guarded selection from 15/20 to 17/20 expected tracks
on the authored test fixture. Nearest embedding intent labels still confuse
non-commands and negation; strict RU calibration rejects all commands. There is
no live semantic command rollout or training claim. Full evidence, resource
observations and limitations are in the experiment guide. All 229 prototype tests
pass. Next: broader vector-fallback evaluation, trained negative-aware intent
classification/slots and typed Natural Language Search; human speech remains open.

## Command snapshots and supervised explanation, 2026-09-18

Implemented [versioned command references and `/explain`](ASSISTANT_COMMAND_CATALOG.md)
(the owner's preferred name for the proposed `/interpret`). Per-locale TOML
examples/templates compile into Assistant schema-3 snapshots; explicit JSON import
adds validated model provenance, reference embeddings and a portable text
classifier. Stale grammar/source changes require an explicit rebuild/retrain.
Existing preferences/history survive migration; normal execution stays on rules.

The isolated supervised experiment compares word/character TF-IDF and frozen
MiniLM linear classifiers, with development-only thresholds and a new authored
challenge. The combined preview recognizes 6/16 RU and 5/16 EN commands, versus
2/16 each for existing rules, and no false activations on eight negatives each.
Most improvement comes from explicit extraction: EN model selection rejects all
predictions. This is not evidence for enabling a learned execution provider.
See [full results and limitations](../research/disc_assistant/experiments/nlu/README.md#supervised-command-study).

Validation: 241 firmware-free tests, including snapshot rollback/staleness,
schema-2 migration, slots, negation, CLI/console execution boundaries and split
isolation; actual training/export/import and scorer parity on 130 cases per locale.
No physical player, microphone or Pi acceptance was performed in this increment.
Next: independent command/STT examples and better supervised coverage, then a new
holdout comparison before enabling the provider. Vector music fallback, structured
NL filters, microphone input and spoken replies remain separately pending.

## Reviewed-data workflow and supervised v2 study, 2026-09-18

Implemented the [annotation and training workflow](ASSISTANT_NLU_DATA.md). A
609-row bilingual corpus has training/development/test frozen before evaluation
and a recorded correction restoring one omitted legacy regression row. Training,
development, new authored test and earlier regression remain separate. Rows retain
review identity/rationale, origin, typed slots and related-example groups. These
are assistant-authored labels, not independently reviewed human examples.

Private history collection creates unlabeled review queues, retains recording/model
fingerprints when present, and never treats previous predictions as ground truth.
Explicit review and freeze commands validate slots and prevent split leakage;
model selection uses development only. The generic runner compares ordinary and
balanced text and frozen-embedding classifiers and exports portable preview models.

The full preview reaches 12/35 RU and 14/35 EN correct complete test intentions,
versus 2/35 per locale for extraction/guards alone, but has 3/20 RU and 2/20 EN false
activations. New language argument extraction is 0/5 per locale. The report exposes
these failures separately from class recognition and earlier synthetic-STT results.
No learned execution promotion follows. Validation: 253 prototype tests, actual
four-way training, JSON scorer parity, import and ordinary-runtime explanation.

Next: human review and new speech data, contextual rejection and slot extraction,
then explicit shadow comparison. Encoder fine-tuning, live learned execution and
Pi resource measurements remain pending. See the workflow document for collection,
annotation, reproduction and per-variant evidence.


### Shadow reporting and MVP scope checkpoint — 2026-09-18

Added offline `run.sh shadow-report`, consuming an explicit history export without
loading runtime config or invoking a provider/device. Reports separate locale,
input modality, STT fingerprint and source revision; retain availability and
coverage exclusions; export prediction-free pending annotations; and compute
quality only against explicit reviewed labels. Request repetitions and unique
inputs are both visible. The [workflow](ASSISTANT_SHADOW_REPORTS.md) explains
sampling bias and why interpretation metrics are not device-outcome metrics.
The firmware-free prototype suite passes 278 tests.

Added the research-local `AGENTS.md` handoff and [MVP tracker #21](https://github.com/eudj1n/snowsky-disc-qemu/issues/21).
Next: freeze a representative, reviewed end-to-end baseline, measure current
execution on DISC, then agree numerical thresholds and run acceptance. Complex
commands and later component replacement/improvement are outside this MVP.


### Baseline preparation — 2026-09-18

Prepared a [physical-player operator worksheet](ASSISTANT_BASELINE.md) with 20
text case specifications per locale, preconditions, current stop semantics and
separate response/interpretation/device observations. The owner confirmed physical `my-player` and text RU/EN first; exact catalog
bindings and owner phrasing still require confirmation. The worksheet is a draft,
not a frozen or executed baseline; thresholds and acceptance remain pending.


### Bound baseline checkpoint — 2026-09-18

Owner-confirmed physical `my-player`, text RU/EN first. Six supplied recordings
were bound through a read-only local snapshot (792 tracks), preserving duplicate
editions and compound artist metadata. A private 30 RU / 21 EN packet includes
complete typed gold, expected physical outcomes and blank observations; its case
set is frozen but live preflight/execution are pending. No personal media list or
packet was committed. See [baseline status](ASSISTANT_BASELINE.md).

Requested Russian synonyms, default-track behavior and explicit album support
are recorded separately from existing behavior. Dictionaries were not tuned
before measurement. Album is a positive desired capability gap, not a rejection
example; no executing album intent was added.
