# Read-only firmware diagnostics

`probe_keys.py`, `probe_network.py` and `inspect_http_routes.py` support the pinned
V2.40 and V2.57 `mq_player` builds. Addresses live in the `diagnostics` section of
`firmware/v<version>.json`. Selection uses the full stock SHA-256 after normalizing
only the existing permitted key-enable instruction; version labels alone are insufficient.
Unknown binaries and an explicitly mismatched `--version` fail before memory is opened.
The legacy `ghidra/probe_out_device.gdb` is V2.40-specific and is not part of this port.

## Environment and commands

The repository Dockerfile supplies Python, MIPS binutils and gdb-multiarch. Build it
on a new computer with `docker build -t diskos-qemu-ci docker`; normal runtime setup
uses `./run.sh up ...`. These probes need no additional Python packages or Ghidra.
Memory probes run inside the emulator container and require one running player:

```sh
docker exec diskos-qemu python3 /repo/tools/probe_keys.py
docker exec diskos-qemu python3 /repo/tools/probe_network.py
docker exec diskos-qemu python3 /repo/tools/inspect_http_routes.py
# Optional explicit version/root; a wrong version is an error, never a fallback:
docker exec diskos-qemu python3 /repo/tools/probe_keys.py --version 2.57 --rootfs /work/rootfs
# Offline route inspection also works on the host:
python3 tools/inspect_http_routes.py /path/to/mq_player --version 2.57
# Offline TCP admission table; reviewed only for active V2.57:
python3 tools/inspect_link_commands.py /path/to/mq_player --version 2.57
```

`player_memory.py` restricts process discovery to the selected chroot and matches
mapped file device/inode to the fingerprinted binary. It derives the guest base from
ELF PT_LOAD offsets, requiring one base consistent with all mappings, rather than
assuming a host base. V2.40 maps the shared boundary file page of its two PT_LOAD
segments at different virtual addresses; intersecting each mapping's possible bases
handles this overlap without confusing code and data.
QEMU's host mapping of executable guest code can be `r--p` because instructions are
translated. Multiple players, missing/unreadable ranges, null context pointers and
short reads fail explicitly. Memory is opened only as `rb`; these tools never write it.
Snapshots span several reads and are not atomic; retry if the guest changes context
or exits. They are manual diagnostics, not a high-rate viewer transport.

## Address map

All values below are **guest virtual addresses** in the exact pinned builds.

| Field | V2.40 | V2.57 |
|---|---|---|
| Local volume byte | `82e98c` | `83a74c` |
| Screen-on byte | `82e995` | `83a755` |
| Single/double/hold assignment bytes | `82e9d2/3/4` | `83a792/3/4` |
| Player context pointer; state at `+48` | `8321f4` | `83dfc4` |
| IPv4 ASCII / ready word | `86c020 / 86c030` | `8781a8 / 8781b8` |
| Storage type / scan worker flag | `88cb9c / 88c844` | `898d2c / 8989d4` |
| `0502` / `0201` callback slots | `82e634 / 82e638` | `83a3f4 / 83a3f8` |
| Device-volume callback slot | `88cc44` | `898dd4` |
| HTTP route table / entries | `6c7a50 / 16` | `6d2580 / 17` |
| TCP allowlist / entries | Not reviewed | `6d84e0 / 111` |
| HTTP thread / active callback | `4b9720 / 4b9d38` | `4c0f90 / 4c15a8` |

V2.57 static derivation, using `mipsel-linux-gnu-objdump -d` and string/pointer xrefs:

