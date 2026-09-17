# FiiO Link over WebSocket — emulator bridge

The browser and Python client can now control the emulated V2.40 player over
**`ws://127.0.0.1:12103/api/websocket`**. This is an explicit WebSocket → TCP adapter,
**not a newly discovered stock WS implementation**. The stock active HTTP callback
has no WS route/message dispatcher; see [the route investigation](NETWORK.md#websocket-investigation).
No firmware code, route table or in-memory pointers are patched for this bridge.

## Addresses and reproduction

The bridge is optional (`wsbridge` Compose profile). The device viewer on 8080,
local playback and direct TCP control work without it. Enable it for WebSocket
clients, the protocol inspector or bridge verification.

| Host endpoint (localhost only) | Destination |
|---|---|
| `12103/api/websocket` | Native `wsbridge` service → stock FiiO Link TCP `emu:12100` |
| Other HTTP paths on `12103` | `wsbridge` HTTP proxy → stock HTTP `emu:12103` |
| `12103/bridge/` | Read-only browser protocol inspector; connects only after clicking Connect |
| `12103/bridge/health` | Bridge identity and active-client flag; **not** proof the guest is ready |
| `12113` | Direct stock HTTP `emu:12103`, bypassing the bridge; `/api/websocket` still returns 200 |
| `12100` / `8080` | Existing direct TCP client / device viewer, unchanged |

```sh
docker compose up -d --build    # recreate emu's port mapping; retain snowsky-disc-work
./run.sh boot
./run.sh view                  # restart the viewer after container recreation
docker compose --profile wsbridge up -d wsbridge  # explicit opt-in
./run.sh wscheck               # compare settings/library with independent direct TCP
./run.sh wscheck --control     # volume test + start indexed library + leave paused
python3 -m controller.diagnostics.probe_websocket --require-upgrade  # host 12103: valid 101
python3 -m controller.diagnostics.probe_websocket --port 12113       # direct stock: 200, websocket=false
```

For a fresh workspace, first obtain/extract the OTA with `./run.sh up …` as in README.
`docker/Dockerfile` installs Debian's `python3-aiohttp` at image build time (tested
3.8.4-1+deb12u1). No `pip install` or guest-image modifications are needed. Compose
runs a separate unprivileged service from that image: UID/GID 65534, read-only root
and repository mount, all capabilities dropped, no-new-privileges, no rootfs/SD volume.
Default Compose startup and `run.sh up/start/boot/view` do not start it. Once enabled,
it survives guest restarts and returns an availability error while the guest is off.
`run.sh down` removes both containers and retains the work volume. `wscheck` expects
the bridge already running. Integration CI explicitly enables the profile.

Stop it with `docker compose --profile wsbridge stop wsbridge`. Adding a profile does
not stop an already running bridge from an older checkout; run this stop command once
when migrating. Port 12103 is unavailable while stopped; direct stock HTTP stays on
12113. An explicit `COMPOSE_PROFILES=wsbridge` also opts in.

Standalone async client, using the dependency already installed in the container:

```sh
docker compose --profile wsbridge exec -T wsbridge python3 -B -m controller.fiio_ws
docker compose --profile wsbridge logs --tail 30 wsbridge
docker exec snowsky-disc-qemu python3 -m research.diagnostics.probe_keys
```

## Transport and application framing

For the extended stock remote controls (selection, next/previous, seek, modes and
albums), see [REMOTE_CONTROL.md](REMOTE_CONTROL.md). TCP and `WSClient` share payload
validation and run the same disposable remote acceptance scenario. The bridge remains
a transport adapter; it does not turn unsupported stock commands into capabilities.

