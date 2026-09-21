# Remote indexing and cancellation (DISC V2.57)

Explicit indexing uses stock Link TCP 12100, or our WS-to-TCP bridge. It is not
an HTTP upload operation or a library-reset command. The active V2.57 emulator
contract below is independently checked against the network catalog and SQLite.
SD-insertion auto-update has separate UI gates: see [MEDIA_LIBRARY.md](../../emulator/docs/media-library.md).
Dedicated `0621` index/favorites reset has a separate destructive contract:
[LIBRARY_RESET.md](library-reset.md). Do not confuse it with cancellation.

## Commands and events

| Direction | Complete frame / payload | Meaning |
| --- | --- | --- |
| Client → DISC | `0622000C0000` | Start a scan |
| Client → DISC | `0622000C0001` | Request cooperative cancellation |
| DISC → client | `a60a` / `000F` | Scan start notification |
| DISC → client | `a622` / hex integer | Number discovered so far; not a percentage or a completion flag |
| DISC → client | `a60a` / `0005` | Scan ended — observed for **both full and cancelled scans** |

The new `Client.cancel_library_scan()` and
`await WSClient.cancel_library_scan()` send one cancellation frame. They do not
wait for a distinct acknowledgement, query settings, drain queued events, retry,
restart or reset the library. These helpers have been validated on V2.57, not on
other products/firmware; they do not auto-detect the connected model/version.

Cancellation is not instantaneous. The scanner finishes in-flight work and
flushes buffered records, so later counts can exceed the count at which cancellation
was requested. The first focused test requested TCP cancellation at 455 and ended
at 508 of 515 files; WS requested at 314 and ended at 397. The final full-suite
fixture had 1027 files: requests at count 1 ended at 167 (TCP) and 31 (WS).
Those are observations, not guaranteed delays or batch sizes.

**Cancellation does not restore the old index.** A new scan drops/recreates the
SONG table before rebuilding it. A cancelled rescan therefore leaves a partial
replacement catalog, even when the previous scan was complete. A subsequent
explicit full scan restores all valid tracks. Generated source files were unchanged
byte-for-byte; cancellation is not file deletion. Playlist/favorite references,
restart persistence of a partial index and unusual formats require separate tests.

Idle cancellation produced no scan start/count/finish events and did not change
the catalog. It sets the stop flag even while idle; starting a new scan clears
that flag, so cancellation is not a persistent "disable indexing" switch.

## Controller lifecycle

Use one owner for the stock single-client connection and serialize library edits
and scan lifecycles. There is no request ID or per-client cancellation token:
the stop flag belongs to the shared scanner, not to a particular UI operation.

1. Send `scan_library()` once, then continuously consume `event()` notifications.
2. On user cancellation, send `cancel_library_scan()` once and show
   **cancellation requested**, not immediately "cancelled".
3. Continue consuming count/finish notifications. `a60a/0005` means the worker
   ended; it does not establish a complete catalog or a distinct cancelled outcome.
4. Refresh the catalog after completion. After a cancellation request, explain
   that the catalog may be partial and offer an explicit new full scan.

The current sequential clients' `request()` methods discard unrelated events.
Do not interleave settings/catalog queries with this event-consumption phase or
treat a missing event as proof of completion. A timeout/disconnect leaves the
outcome uncertain; do not replay cancellation after reconnect, where it could
affect a later scan. A late cancellation can race normal completion.

Static analysis also shows the start notification precedes stop-flag reset.
Sending start and cancel back-to-back can therefore lose an early cancellation;
this ordering risk is not a measured guarantee about every race. Acceptance sends
cancel only after a positive `a622` event and read-only confirmation of a running
worker. Neither an immediate socket write nor `a60a/000F` alone proves that an
immediate cancel has been consumed. Never substitute `0800` factory reset.

## Static evidence and reproducible validation

Addresses below apply only to the fingerprinted V2.57 `mq_player`:

- `0622` is admitted by the separate TCP allowlist. Handler `4f0550` calls
  `42e18c`: zero starts worker `42c050`; nonzero calls `469178(1)` to set stop
  word `85fbdc`. The public helper uses exactly 1, not a sweep of payloads.
- `42c050` sets running word `8989d4`, checks the mount, sends start, then calls
  `469184`. It clears running after the scanner returns.
- `469184` locks the scan, clears stop, drops SONG through `444040`, creates
  its replacement and scans accessible `/dev/mmcblk0`/`/dev/sd` mounts.
- `468bd8` joins traversal/parser threads and sends a final count. Parser
  `467dbc` checks stop between work items and flushes buffered rows before exit;
  its normal batches contain up to 200 records. Progress is throttled.
- Even the stop path returns through the normal scanner end: `469184` sends
  `a60a/0005` and clears stop. There is no separate cancellation result here.

Reproduce with `research/ghidra/DecAt.java` at these entries and `RefsTo.java` for the flag;
see [Ghidra instructions](../../research/ghidra/README.md). Keep binaries and raw outputs ignored.

`tests/integration/scan_cancel_check.py` creates 1024 deterministic one-second silent WAVs in a
new directory on the **disposable guest SD**, in addition to the three standard
fixtures. It first builds a complete index, then tests each transport: idle cancel,
cancel after observed progress, partial TCP/HTTP/SQLite agreement, flag cleanup,
and a new full scan. No guest memory/DB patch or artificial scanner delay is used.
It checks source bytes, removes only its generated files, and reindexes the
original three. Acceptance fails if the cancellation misses the active scan; it
does not retry the mutation until a desired partial count happens.

```sh
CI_SCENARIO=scan-cancel FW_VERSION=2.57 CI_LOGS="$PWD/work/scan-cancel" \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The full V2.57 pipeline runs this scenario before the SD hotplug tests (which
reboot the guest). All fixture changes are tracked in CI; no additional Docker
dependency or change to interactive settings is required. See
[PROTOCOL_RESEARCH.md](../../research/docs/status.md) for current validation status.
