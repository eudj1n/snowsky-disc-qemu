# Genres, folders and bulk selections (V2.57)

The helpers below have stock V2.57 emulator evidence. A subsequent physical
FiiO Control capture confirms genre browsing and scoped-album selection; its
whole-genre selector is now validated and used by the helper. See
[physical evidence](#physical-genre-flow-2026-09-16).
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
# The same methods on WSClient are awaited.
```

Both helpers require reported V2.57, fresh HTTP bounds and a nonempty source.
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

Preflight is best effort, not an atomic revision check or persistent identity.
Refresh displayed source positions before choosing, serialize edits and selections,
and never replay an uncertain mutation after reconnecting.

## Bulk addition

`POST /add_custom_list/` uses inclusive ranges of positions in the exact source
category and filters, plus `dst_list_id` as a **playlist position**, not SQLite ID.
The following are tested through direct and proxied HTTP:

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
pass directory positions as `all/song` positions. Folder-to-playlist expansion
and its FiiO Control wire workflow remain separate follow-up work.

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
This establishes index removal, not what the app's Delete confirmation selects.
The `delete_source: 1` branch contains `unlink`; it is not exposed or exercised
here. Deletion of a currently playing item, favorite/custom-list side effects,
CUE/shared-file identity and physical app confirmations remain unvalidated.
The existing unsafe recursive `/file/` directory-batch path remains prohibited.

## Physical genre flow (2026-09-16)

Owner-provided `2026-09-16-185016.pcap` and `.har`, physical DISC; fresh `a501`
reports firmware **257** and play mode **0**. The app version is not present.
Source hashes, packet references and sanitized requests are preserved in
[the fixture](../tools/fixtures/fiio_control_ios_genres.json). Names in the fixture
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

## Static evidence and reproduction

All addresses below are from the full-fingerprint-verified V2.57 `mq_player`:

- `429008` indexed selection; `429500` play all.
- `428778` genre control; `42890c` folder control, directory sort and index mapping.
- `4927f8` local-directory GET, using the same stock scan/sort helpers.
- `4936b8` category GET; `493ee4` bulk add → `41aff8` category expansion.
- `49484c` category DELETE; allowlist at `6cda34`, add mapping at `6cdc00`.

Use [the Ghidra workflow](../ghidra/README.md), `DecAt.java` at these entries,
and `tools/inspect_http_routes.py --version 2.57` against the extracted binary.
Keep binaries, projects, decompilation and raw logs in ignored `work/`.
This host's cached scripts were compiled with Java 26; Java 21 rejected them.
Using the matching Java 26 runtime resolved that local analysis issue.

```sh
docker run --rm --network none -v "$PWD:/repo:ro" diskos-qemu-ci bash /repo/ci/test.sh
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
