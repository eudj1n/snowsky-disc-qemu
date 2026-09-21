# FiiO Link protocol & IPC

Reference for the wire/IPC protocol used by the Snowsky Disc, gathered from the
firmware (`control_core`/`fiio_link.c`, `http_server_mongoose.c`) and direct device probes.

**Remote-control follow-up (2026-09-16):** see [REMOTE_CONTROL.md](remote-control.md)
for tested selection/navigation/seek/mode commands, distinct catalog/queue/favorites
schemas, rate limits and physical V2.57 comparisons. Historical V2.40 observations
below are not automatically capabilities of every firmware or the M21.
The follow-up also documents `0105` → `a102` mode reads and the unassigned DISC
`0426` queue-counter handler; use the verified TCP/HTTP queue APIs instead.
The [research continuation plan](../../research/docs/status.md) records remaining tasks,
their priority and the validation status of the current checkpoint.

**Stock capabilities follow-up:** [HTTP_API.md](http-api.md) covers verified file
upload, folders, custom playlists, cover retrieval and network scanning;
[REMOTE_SETTINGS.md](remote-settings.md) covers gain, DRE, filter, SPDIF and PEQ.
[REMOTE_MODES_THEMES.md](remote-modes-themes.md) adds work-mode transitions,
Bluetooth source-codec preferences, lock-screen upload/selection and a traffic
capture checklist for comparison with FiiO Control.
The supplied Android 4.6.0 APK, iOS HTTP captures and a raw TCP capture with
physical mode transitions and capability metadata are recorded in
[FIIO_CONTROL_APP.md](../../research/docs/reports/fiio-control-app.md).
The [M21 comparison](../../research/docs/reports/m21-comparison.md) records the related Android BLinker dialect:
its UTF-16 length units, opposite playback-state enum, mode/favorite toggle
semantics and separate HTTP API must not be applied to DISC.

Current V2.57 implementation entry point: [DISC capability summary](disc-capabilities.md).
The agreed local research checkpoint is finalized; historical probes below
retain their original firmware/evidence scope.

## Frame format (FiiO Link)

ASCII-hex header + payload:

```
TAG(4 hex chars) + LEN(4 hex chars) + VALUE
```

`LEN` is the total frame length in bytes (header included), as 4 hex chars.

- **session handshake** (send first): `0599` + `000c` + `0000` → `a599 000C 0306` (protocol
  rev **3.06** on V2.40). On the raw TCP socket this must precede the other queries — `0202`
  returned nothing until `0599…` was sent.
- **8-byte** query: `0202` + `0008`  (empty value — e.g. now-playing track)
- **play-mode read**: `01050008` → `a102000C<mode>`; the reply tag is shared with
  mode-change notifications and is not `a105`.
- **12-byte**: `0102` + `000C` + 4-byte value
- **selection**: `0100` + length + zero-based position (4 hex) + list type (4 hex)
  + optional UTF-8 name. The position is **not a song ID**.
- **seek**: `0103` + `0010` + milliseconds (8 hex); local playback rounds down to
  whole seconds. `a103` position notifications also use milliseconds.
- **library list query** (12-byte): `<cmd>` + `000c` + `<offset>`
  - `0401` tracks · `0402` artists · `0403` albums · `0404` genres · `0405` legacy playlists
  - `0406` queue · `0408` folders · `0413` album-by-name (`cmd+len+offset+name`)
  - response: `a4XX` + `<pagelen 4hex>` + `<total 4hex>` + `[json]`; page by re-sending the
    running `offset` until `offset ≥ total` (~900 bytes/page)
  - **V2.57:** `0405` gave no response on both emulator and physical DISC.
    Built-in favorites can be read with `0415` and the literal name `我的最爱`.
- **reply tags** begin `aNNN`:
  - `a103` position tick · `a202` track/state · `a501` settings
  - boot push seen on the `ui` queue (see [EMULATION.md](../../emulator/docs/emulation.md)):
    `aa1d` battery · `aa24` settings json · `a620` device-info json · `a202 {"state":2}` …

The full set of tags seen in `mq_player` (~350) is broader than the ones above; the `04xx`/`a4xx`
family concerns the library, `0[15]xx`/`a[15]xx` control+state. A prefix is not a
read-only guarantee: `04xx` includes mutations and unimplemented handlers. Probe
only individually identified commands; setters change playback or library state.

### TCP admission is separate from local IPC

