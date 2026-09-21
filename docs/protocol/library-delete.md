# DISC V2.57 category deletion

The emulator matrix below is a **firmware contract on disposable generated
media**. Physical iOS `224332` and `225423` confirm scoped-track deletion with
flags zero/one and subsequent directory inspection; `IMG_6820` reports
album-group Delete unsupported.
Those evidence levels are separate. Emulator experiments sent no deletion to the
physical DISC; the owner later deleted only the supplied disposable fixture.

## Request and identity

`DELETE /song_category_tree/` accepts a category in the `type` header and a JSON
array of inclusive, zero-based position ranges, for example `[[0,0],[2,2]]`.
Positions belong to the current filtered category. For `custom/song`,
`src_list_id` is the playlist's current position, not its internal SQLite ID.
For `custom`, the body must select exactly one playlist: `[[position,position]]`.

`delete_source: 0` preserves source files. The tested `delete_source: 1` also
unlinks files; the handler branches on nonzero, with default zero. Neither the
flag nor the HTTP status describes all database side effects. Empty HTTP 200 is
also used for rejected requests; always read back affected catalogs and files.

Accepted categories: `all/song`, `artist/song`, `artist/album/song`, `album/song`,
`style/song`, `style/album/song`, `love/song`, `curlist/song`, `custom/song`,
`custom`. Group categories `style`, `style/album`, `album`, `artist` are absent
from DELETE's allowlist. The existing `library` scenario verifies that
`style/album` returns 200 without deleting anything, while a scoped
`style/album/song` index deletion works. ADD's group expansion is not DELETE's
contract; do not reuse it blindly.

## Observed effects

Fixture: eight generated tracks, two custom playlists each containing Alpha,
Beta and Gamma, Alpha in favorites. The current player is paused on a separate
baseline track. Track deletion selects Alpha and Gamma; favorites removal
selects Alpha; whole-list deletion selects the first playlist.

| Category / flag | Files | General catalog | Favorites | Custom playlists |
| --- | --- | --- | --- | --- |
| `custom/song`, 0 | Preserved | Unchanged | Unchanged | Selected entries removed from the selected list only |
| `love/song`, 0 | Preserved | Unchanged | Selected favorite removed | Unchanged |
| `custom`, 0 | Preserved | Unchanged | Unchanged | Selected list removed; other list unchanged |
| `all/song`, 0 | Preserved | Selected tracks removed | Matching favorite removed | Matching tracks removed from **both** lists |
| `all/song`, 1 | Selected files removed | Selected tracks removed | Matching favorite removed | Matching tracks removed from **both** lists |
| `custom/song`, 1 | Selected files removed | **Stale entries remain** | **Stale favorite remains** | Matching paths removed from **both** lists |
| `custom`, 1 | All three list files removed | **Stale entries remain** | **Stale favorite remains** | Selected list removed; other list retains **stale entries** |

After each request a stock scan verifies recovery:

- Index-only deletion restores the general catalog, but does **not** restore
  removed favorites or playlist membership.
- A scan removes missing files from the general catalog. It does **not** clean
  the stale favorites/custom entries left by the tested custom source deletions.
  A favorite created from folder playback can change its display from the tag
  title to `01.flac` when the SONG row vanishes; its saved path remains unchanged.
- Removing a playlist member or a favorite with flag zero stays local to that
  collection across the scan.

Thus “remove from playlist”, “remove from library” and “delete files” need
distinct consequences in a future controller. In particular, flag zero on
`all/song` still loses collection membership, and flag one on `custom/song`
affects other playlists containing those paths. Do not advertise these as
reversible by scanning.

## Static cross-check

Addresses below are V2.57 `mq_player`, selected by the reviewed full stock/key-
patched fingerprint through `firmware.profile.identify_player`, not version text:

- `0x49484c`: category DELETE; allowlist at `0x6cda34`, range gathering,
  scan-running gate, ID-based deletion for flag zero and path/unlink branch for
  nonzero. General-catalog removal also deletes matching paths from auxiliary
  tables. A currently selected item has a separate next-track path.
