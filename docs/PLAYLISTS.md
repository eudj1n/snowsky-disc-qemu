# Custom-playlist playback (DISC V2.57)

Custom playlist creation/editing uses the [stock HTTP API](HTTP_API.md#http-catalog-and-custom-playlists).
Playback uses stock TCP 12100, or the emulator's WS-to-TCP bridge, not a new HTTP
play endpoint. The implementation targets active V2.57 only; no firmware patch.

## Wire contract

| Action | Complete frame |
| --- | --- |
| Play playlist at position 0 from its first track | `010100140005{"id":0}` |
| Play its second track | `0100001800010005{"id":0}` |

`0100` carries a four-hex-digit **track position**, then list type `0005`, then
JSON. `0101` omits the track-position field. JSON `id` is a **decimal integer
playlist position**, despite its misleading name: it is not `LIST_ID`, the list
name or a song ID. For playlist position 12, send `{"id":12}`, not hex `000C`.
Indices are zero-based. Length includes the eight ASCII header bytes.

Use positions and ordering from fresh HTTP `custom` and `custom/song` pages.
Do not infer track order from insertion order: the initial reverse-add test
produced a different catalog order. Deleting a preceding playlist shifts later
playlist positions; track additions/removals may change selection bounds/order.

## Client helper

Both `Client` and `WSClient` expose:

```python
# Run from the repository with python3.
# http and link must connect to the SAME physical device or emulated guest.
# Example local direct endpoints; the guest must already be running.
from controller.fiio_http import HTTPClient
from controller.fiio_link import Client

http = HTTPClient(port=12113)
with Client() as link:
    link.handshake()
    lists = http.catalog('custom')
    selected = lists['items'][0]  # UI-selected row; handle an empty page first.
    link.play_playlist(selected['pos'], index=1, http=http,
                       expected_name=selected['name'])
    # Omit index (or use None) to send 0101 and play the whole list.
    # Sending is not acknowledgement: wait for matching 0202/a202 state/metadata.
```

On `WSClient`, await the same method. Its synchronous HTTP preflight runs in a
worker thread so the WS receiver can continue handling events. The caller supplies
the HTTP client explicitly: a WS URL does not imply a stock HTTP port. In the
emulator, HTTP can use direct port 12113 or the bridge/proxy on 12103.

The helper validates argument types/ranges before I/O, checks `0501.soc_version`
equals 257, then reads the playlist row, requested song row, and playlist row
again. The observed list name must match `expected_name`, returned positions must
match, and the track must exist. Missing/empty lists, stale names/positions and
out-of-range tracks fail before a playback command is sent. HTTP failures also
prevent selection. No cached count, fallback to list 0, or mutation retry is used.

These reads are **not an atomic transaction**. Stock HTTP provides no stable list
identity/revision token for this workflow. Another editor can race the checks;
deleting/recreating a list with the same name cannot be distinguished. Serialize
edits and playback selection, refresh after mutations, and never replay a queued
selection after reconnect. The generic `play_index(..., list_type=5)` remains
disabled so it cannot bypass the dedicated preflight accidentally.

Playback still has the stock navigation timing gate: tests separate selections
by 2.1 seconds. Observe matching track metadata/state rather than treating a
completed socket write as success. Current playback and queue are available
through `0202` and HTTP `curlist/song`; `playerflag` is 5 for this source.
After natural final stop, `0202` can be silent while the queue remains readable;
see the [EOF lifecycle](TRACK_END.md), not a timeout-based state inference.

## Static evidence and reproduction

All addresses are from the fingerprinted V2.57 `mq_player` build:

- TCP admits `0100` and `0101`; `4d61f8` parses their numeric fields/string tail.
- `4edd58` → `429008`, case 5, parses JSON `id` and calls `428dd0` with the track
  position. `4ede38` → `429500`, case 5, does the same with track position 0.
- `4377d8` translates list position using
  `SELECT LIST_ID FROM CUSTOM_PLAYLIST_INDEX ORDER BY LIST_ID LIMIT 1 OFFSET %d`.
- `428dd0` builds the custom playback list via `450d48`, then `435c68` selects
  its row using `SELECT ID FROM LIST_SONG_%d ORDER BY id LIMIT 1 OFFSET %d`,
  before the normal playback selector `423160`. Network positions are not these
  internal IDs; mapping belongs to stock firmware.

Reproduce with `research/ghidra/DecAt.java` at those function entries; see
[Ghidra instructions](../research/ghidra/README.md). Keep binaries, projects and raw
decompilation under ignored `work/`. Do not reuse the addresses on other builds.

`tests/integration/playlists_check.py` is a disposable generated-media scenario. It deliberately
creates a gap between playlist position and SQLite `LIST_ID`, checks selected
metadata and HTTP queue order/mark, exercises rename/add/remove and position shifts,
and checks rejection of stale/empty/out-of-range selectors. It leaves playback
paused on a valid album, restores the original mode, deletes only its generated
playlists and verifies unchanged source-media bytes.

```sh
CI_SCENARIO=playlists FW_VERSION=2.57 CI_LOGS="$PWD/work/playlist-check" \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

Validation is tracked in [PROTOCOL_RESEARCH.md](PROTOCOL_RESEARCH.md). Emulator
evidence is not a physical FiiO Control capture. Natural five-mode EOF behavior
has separate [short-track acceptance](TRACK_END.md).
