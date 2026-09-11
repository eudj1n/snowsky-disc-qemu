# Local network emulation (V2.40)

The stock firmware serves FiiO Link on TCP **12100** and Mongoose HTTP on **12103**.
No network binary patches, hard-coded IP, dummy Wi-Fi or DB flag overrides are needed.
This milestone is local control, not Wi-Fi radio emulation or cloud streaming.

## Reproduce

Use Docker Compose **2.36+** (tested with 5.5.1):

```sh
docker compose up -d --build
./run.sh boot
./run.sh view
python3 tools/fiio_link.py
python3 tools/verify_network.py
```

For a new work volume, first use `./run.sh up /path/to/ota_v240` as in the README.
Do not delete an existing volume to upgrade. Setup stops the guest before updating
mapped shims or rebuilding its SD. Power-on from the viewer reruns network preparation
and announcement too. The viewer itself must be started again after container recreation.

The actual Compose file is `docker-compose.yml`, not `compose.yaml`.
Its [`interface_name`](https://docs.docker.com/reference/compose-file/services/#interface_name)
setting gives Docker's normal bridged interface the firmware-supported name **eth1**.
Docker assigns the address and default route. All four published ports bind **127.0.0.1**:
12100, 12103, UDP 12101 and the viewer 8080. Auth-free player controls must not be
accidentally exposed to the LAN.

## Why it was blocked

Three independent gates were observed:

1. `FUN_004b89a0` subscribes to NETLINK_ROUTE groups `0x11` (link + IPv4 address),
   but does **not** request a dump of addresses that existed before player startup.
2. `FUN_004b7e00` handles `RTM_NEWADDR`, saves the IP at `0x0086c020`, and sets
   `0x0086c030 = 1`. `FUN_004e99d0` checks this flag every second and starts HTTP
   (`004b9914`) and FiiO Link (`004d344c`). Merely setting WIFI_STATUS is insufficient.
3. FiiO Link's `FUN_004c7408` independently reads the default route and supports only
   `wlan0` or `eth1`. The standalone firmware `/sbin/ip addr show eth1` fails under
   this QEMU 7.2 with **Operation not supported**; the stock BusyBox `ip` applet works.

`scripts/16_network.sh prepare` mirrors eth1's actual MAC/operstate into guest sysfs
and installs command wrappers. `announce` waits for the detector's startup log and
re-announces the **same** Docker IPv4 address with `ip addr change … valid_lft forever
preferred_lft forever`, then waits for both listeners. No interface down/up, new
address, DHCP exchange, host route or firmware-memory mutation is involved.
The `ip` wrapper delegates the two read-only queries to `/bin/busybox ip`.

## Confinement and reproducibility

This is still a **privileged development container**, not a security boundary for
untrusted firmware. `guest_run()` in `scripts/lib.sh` uses the Dockerfile's
`util-linux`/`setpriv` to remove NET_ADMIN, SYS_TIME, SYS_BOOT, SYS_MODULE and SYS_RAWIO
from the guest bounding/effective capability sets and enables no-new-privileges.
This applies to the normal boot, first-boot priming, GDB and touch diagnostic launchers,
including child commands. SYS_ADMIN remains for the existing SD mount workflow.

The stock network-up path launches OTA helpers/NTP and executes `hwclock -w` every
21 seconds. `scripts/guest-command.sh` blocks those commands and guest network
configuration tools; original executables are preserved at `/emu/original-commands/`.
Wrappers are installed atomically without following BusyBox symlinks. No utilities
were installed ad hoc in the image. Dockerfile checks `setpriv` and `ip` availability.
These wrappers are an accident-prevention measure, **not an outbound firewall**;
library-level connections and direct syscalls are not comprehensively sandboxed.

Read-only live state/capability check (never writes `/proc/PID/mem`):

```sh
docker exec diskos-qemu python3 /repo/tools/probe_network.py
docker exec diskos-qemu python3 /repo/tools/probe_keys.py
docker exec diskos-qemu ip route
```

## Wire checks and controls

The library scanner has a separate storage gate from Browse files. It checks
`access(source)` for entries in `/proc/mounts` (`004bc890`, called by `004269e0`).
The old source `/work/rootfs/dev/mmcblk0p1` was inaccessible inside chroot: Update now
stayed on **0 songs**, and its worker returned early. `sd_mount()` now mounts from
inside the guest, recording `/dev/mmcblk0p1 /tmp/sdcard`. The stock scanner then
finished with **4 songs**, and TCP 0401 returned the same four records. No synthetic
database rows were inserted. Use Settings → Update media lib → Update now after
placing files on the SD. Screenshots are in [STATUS.md](STATUS.md).

Temporary Auto update fixture, generated with the Dockerfile's SoX dependency:

```sh
docker exec diskos-qemu bash /repo/scripts/media_fixture.sh add
./run.sh boot
# Inspect the app and run tools/fiio_link.py; do not press Update now for the auto test.
docker exec diskos-qemu bash /repo/scripts/media_fixture.sh remove
./run.sh boot
```

The fixture generator refuses to overwrite existing media; removal verifies its
recorded SHA-256. The second boot rebuilds the SD without the generated file.
In the 2026-09-11 test the fifth file was present on the rebuilt SD, but no startup
scan ran and the index stayed at four records. Clicking Auto update gave no confirmed
effective-state change. Its persistence/trigger are **not established**, so do not
assume it works. The generated file was removed and the original SD restored.

`tools/fiio_link.py` uses only Python's standard library, defaults to localhost and
handles fragmented/coalesced frames. Lengths count UTF-8 **bytes**. It decodes the
nested JSON string in `now_playing.song`. Stock firmware sometimes sends no 0202
reply before a track is selected or after its state is cleared; the CLI reports
that timeout separately instead of claiming playback metadata exists.

```sh
python3 tools/fiio_link.py --volume 118  # absolute logical volume, 0..120
python3 tools/fiio_link.py --play-pause # selected track only
python3 tools/fiio_link.py --play-all   # start all indexed local songs
# Open a test track first. This writes volume (then restores it) and toggles twice:
python3 tools/verify_network.py --control
# Or select the indexed library over TCP; final test state is paused:
python3 tools/verify_network.py --control --start-library
```

Confirmed command routing, without sweeping arbitrary setters:

| Request | Stock route |
|---|---|
| `0599000C0000` | handshake, `a599000C0306` |
| `05010008` | settings JSON including volume and firmware 240 |
| `0401000C0000` | indexed library page, not a live SD directory listing |
| `02020008` | now-playing JSON, including actual `/tmp/sdcard/…` path |
| `0502000C0076` | volume 118: table 82d520 → 41c640 → 4e4744 → callback 88cc44 → 4e0fdc |
| `0201000C0000` | play/pause: table 82d528 → 41c660 → 4e477c → 424b2c(0, 0) |
| `0101000C0001` | start all indexed songs: 4e4cb4 → 423e94, list type **1**; type 0 reuses the current queue |

Live verification after repeated setup/boot: volume **119 → 118 → 119**; wire play
state **0 → 1 → 0** for the same indexed track (playing → paused → playing), then
left paused. Independent guest memory readback showed player state **2** (paused)
and volume **119**. Wire state numbers are different from the internal player enum.
The client drains old asynchronous notifications before new queries: a queued `a202`
must not be mistaken for a response to a later play/pause action. The protocol has no
request IDs; the client is sequential and intentionally does not support concurrent requests.

Mongoose `GET /api/hi` returns HTTP 200 with an empty body. A standard WebSocket
upgrade on `/api/websocket` also returns **200, not 101**: WebSocket control is **not
validated** by this milestone. Raw TCP does not depend on dashboard credentials.
Multicast discovery across the Mac/Docker/LAN boundary is also not implemented;
publishing UDP 12101 is not a multicast relay. Use explicit localhost connections.
OTA installation, NTP, internet services and actual Wi-Fi association are out of scope.

## Re-run the reverse engineering

On an analyzed stock V2.40 `mq_player` Ghidra project, use the committed scripts:

```sh
analyzeHeadless /path/to/project mqproj -process mq_player -noanalysis -readOnly \
  -scriptPath /path/to/diskos-qemu/ghidra \
  -postScript DecFuncs.java 0x4b89a0 0x4b7e00 0x4e99d0 0x4c7408 0x4b6a60 \
  -postScript DecFuncs.java 0x4e4744 0x4e477c
```

Scanner gate: `-postScript DecFuncs.java 0x4269e0 0x4bc890 0x462488`.
The `mq_ui` function `0043ed1c` (`ui_set_media.c`) is **AirPlay settings**, not
Update media lib; do not follow that misleading "media" string when investigating Auto update.

The pointer tables and trampolines can also be inspected inside the image with
`mipsel-linux-gnu-objdump -s/-d --start-address=… --stop-address=…
/work/rootfs/usr/bin/mq_player`. Data virtual addresses are **not** uniformly
`file offset + 0x400000`; use ELF-aware tools rather than raw-offset guesses.