- `0x440fd0`: returns the shared `CUSTOM_PLAYLIST` table name.
- `0x48f2cc`: deletes matching paths in the supplied table. In the custom/song
  source branch this has no playlist-ID restriction, explaining cross-list loss.
- `0x437190`: removes one list's rows and its index entry by internal LIST_ID.
  Whole-list source deletion first unlinks the collected paths without cleaning
  the other catalogs, explaining the stale references.

No firmware patch or direct database write implements any deletion in the test.
SQLite is inspected read-only; requests, favorites and scans use stock services.

## Reproduction and limits

```sh
CI_SCENARIO=library-delete FW_VERSION=2.57 \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

`tests/integration/library_delete_check.py` requires `CI_DISPOSABLE=1`, V2.57, exactly the three
original generated CI files and no preexisting custom lists. It adds five tagged
FLAC fixtures and tests all seven rows through direct and bridged HTTP, with
TCP/WS used for selection, favorites, scans and state readback. HTTP mutations
are not WebSocket commands. It verifies SQLite membership, fresh HTTP totals and
rows, exact remaining file set, bytes/hashes and the unrelated paused track.
Only its own removed fixtures are recreated; all five additions are removed at
the end and the original three-track catalog/files are verified. The random
Compose stack and volume are then discarded.

Validation on 2026-09-16: the fresh V2.57 `library-delete` run passed all
**14 cases (seven direct + seven proxied)**, including post-delete scans,
restoration, final three-track baseline and disposable-stack cleanup.
Firmware-free checks passed **286 Python / 23 JavaScript tests**, shell syntax
and four shim builds. Shared runtime and production helpers were unchanged;
`full`, `idle` and `idle-usb` were not repeated. Local evidence is ignored under
`work/library-captures/delete-verified.log`, `delete-verified-logs/`,
`delete-unit.log` and `delete-{decompile,callees}.log`; the committed scenario
and assertions provide reproduction without those local artifacts.

The first exploratory run completed seven direct-HTTP cases, then failed while
preparing the WS pass: after deletion/recreation/scanning, album position zero
selected Beta instead of the expected Alpha. This is not a deletion failure or
an established transport defect. The final fixture selects Alpha by its fresh
folder row and verifies both title and path before setting its favorite. The
exact cause of the album-order mismatch remains separate; do not assume HTTP
display order is universally the playback order after rebuilding a library.
A second probe caught the folder-origin favorite's title-to-filename fallback
after a missing-file scan; final assertions distinguish display metadata from
persistent favorite identity using the stored path.

Not covered: deletion of the current track/list, nonzero `love/song` or
`curlist/song`, unlink failures, interrupted requests, concurrent edits, reboot
persistence, CUE/SACD logical tracks sharing one path, and arbitrary group-delete
expansion. Do not infer those semantics from the seven tested cases.

The public client keeps `remove_from_playlist()` and `delete_playlist()` fixed
at flag zero. No general catalog/source deletion helper is added. The unsafe
recursive `/file/` directory-batch path remains prohibited. The physical iOS
flag-zero, flag-one and unsupported-group evidence follows.

## Physical iOS track deletion and unsupported group action (2026-09-16)

Owner supplied `2026-09-16-224332.pcap` / `.har` and `IMG_6819.PNG`, then
`IMG_6820.PNG` for the second pass. The first capture has seven HTTP exchanges;
all response-body hashes match HAR, TCP payload reconstruction is contiguous,
and tshark reports no device-stream loss/retransmission/truncation. The owner
confirmed that all supplied iOS checks used FiiO Control **4.6.0**. No 12100
payload/settings reply was captured here, so the firmware version is not freshly
established by this trace. Fixture hashes and frame references are retained in
`controller/tests/fixtures/fiio_control_ios_track_delete.json`; unrelated genre names are
omitted. Local reconstruction: `work/library-captures/delete1-*`.

`IMG_6819` shows selected `Probe B1` inside `DISC Delete Album B`, a
**Confirm to delete?** dialog, unchecked **Also delete source files**, and
Cancel/Delete buttons. The wire mapping is:

```text
DELETE /song_category_tree/
type: style/album/song
style: DISC%20Delete%20Probe
album: DISC%20Delete%20Album%20B
artist: <empty>
delete_source: 0
Content-Type: application/json
Transfer-Encoding: chunked

