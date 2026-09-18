# Assistant request and decision journal

Implemented in the research prototype on **2026-09-18**. This records requests,
search decisions and operation outcomes for later analysis. It does not yet
collect listening intervals or change ranking/recommendations.

## What is recorded

Every nonblank console request and application CLI command receives a `request_id`
before command parsing. The console shares a session ID across requests; each
one-shot process has its own. Sources distinguish `interactive`, `cli`, explicitly
marked `scheduled` requests, and automatic `startup` preparation.

| Evidence | Fields and meaning |
| --- | --- |
| Input | Original text, normalized copy, command, source, device namespace, session/request IDs, UTC time |
| Parsing | Enabled command languages, parser version, hash of the actual language rules, parsed intent/parameters and resolved artist/title intent |
| Search context | Snapshot/index generation, collection and index signature (including the alias/config fingerprint); actual fuzzy query when used |
| Retrieval | Up to 10 candidates with metadata, snapshot identity/provenance, matched tokens and search scores; returned/found counts and truncation flag |
| Ranking | Up to 10 ranked candidates, scores/reasons, ranking policy and retrieval method; exact SQLite matches do not invent a Typesense query |
| Selection | Best candidate, rank, snapshot generation and `automatic_best_match` method; recorded only for a requested launch |
| Execution | Start of the operation, linked operation ID, reported mutation attempt, observed result/state and separate mode-change outcome when available |
| Failure | Stage, category and exception class, or `not_sent`/`uncertain` operation outcome; raw exception bodies are excluded |
| Timing | Per-event UTC timestamp and elapsed milliseconds from request start |

`rank` and `search` retain candidates without claiming playback selection. A
zero-result search is identifiable by `found=0`; music ranking returns `not_found`.
Unrecognized/invalid phrases, invalid preferences, stale catalog/index, search
failure and execution failure remain distinguishable. The current bounded grammar
cannot reliably identify an unsupported natural-language intention; retain the
original phrase for later analysis rather than inventing its meaning.

The journal retains duplicate/CUE candidates separately. Metadata accompanies
snapshot-scoped IDs so evidence survives catalog refresh/pruning. It does not
claim permanent recording identity or reconstruct every omitted candidate.
Original input is capped at 4,000 characters with `input_truncated`; structured
evidence bounds string lengths, nesting and list sizes. Candidate truncation is
explicit. No full library/queue dump, raw network packet, credential, SDK response
body or microphone recording is deliberately collected. User-entered text itself
is personal data and is stored locally as supplied within the input limit.

## Storage and failure semantics

The journal uses `assistant.sqlite3` in `[storage].data_dir`, alongside the separate
`library.sqlite3`. Schema **2** adds `requests` and `request_events` to the existing
`settings` table. Migration from schema 1 preserves preferences under a transaction;
unknown schema versions are rejected. Event foreign keys cascade when a request
is removed. New database/export files are private to the user.

Each stage commits independently, before progressing to the next stage. A process
crash can leave `pending` evidence; interrupted commands are marked `interrupted`
when the handler can save their outcome. Neither means that no device write
happened. `execution_started` records entry into execution, not proof of socket
dispatch. A reported `mutation_attempted` and Controller outcome are separate
evidence. The journal never replays commands, restores a queue or resumes music.

With journaling enabled, an initial storage failure prevents the request from
running. A later journal-write failure can follow a completed device action and
is reported with an explicit no-replay warning. A saved outcome is an observation,
not a guarantee of audible output, atomic device state or completed listening.

This is an inspection journal, not an idempotent command API or an IPC result
service. Future shared API work must preserve these boundaries. No listening
history is inferred from native playback that continued after Assistant exit.

## Commands and retention

In the console:

```text
/history
/history 50
/history show REQUEST_ID
/history export "/absolute/path/request history.jsonl"
/history prune
/history clear --yes
```

The same operations are available without a device or search connection:

```sh
./research/disc_assistant/run.sh history
./research/disc_assistant/run.sh history show REQUEST_ID
./research/disc_assistant/run.sh history export /absolute/path/history.jsonl
./research/disc_assistant/run.sh history clear --yes
./research/disc_assistant/run.sh --source scheduled ask 'Pause'
```

Put global `--config`/`--source` options before the command. Scheduled origin must
be explicit; the application does not guess whether a process came from cron.
Recent-history limit is 1–100, default 20. Detailed records include ordered events.
JSONL export uses a consistent SQLite read transaction, requires a new destination
outside the checkout and refuses overwrite. Treat a failed export as incomplete.

History operations are excluded from journaling so inspection does not alter the
history and clearing does not immediately insert another record. Clear removes
all request history in this data directory, across devices, while preserving
preferences and the catalog. It requires the literal `clear --yes` command.
Blank console input is ignored. Launcher infrastructure (`setup`, `up`, `down`,
tests), invalid CLI syntax/configuration before application startup, and raw
transport pushes are outside this request journal.

TOML defaults, also applied to older configurations:

```toml
[journal]
enabled = true
retention_days = 90
max_requests = 10000
```

Age retention covers completed and unfinished requests. The count limit covers
completed requests; recent in-flight requests are retained separately. Cleanup
runs when starting/finishing a journaled request or explicitly with `history prune`.
It is not a wall-clock background deletion service. SQLite may retain reusable
free pages after deletion; this is not a secure-erasure facility. Disabling new
collection does not delete old history; inspection/export/clear still work.
Back up both SQLite databases consistently while the application is stopped, or
use SQLite's online backup API.

## Analysis boundaries and next step

An automatic best match is an algorithm decision, not an explicit like. A command
from cron differs from a manual request. Search, dispatch, confirmed playback,
observed listening and favorites must remain distinct signals. A pause alone does
not establish dislike. Recommendation features and listening aggregates are later
work; this increment provides their request-side evidence.

Next, define and extract the shared Controller session/state API for Assistant
and a software remote. Keep language preferences, command journals, ranking and
recommendation policy in Assistant. See the [API boundary plan](ASSISTANT.md#shared-controller-api-follow-up).

Validation covers schema migration, malformed commands, source attribution,
ranking/selection provenance, duplicate entries, bounded candidates, missing search,
uncertain operations, interrupted/pending records, journal failures, retention,
export/clear and preference preservation. Disposable Typesense acceptance exercises
the real CLI/controller path against a synthetic player and checks journal records
after process exit. It does not use a physical player or collect personal history.

The 2026-09-18 firmware-free checks passed 142 prototype tests and the shared
313 Python / 37 JavaScript tests. The disposable real-Typesense/synthetic-player
acceptance passed request/search/selection/outcome persistence across process
exit, rejected commands, scheduled attribution, export and clear.
