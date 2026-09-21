# DISC LAN discovery and an opt-in phone bridge

Active firmware: V2.57. SACD ISO follow-up is separate in
[issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8).

## Stock UDP contract

`mq_player` sends the exact ASCII bytes `SNOWSKY DISC` (12 bytes, no NUL/newline,
JSON or FiiO Link header) to **224.0.0.255:12101/UDP** about every two seconds.
The sending socket is not bound to 12101: the observed source port is ephemeral.
The sender IP identifies a candidate address; the packet does **not** contain an
IP, TCP/HTTP port, serial number, MAC address or firmware version. TCP 12100 and
HTTP 12103 are separately known DISC endpoints, not parsed announcement fields.

This is a periodic announcement, not a response to a search query. The V2.57
thread sends but does not receive discovery probes. **It stops announcing as
soon as a TCP control client is accepted**, before the `0599` handshake. After
disconnect, announcements resume. An absent beacon is not proof that a device
is offline: it may already have a client, be asleep, or be behind multicast
filtering. Discovery data is unauthenticated and spoofable; never automatically
connect to every address or replay commands to a rediscovered device.

Static evidence in fingerprinted V2.57 `mq_player`:

- `4da780`: UDP sender, literal product name, multicast destination and two-second
  sleep loop. It sends only while `898950` is zero.
- `4db020`: TCP accept sets `898950=1`; disconnect paths clear it.
- `4dbf48`: Link shutdown clears connected state and closes the UDP socket.
- MIPS uses its own socket constants: `socket(2,1,0)` here is datagram, not the
  native host's usual interpretation of numeric `SOCK_STREAM`.

Reproduce static inspection with `research/ghidra/DecAt.java` and `RefsTo.java`; do not
copy V2.40 addresses or commit extracted binaries/decompilation.

## Passive host observer

```sh
# Choose the Mac/Linux interface on the phone/player's network, not a VPN.
# macOS examples: route -n get default; ipconfig getifaddr en1
python3 -B -m controller.fiio_discovery --interface <MAC_LAN_IPV4> --seconds 15
```

The standard-library helper joins only the selected interface/group, recognizes
the exact observed DISC payload, prints JSON lines with sender address/port and
elapsed time, and exits after a bounded interval. It sends no application probes,
makes no TCP connections and changes no player settings. Joining multicast can
cause normal OS membership traffic. Unknown payloads are ignored, not interpreted
as arbitrary device names. The listener has no discovery cache or stable-identity
claim; do not persist stale IPs indefinitely. Local addresses/logs stay in ignored
`work/`; use placeholders when sharing reports.

Physical V2.57 evidence on 2026-09-16: the Mac received 15 exact announcements in
30 seconds, intervals about 1.84–2.15 s. The user simultaneously found SNOWSKY DISC
at the same address in FiiO Control on iPhone. The user also connected and returned
to discovery, seeing a disconnect confirmation. The follow-up capture shows
announcements afterwards, but the short connected interval was not aligned well
enough to prove physical suppression. The controlled emulator test proves that
lifecycle independently; do not label it a timed phone capture.

## mDNS is a separate path

V2.57 `4898a4` builds Avahi TXT fields `device=`, `ip=` and `mac=`;
`489d70` registers `_fiio._tcp` on **12102**, not control port 12100 or HTTP 12103.
An imported Avahi API or service string is not proof that it was registered.
Earlier physical notes reported the service during a control connection; the
short browse in this session observed no instance. Its exact current lifecycle
and purpose remain unvalidated. Do not advertise a guessed `_fiio._tcp` record
pointing to TCP 12100, or start extra Avahi daemons inside the guest to compensate.
AirPlay/mDNS discovery is not the same as the UDP DISC announcement.

## Why a host bridge