- TCP receiver `4db020` calls `4dabc4`, which compares tags against the independent
  allowlist at `6d84e0` before enqueueing a command. NULL terminates it at `6d869c`.
  `inspect_link_commands.py` checks the full fingerprint, file-backed PT_LOAD
  ranges, exact count, lowercase tag strings, uniqueness and termination. It
  does not execute firmware or send commands. Presence means admission, not an
  implemented callback. Local dispatch tables are broader than this list; see
  [playback preferences](REMOTE_SETTINGS.md#playback-preferences-v257) for rejected
  TCP/WS commands despite populated runtime callbacks.
- Key dispatcher `4e72f0` uses configuration base `83a740`; the screen/assignment
  loads are at offsets `15`, `52`, `53`, `54`. Local-volume getter `4ea718` selects
  `83a74c`; the decrease path writes the same byte.
- State getter `4536c0` loads `*(83dfc4) + 48`; play/pause `42a198` calls it.
- Netlink handler `4bf504` stores ready at `4bfa40` and formats the observed IPv4
  string into `8781a8` at `4bfac8`. Detector thread is `4c00a4`.
- Scan thread `4ed42c` loads storage type at `8989c0 + 36c`, sets the worker flag
  at `+14` before `4c4100`, and clears it on success/failure. This flag describes
  that worker, not every possible library operation or auto-update trigger.
- Protocol table entries at `838e90`/`838e98` map `0502`/`0201` to wrappers
  `41fd50`/`41fd70`, which read the callback slots. Observed targets are
  `4ed814`/`4ed84c`; `4ed814` calls the device-volume slot, registered as `4e9d24`
  by `4ec2b4`. V2.40 targets remain `4e4744`, `4e477c`, `4e0fdc`.
- HTTP thread `4c0f90` supplies callback `4c15a8` to listen helper `4b5334` on
  port 12103. That callback references `6d2580` in both event paths (10/11).
  The existing 16 method/path pairs remain; V2.57 adds `POST /image/` → `48e46c`
  in the HTTP_CHUNK path. `GET /log/` exists in both versions (`4ba020` / `4c1890`).
  There is still no `/api/websocket` entry. This is the active table, distinct
  from the bundled inactive dashboard router. `/log/` functionality has not been
  exercised; neither has the new `/image/` upload. Live V2.57 requests to `/api/websocket` (with Upgrade headers) and
  `/__unmapped_probe__` both returned HTTP 200 with zero-length content on direct
  host port 12113. Route parsing checks PT_LOAD ranges, strings, executable handlers,
  event values, expected count and termination.

## Verification

`ci/integration.sh` now compares diagnostic volume with TCP before/after physical
buttons, state `1/2` with playing/paused protocol results, screen byte with sysfs,
and all three assignment bytes with SQLite. It verifies the detected IP against
the container's address, ready/storage/idle-scan values, exact callback targets,
capability drops and the version's route count. The stock UI scanner's flag is sampled
at 10 ms intervals and reported; an extremely short transition may be missed.
Wire playback state uses a different enum from the internal state.

Firmware-free tests cover stock/permitted-patch selection, wrong versions and modified
builds, malformed route tables/ELFs, file identity, conflicting mappings, inaccessible
ranges and short reads. Raw firmware, disassembly and runtime captures stay ignored.

Local arm64 verification on 2026-09-11 (working tree after `d706613`): V2.57 fresh
integration passed all the above comparisons plus byte-exact PCM, TCP/WebSocket bridge
controls and reboot-shim binding. The scan sampler observed both `0` and `1`, and the
post-scan snapshot returned `0`. The interactive V2.57 snapshot independently matched
the container IP and default assignment bytes `1/0/1`. These are local results, not
hosted CI or an exact-commit release gate.

V2.40 fresh integration also passed, including scan flag values `0/1`, all physical
controls and callback targets. Its overlapping PT_LOAD boundary exposed an ambiguity
in the initial base calculation; the corrected intersection is covered by a synthetic
regression test. Both V2.57 live memory probes were rechecked after that correction.
Final Python suite: **109 passed**. The full firmware-free run also passed all **19
JavaScript tests**, shell syntax and four shim builds. Test stacks and their work volumes
were removed; the interactive V2.57 environment remains separate.
