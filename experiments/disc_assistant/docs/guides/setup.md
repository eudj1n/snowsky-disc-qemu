# Assistant setup and lifecycle

Run commands from the repository root. The Assistant has its own launcher;
`emulator/run.sh` starts the emulator. Requirements are Python 3.11+ and Docker for
managed Typesense and optional speech services.

## Install and select the device

```sh
./experiments/disc_assistant/run.sh setup
# Or install the optional managed Whisper/Piper stack as well:
./experiments/disc_assistant/run.sh setup --all
```

Setup creates `assistant/.venv`, installs pinned requirements, creates
`~/disc-assistant.toml` when missing and prepares a private Typesense key in
`assistant/.env`. Existing config and keys are preserved. The launcher calls the
venv interpreter directly; no activation is required. Set `DISC_ASSISTANT_PYTHON`
to a Python 3.11+ executable if automatic selection fails.

Review the configuration before device access. The template targets emulator TCP
12100 and direct HTTP 12113 on loopback. For a physical DISC, use its actual IP:

```toml
[device]
key = "my-snowsky-disc"
host = "192.168.1.50"
tcp_port = 12100
http_port = 12103
```

HTTP and TCP must identify the same device. `device.key` is your persistent
namespace, not a discovered serial number. Use distinct keys and data directories
for independent devices/profiles. See [configuration and backups](../reference/configuration.md).
Close an active FiiO Control or other stock TCP client before connecting.

## Choose an interface

| Command | Startup behavior |
| --- | --- |
| `./experiments/disc_assistant/run.sh web --bootstrap` | Start managed search/speech services, prepare catalog/index and open the loopback web service on port 8090. Enable browser sound explicitly for Piper replies. |
| `./experiments/disc_assistant/run.sh start` | Start Typesense, connect, synchronize/index and open the text console. |
| `./experiments/disc_assistant/run.sh listen` | Open the text console using existing catalog/index; no Docker startup or automatic synchronization. |

Only one foreground interface may own a data directory/device connection. The
web page provides microphone capture; `listen` takes text and explicit WAV-file
commands. [Web usage](web.md) and [speech installation](tts.md) document the media
permissions, managed models and delivery limits.

Example console session:

```text
/device
/language ru
Включи Linkin Park — Numb
Пауза
Что играет
/queue
/exit
```

`/sync` refreshes the device catalog; `/index` rebuilds search. Upgrading the artist
projection requires `/index`, not another `/sync` for an existing snapshot.
Use [command examples](quick-guide.md) and the [full reference](commands.md) for
one-shot JSON commands, locale/response policy, history, terminal editing and debug.

## Disconnect, stop and update

Unexpected disconnects recover observations without replaying commands. Requests
submitted while disconnected fail; they are not queued for later playback.
`/disconnect` releases TCP and disables reconnect; `/connect` re-enables it.
`/exit` releases local ownership and leaves native playback and services running.

```sh
./experiments/disc_assistant/run.sh down
./experiments/disc_assistant/run.sh speech-down
```

`down` stops Typesense without removing its volume or SQLite data. Speech shutdown
preserves installed models. Neither command stops the emulator. After an update,
stop the foreground application, rerun `setup` (or `setup --all` for speech), then
restart the chosen interface. Existing configuration and keys remain in place.
A moved virtualenv may retain old activation/console-script paths; the launcher
uses its Python directly. To recreate it, stop the application, move only the
local `.venv` aside and rerun setup, preserving `.env`, TOML and external data.