decoded body: [[0,0]]
```

HAR preserves the chunk envelope `7\r\n[[0,0]]\r\n0\r\n\r\n`; it is not part of
the JSON payload. No general deletion helper is added from this observation.

| Relative seconds / request frame | Observation |
| --- | --- |
| 13.212 / 1117 | Genre album page: A has two tracks; B has one |
| 16.131 / 1126 | Scoped album B page: Probe B1 at position zero |
| 37.745 / 1161 | DELETE above; frame 1165 returns empty 200, `type: delete` |
| 37.800 / 1167 | Fresh scoped album B page: `total-num: 0`, body `[]` |
| 37.857 / 1173 | Fresh genre album page: only A remains, count two |
| 37.857 / 1175 | Root genre readback: test genre count falls from three to two |

The owner skipped the Wi-Fi file inspection and reports no re-upload. The
capture indeed contains no directory/file read, upload or scan. Thus it proves
the selected flag and index removal, not independent physical file survival,
favorite/playlist side effects or reboot persistence. Emulator file-preservation
evidence must not be relabelled as a physical file check. The omitted scenario
step meant **inspect the folder**, not upload anything again.

Second pass: the owner reports Delete on the genre's selected album A group.
`IMG_6820` shows A with two tracks and the toast **This function is not yet
supported**. Its heading's `1 songs in total` counts the one album row here;
it is not evidence that one of A's two tracks disappeared. No packets were
supplied, so request presence/absence is unknown. Classify this group action as
unsupported in the inspected app state. It agrees with the independent firmware
allowlist and existing `style/album` no-op acceptance, but does not establish
the precise UI/firmware rejection path. No repeat of this group capture is needed.

Validation for this capture-only checkpoint: **287 Python / 23 JavaScript tests**,
shell syntax and four shim builds passed. No production helper/runtime changes
or firmware rerun. The new fixture regression covers exact scoped filters,
flag/ranges, chunk-envelope distinction and a valid empty catalog readback.

The subsequent `225423` capture closes track-level flag-one and directory
inspection below. Other deletion edge cases retain the limits above.

## Physical source-file deletion and retained B1 (2026-09-16)

`2026-09-16-225423.pcap` / `.har` contain **11 HTTP exchanges**, with matching
response-body hashes, contiguous TCP payloads and no reported device-stream
loss/retransmission/truncation. The fresh `a501` at frame 1632 identifies DISC
firmware **257**, play mode zero. FiiO Control **4.6.0** is owner-confirmed.
The only HTTP mutation is one category DELETE; Link traffic is initial
handshake/read traffic, with no scan/playback mutation. No upload is captured.
`IMG_6821` is the resulting file browser, not a screenshot of the checkbox.

The exact request at **34.344 seconds / frame 1729** is:

```text
DELETE /song_category_tree/
type: style/album/song
style: DISC%20Delete%20Probe
album: DISC%20Delete%20Album%20A
artist: <empty>
delete_source: 1
Content-Type: application/json
Transfer-Encoding: chunked

