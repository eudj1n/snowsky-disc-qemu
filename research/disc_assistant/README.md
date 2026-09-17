# Disc Assistant research prototype

Working desktop slice: **device catalog → SQLite → Typesense → text candidates**.
The experiment lives entirely here until it is ready for promotion into the main
project. The [plan](../../docs/ASSISTANT.md) describes the wider assistant/dock work.
It runs independently of the emulator and only imports its public controller package.

- [assistant/](assistant/README.md): configuration, CLI and a bounded device session.
- [library/](library/README.md): complete catalog reads, snapshot storage and search.
- [check.py](check.py): disposable acceptance with synthetic TCP/HTTP servers and a
  real Typesense container. No firmware or physical device is needed.

This slice returns candidates; intent parsing, playback, browser UI, microphone,
listening history and external lyrics follow later. `search "линкин парк намб"`
is a metadata search, not yet a `Включи …` / `Play …` command parser.

## Run on a computer

Use Python 3.11+ and Docker with Compose. The entry point is
[run.sh](run.sh), independent of the root emulator launcher. No virtualenv
activation or exported secret is needed. From the repository root:

```sh
./research/disc_assistant/run.sh setup
```

`setup` creates `assistant/.venv` if missing, installs the pinned requirements,
creates `~/disc-assistant.toml` if missing and generates a private search key in
`assistant/.env` if missing/empty. Existing config and keys are preserved. The key
is never printed. Edit the generated TOML before connecting to your player:

```toml
[device]
key = "my-snowsky-disc"
host = "192.168.1.50" # Replace with the actual player IP.
tcp_port = 12100
http_port = 12103
```

The template initially targets the emulator at `127.0.0.1`, HTTP **12113**;
physical DISC normally uses HTTP **12103**. Choose a distinct persistent
`device.key` per device. It is a user-assigned namespace, not a discovered serial
number. Both HTTP and TCP must point to the same device.

```sh
./research/disc_assistant/run.sh up
./research/disc_assistant/run.sh sync
./research/disc_assistant/run.sh status
./research/disc_assistant/run.sh index
./research/disc_assistant/run.sh search 'Linkin Park Numb'
./research/disc_assistant/run.sh search 'линкин парк намб' --limit 5
```

`up` starts the separate local `disc-assistant` Typesense stack and waits up to
45 seconds for HTTP readiness after Compose startup. It uses `[typesense].port`
from TOML, including for the Docker port publication. The legacy `TYPESENSE_PORT`
in `.env` is used only by manual Compose invocations. Change the TOML port if 8108
is occupied. Remote Typesense can be used by index/search, but `up` only manages
local HTTP Typesense. No CORS or LAN port exposure is enabled.

For a different configuration, place the option **before** the command:

```sh
./research/disc_assistant/run.sh --config /absolute/path/disc.toml setup
./research/disc_assistant/run.sh --config /absolute/path/disc.toml sync
```

Alternatively set `DISC_ASSISTANT_CONFIG`. Relative config paths resolve against
the calling directory. The script can be invoked by absolute path from anywhere.

The runner always calls `.venv/bin/python`, bypassing aliases such as
`alias python=/usr/bin/python3`. It selects an installed Python 3.11+ when creating
the environment; override with `DISC_ASSISTANT_PYTHON=/absolute/path/python3`.
An existing incompatible environment is reported instead of being silently deleted.
See `./research/disc_assistant/run.sh help` for commands.

The `.env` supports literal `TYPESENSE_API_KEY` and `TYPESENSE_PORT` assignments
with optional quoting/comments. It is parsed as data, never sourced as shell code.
The local key takes precedence over a previously exported default key. A custom
`api_key_env` in TOML selects that environment variable instead. Keep keys out of
browser code and committed files. The underlying Python CLI remains available
through the explicit venv interpreter and does not itself load `.env`.

`sync` needs an awake, idle V2.57 DISC with its media library already scanned.
Disconnect FiiO Control/other TCP inspectors first; stock control is single-client.
It reads metadata only, without scanning, reset, file edits or playback. It publishes
SQLite only after two equal full reads. `index` and `search` need Typesense but no
connection to the player. `status` reads local state without contacting either
service; `index_current` means matching locally recorded generations/config,
not a live Typesense health check. Commands return JSON; failures exit nonzero.

Search returns the observed title, artist, album, matched fields/tokens, a ranking
score and snapshot provenance. The score is **not a confidence percentage**.
Duplicates remain separate candidates, including identical CUE rows. Explicit
aliases are configured locally; there is no automatic transliteration claim.
Query token dropping is disabled so a missing title is not silently replaced by
an artist-only result. Each sync makes the old projection stale until `index`
finishes successfully. Changed aliases/search server also require reindexing.

