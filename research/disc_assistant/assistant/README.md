# Assistant application prototype

Experimental CLI orchestration in `research/disc_assistant/assistant/`.
See the [prototype guide](../README.md) for setup, commands and acceptance, and the
[implementation plan](../../../docs/ASSISTANT.md) for later voice/playback work.

| File | Responsibility |
| --- | --- |
| `__main__.py` | `sync`, `status`, `queue`, `index`, `search`, `rank`, `ask`; JSON output and errors |
| `config.py`, `config.example.toml` | Explicit device/search/storage configuration and aliases |
| `intents.py`, `ranking.py` | Bilingual play grammar and explained best-match ranking |
| `languages.py`, `locales/*.toml` | Validated language dictionaries; merged literal command/target/version phrases |
| `playback.py` | Serialized, fresh Controller selection and playback-state verification |
| `device.py`, `controls.py` | Shared sequential connection/lock; state-aware pause/resume/stop/next/previous |
| `queue.py` | Paginated native queue observation; optional verified repeat-list preparation |
| `session.py` | One short sequential controller TCP session and matching HTTP endpoint during import |
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

The current controller client deliberately discards unrelated events during
queries. This bounded importer checks queued scan events around HTTP reads, but
is not a persistent event service or listening-history collector. Playback uses a
separate sequential reader that retains unrelated events during
queries, guards scan activity and dispatches at most one selection. It serializes
local device operations and never replays an uncertain mutation. Long-lived
background event routing/history remain future work.

Initial connection refusal is retried within the configured timeout to allow the
stock listener to reopen after disconnect. This occurs before handshake/mutations;
established sessions are never automatically reconnected. Explicit continuous
context has two named mutation phases, mode then selection; each allows at most
one write and reports partial results. Controls never change mode.

Russian and English metadata/aliases are searchable independently of the device's
UI language. Typed play requests now use lexical ranking and fresh selection verification.
The owner deferred dialogue/confirmation: `ask` launches the best result; `rank`
shows the same ordering without playback. See the
[command table](../../../docs/ASSISTANT_COMMANDS.md).

`[language].enabled = ["ru", "en"]` is the default in the user configuration.
The dictionaries support mixed commands such as `Play песню Numb`. Add a language
file and enable its code to extend forms for existing semantics. Unknown keys or
conflicting meanings fail configuration validation. Music-name aliases remain
separate. See the [dictionary format](../../../docs/ASSISTANT_COMMANDS.md#language-dictionaries).
