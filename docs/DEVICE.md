# The physical device (reconnaissance)

What the real FiiO Snowsky Disc does on the network and how the stock OS behaves — gathered from
the device itself, as groundwork for the emulator and a sync bridge. Hardware/SoC facts and the
firmware format are in [../firmware/README.md](../firmware/README.md); the wire protocol is in
[PROTOCOL.md](PROTOCOL.md). This page is the "what's actually reachable" side.

## Finding it on the network

- Hostname is **`ingenic`** → mDNS name **`ingenic.local`** (survives DHCP IP changes; prefer it
  over a raw IP).
- MAC prefix **`40:d9:5a`** (observed `40:d9:5a:e2:9b:aa`).
- Announces over mDNS/avahi: `_fiio._tcp`, `_ssh._tcp` + `_sftp-ssh._tcp` (port 22), and an
  AirPlay name **"SNOWSKY DISC"** (only while in AirPlay mode).
- The phone apps discover it via a **UDP 12101 multicast** heartbeat on `224.0.0.255` (~2 s).
  Corporate/guest Wi-Fi often blocks multicast (and isolates clients) → the apps then **can't
  auto-find** the player, but a **direct connection by IP still works** — discovery isn't required.

```sh
ping ingenic.local
dns-sd -G v4 ingenic.local     # IPv4 only (Ctrl+C to stop)
dns-sd -B _fiio._tcp           # an instance appears only while a control channel is active
arp -n <ip>                    # MAC, to re-find the device after a DHCP change
```

V2.57 follow-up: the UDP payload is exactly `SNOWSKY DISC`, with no embedded
address/port. Stock TCP acceptance suppresses its beacons until disconnect.
The `_fiio._tcp` registration code uses port **12102**; do not infer control port
12100 from that service name. Current physical/emulator evidence, caveats and
the opt-in host LAN bridge are in [DISCOVERY.md](DISCOVERY.md).

## Open ports (stock V2.40, full 65535 scan)

| port | service | notes |
|---|---|---|
| 53/tcp | dnsmasq (DNS) | background |
| 111/tcp + high (mountd/statd) | rpcbind + NFS RPC daemons | **no exports, no `nfsd`** → NFS is *not* a file-access path (it exists for the NFS *client*, to mount a NAS) |
| **12100/tcp** | FiiO Link — control, state, library | **auth-free**, one client at a time |
| **12103/tcp** | Stock Mongoose HTTP — `/dir/`, `/audio/`, image and library routes | Active router is not `mg_dash`; no stock WebSocket route established (see [PROTOCOL.md](PROTOCOL.md)) |
| 12101/udp | discovery multicast | `224.0.0.255` |

12100 is the working channel. Minimal client:

```python
import socket
s = socket.socket(); s.connect(("ingenic.local", 12100))
s.sendall(b"0599000c0000")   # handshake  -> a599000C0306
s.sendall(b"05010008")       # settings   -> a501...{json}
print(s.recv(4096))
```

## Stock firmware has no developer/debug unlock

- **"Settings → System → Debug Mode"** and SSH that enthusiasts mention are **diskOS** features,
  **not** stock. On stock V2.40, System Settings has only *Screen rotation / Reset all / About
  device*; Network Settings has only Wi-Fi connection. There is **no wireless-control toggle** and
  **no hidden "tap the version 7×"** gesture (nothing in the binary implements one).
- **No sshd in the stock rootfs** — avahi advertises `_ssh._tcp`, but nothing listens (port 22
  scans closed). A root shell needs either **diskOS** (adds Debug Mode + SSH; see
  [DISKOS.md](DISKOS.md)) or the board's **UART** test pads (inittab gives a passwordless
  `/bin/sh`).
- The only hidden mode is `factory_test` (`factory_test/1..10.jpg`), reached by a boot key-combo /
  factory rig — not from the UI, and unrelated to networking.
- FiiO Link is not "enabled" anywhere in the menu — the server listens whenever the player is up;
  the phone app just connects (multicast discovery, or manual IP). "Enabling wireless control" is
  a client-side action, not a device toggle.

## SD card and file access

- The music SD is mounted at **`/tmp/sdcard/`** (confirmed from a now-playing path, e.g.
  `/tmp/sdcard/<Artist>/<Album>/NN. Track.flac`). The emulator reproduces this mount point.
- FiiO Control exposes Wi-Fi file import and folder creation for DISC in user-provided
  screenshots (2026-09-15). Follow-up tests confirmed `POST /audio/`, `GET/POST /dir/`
  and single-path `DELETE /file/` in the emulator and on physical V2.57 with generated
  media; see [HTTP_API.md](HTTP_API.md) for the exact request contract and evidence.
  The earlier claim that SD writes require `mg_dash` credentials or a root shell was
  incorrect. Tested library **read** and transport **control** use auth-free 12100;
  file management is a separate [HTTP investigation](PROTOCOL.md#file-transfer-is-a-separate-http-investigation).