## Data and limitations

The SQLite file is `library.sqlite3` under `[storage].data_dir`, defaulting to:

- macOS: `~/Library/Application Support/disc-hub/prototype/`.
- Linux: `${XDG_DATA_HOME:-~/.local/share}/disc-hub/prototype/`.
- Windows: `%LOCALAPPDATA%/disc-hub/prototype/`.

An override must be absolute (or start with `~`) and outside the repository.
New data directories are private to the user. Back up SQLite with all prototype
processes stopped, or use SQLite's online backup API. Keep the TOML alias config
with the backup. Typesense lives in the separate `disc-assistant_typesense-data`
Docker volume and can be rebuilt using `index`, even when DISC is offline.

A snapshot is a complete **observation**, not an atomic device revision. Stock API
pagination has no revision token. Two equal reads catch many races but cannot
prove that a scan was not already underway or that no edit happened between
checks. Only confirmed scan notifications block it: `a60a/000F` (start), `a622` (count),
and `a60a/0005` (end) if received during the reads. An end received before the reads
allows a new observation, without claiming that a cancelled scan was complete.
Other `a60a` statuses such as initialization `0010` are not scan evidence; an already-running scan may be
missed by the existing diagnostic client. Only sync while the player is idle.
Persistent event routing and a stronger session contract remain work for M2.

Tracks carry a new internal ID **per snapshot** plus the literal `album/song`
scope/position/raw row. Identity continuity across rescans is deliberately not
claimed: the API does not expose enough information to distinguish every CUE or
duplicate recording. These IDs/positions cannot be used as cached playback commands.
No history reconciliation is implemented yet.

If any page fails, counts/positions change, album/root membership differs, the
request/track budget is exceeded or publication loses a concurrent-import race,
the previous snapshot survives. Unsupported catalog shapes fail explicitly;
there is no guessed album fallback. Settings gate the prototype to reported
`soc_version=257`; they do not provide a verified device-language getter.

Imports are staged in bounded memory. SQLite retains old snapshots; successful
index attempts retain old collections. Failed attempts remove only their own
new collection when possible. Automatic pruning/migrations beyond schema 1 are
not implemented; monitor storage during repeated experiments. Do not run an
unbounded sync/reindex loop. Interrupted indexing may leave an unreferenced
collection; a fresh `index` never reads it. Cleanup/retention is a promotion task.

Stop Typesense with:

```sh
./research/disc_assistant/run.sh down
```

`down` keeps the index volume and also works if the TOML/key is missing. The
runner does not expose volume deletion. It never stops the emulator or deletes SQLite.

## Verification and promotion

Unit tests use the standard library, without a device, Docker or search server
(after `setup`, the runner uses its venv). They can also run directly with
`python3 -B -m unittest discover -s research/disc_assistant -t . -v`:

```sh
./research/disc_assistant/run.sh test
```

Explicit acceptance uses the prototype venv and a locally available server image:

```sh
docker pull typesense/typesense:30.2
./research/disc_assistant/run.sh check
```

The check starts a unique disposable Compose project on an ephemeral loopback
port, tests the real CLI/controller/SDK path, then removes its servers, temporary
SQLite database and index volume. It covers exact, typo, Cyrillic-alias, album,
duplicate/CUE and missing queries, index loss/rebuild and catalog/index lag.
This is a small functional fixture, not a ranking benchmark for a personal library.

Validation on 2026-09-17: the firmware-free project suite and prototype unit
tests passed (39 prototype tests), as did the disposable Typesense acceptance above. Read-only CLI
`sync`/`status` also passed against the interactive V2.57 guest with an empty
catalog. A later read-only check on the configured physical V2.57 DISC imported
792 rows through two equal full reads into a disposable SQLite database, then
removed it. This also reproduced `a60a/0010` after connection and verified the
fix that classifies scan events by payload rather than treating all `a60a` as scans.
The owner subsequently confirmed successful `sync → index → search` against
the physical player. The read-only slice is ready for the next implementation
step: typed Russian/English commands, explicit disambiguation and freshly checked
Controller playback. Measured ranking quality and physical playback remain
unvalidated; microphone input follows the text-to-playback path.

The prototype suite is intentionally run explicitly; `ci/unit.py` has not been
changed to discover this experimental directory. Before promotion, register its
component tests in shared CI, broaden physical-catalog coverage and establish
resource/ranking baselines, implement retention and decide the stable storage/API
contract. Then move the reviewed assistant/library components and update imports,
entry points, docs and CI together. Promotion does not require splitting repositories.