The transport is [RFC 6455 WebSocket](https://www.rfc-editor.org/rfc/rfc6455), handled
by [aiohttp](https://docs.aiohttp.org/en/v3.8.4/web_reference.html#aiohttp.web.WebSocketResponse).
Upgrade must succeed with HTTP **101** and the matching Sec-WebSocket-Accept. No
token, password, special Origin or subprotocol is needed by the CLI. Browser Origin
restrictions below are emulator protections, not vendor authentication.

Each application record remains the existing FiiO Link format:

```text
TAG[4 ASCII hex] + TOTAL_LENGTH[4 ASCII hex] + PAYLOAD
0599             000C                       0000
```

The length counts **UTF-8 bytes including the eight header bytes**, not characters
and not WebSocket framing bytes. Maximum record length is `FFFF` (65535 bytes).
Send a text WebSocket message containing the record, not a JSON wrapper. Binary
messages containing the same bytes also work. The bridge accepts split/coalesced
FiiO records across messages, and emits **one complete FiiO record per WS message**:
text if valid UTF-8, otherwise binary. Hex headers are normalized (lowercase tag,
uppercase length); payload bytes are preserved. WS messages are capped at 65535
bytes after WS-fragment reassembly. Ping/pong/close are transport frames, never
forwarded as FiiO commands; compression is not negotiated.

| Outbound message | Reply / effect confirmed on emulated stock V2.40 |
|---|---|
| `0599000C0000` | `a599000C0306` — FiiO Link handshake |
| `05010008` | `a501…{…}` — settings including currentVolume and soc_version 240 |
| `0401000C0000` | `a401…0004[{…},…]` — total count as four hex digits, then indexed track array |
| `02020008` | `a202…{…}` — current track and wire state: 0 playing, 1 paused, 2 stopped |
| `0502000C0072` | Set absolute logical volume 114 (valid 0..120); query 0501 to verify |
| `0101000C0001` | Start all indexed songs (list type **1**, not 0) |
| `0201000C0000` | Toggle play/pause; query 0202 to verify |

`now_playing.song` is itself a JSON-encoded string; the Python clients decode it.
Before a track is selected / after the firmware clears playback, 0202 can send no
reply; a timeout is not proof of a broken WS connection. The inspector shows raw
frames, including such absence of replies, rather than inventing a state.

**Notifications:** incoming a-tags are not all responses to the most recent request.
The browser observed unsolicited `a60a` and `aa05` alongside query replies. `a202`
can also be an async player-state notification. There are no request IDs. `WSClient`
uses a sequential query lock and drains already-queued notifications before a query;
this does not create perfect correlation for an event arriving after the request.
Control tests query fresh state after the action and independently read guest memory.
The notification queue is bounded at 256 records and drops oldest records on overflow.

## Lifecycle and limits

- **One control client at a time.** Stock TCP closes/recreates its listening socket
  around a connection. A second bridge WS is rejected with HTTP **409**. Do not run
  a raw TCP client or FiiO app while WS is connected. The bridge cannot arbitrate an
  independent client accessing direct port 12100. Disconnect the inspector before
  `wscheck`. Connection refusal during handover is retried for up to 3 seconds;
  commands are never replayed after a disconnect.
- Guest unavailable: HTTP **503** before upgrade. Stock HTTP unavailable: **502**.
  Invalid FiiO record: WS **1007**; oversized message: **1009**; upstream closes:
  **1011**; bridge shutdown: **1001**. Client close releases the TCP channel.
- Bridge heartbeat 20 seconds, write/drain deadlines 10 seconds. Python query
  timeout defaults to 8 seconds. HTTP proxy connection/read timeouts are 3/30 seconds.
- HTTP proxy preserves methods, encoded paths/query, body bytes, status and end-to-end
  headers; it streams bodies and strips hop-by-hop headers. It neither follows redirects
  nor shares cookies between users. Compressed HTTP **request** bodies return 415 to
  avoid forwarding decoded data with stale Content-Encoding/Length. File-upload
  semantics and large-file performance are not validated by this task.
- Host must be localhost/127.0.0.1; allowed browser Origins are their HTTP URLs on
  12103 and 8080. Other Origins, including `null`, return **403**. CLI clients may
  omit Origin. All published ports are localhost-only. This is not authentication,
  TLS, an internet-facing gateway or a sandbox for the privileged emulator.
- The bridge does not emulate LAN discovery, app onboarding, Wi-Fi or cloud APIs.
  **Compatibility with the FiiO Control phone app is not established.** This proves
  FiiO Link transported over our WS adapter, not the app's full multi-device protocol.

## Verification evidence — 2026-09-11

Native browser connected, received `a599000C0306`, matching settings, four tracks
and the selected Tone A WAV with wire state 1. [Protocol screenshot](images/16-websocket-protocol.jpg).
The inspector was disconnected after capture so it does not reserve the only channel.

Live `./run.sh wscheck --control`: TCP/WS settings and catalog matched; volume
**115 → 114 → 115**; selected Tone A went **playing → paused** with the same track ID.
Independent `/proc/PID/mem` probe: logical volume **115**, internal state **2** (paused).
Second WS got 409; reconnect handshake returned 0306. Host 12103 upgrades to 101;
direct stock host 12113 still returns 200. Browser received unsolicited notifications.
After bridge recreation, a powered-off guest returned HTTP 503; booting it restored
the full control/reconnect test without restarting the bridge.

Automated: **55 Python + 10 JavaScript tests**. The Python suite includes 18 bridge
tests for masked WS fragmentation with interleaved ping, fragmented/coalesced FiiO
records, UTF-8/binary payloads, notifications, disconnect/reconnect, client conflict,
Origin/Host rejection, invalid/oversized messages, unavailable upstream, HTTP proxy
and client timeout/queued-state behavior. Run the full suite **in the new image**:

```sh
docker exec snowsky-disc-qemu python3 -B -m unittest discover -s /repo -t /repo -p 'test_*.py'
node --test viewer/tests/test_keys.js viewer/tests/test_audio_browser.js
```

Without aiohttp installed on the host, its bridge tests are explicitly skipped there;
a host-only run is not the complete test result.
