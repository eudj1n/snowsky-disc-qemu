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

- **8-byte** query: `0202` + `0008`  (e.g. generic query, empty value)
- **12-byte**: `0102` + `000C` + 4-byte value
- **library list query** (12-byte): `<cmd>` + `000c` + `<offset>`
  - `0401` tracks · `0402` artists · `0403` albums · `0404` genres · `0405` playlists
  - `0406` queue · `0408` folders · `0413` album-by-name (`cmd+len+offset+name`)
  - response: `a4XX` + `<pagelen 4hex>` + `<total 4hex>` + `[json]`
- **reply tags** begin `aNNN`:
  - `a103` position tick · `a202` track/state · `a501` settings
  - boot push seen on the `ui` queue (see [EMULATION.md](EMULATION.md)):
    `aa1d` battery · `aa24` settings json · `a620` device-info json · `a202 {"state":2}` …

## Internal IPC (on-device, between the two UI processes)

POSIX message queues (created with `mq_maxmsg=32, mq_msgsize=8192`):

- **`ui`** — created by `mq_ui`; `mq_player` opens it `O_RDWR|O_NONBLOCK` and pushes the
  frames above (battery, settings, player state, device info).
- **`player`** — created by `mq_player`; `mq_ui` sends control frames back.

These carry the same FiiO-Link frames as the network protocol. Sniff them non-destructively
by creating `/ui` yourself and reading it before `mq_player` connects: `tools/uisniff.c`.

## Network services (real device)

- **TCP 12100** — raw FiiO Link (binary frames). **Auth-free.** Used by the FiiO Music app
  and this is the channel FiiO Control's device control actually uses
  (`flutter_module/remote/web_socket.dart` `WebSocketClient`, binary frames).
- **TCP 12103** — Mongoose HTTP/WS (`http_server_mongoose.c`, port `0x2f47`). Routes:
  `/api/hi|login|logout|get|set|add|del|ota|websocket`, `POST /fs/*/*` (upload),
  `/dashboard.html`. Auth via `mg_dash`/`mg_dash_authenticate`: if `config+8==0` → guest
  level 9 (open); else callback returns a level; level>0 → 20-char random `access_token`
  cookie from `/dev/urandom`.
- **UDP 12101** — discovery, multicast `224.0.0.255`.

Note: `cipherSign`/RSA+AES in the FiiO Control APK is the **cloud** API (SCConnect); Airable
/ Kugou are streaming. Neither is device control.

## Emulating the network side

Under user-mode qemu the two processes bind their TCP/UDP sockets on the container's network
namespace, so a host client can reach them once the ports are published. `docker-compose.yml`
**publishes 12100 (TCP), 12103 (TCP), 12101 (UDP)** to the host for exactly this. Whether the
emulated `mq_player` actually binds/serves them is **not yet verified** — that's the next thing
to test (then build a FiiO-YMD-style bridge against the emulator). See [STATUS.md](STATUS.md) "Next".