decoded body: [[1,1]]
```

The body on the wire/HAR includes `7\r\n[[1,1]]\r\n0\r\n\r\n`. Frame 1733 returns
empty HTTP 200 with `type: delete`. Independent readbacks establish the effect:

| Relative seconds / request frame | Observation |
| --- | --- |
| 19.652 / 1684 | Scoped album A rows are **A2 at position 0, A1 at position 1** |
| 34.389 / 1735 | Track GET at **start-pos 1** returns `[]`, **total-num 1** |
| 34.415 / 1741 | Genre album page still contains A, now with count one |
| 34.416 / 1743 | Test genre count changes from two to one |
| 50.943 / 1782 | Test directory contains exactly `02-Probe-A2.flac` and `03-Probe-B1.flac`; total two, both files |

Directory request: `GET /dir/tmp/sdcard%2FDISC%20Delete%20Probe/`,
`start-pos: 0`, `num-max: 50`. The app encodes an internal slash as `%2F`;
the helper's unescaped slash refers to the same decoded path. Fresh directory
readback and the screenshot agree: **A1's file is absent, A2 and B1 remain**.
B1's presence supplies the file observation missing from the earlier flag-zero
capture. There is no re-upload in either trace; continuity across the uncaptured
gap also relies on the owner's report. This is filename/existence evidence, not
a byte-hash comparison or continuous monitoring of the card.

Two controller rules follow directly from this capture:

- Use current response positions, not filename suffixes or an assumed sort.
  A1 was position **1**, not zero.
- An empty page is not an empty library. After deletion, offset one was already
  past the single remaining item. Preserve `total-num: 1` and refresh from zero;
  do not display the entire album as empty based only on `items: []`.

The track-level iOS deletion investigation is complete for both flags; album-
group Delete remains unsupported in the inspected UI. No repeat capture is
needed for these cases. Favorite/custom-list side effects, reboot persistence,
shared-file/current-track behavior and failure cases remain outside this physical
capture. Their independent emulator evidence/limits are not broadened.

Sanitized fixture: `controller/tests/fixtures/fiio_control_ios_source_delete.json`, containing
input hashes and frame references. It omits the owner's root-card contents,
unrelated genres and full settings. Local reconstruction is ignored under
`work/library-captures/delete2-*`. Two regressions cover positional deletion,
empty-page/nonzero-total handling and the subsequent directory result. No public
source-delete helper or runtime change is introduced. Firmware-free validation
passed **289 Python / 23 JavaScript tests**, shell syntax and four shim builds
(`work/library-captures/delete2-unit.log`). No firmware rerun; the prior 14-case
emulator acceptance remains separate from this capture-only checkpoint.

## Original iPhone scenario (passes now reported above)

Prepared locally under ignored `work/delete-probe/`: `DISC-Delete-Probe.zip`
contains three generated, silent, three-second FLAC files. All have artist and
genre `DISC Delete Probe`; `DISC Delete Album A` contains `Probe A1`/`Probe A2`,
and `DISC Delete Album B` contains `Probe B1`. Tags/duration were checked with
SoX. These are newly generated fixtures, not copies of owner music.

Preparation, outside capture: unpack/upload the folder to the card, run the stock
library update and verify exactly these two albums/three tracks. Leave playback
paused on an unrelated track. Existing owner playlists are not deletion targets.

1. **Track pass, separate PCAP/HAR:** open genre `DISC Delete Probe`, then album
   B. Select only `Probe B1` and press Delete. Screenshot any confirmation and
   options. If a source-file checkbox exists, leave it off, then confirm; if
   there is no such option, record the available wording/default behavior.
   Wait three seconds, reopen the genre/album catalog, then inspect the uploaded
   folder through Wi-Fi transfer. End capture. No rescan during this pass.
2. **Group pass, new PCAP/HAR:** open the same genre's album-group screen. Select
   only album A (two tracks); do not enter its track list. Press Delete and
   screenshot any confirmation/options. If source-file deletion is offered,
   enable it and confirm; otherwise record the exact choice available. Wait
   three seconds, reopen the genre catalog and inspect the uploaded folder
   through Wi-Fi transfer. End capture without a rescan.

All three files are disposable even if Delete acts immediately. If the exact
fixture counts/names differ, correct preparation before deleting. Return both
PCAP/HAR pairs and dialog screenshots, identifying each selected option and
whether a dialog existed. Pass one is now captured except file inspection;
pass two is reported unsupported with a screenshot. No repeat group pass is
requested. The replacement track-level flag-one pass is now captured in `225423`
with directory inspection. Both track-level variants are complete; cleanup of
the remaining disposable files is optional owner work, not another capture gate.