Normal Compose ports remain bound to `127.0.0.1`. Docker Desktop runs containers
behind its VM/backend and forwards published ports; publication alone does not
relay the guest's multicast announcements onto a selected physical interface.
See [Docker Desktop networking](https://docs.docker.com/desktop/features/networking/).
Desktop host networking also does not give a container direct access to host
interfaces ([documented limitations](https://docs.docker.com/engine/network/drivers/host/#limitations)).
We leave the existing network/confinement setup intact.

`controller/bridge/lan_bridge.py` requires host Python **3.11+** (standard library only).
It is an explicit, temporary **host process**, not firmware
support or a WS adapter. It binds two TCP listeners on one chosen local IPv4:

| LAN endpoint | Fixed local destination |
| --- | --- |
| TCP 12100 | `127.0.0.1:12100`, stock FiiO Link |
| TCP 12103 | `127.0.0.1:12113`, direct stock HTTP, bypassing wsbridge |
| UDP multicast announcement | Host-selected interface → `224.0.0.255:12101`, TTL 1 |

It forwards bytes unchanged, including streaming HTTP bodies and half-close.
Only one explicit phone IPv4 is allowed; other peers are closed before reaching
the guest. A second control connection is rejected; HTTP is capped at eight
connections. It emits the same product-name announcement only when stock HTTP
responds and no control connection is active through this bridge. HTTP health
uses `GET /`, never a control-channel probe. It cannot detect another client
using localhost directly: disconnect the web inspector and other control clients
before starting. It does not relay arbitrary multicast packets, advertise mDNS,
rewrite HTTP paths or implement reconnect/replay.
Forwarding bounds are three seconds for upstream connect, 120 seconds without
bytes in either read direction, and 30 seconds for write backpressure. Those are
adapter limits, not measured stock idle-power or reconnect semantics; a long
paused session may end at the bridge's own timeout.
Each direction has its own deadline: continuous player notifications do not
keep a silent phone's read direction alive. A loopback regression checks timeout
cleanup and immediate reuse of the control slot even under those notifications;
the pumps use directly cancellable `asyncio.timeout` contexts. No timer or LAN
exposure policy was relaxed. See [idle/reconnect](../../emulator/docs/idle-power.md) for the separate
stock TCP, WS heartbeat and firmware power timers.

**Security:** stock APIs have no authentication and include file writes/deletion.
An IP allowlist is not authentication and can be defeated on an untrusted LAN.
Use only a trusted network, explicit approval and the shortest test window.
Do not bind `0.0.0.0`, remove the allowlist, expose it to the internet or add an
automatic background service. The viewer and Docker socket are not forwarded.
No firmware URL, password, binary or private media is committed with this tool.
An allowed phone can access the guest's actual SD contents while the bridge runs.

```sh
./run.sh boot
# Run on the HOST; no extra Python package or Docker image change is needed.
python3 -B -m controller.bridge.lan_bridge \
  --interface <MAC_LAN_IPV4> --allow-client <PHONE_IPV4> --seconds 900 \
  --acknowledge-unauthenticated-control
```

Open FiiO Control search. The candidate uses the **Mac's address**, distinct from
the physical DISC. The name remains SNOWSKY DISC for protocol compatibility;
do not select by name alone. Quit with Ctrl+C or let the 15-minute timer expire;
listeners and active forwarding close. Maximum session duration is one hour.
If macOS asks about local-network/firewall access, grant only what this test needs.
A failed bind or missing announcement is not a reason to disable the firewall.
Ordinary `up`, `boot`, `view` and `wsbridge` never start LAN exposure.

## Automated validation and limits

```sh
CI_SCENARIO=discovery FW_VERSION=2.57 \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The disposable scenario joins multicast inside the emulator namespace, checks
three or more idle beacons, then verifies silence before/after TCP handshake,
fresh protocol/settings reads, disconnect and resumed beacons. Read-only
fingerprinted memory independently verifies connected state. It does not scan
or mutate the library/settings. Full integration runs it after the first boot,
before UI scanning. A local pass does not prove Docker-to-LAN multicast relay.

Firmware-free tests cover strict payload recognition, interface selection,
bounded observation, setup cleanup, host relay bytes/half-close, peer rejection,
single-client control, HTTP readiness and announcement gates/TTL. The host bridge
is opt-in and uses the existing loopback publications; Compose documents the
entry point and Dockerfile requires no new dependency or image-only experiment.

Physical iPhone acceptance on 2026-09-16: with explicit approval and a single-phone
IP filter, the host emitted the verified product-name packets from its LAN address.
The user found and connected to that address in FiiO Control and opened the
emulator's media library. The bridge independently recorded one control connection
and HTTP connections. After the user confirmed disconnect, the host observer saw
the emulator's announcements resume and the user found it again in search. The
bridge was then stopped explicitly and absence of its LAN listeners was checked.
No mDNS advertisement or WebSocket translation was needed
for this tested path. This is discovery/connection/library browsing evidence,
not a claim that every official-app operation works. No library reset, file
deletion or settings change was part of this manual test.

Background reconnect, multiple phones, Android support, mDNS/AirPlay and stock
sleep/wake compatibility remain separate. Default idle power can stop the guest;
HTTP readiness then suppresses announcements, but the bridge cannot wake it.

Final validation: 250 Python tests, 23 JavaScript tests, shell checks, four shim
builds, Compose validation, focused discovery and full local V2.57 integration
passed. Two pre-existing EOF test assumptions surfaced in the full runs and were
corrected with trace evidence before the successful third run; see the
[failure/validation history](../../research/docs/reports/2026-09-19-protocol-checkpoints.md#lan-discovery-investigation-2026-09-16).

### Host adapter shutdown regression (2026-09-19)

On current asyncio, listener `wait_closed()` also waits for accepted connections.
The bounded LAN adapter now stops accepting, closes its owned proxy connections,
then awaits listener shutdown. Previously the reverse order could keep shutdown
waiting for an active client. A lifecycle regression models an accepted connection
and checks completion without binding LAN ports or sending discovery packets.
Together with the WebSocket cleanup regression, all 29 bridge tests pass locally.
