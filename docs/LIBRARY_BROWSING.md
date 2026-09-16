# Genres, folders and bulk selections (V2.57)

This is stock-firmware emulator evidence, not a captured FiiO Control request
sequence. The physical screenshots show the workflows, but on 2026-09-16 the
owner deferred the requested TCP/HTTP capture because the phone could not connect
to the player (suspected Wi-Fi problem, not diagnosed here). No physical device,
interactive emulator, user media or LAN exposure is involved in these tests.

## Browse and play

| Context | HTTP source | Link type / argument |
| --- | --- | --- |
| Genre tracks | `style/song`, header `style` | `10` (`000A`), raw UTF-8 genre name |
| Albums within a genre | `style/album`, header `style` | Browse/group selection only; drill down before selecting a track |
| Tracks within a genre's album | `style/album/song`, headers `style`, `album` | `8` (`0008`), `{"style":"Genre", "album":"Album"}` |
| Folder entries | `/localdir/tmp/sdcard/.../` | `4` (`0004`), raw absolute directory path |

`0100` carries four hexadecimal digits of zero-based position, then four of
list type, then the argument. `0101` omits the position and starts the list.
Frame length counts UTF-8 bytes, including the eight-byte header. Navigation and
pause still require the stock >1 integer-second interval (tests wait 2.1 seconds).

The genre-scoped album is **not** equivalent to `album/song`: the fixture's
`Shared Album` contains Alpha/Beta in `Genre Ё` and Gamma in `Genre Other`.
Scoped reads, playback and queues contain only Alpha/Beta. Genre playback adds
Delta from another album. Whole-list and last-position selection are checked
over TCP and WS; `playerflag` is respectively 10, 8 or 4.

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

The scoped-album argument is parsed by stock **`sscanf`, not JSON**. Keep key
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
