# Dedicated library reset (DISC V2.57)

`0621000C0000` is a dedicated, TCP-admitted reset of the music index and favorites.
It is **not** `0800` factory reset, file deletion, scan cancellation or a rescan.
The helper requires explicit confirmation:

```python
client.reset_library(confirm=True)            # TCP
await ws_client.reset_library(confirm=True)   # our WS-to-TCP bridge
```

Both helpers send exactly one frame. Without literal `True`, they fail before
network I/O. They do not wait for an acknowledgement, retry, reconnect/replay,
scan, reboot, or fall back to a broader reset. They do not auto-detect firmware;
the contract is validated only on the fingerprinted DISC V2.57 emulator.

## Scope and immediate results

Acceptance seeds three generated tracks, one favorite, an album queue paused
before reset, and a two-track custom playlist. On both TCP and WS:

| State | Observed after reset |
| --- | --- |
| SONG index | Table dropped; TCP tracks and HTTP `all/song` return zero |
| Favorites | `MY_LOVE` dropped; HTTP `love/song` reports invalid `total-num: -1` until repaired, not a valid empty catalog |
| Queue | `LIST_SONG_0` dropped; HTTP `curlist/song` returns zero |
| Custom playlists | `CUSTOM_PLAYLIST_INDEX` and `CUSTOM_PLAYLIST` rows unchanged; list name/count survive, but immediate `custom/song` has `total: 2, items: []` |
| Player snapshot | `0202` returns an empty payload (`{}` in the helper); read-only runtime state remains paused |
| Settings/files | SYSCONFIG rows, Wi-Fi config and theme DB presence/content unchanged; all source media byte-identical |

The missing player snapshot is **not evidence that playback stopped**. The reset
handler does not call the player stop path. Playing-state behavior is not covered
by the paused acceptance; do not implement a reset as an implicit stop command.
No `a621` acknowledgement or `a60a`/`a622` scan sequence was observed. Unrelated
volume notifications can still arrive and must not be used as reset completion.

The command also attempts to drop `LIST_SONG_3` and deletes `PLAY_LIST` rows with
IDs 0 and 3. The fixture had `LIST_SONG_0`, not `LIST_SONG_3`; deletion of an
already absent table is logged by stock code. Other PLAY_LIST rows are preserved.
Custom-list IDs are a different namespace; do not infer that custom list 0 is deleted.

## Recovery and controller requirements

Warn explicitly that **favorites are discarded**. Reindexing can rebuild the
file catalog; it cannot reconstruct the user's old favorite selections.

Serialize this operation with indexing and library/playlist edits. Static reset
code has no scanner-running guard or surrounding scan mutex. Never reset during
an active scan; do not invent concurrent-reset semantics from the isolated test.
Use one owner of the stock single-client connection and send once after explicit
user confirmation. A timeout/disconnect means uncertain outcome, not permission
to replay the destructive command.
Use the validated paused-player, idle-scanner path: pause playback and observe it before
reset, rather than assuming reset will stop audio. Returning from the helper only
means the frame was sent; it is not an acknowledgement of completed DB changes.

Invalidate cached catalogs, queue positions and now-playing metadata after reset.
Do not interpret `total > 0` with no items as a usable playlist or repeatedly
paginate it without a no-progress bound. Preserve the HTTP client's rejection
of negative totals; don't normalize a missing favorites table to a successful
empty response. Refresh state before offering any playback operation.

An explicit guest restart was verified to preserve the empty index/favorites and
recreate readable tables. Saved custom playlist membership becomes readable again.
A subsequent explicit full scan restores the three source tracks, not favorites.
Restart is a test recovery step, **not part of `reset_library()`**, not a remote
reboot API and not a claim about what FiiO Control automatically does.

A TCP-triggered scan **without restart** restores the track catalog and custom
membership, but does not recreate MY_LOVE: favorites still report `total-num: -1`.
The custom page's playback `mark` can change; it is not a membership identifier.
Thus a successful full scan alone does not establish complete recovery of every
library endpoint. A later guest restart recreates the empty favorites table.
See [PROTOCOL_RESEARCH.md](PROTOCOL_RESEARCH.md) for final regression status.

## Static evidence

V2.57 `mq_player`, matched by its full firmware-profile fingerprint:

- `0621` is in the separate TCP allowlist at `6d84e0`; `0800` is absent.
- Shared dispatch table `8388d0`: `0621` → stub `414bc0` → callback slot
  `83a56c` → `4f0814`. Unlike a string found in a binary, this is a reachable
  handler chain, verified again against the live callback before the test.
- Parser `4d61f8` treats `0621` as an integer
  argument plus optional suffix. The handler ignores the argument. We use one
  tested zero payload; other values are not a supported public interface.
- `4f0814` calls `444040` (`DROP TABLE SONG`), `43ac00` (`DROP TABLE MY_LOVE`),
  `43665c(0/3)` (`DROP TABLE LIST_SONG_n`) and `43a448(0/3)`.
- `43a448` calls `4309e8` to delete matching `PLAY_LIST` rows, and drops their
  song tables if still present. None of these functions removes SD files.
- Compare only statically with `0800` → `414aa0` → slot `83a548` → `4f05d8`:
  that broader path also rewrites Wi-Fi config, clears Wi-Fi data, removes theme
  and song DB files and calls system-reset logic. **Never sent in this task.**

Reproduce with `tools/inspect_link_commands.py`, `ghidra/DecAt.java` at the
function entries and `RefsTo.java` on the callback/SQL functions. Raw binaries,
Ghidra projects and decompilation stay ignored under `work/`.

## Acceptance and limits

```sh
CI_SCENARIO=library-reset FW_VERSION=2.57 CI_LOGS="$PWD/work/library-reset" \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

`ci/library_reset_check.py` refuses anything but `CI_DISPOSABLE=1`, V2.57, the
reviewed binary and exact generated SD fixture. Mutations use stock Link/HTTP;
DB/memory inspection is read-only. Tests never reset the interactive emulator or
a physical device. No image patch or new Docker dependency is required.
The full V2.57 pipeline runs this after scan-cancellation acceptance and before
SD hotplug/preference checks. Both focused and full local runs passed, along with
213 Python tests, 23 JavaScript tests and four shim builds; see the checkpoint
report for the earlier test-assertion correction and remaining limits.

The owner confirms that FiiO Control exposes library reset. Its exact app-generated
frame and follow-up sequence are **not captured**: Android AOT's
`getResetLibraryMsg` was only a string lead. This document establishes the stock
DISC command and emulator behavior, not an observed iOS/Android action sequence.
Physical effects, playing/concurrent-scan reset, folder/CUE/SACD queues and other
firmware versions remain unvalidated. Do not request a real-player reset capture
without first explaining the loss of favorites and agreeing on disposable state.