V2.57 TCP receiver `4dabc4` checks an independent 111-tag allowlist at `6d84e0`
before dispatch. A local UI command/callback is therefore not necessarily reachable
over the network. The six playback-preference setters `0647/0687/0718/0648/064d/064e`
are absent and were rejected in disposable TCP/WS tests. Three current preference
values are still readable through `0501`; see [the exact contract](remote-settings.md#playback-preferences-v257).
Button-assignment `0820/0821/0822` and cover/lyrics `064b/064c` tags are also absent
(static evidence). Conversely, admitted `0426` has no assigned handler.

An invalid tag clears the current receive buffer, potentially dropping coalesced
valid frames too. Do not batch negative probes with reads. The WS bridge does not
add stock commands. Reproduce the list offline with fingerprint-validating
`research/diagnostics/inspect_link_commands.py`; see [diagnostics](../../research/docs/diagnostics.md).

## Verified live against the physical V2.40 device

Confirmed on the real player over **auth-free TCP 12100**. Library-list requests use
12-byte frames including their offset, not 8-byte empty requests:

| frame | reply | gives |
|---|---|---|
| `0599000c0000` | `a599000C0306` | handshake, rev 3.06 |
| `05010008` | `a501…{json}` | `currentVolume`, `maxVolume:120`, `playMode`, `soc_version:240`, `ota_site:"https://discpick.fiio.net"`, screen 364² |
| `02020008` | `a202…{song json}` | full track metadata **including `song_file_path`** |
| `0401000c<off>` | `a401 <pagelen> <total> [json]` | all tracks (paged) |
| `0402/0403/0404/0405/0406 000c<off>` | `a40x…` | artists / albums / genres / playlists / queue |
| `0413 <len> <off><name>` | `a413…` | tracks of a named album (title = filename) |
| `a103…` | stream | position tick, ~1/s |

**Only `a202` (now-playing) provides a verified nonempty file path in these probes.**
Track/album-track lists return `{id, title/filename, artist}`;
artist/album groups return `{count, name}`. Queue `0406` uses
`{songId, flag, itemName, itemInfo?}`; favorites `0415` has another schema with
`songName` and an observed empty `songPath`. There is **no `song_file_path`** in
the catalog pages. To match
a full library by path you need `song.db` (`/usr/data/fiio/db/song.db`), not the list frames.
The music SD is mounted at **`/tmp/sdcard/`** on the device (seen in the `a202` path).

Practical constraints: the device serves **one TCP client at a time** on 12100 (leave a gap
between connects), and the handshake is per-connection.

## Internal IPC (on-device, between the two UI processes)

POSIX message queues (created with `mq_maxmsg=32, mq_msgsize=8192`):

- **`ui`** — created by `mq_ui`; `mq_player` opens it `O_RDWR|O_NONBLOCK` and pushes the
  frames above (battery, settings, player state, device info).
- **`player`** — created by `mq_player`; `mq_ui` sends control frames back.

These carry the same FiiO-Link frames as the network protocol. Sniff them non-destructively
by creating `/ui` yourself and reading it before `mq_player` connects: `research/diagnostics/uisniff.c`.

## Network services (real device)

- **TCP 12100** — raw FiiO Link (ASCII-hex frames above). **Auth-free.** The FiiO Music app
  uses it directly.
- **TCP 12103** — Mongoose **HTTP** (`http_server_mongoose.c`, port `0x2f47`).
  V2.40's active callback `004b9d38` uses table `006c7a50`, **not** the bundled
  dashboard router. Active routes include `/dir/`, `/localdir/`, `/audio/`,
  `/image/lock_screen/`, `/image/cover/`, `/song_category_tree/`, `/mark_list/` and
  `/log/`. No `/api/websocket` route is registered. Unknown URLs return HTTP 200/empty
  via `0048f8f8`. See [NETWORK.md](../../emulator/docs/network.md#websocket-investigation).
- **UDP 12101** — discovery, multicast `224.0.0.255`, ~2 s heartbeat.
  V2.57 sends raw `SNOWSKY DISC`, not a Link frame, and suppresses beacons while
  a TCP client is connected. See [discovery evidence and opt-in LAN bridge](../../controller/docs/discovery.md).

## Authorization: device control is auth-free; `mg_dash` is unused by the apps

Reversing `mq_player` (Ghidra) and both phone apps (Blutter on the Flutter `libapp.so`) settles
what looked like a hard auth gate:

- **TCP device control has no auth.** Our 12100 client uses the plain FiiO Link handshake
  without a token, password or `cipherSign`. Earlier app analysis found an auth-free
  `WebSocketClient` carrying FiiO Link; its presence in a multi-device app does **not**
  establish that DISC V2.40's server supports that transport.
- **`mg_dash` (`/api/login` + `/fs`) is a separate built-in Mongoose dashboard** that the stock
  clients never use for control. **The earlier explanation of empty HTTP 200 as a password
  gate was wrong.** The active server returns it directly for unknown URLs, without invoking
  dashboard authentication. Dashboard code in the binary is not an active dashboard API.
- The `cipherSign`/RSA+AES/Bearer tokens in the APK belong to **four unrelated stacks**, none of
  which is device control: **FiiO cloud** (`SCConnect`, RSA+AES), **Airable** (`fiio_media`,
  OAuth/QR), **Kugou/Deezer/Qobuz/Tidal** (`userId/userToken`), and **device control**
  (`WebSocketClient`, auth-free FiiO Link). Chasing `cipherSign` for `/fs` was a dead end.
- `libkey_jni.so` exports a `com.yscoco.ai` secret (`8DD8735BEB1B4CABBD6B17F7F9799E10`) — that is
  their cloud/AI SDK, unrelated to the device WS.

## File transfer is a separate HTTP investigation

The analyzed device-WS command set (from Blutter) includes `requestApplicationGetList`,
`requestVolume`, `requestWorkMode`, `requestAudioGain/Format`, `sendKeyEvent`, `sendPlayPosition`,
`requestBluetoothDevices`, `requestStartApplication`, streaming opens (`requestKugou/Deezer/…`) —
no file-push command was identified in that analyzed subset. This does **not** establish
that the official app cannot transfer files. User-provided FiiO Control screenshots
(2026-09-15) show DISC's Wi-Fi transfer browser at `tmp/sdcard`, a new-folder action,
and import choices for audio, images and folders. They establish the app UI, not a
successful transfer or its exact wire format.

The fingerprinted active HTTP tables provide concrete leads: `GET/POST /dir/`,
`DELETE /file/`, `POST /audio/`, `GET /progress/`, and image routes. V2.57 additionally
has `POST /image/`. Follow-up tests established raw-body upload, folder creation,
single-path deletion and custom playlist operations; see [HTTP_API.md](http-api.md)
for the request contract and per-device evidence. A separately hosted remote can use
stock HTTP 12103 for these operations alongside **auth-free TCP 12100 for playback,
settings and scanning**.
The earlier blanket claim that writing files requires a root shell or dashboard
credentials was incorrect. See [REMOTE_CONTROL.md](remote-control.md#official-app-ui-evidence).
Do not chase supposed `/fs` credentials based on the earlier incorrect route mapping.

## Emulating the network side

Under user-mode qemu the two processes bind their TCP/UDP sockets on the container's network
namespace, so a host client can reach them once the ports are published. `emulator/compose.yaml`
**publishes 12100 (TCP), 12103 (TCP), 12101 (UDP)** to the host for exactly this.
Host 12103 now goes through the explicit [WebSocket bridge](../../controller/docs/websocket.md);
host 12113 exposes the original guest HTTP listener directly.

**Current state (2026-09-11):** both services bind with the committed pipeline. Compose
names Docker's actual interface `eth1`; `16_network.sh` re-announces its existing IP after
the stock netlink subscription. The real gate is `DAT_0086c030`, set by `RTM_NEWADDR`,
not simply NETWORK_MODE/WIFI_STATUS. No dummy Wi-Fi or DB flag override is needed.
The guest's BusyBox `ip` replaces two read queries unsupported by the standalone utility
under QEMU. See [NETWORK.md](../../emulator/docs/network.md) for reproduction, confinement and the host client.

Verified TCP setters: `0502 000C <volume 4hex>` (absolute 0..120),
`0201 000C 0000` (selected-track play/pause toggle). These are not evdev key codes.
The follow-up also verifies `0201/0001` next, `0201/0002` previous, `0100` selection,
`0103` seek and `0102` modes; details and per-device evidence are in
[REMOTE_CONTROL.md](remote-control.md). No absolute play/pause command is established;
V2.57 `0203` is an empty handler, not a replacement for the toggle.
The host mappings are localhost-only. `/api/hi`, `/api/websocket` Upgrade and an invented
URL give the same empty 200 **when querying direct stock HTTP on host 12113**.
The traced active router has no WebSocket route/message dispatch. Our separate bridge
on host 12103 now upgrades and transports FiiO Link successfully, without a binary patch.
