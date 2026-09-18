# Disc Assistant: implementation plan

Checkpoint: **2026-09-18**. The desktop prototype in
[research/disc_assistant](../research/disc_assistant/README.md) now includes catalog
import, SQLite snapshots, Typesense search, bilingual text commands, explained
ranking and bounded Controller playback. `rank` previews the ordering; `ask`
automatically launches the best candidate. The owner explicitly deferred a
choice/confirmation dialogue. Voice, listening history and a browser UI remain
unimplemented. See the [command table](ASSISTANT_COMMANDS.md).
The current device contract is [DISC capabilities](DISC_CAPABILITIES.md).

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

Implemented language forms live in separate `assistant/locales/ru.toml` and
`en.toml` files. `[language].enabled` merges literal command, target and version
phrases; the default enables both, including mixed-language requests. Conflicting
meanings fail validation. Adding forms for existing semantics requires no parser
change; new actions still require implementation. See the
[language configuration](ASSISTANT_COMMANDS.md#language-dictionaries).

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

Add microphone recording by button before continuous listening. Select the input,
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

### Device language and bilingual commands

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
Keep assistant UI/reply language and accepted command languages independent of it.
The command parser accepts both `Включи Linkin Park` and `Play Linkin Park`,
mapping them to the same intent. Test both text variants and mixed Russian/English
speech; do not force an English-only model based on a presumed device locale.
Choose assistant UI language explicitly or from the host/browser preference with
a user override. A future verified device-locale getter may supply a default,
but must not restrict accepted command languages.

### Device session rules

- The production direction is a persistent connection owned by the Assistant
  application service. Per-command connections are a temporary CLI prototype
  boundary, not the intended lifecycle. Implement M2c before microphone work;
  see [persistent session migration](ASSISTANT_PLAYBACK.md#m2c-persistent-device-session).
- Own one TCP connection and one reader in the application service. Serialize
  requests and route replies/events centrally; do not give each UI, catalog worker
  or voice request its own connection. FiiO Control can compete for the stock
  single-client connection. Existing diagnostic reply-draining behavior needs
  review before reuse as a persistent event service.
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
bypass search/index dependencies. A short-lived CLI has no background continuation
plan to cancel. `playback.continuous_context=true` explicitly permits a separately
verified persistent repeat-list mode change before selection; default configs
preserve mode. Arbitrary queue plans and their cancellation remain future work.

These rules follow [DISC capabilities](DISC_CAPABILITIES.md),
[remote control](REMOTE_CONTROL.md) and [track completion](TRACK_END.md).

## History, preferences and external enrichment

Design event storage early, then add personalized selection after basic playback
works. Record user intent, command dispatch, confirmed playback and observed
listening intervals separately. Do not count a command as a completed listen,
count repeated state events twice, or fill disconnected time with assumed plays.
Track skips only when evidence supports that attribution. Seeking is not elapsed
listening. Completion must follow observed firmware behavior; retain partial or
unknown sessions when evidence is insufficient.

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
| M2c: persistent device session | One application service owns TCP and event/state routing; CLI becomes a local client; explicit connect/disconnect and bounded reconnect | Repeated commands use one connection; events arrive without commands; disconnect cancels unsent mutations; reconnect refreshes state without playback replay; explicit disconnect suppresses reconnect |
| M3: microphone | Button recording, speech boundaries, multilingual transcription into the same pipeline | Recorded evaluation phrases and live microphone trials; silence rejection; recognition, retrieval and total latency reported separately |
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
rejects lagging search indexes. It has a short diagnostic device session, not the
persistent event-routing service in the target architecture. Internal identities
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

This does not complete every original M0/M1 goal: persistent event routing,
cross-snapshot identity reconciliation, a browser UI and measured search/resource
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
recording and requested-live launches. All 97 prototype unit tests pass, including
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

Next: migrate per-command sessions to the persistent application service (M2c),
evaluate `rank` on representative physical-library queries and validate bounded
`ask` playback, controls and native continuation on deliberately selected physical
music, then add button-driven microphone input
(M3). Continue in `research/disc_assistant/`; promotion, repository splitting,
arbitrary recommendation-queue execution, a background history session and a
choice dialogue are separate later work. Native queue selection works through
existing guarded Controller APIs; no new firmware command was introduced.
