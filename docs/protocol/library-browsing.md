# Artists, genres, folders and bulk selections (V2.57)

The helpers below have stock V2.57 emulator evidence. A subsequent physical
FiiO Control capture confirms genre browsing and scoped-album selection; its
whole-genre selector is now validated and used by the helper. See
[physical evidence](#physical-genre-flow-2026-09-16).
Later physical captures also confirm folder and ordinary album selection, and
identify type-7 artist/scoped-album playback; see [the new checkpoint](#physical-folder-album-and-artist-flow-2026-09-16).
Emulator tests use disposable generated media, not the interactive guest or user
library. Raw physical captures remain private; no commands are replayed to the device.

## Browse and play

| Context | HTTP source | Link type / argument |
| --- | --- | --- |
| Whole genre, Play all | `style/song`, header `style` | `8` (`0008`), `{"style":"Genre", "album":""}` |
| Indexed genre track | `style/song`, header `style` | `10` (`000A`), raw UTF-8 genre name |
| Albums within a genre | `style/album`, header `style` | Browse/group selection only; drill down before selecting a track |
| Tracks within a genre's album | `style/album/song`, headers `style`, `album` | `8` (`0008`), `{"style":"Genre", "album":"Album"}` |
| Folder entries | `/localdir/tmp/sdcard/.../` | `4` (`0004`), raw absolute directory path |
| Whole artist, Play all | `artist/song`, header `artist` | `7` (`0007`), `{"artist":"Artist", "album":""}` |
| Albums within an artist | `artist/album`, header `artist` | Browse groups; this is not the artist's track list |
| Tracks within an artist's album | `artist/album/song`, headers `artist`, `album` | `7` (`0007`), `{"artist":"Artist", "album":"Album"}` |

Whole-genre Play all matches the captured phone request. Indexed genre selection
retains the separately tested type-10 path; the app capture does not cover it.

`0100` carries four hexadecimal digits of zero-based position, then four of
list type, then the argument. `0101` omits the position and starts the list.
Frame length counts UTF-8 bytes, including the eight-byte header. Navigation and
pause still require the stock >1 integer-second interval (tests wait 2.1 seconds).

The genre-scoped album is **not** equivalent to `album/song`: the fixture's
`Shared Album` contains Alpha/Beta in `Genre Ё` and Gamma in `Genre Other`.
Scoped reads, playback and queues contain only Alpha/Beta. Genre playback adds
Delta from another album. Whole-list and last-position selection are checked
over TCP and WS; `playerflag` matches the chosen type (8, 10 or 4).

Folder positions include subdirectories. For example, `Nested`, `01.flac`,
`02.flac` occupy positions 0, 1, 2. Selecting 2 plays the second audio file;
the resulting queue contains two tracks, with no directory row. Play all starts
at the first non-directory and does **not** recursively include Nested's tracks.
Filenames need not equal ID3 titles. Empty and missing directory replies can
lack `total-num`; they must not become a playable empty list.

### Helpers

```python
# HTTP and TCP/WS clients must address the same device.
client.play_genre('Genre Ё', http=http)  # entire genre
client.play_genre('Genre Ё', 1, album='Shared Album', http=http)
client.play_folder('/tmp/sdcard/Album', http=http)
client.play_folder('/tmp/sdcard/Album', 2, expected_name='02.flac', http=http)
client.play_artist('Artist Ё', http=http)  # entire artist, captured type 7
client.play_artist('Artist Ё', 1, album='Shared Album', http=http)
# The same methods on WSClient are awaited.
```

These helpers require reported V2.57, fresh HTTP bounds and a nonempty source.
Indexed folder selection additionally compares the displayed filename and rejects
directories, CUE/M3U/image rows. Play all checks the first playable row; mixed
special-format folder queues are not validated. Folder paths stay under SD,
fit the stock 512-byte slash-terminated buffer and reject `.m3u` anywhere in the
path (stock uses substring detection). Missing/renamed/out-of-range selections
are rejected before a playback write. Generic `play_index`/`play_all` deliberately
retain their old allowlist; use the guarded context-specific helpers.

The type-8 genre/album argument is parsed by stock **`sscanf`, not JSON**. Keep key
order and colon spacing; do not use a generic serializer that escapes Unicode
or inserts spaces after colons. Names containing quotes/backslashes are rejected
for this context. HTTP name-header length limits also apply. Reserved
`unknown_style` / `unknown_album` token translation and localized unknown labels
remain unvalidated; the helpers do not translate these labels.

Type 7 uses the same strict `sscanf` format, with `artist` before `album`.
`play_artist` rejects quotes/backslashes, reserved `unknown_artist` /
`unknown_album` tokens and explicit empty names. Only whole-artist Play all
internally inserts the empty album. Indexed type-7 selection requires a named
album; indexed whole-artist playback retains existing generic type 2. Existing
type-2 helpers remain unchanged. Artist names are literal: do not split a
semicolon-delimited collaboration into separate artists.

The artist fixture deliberately shares an album name between two artists and
gives the selected artist another album. Scoped type 7 must exclude the other
artist's track; whole-artist type 7 is compared with type 2 for queue order and
restart behavior in modes 0/4. These are generated-media tests, not proof of
unknown-label, failed-media or random-mode behavior.

Preflight is best effort, not an atomic revision check or persistent identity.
Refresh displayed source positions before choosing, serialize edits and selections,
and never replay an uncertain mutation after reconnecting.

## Bulk addition

`POST /add_custom_list/` uses inclusive ranges of positions in the exact source
category and filters, plus `dst_list_id` as a **playlist position**, not SQLite ID.
The following are tested through direct and proxied HTTP:

- `album/song`: disjoint first/third track rows from a named album, matching the
  physical app request documented below.
- `style/album`: one or multiple selected album rows expand to their tracks,
  preserving the genre restriction even when the album name exists elsewhere.
- `style/album/song`: selected tracks stay restricted by both genre and album.
- `style/song`: disjoint ranges select only those genre tracks.
- `style`: selected genre rows expand into all their tracks.

`HTTPClient.add_selection_to_playlist(position, ranges, expected_name=...,
category=..., **filters)` adds current destination-name checks before and after
source range-bound checks. It rejects missing/extraneous filters, unsupported
sources, empty/out-of-range rows and renamed/shifted destinations before writing.
Its reviewed source allowlist is all songs, genres/genre songs/genre albums/scoped
songs and albums/album songs. Generic album expansion is not part of this focused
genre acceptance. `add_to_playlist` remains the lower-level request helper.
Always read resulting membership: HTTP 200 alone is not success, and stock
ordering is not necessarily selection/insertion order. No automatic retry.

Folder ranges are **not** a category source in this HTTP add handler. Do not
pass directory positions as `all/song` positions. The owner now confirms that
sdcard browsing offers no batch actions, so there is no folder-to-playlist app
workflow to capture in the inspected UI. Any future folder expansion would be
a separate controller feature, not reproduction of an observed app action.

### Physical album-track addition (2026-09-16)

Input: `2026-09-16-215831.pcap` / `.har`. The owner identifies the already
created destination as `test2`. Source names and playlist names are replaced in
[the fixture](../../controller/tests/fixtures/fiio_control_ios_album_batch_add.json); full
catalogs, artwork and raw captures remain outside Git. Fresh Link settings report
DISC 257 / play mode 0; app 4.6.0 is retrospectively owner-confirmed.

PCAP and HAR contain the same eight HTTP exchanges: seven GETs and one POST.
All response-body hash multisets agree. Device TCP payloads on 12100/12103 are
contiguous with no reported retransmission, loss or truncation. The Link stream
contains initial handshake/settings/current-track queries, no playlist command
or playback mutation; the addition occurs entirely over stock HTTP.

| Request frame / seconds | Operation | Evidence |
| --- | --- | --- |
| 1167 / 11.949 | GET `album/song`, named album | 15 source rows; first and third are positions 0 and 2 |
| 1184 / 28.975 | GET `custom` | Two existing playlists, both empty; destination at position 1 |
| 1190 / 32.006 | POST `/add_custom_list/` | `type: album/song`, percent-encoded `album`, `dst_list_id: 1`, decoded body `[[0,0],[2,2]]` |
| 1194 / 32.117 | POST response | HTTP 200, `type: add`, empty body |
| 1210 / 43.667 | GET `custom` | Destination count now 2; other list remains at 0 |
| 1219 / 45.102 | GET `custom/song`, `src_list_id: 1` | Exactly the chosen first/third source titles, now at destination positions 0/1 |

This is one batch request with two inclusive singleton ranges, not two writes
or catalog song IDs. It agrees with `add_selection_to_playlist(1, [[0, 0], [2, 2]],
expected_name=..., category='album/song', album=...)`. The helper additionally
checks current destination name and source bounds; the app's observed request
does not establish those safeguards. Position 1 comes from the fresh custom-list
response, not from parsing a number in the playlist name. The trace does not
contain SQLite IDs and does not independently prove their relationship.

The app uses `Transfer-Encoding: chunked`. HAR retains the chunk envelope:
`D\r\n[[0,0],[2,2]]\r\n0\r\n\r\n`; `D` is hexadecimal 13, the JSON byte
count. PCAP confirms the same bytes and complete terminating chunk. Remove
HTTP chunk framing before JSON parsing. Our client sends the same JSON with
Content-Length and omits empty artist/style headers; reproducing chunked transfer
is not required. No new production client behavior is needed.

Success is established by the subsequent list count and track readback, not
the empty 200 alone. There is **one** post-add `custom/song` GET in the capture;
a second reopening, app restart/reboot persistence and duplicate-add semantics
are not established. No playlist creation, deletion, source removal or grouped
album expansion was captured in `215831`. The later `221421` recording below
adds genre-album groups and rename evidence; Delete scope remains separate.

Validation: added the captured `album/song` first/third-row case to disposable
V2.57 `library` acceptance. Fresh direct and proxied HTTP runs return exactly
the two expected generated tracks, preserving source hashes and restoring the
baseline. Firmware-free checks pass **284 Python / 23 JavaScript tests**, shell
syntax and four shim builds. No production client/runtime change, full or idle
rerun, physical command replay or interactive guest modification.

### Physical genre-album groups and playlist rename (2026-09-16)

Input: `2026-09-16-221421.pcap` / `.har`, physical iPhone FiiO Control. Fresh
Link settings report DISC 257 / play mode 0; app 4.6.0 is retrospectively owner-confirmed.
The owner also reports renaming the playlist at the end. Fourteen HTTP exchanges
match between PCAP and HAR, including all response-body hashes and the chunked
add body. Device TCP directions are contiguous; no reported retransmission,
loss or truncation on 12100/12103. Link contains startup queries only; all three
mutations are HTTP. Sanitized [fixture](../../controller/tests/fixtures/fiio_control_ios_group_add_rename.json)
keeps source group counts and playlist readbacks, not personal track contents.

| Request frame / seconds | Operation | Observable result |
| --- | --- | --- |
| 1284 / 15.569 | POST `/custom_list_cmd/`, `type: create`, `list_name: alt1`, empty body | GET at 1288 lists new empty playlist at position 2 |
| 1350 / 30.989 | GET `style/album`, named genre | Six album groups with counts 16, 18, 89, 20, 16, 18 |
| 1363 / 41.375 | POST `/add_custom_list/`, `type: style/album`, genre header, `dst_list_id: 2`, body `[[0,0],[2,2]]` | One request selects the first and third **album rows**, not track rows |
| 1384 / 47.284 | GET `custom` | New list count 105 = 16 + 89; existing lists retain counts 0 and 2 |
| 1432 / 59.053 | POST `/custom_list_cmd/`, `type: update`, `list_id: 2`, `list_name: alt2`, empty body | Rename addresses the current playlist position |
| 1436 / 59.097 | GET `custom` | Position 2 is now `alt2`, still count 105; other lists unchanged |
| 1519 / 64.056 | GET `custom/song`, `src_list_id: 2`, `start-pos: 0`, `num-max: 100` | Header total 105; body contains positions 0–99 only |

The app performs no per-album track GETs and no series of per-track add requests.
It delegates group expansion to stock `/add_custom_list/`, preserving the genre
filter with empty artist/album headers. This matches the existing guarded helper
for `category='style/album', style=...`; source bounds refer to the six groups.
Create and rename match `create_playlist` / `rename_playlist` without a JSON body.
The HTTP `list_id`/`dst_list_id` values agree with observed list positions, not
IDs derived from names. SQLite identities are not present in the trace.

Each POST returns empty 200 with a matching `type` header; later GETs establish
creation, added count and renamed name. The capture verifies **105 total and
only the first 100 returned tracks**. There is no request at offset 100, no
pre-rename membership read and no individual source-album track read. Therefore
it cannot prove every one of the 105 identities or byte-identical membership
across rename; it proves unchanged count and accessible membership after rename.
Displayed rows mix tracks from the selected albums, so do not promise contiguous
album blocks or insertion order. Reboot persistence and duplicate handling are
not tested here. No DELETE occurs.

No production helper change is required. The existing disposable `library`
scenario already covers genre-scoped album expansion and exclusion of tracks
with the same album name in another genre; playlist rename has separate prior
acceptance. This capture adds physical evidence for disjoint group ranges and
rename plus regression fixtures. No repeat of this group-add capture is needed;
the remaining batch question is Delete confirmation and source/index scope.

Validation: **286 Python / 23 JavaScript tests**, shell syntax and four shim
builds passed. The new fixture checks create, guarded group-add and rename
request compatibility, fresh name/count readback and the 105-versus-100 page
limit. No production code or integration fixture changed in this checkpoint;
the preceding fresh V2.57 `library` acceptance remains applicable. No firmware
rerun, physical replay or interactive guest modification.

## Deletion is a different contract

The stock DELETE category allowlist includes only `all/song`, `artist/song`,
`artist/album/song`, `album/song`, `style/song`, `style/album/song`, `love/song`,
`curlist/song`, `custom/song` and `custom`. It does not accept `style/album`,
`style`, `album` or `artist` group rows. Thus the visible Delete toolbar on the
phone's album-group screen does not establish a one-request group delete API.
The client does **not** expose arbitrary catalog/source deletion or emulate it
by blindly expanding names into a series of destructive requests.

The disposable probe sends `style/album` with `delete_source: 0`: stock returns
empty HTTP 200 and leaves the catalog unchanged. A subsequent
`style/album/song` request for Alpha/Beta with `delete_source: 0` removes their
index entries while preserving the source files and Gamma from the other genre.
A stock rescan restores the entries. File hashes are checked after all tests.
This originally established emulator index removal. Physical `224332` now pairs
the unchecked app checkbox with flag zero and fresh index readback; it does not
include a source-file inspection. `IMG_6820` reports group Delete unsupported.
The dedicated `library-delete` scenario now exercises seven index/list/source
cases, including favorite/custom-list side effects and stale references after
source deletion. See [the deletion contract](library-delete.md). Source deletion
is still not exposed by the client. Current-track deletion, CUE/shared-file
identity and physical app confirmations remain unvalidated.
The existing unsafe recursive `/file/` directory-batch path remains prohibited.

## Physical genre flow (2026-09-16)

Owner-provided `2026-09-16-185016.pcap` and `.har`, physical DISC; fresh `a501`
reports firmware **257** and play mode **0**. App 4.6.0 is retrospectively owner-confirmed, not present in the wire metadata.
Source hashes, packet references and sanitized requests are preserved in
[the fixture](../../controller/tests/fixtures/fiio_control_ios_genres.json). Names in the fixture
are replacements, not the user's catalog. No artwork, IPs or full settings are committed.

The HAR contains only **3** device HTTP exchanges; the PCAP contains **13**.
Later browsing and control must be reconstructed from PCAP, not inferred absent
from HAR. TCP stream 118 carries all control; payload sequence numbers are
contiguous in each direction, including coalesced Link frames. Relevant TCP
traffic has no reported retransmissions, lost segments or truncated packets.

| PCAP time / frame | Observed action | Contract / result |
| --- | --- | --- |
| 17.990 / 7102 | List genres | HTTP `type: style`, empty artist/album/style, 17 rows |
| 19.998 / 7709 | Open first genre | `style/album`, percent-encoded genre header; one album, 17 tracks |
| 23.220 / 8078 | Whole genre | `0101`, type `0008`, `{"style":"…", "album":""}` |
| 37.784 / 8376 | Open another genre | `style/album`, four albums with counts 18 + 16 + 1 + 19 = 54 |
| 39.541 / 8483 | Whole genre | Same empty-album type-8 selector; reply uses `playerflag=8`, queue `7/54`, then playing state and advancing progress |
| 66.055 / 9807; 73.974 / 10043 | Open its album | `style/album/song`, both name headers; 19 rows at positions 0–18 |
| 76.349 / 10105 | Select position 15 | `0100` + `000f0008` + both names; selected row matches snapshot, queue `16/19` |
| 79.567 / 10268; 81.683 / 10404 | Next twice | `0201/0001`, queues `17/19`, `18/19` |
| 84.400 / 10636 | Toggle to pause | `0201/0000`, followed by state 1 |
| 87.402 / 10812 | Whole scoped album | `0101` + type 8 + both names; queue `1/19`, then playing/progress |
| 91.519 / 11257 | Toggle to pause | `0201/0000`, followed by state 1 |

Scoped-album payload syntax matches `genre_command(..., album=...)`, including
the space before `"album"`. Lowercase hexadecimal `000f` from the app and our
uppercase `000F` encode the same position. HTTP uses percent-encoded headers;
Link names are raw UTF-8. The app sends unused name headers as empty and requests
100 rows; our client omits unused headers and defaults to 200 rows. Fixture tests
compare the meaningful filters with an explicit 100-row request, not identical
default HTTP bytes. The initial capture-only checkpoint passed 274 Python / 23
JavaScript tests, shell syntax and four shim builds without changing runtime code.
The helper change and focused firmware acceptance followed as described below.

**Whole-genre follow-up:** `play_genre(genre)` now sends the captured type 8 with
an empty album. Fresh disposable V2.57 `library` acceptance compares this with
type 10 over TCP/WS in modes 0 and 4: identical three-track queue/order, no
cross-genre leak, and restart at the first track after selecting the last one.
This is generated playable-FLAC evidence, not a guarantee for failed/CUE tracks
or random-mode start positions. The physical `7/54` remains an observation,
not evidence of random mode or a promised start position.

Do not generalize the empty-album form to indexed `0100`: an exploratory probe
did not reach the expected playing snapshot (last state was paused), and stock
`429008` takes a different path from Play all `429500`. Indexed whole-genre
selection therefore retains validated type 10; named scoped albums retain type 8.
Explicit empty/unknown names are still rejected. Only the internal Play-all
encoding introduces the empty album; quotes/backslashes are rejected for type 8.

**CUE caveat:** after the first genre selection, six full loading snapshots show
`is_cue=true`, zero duration and positions `1/17` through `6/17`, all referencing
one source path with different track numbers. Each is followed by `a60a/000D`.
No playing-state/progress event occurs in that interval. This is not successful
playback or natural EOF evidence; the exact status meaning and cause are not
diagnosed by this capture. The second genre does reach playing state/progress.

Only `/localdir/tmp/` browsing is present: no type-4 folder selection, folder
track browsing, bulk POST/DELETE or root-category Play all is captured. Those
remain separate gaps. No pause command appears between the second whole-genre
selection and the later album-track selection; the requested action script is
not a substitute for the observed timeline.

Read-only reproduction (inspect locally; output may contain private metadata):

```sh
tshark -r /path/to/capture.pcap -Y 'tcp.port == 12100 && tcp.len > 0' \
  -T fields -e frame.number -e frame.time_relative -e tcp.stream \
  -e tcp.srcport -e tcp.seq -e tcp.payload
tshark -r /path/to/capture.pcap -Y 'tcp.port == 12103 && http.request' \
  -T fields -e frame.number -e tcp.stream -e http.request.uri -e http.request.line
tshark -r /path/to/capture.pcap -q -z follow,tcp,raw,225
```

Stream 225 contains the first scoped-track HTTP response; 231 is the repeated
read. Decode Link by the eight-byte ASCII-hex header's total byte length, not
TCP packet boundaries. Reassemble each HTTP direction and honor transfer/content
encoding before comparing category totals, positions and selected-row identity.

## Physical folder, album and artist flow (2026-09-16)

Owner supplied `2026-09-16-211747.pcap` / `.har` and
`2026-09-16-212141.pcap` / `.har`. The first session visits folders, a named
album, then an artist's albums and a scoped album. The second presses Play all
**inside a selected artist**, not on the root Artists page. Both handshakes and
fresh `a501` replies report firmware 257 and play mode 0; app 4.6.0 is retrospectively owner-confirmed. Source hashes, packet references and anonymized requests are
in [the fixture](../../controller/tests/fixtures/fiio_control_ios_folders_artists.json).

PCAP and HAR contain the same 16 and 5 HTTP exchanges respectively; all response
body hash multisets agree, including artwork (not committed). TCP directions on
12100/12103 have contiguous payload sequences; no loss, retransmission or
capture truncation is reported for those ports. HTTP parsing accounts for
multiple exchanges on a persistent connection and verifies Content-Length.
Link decoding handles coalesced frames independently of packet boundaries.

| Session / request frame | Action | Observed command and response |
| --- | --- | --- |
| 1 / 1054 → 1068 | Folder listing → second audio track | HTTP has 17 rows: directory at 0, audio at 1–16. `0100` + `00020004` + path selects the second audio track; `playerflag=4`, `playing_num=2/16` |
| 1 / 1159 | Same folder Play all | `0101` + `0004` + path; first audio track, `1/16` |
| 1 / 1233 → 1244 → 1250 | Albums → named album → second track | HTTP `album` then `album/song`; `0100` + `00010003` + album name, `playerflag=3`, `2/15` |
| 1 / 1356 | Named album Play all | `0101` + `0003` + album name, `1/15` |
| 1 / 1476 → 1487 → 1496 → 1502 | Artists → artist's albums → album tracks → second track | HTTP `artist`, `artist/album`, `artist/album/song`; `0100` + `00010007` + `{"artist":"…", "album":"…"}`, `playerflag=7`, `2/17` |
| 1 / 1593 | Artist-scoped album Play all | `0101` + type 7 + both names, `1/17` |
| 2 / 1048 → 1073 → 1079 | Artists → one artist → Play all | HTTP `artist`, `artist/album`; `0101` + `0007{"artist":"…", "album":""}`, `playerflag=7`, `1/13` |

Each of the seven selections is followed by a full loading snapshot (state 2),
state-0 deltas and nonzero `a103` progress. Six have multiple increasing progress
samples; the scoped-album Play all at frame 1593 has only one (1000 ms) before
pause, so no multi-sample progression is claimed for that selection. Each subsequent `0201/0000`
toggle yields paused state 1. The track names/paths in loading snapshots match
the browsed row for indexed folder/album/scoped-album selection. `playing_num`
is observed here; no HTTP `curlist/song` read was captured, so these traces alone
do not verify every queued track or the contents of nested directories.

Folder Link paths are raw UTF-8 without a trailing slash. The app HTTP URI
percent-encodes slashes below `/tmp/`; our helper preserves slash separators.
Compare decoded paths, not identical URI bytes. The folder's first directory
explains why the second audio track uses index 2 rather than 1; this agrees with
the existing helper and does not require an index correction.

The artist album has the same displayed name as its artist in session 1. That
does not make type 7 equivalent to type 3: the command carries two independent
filters. Session 2's artist has only one album, so physical cross-album scope
remains unproven by that trace; the overlapping emulator fixture covers it.

No root-category Play all, playlist addition or DELETE was captured. Do not mark
those gaps complete or request a repeat of these now-confirmed selectors.

Validation: fresh disposable V2.57 `library` acceptance passed on TCP and WS,
including type-7 scoped/whole-artist selections in modes 0/4, overlapping names,
two albums for one artist, comparison against type 2, rejected missing/stale
sources and unchanged source-file hashes. The suite restores its three-track
baseline and removes its temporary containers/volume. Firmware-free acceptance
passed **281 Python / 23 JavaScript tests**, shell syntax and four shim builds.
No shared runtime/Compose changes: full and idle/USB scenarios were not rerun.
Physical DISC and interactive guests were not changed by this analysis/testing.

## Root-tab Play all produces no playback request (2026-09-16)

Input: `2026-09-16-213631.pcap` / `.har`; owner reports that root-tab Play all
taps had no visible effect and the last action was inside a selected genre.
Fresh handshake/settings identify DISC 257, play mode 0 and initially paused
playback. App 4.6.0 is retrospectively owner-confirmed. The [sanitized fixture](../../controller/tests/fixtures/fiio_control_ios_root_play_all.json)
retains every outgoing Link frame, relevant HTTP filters and later genre events.
Tap times themselves are not present in PCAP; their attribution uses the owner's
report, while navigation and the absence of commands are packet evidence.

All eight device HTTP exchanges are GETs; their response-body hash multisets
match HAR. Both device TCP services have contiguous captured payload sequences,
no reported retransmissions/lost segments/truncation, and complete HTTP bodies
according to Content-Length. Link contains the opening handshake and queries,
then **no `0100`, `0101` or `0201` before the named-genre action**.

| Frame / relative seconds | Observed action | Result |
| --- | --- | --- |
| 1125 / 6.434 | GET `all/song` | 791 total, first 100 returned |
| 1153 / 18.551 | GET `artist` | 38 artist rows |
| 1170 / 22.168 | GET `album` | 53 album rows |
| 1187 / 24.635 | GET `style` | 15 genre rows |
| 1196 / 26.771 | GET `style/album`, named genre | 6 album rows |
| 1202 / 28.212 | `0101`, `0008{"style":"…", "album":""}` | `playerflag=8`, `playing_num=1/177` |
| 1204–1296 / 28.490–30.438 | Player events | Full loading state 2, transient state 1, then two playing-state 0 deltas |
| 1298 / 31.360 | `a103/000003E8` | 1000 ms; only one progress sample before pause |
| 1300 / 31.812 | `0201/0000` | Two paused-state 1 replies |

The trace supports a **no-op before device-command dispatch in this app state**,
not a firmware rejection of root Play all. It cannot establish the exact UI
cause (disabled handler, state guard or app defect), nor that all versions/states
behave this way. The same live connection successfully dispatches named-genre
playback. TCP resets at 47.270/47.280 seconds occur after playback and pause;
they do not explain earlier root taps producing no request.

Root ordering and a root-category wire selector remain unestablished. Do not
invent empty artist/album selectors, treat this as a network permission failure,
or copy an app no-op into the client. Existing all-song type-1 playback remains
independently tested; any frontend choice to use it across grouped root screens
would be a product decision, not observed FiiO Control behavior. No repeat trace
of these same taps is needed unless app state/version or visible behavior changes.

## Next app capture: folders and root Play all

Requested after synchronizing the research branch to `28c5008`. Status:
**folder and named/scoped playback captured**. The later root-tab capture is
analyzed above: reported taps send no playback command, while named-genre Play
all works. Root-selector semantics are unknown; repeated identical taps are not
the next task. Continue with the separate batch-menu questions below.
The original Pass A below is retained for provenance, **not a repeat request**.
The owner has now confirmed Play all on all four root tabs specifically in
FiiO Control on iPhone. The requested root capture is complete; its observed
navigation order is All songs → Artists → Albums → Genres, then one named genre.
Record the app/firmware versions and capture both TCP 12100 and HTTP 12103.
PCAP is necessary; HAR is useful as an additional decoded HTTP view but has
previously omitted exchanges. Do not change the capture setup that already works.

### Pass A: playback only (original request, captures analyzed)

1. Open Local playback → Folders → sdcard → a folder containing at least two
   ordinary FLAC/MP3 tracks. Prefer one with a subfolder too, if already available;
   do not reorganize the library for this test.
2. Tap the second audio track, wait at least three seconds, then pause. Record
   whether directory rows precede it: second audio track need not mean position 1.
3. In the same folder tap Play all, wait at least three seconds, then pause.
4. Return to the root Albums page (not a named album), tap Play all if offered,
   wait at least three seconds, then pause. Repeat on the root Artists page.
   If absent/disabled, record that instead of entering a named group as a substitute.
5. End capture. If any confirmation appears, cancel and record its text. No
   add/delete/reset action is part of this pass.

Analyze the resulting trace against these independent questions:

| Action | Evidence to extract | Existing comparison, not a predicted app request |
| --- | --- | --- |
| Folder track | `/localdir/` response order/flags, exact Link payload, selected metadata and queue | `0100`, type 4, absolute path; index includes directory rows |
| Folder Play all | Exact request, first playable snapshot and queue membership | `0101`, type 4; ordinary folder playback is nonrecursive |
| Root Albums / Artists Play all | Root navigation GET, selector type/name/index, following queue/readback | Named album/artist helpers do not establish root-page semantics; do not guess empty names or all-song fallback |

Reassemble TCP before decoding frames; compare observed requests with the action
order rather than assuming every tap sent a command. Record loading/failure
events separately from successful playback. Preserve only sanitized requests and
response assertions as regression fixtures. A helper change, if needed, requires
focused disposable V2.57 acceptance; do not replay a capture on physical DISC.

### Pass B: album-track batch addition (corrected after IMG_6818)

**Captured and analyzed in `215831`**, see [physical addition](#physical-album-track-addition-2026-09-16).
The original sequence below is retained for provenance, not a repeat request.
The existing test playlist was empty at capture start; only one membership GET
after addition is observed.

The owner corrects the proposed folder scenario: batch actions appear on the
same detail screens where Play all works, **except sdcard browsing**. The
single-track player exposes favorite on/off, not Add to Playlist. `IMG_6818.PNG`
shows an album's track list in selection mode with Add to Playlist and Delete.
This is UI evidence plus owner report, not a captured batch request or proof
that the outlined checkmarks denote selected rows.

Original corrected capture sequence (TCP 12100 and HTTP 12103; HAR optional):

1. Create a new empty custom list with a unique test name (reuse a just-created
   test list only if it is still empty).
2. Navigate Albums → one named album → its track list, as on IMG_6818. Use the
   ordinary Albums route so the source context is unambiguous.
3. Enter selection mode and select only the first and third displayed tracks.
4. Add them to the new test list. Open that list, then leave and reopen it to
   obtain fresh membership readback. Record selected positions and resulting count.
5. Stop capture; leave the test list intact. Do not press Delete in this pass.

Extract the actual source category/filters, inclusive selection ranges,
destination position and fresh resulting membership. Compare with existing
`album/song` bulk-add helpers; do not presume whether the app emits one batch
request or multiple writes. The earlier folder scenario is withdrawn; no
folder or single-track-player Add capture is requested.

Delete remains a separate UI/scope question. Only inspect a confirmation when
its existence is established; a menu labelled Delete might act immediately.
Do not press an unknown destructive action merely to discover its dialog.
Actual deletion semantics belong on generated disposable emulator files, after
the command and scope are identified. No physical deletion is requested here.

## Static evidence and reproduction

All addresses below are from the full-fingerprint-verified V2.57 `mq_player`:

- `429008` indexed selection; `429500` play all.
  Their type-7 cases parse `artist` then `album` with `sscanf` and dispatch
  `450d48`; both were rechecked for this capture. Empty album is exposed only
  for whole-artist Play all, not an indexed type-7 whole-artist selector.
- `428778` genre control; `42890c` folder control, directory sort and index mapping.
- `4927f8` local-directory GET, using the same stock scan/sort helpers.
- `4936b8` category GET; `493ee4` bulk add → `41aff8` category expansion.
- `49484c` category DELETE; allowlist at `6cda34`, add mapping at `6cdc00`.

Use [the Ghidra workflow](../../research/ghidra/README.md), `DecAt.java` at these entries,
and `research/diagnostics/inspect_http_routes.py --version 2.57` against the extracted binary.
Keep binaries, projects, decompilation and raw logs in ignored `work/`.
This host's cached scripts were compiled with Java 26; Java 21 rejected them.
Using the matching Java 26 runtime resolved that local analysis issue.

```sh
docker run --rm --network none -v "$PWD:/repo:ro" snowsky-disc-qemu-ci bash /repo/ci/test.sh
CI_SCENARIO=library FW_VERSION=2.57 bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The scenario generates five FLACs with overlapping tags and nested/empty folders
alongside the three ordinary CI tracks. It scans through stock Link, validates
reads/pagination, selections/queues, rejected selectors, bulk memberships and
index-only deletion/recovery. All generated files are hash-checked; added files
are removed and a final scan restores the three-track fixture. Cleanup destroys
only the random disposable stack. No new dependencies, firmware patches,
Dockerfile/Compose changes or ad-hoc runtime edits are needed.

Validation on 2026-09-16: fresh focused `library` passed on V2.57 through both
transports; firmware-free suite passed 271 Python and 23 JavaScript tests, shell
syntax checks and four shim builds. Full and long idle/USB scenarios were not
rerun for these client/research changes. No viewer UI changed, so no new visual
acceptance screenshots are claimed.
