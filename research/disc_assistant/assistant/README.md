# Assistant application prototype

Experimental application and CLI orchestration in `research/disc_assistant/assistant/`.
See the [prototype guide](../README.md) for setup, commands and acceptance, and the
[implementation plan](../../../docs/ASSISTANT.md) for later voice/playback work.

| File | Responsibility |
| --- | --- |
| `__main__.py` | `start`, `listen`, `language`, `sync`, `status`, `queue`, `index`, `search`, `rank`, `ask`; JSON output and errors |
| `preferences.py` | Versioned Assistant SQLite settings; persistent command languages, override/reset and effective configuration |
| `config.py`, `config.example.toml` | Explicit device/search/storage configuration and aliases |
| `intents.py`, `ranking.py` | Bilingual play grammar and explained best-match ranking |
| `languages.py`, `locales/*.toml` | Validated language dictionaries; merged literal command/target/version phrases |
| `playback.py` | Serialized, fresh Controller selection and playback-state verification |
| `device.py`, `controls.py` | Shared sequential connection/lock; state-aware pause/resume/stop/next/previous |
| `queue.py` | Paginated native queue observation; optional verified repeat-list preparation |
| `session.py` | Catalog synchronization using a borrowed persistent session or a one-shot connection |
| `live.py` | Single TCP receiver, event/state routing, session ownership, pacing and observation-only reconnect |
| `console.py` | Foreground application, startup sync/index and interactive text/maintenance commands |
| `requirements.txt` | Python runtime pins: official Typesense async SDK and aiohttp |
| `compose.yaml`, `.env.example` | Independent local Typesense service |
| `voice/` | Reserved package; no recording or recognition yet |
| `tests/` | Configuration, CLI and session tests |

The application asks [library](../library/README.md) for persistence/search and
uses the existing [controller](../../../controller/) public APIs. No emulator or
viewer imports. Importing modules creates no storage, connections or microphone.
Use `research/disc_assistant/run.sh` for setup, local Typesense and CLI commands.
It selects the explicit `.venv/bin/python`, loads the private key and invokes
`-m research.disc_assistant.assistant` from the repository root; shell aliases
do not override its interpreter.

The official [typesense-python](https://github.com/typesense/typesense-python)
2.0.0 AsyncClient is used only by library search; its transport closes on CLI exit.
Aiohttp is reserved for the future application's HTTP/WebSocket service and is
used by disposable acceptance for readiness. This slice has no application server.
Speech dependencies and a transitive lockfile remain deferred.

`run.sh start` starts Typesense, then opens one foreground application for
connection, sync/index and interactive input. `listen` skips search startup and
automatic synchronization. Both use `DeviceSession`: a background socket reader
keeps receiving while the main thread waits for input, runs search or reads HTTP.
A separate session worker establishes the connection and performs bounded health
reads/reconnect. Device operations borrow the same client under a serialization
lock; only the receiver reads bytes. SQLite stays on the application thread.

The service holds the local device lock for its lifetime. Explicit disconnect
releases TCP and disables reconnect; `/exit` releases local ownership. Unexpected
loss invalidates observations and pending commands. Reconnect performs handshake
and fresh reads only; no selection, toggle or mode write is replayed. Search
failures leave controls available. See the implemented
[M2c contract](../../../docs/ASSISTANT_PLAYBACK.md#m2c-persistent-device-session).

Existing one-shot commands keep their bounded connection lifecycle and JSON/exit
status contract for scripts and cron. Their initial connection refusal is retried
within the timeout before handshake/mutations; established one-shot sessions are
not reconnected. They require the interactive process to release the shared
ownership lock before device access. Offline search/index/status remain independent.
There is no IPC endpoint, durable operation journal or history collector yet.

Explicit continuous context has two named mutation phases, mode then selection;
each allows at most one write and reports partial results. Controls never change
mode. The persistent client caches handshake only within its current connection,
retains interleaved events and applies the same fresh-state/source checks.

Russian and English metadata/aliases are searchable independently of the device's
UI language. Typed play requests now use lexical ranking and fresh selection verification.
The owner deferred dialogue/confirmation: `ask` launches the best result; `rank`
shows the same ordering without playback. See the
[command table](../../../docs/ASSISTANT_COMMANDS.md).

`[language].enabled = ["ru", "en"]` is the default in the user configuration.
`/language` (or one-shot `language`) saves an override in `assistant.sqlite3`
for later sessions; `reset` removes it and restores TOML defaults. The dictionaries support mixed commands such as `Play песню Numb`. Add a language
file and enable its code to extend forms for existing semantics. Unknown keys or
conflicting meanings fail configuration validation. Music-name aliases remain
separate. See the [dictionary format](../../../docs/ASSISTANT_COMMANDS.md#language-dictionaries).
