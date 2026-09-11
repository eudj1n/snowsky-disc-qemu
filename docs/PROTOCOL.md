# FiiO Link protocol & IPC

Reference for the wire/IPC protocol used by the Snowsky Disc, gathered from the
firmware (`control_core`/`fiio_link.c`, `http_server_mongoose.c`) and prior work on
`eudj1n/fiio-ymd` + `eudj1n/ymd`.

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
- **12-byte**: `0102` + `000C` + 4-byte value
- **library list query** (12-byte): `<cmd>` + `000c` + `<offset>`
  - `0401` tracks · `0402` artists · `0403` albums · `0404` genres · `0405` playlists
  - `0406` queue · `0408` folders · `0413` album-by-name (`cmd+len+offset+name`)
  - response: `a4XX` + `<pagelen 4hex>` + `<total 4hex>` + `[json]`; page by re-sending the
    running `offset` until `offset ≥ total` (~900 bytes/page)
- **reply tags** begin `aNNN`:
  - `a103` position tick · `a202` track/state · `a501` settings
  - boot push seen on the `ui` queue (see [EMULATION.md](EMULATION.md)):
    `aa1d` battery · `aa24` settings json · `a620` device-info json · `a202 {"state":2}` …

The full set of tags seen in `mq_player` (~350) is broader than the ones above; the `04xx`/`a4xx`
family is the library, `0[15]xx`/`a[15]xx` control+state. Only read/query tags
(`0599`/`0501`/`0202`/`04xx`) are safe to send blindly — setters change playback.

## Verified live against the physical V2.40 device

Confirmed on the real player over **auth-free TCP 12100** (this is the same protocol the
`eudj1n/fiio-ymd` M21 client used, only the list frames are 12-byte, not 8-byte):

| frame | reply | gives |
|---|---|---|
| `0599000c0000` | `a599000C0306` | handshake, rev 3.06 |
| `05010008` | `a501…{json}` | `currentVolume`, `maxVolume:120`, `playMode`, `soc_version:240`, `ota_site:"https://discpick.fiio.net"`, screen 364² |
| `02020008` | `a202…{song json}` | full track metadata **including `song_file_path`** |
| `0401000c<off>` | `a401 <pagelen> <total> [json]` | all tracks (paged) |
| `0402/0403/0404/0405/0406 000c<off>` | `a40x…` | artists / albums / genres / playlists / queue |
| `0413 <len> <off><name>` | `a413…` | tracks of a named album (title = filename) |
| `a103…` | stream | position tick, ~1/s |

**Only `a202` (now-playing) carries the file path.** The list frames return just
`{id, title/filename, artist}` (+`count` for artists/albums) — **no `song_file_path`**. To match
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
by creating `/ui` yourself and reading it before `mq_player` connects: `tools/uisniff.c`.

## Network services (real device)

- **TCP 12100** — raw FiiO Link (ASCII-hex frames above). **Auth-free.** The FiiO Music app
  uses it directly.
- **TCP 12103** — Mongoose HTTP/WS (`http_server_mongoose.c`, port `0x2f47`). Routes:
  `/api/hi|login|logout|get|set|add|del|ota|websocket`, `POST /fs/*/*` (upload),
  `/dashboard.html`. Auth via `mg_dash`/`mg_dash_authenticate` (`FUN_004af7e0`): if
  `config+8==0` → guest level 9 (open); else callback `(*config->fn)(user,100,pass)` returns a
  level; level>0 → 20-char random `access_token` cookie from `/dev/urandom` (`FUN_004ae108`),
  with `Max-Age`. FiiO Control **does** reach the device over WebSocket `/api/websocket`, but it
  carries the **same auth-free FiiO Link frames** (`flutter_module/remote/web_socket.dart`
  `WebSocketClient`) — see below.
- **UDP 12101** — discovery, multicast `224.0.0.255`, ~2 s heartbeat.

## Authorization: device control is auth-free; `mg_dash` is unused by the apps

Reversing `mq_player` (Ghidra) and both phone apps (Blutter on the Flutter `libapp.so`) settles
what looked like a hard auth gate:

- **Device control has no auth.** Both **FiiO Music** (raw 12100) and **FiiO Control** (WS on
  12103) drive the player with the plain FiiO Link handshake (`requestLinkOpen`/`bindHandshake`),
  **no token, no password, no `cipherSign`**. This is why FiiO Music connects instantly and why
  our own 12100 client works.
- **`mg_dash` (`/api/login` + `/fs`) is a separate built-in Mongoose dashboard** that the stock
  clients never use for control. A plain HTTP client gets `200`/empty on everything and the WS
  won't upgrade, because the dash callback rejects unknown `(user,pass)` — it is a real password
  gate, but the credentials are a vendor secret provisioned by the app, **not** `admin:admin`.
- The `cipherSign`/RSA+AES/Bearer tokens in the APK belong to **four unrelated stacks**, none of
  which is device control: **FiiO cloud** (`SCConnect`, RSA+AES), **Airable** (`fiio_media`,
  OAuth/QR), **Kugou/Deezer/Qobuz/Tidal** (`userId/userToken`), and **device control**
  (`WebSocketClient`, auth-free FiiO Link). Chasing `cipherSign` for `/fs` was a dead end.
- `libkey_jni.so` exports a `com.yscoco.ai` secret (`8DD8735BEB1B4CABBD6B17F7F9799E10`) — that is
  their cloud/AI SDK, unrelated to the device WS.

## No file-upload command in the device protocol

The device-WS command set (from Blutter) is control/query only — `requestApplicationGetList`,
`requestVolume`, `requestWorkMode`, `requestAudioGain/Format`, `sendKeyEvent`, `sendPlayPosition`,
`requestBluetoothDevices`, `requestStartApplication`, streaming opens (`requestKugou/Deezer/…`) —
**there is no "push a file to the SD" command.** Even the official app does not upload tracks over
the device protocol; it scans files already placed on the SD (via USB or a network share). So a
sync bridge's "copy music to the player" step is **not** solvable on 12100/WS — it needs file
access (`mg_dash` `/fs` with the provisioned creds, or root over UART/diskOS), while **library
read + transport control are fully solved on auth-free 12100.**

## Emulating the network side

Under user-mode qemu the two processes bind their TCP/UDP sockets on the container's network
namespace, so a host client can reach them once the ports are published. `docker-compose.yml`
**publishes 12100 (TCP), 12103 (TCP), 12101 (UDP)** to the host for exactly this.

**Current state:** with the committed `10_setup_env.sh` the emulated `mq_player` does **not** bind
12100/12103 (the only listening TCP socket is Docker's internal DNS) — the FiiO Link servers are
gated on the network being up (`NETWORK_MODE`/`WIFI_STATUS`, and a real interface). In an earlier
throwaway container, adding a **dummy `wlan0` + a faked wifi-up state** got the **Mongoose 12103**
server listening and answering `GET /api/hi → 200` exactly like hardware — so the path is known,
it just isn't scripted yet. The next step is a `40_network.sh` that brings up a dummy `wlan0` and
sets `NETWORK_MODE=1`/`WIFI_STATUS=1`, verifying it actually produces a `0.0.0.0:12100` bind
before building a FiiO-YMD-style bridge against the emulator. See [STATUS.md](STATUS.md) "Next".
