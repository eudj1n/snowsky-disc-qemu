# CUE and DSD metadata/identity (DISC V2.57)

This checkpoint tests stock indexing and protocol selection, not native DSD/DoP
output or audible fidelity. Fixtures are generated locally: one 12-second WAV
with a two-track UTF-8 CUE sheet, an eight-second stereo DSD64 DSF with ID3v2.3
tags, and an uncompressed DSDIFF/DFF with a title. No downloaded music is needed.
SACD ISO is a separate source; it is not equivalent to DSF/DFF. The owner-approved
stereo-image investigation resumed on 2026-09-17; see [SACD evidence and limits](../../research/docs/reports/sacd.md)
and [issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8).

## Observed formats

| Source | Indexed entries | Now-playing metadata |
| --- | --- | --- |
| WAV + external CUE | Two CUE titles replace the unsplit WAV in the song catalog | Same WAV path, `is_cue: true`, separate titles, 6000 ms each, 44100 Hz / 16 bit / stereo |
| DSF | ID3 title, artist, album and track 7 | `is_dsd: true`, 2822400 Hz / 1 bit / stereo, 8000 ms; Unicode title preserved |
| DFF | DITI title; missing artist/album use stock fallbacks | `is_dsd: true`, 2822400 Hz / 1 bit / stereo, 8000 ms |

Both DSD files have `is_sacd: false`. A DSD flag describes the source, not the
DAC output format. Selection, state 0 and successful pause are tested; bit-exact
decoding, native DSD/DoP, DSD128+, DST and hardware output are not established.

The stock HTTP directory page in this fixture lists `Image.wav`, `Pattern.dsf`
and `Pattern.dff`, but omits the sidecar `Image.cue`. The database/library catalog
does expand that CUE. Directory browsing is not an equivalent view of indexed
logical tracks; do not infer CUE absence from that directory result alone.

## CUE identity: three important traps

1. **Path plus `song_track` is insufficient.** Both CUE entries report the same
   `song_file_path` and `song_track: 0` in `0202/a202`. Read-only `SONG` rows do
   distinguish them: `IS_CUE=1`, `TRACK=1/2`, offsets 0/6000 ms and durations
   6000/6000 ms. The wire track field is not the CUE selector in this case.
2. **Queue IDs can collide with ordinary tracks.** On the fresh generated stack,
   DFF has catalog ID 6; the first CUE entry has catalog ID 7 but reports ID 6 in
   the current queue and now-playing. Both queue rows remain present with
   `songId=6` / `flag=6`. Selecting DFF gives `pos_id=2`, `playing_num=2/7`, yet
   HTTP `curlist/song` reports `mark=5`, the first CUE row. Do not deduplicate by
   ID or trust this mark as authoritative in a mixed CUE queue.
3. **Favorites omit CUE identity fields.** Adding both CUE tracks creates two
   distinct `MY_LOVE` rows, with the shared path, `IS_CUE=1`, `TRACK=1/2`.
   But `0415` reports `songPath: ""`, `isCue: false`, `track: 0` for both. Titles
   remain distinct, and the tested IDs use the favorites namespace (800000001/2
   on the fresh fixture). Those numbers are observations, not stable identifiers.

For a future controller, keep a list snapshot and its ordered rows; key displayed
rows by **snapshot + position**, not by path or the returned ID. Send current
positions only after a fresh source/bounds check, and verify matching metadata
and one-based `pos_id` when available. Invalidate pending selections when the
queue/source changes. No stock atomic list revision or persistent track key has
been established; don't create one by concatenating fields that are missing or
ambiguous. Existing helpers keep all rows and use positions without rewriting IDs.

This is a limitation of the stock responses, not a reason to patch live SQLite
or infer CUE numbering from a title. The usual navigation delay and no-replay
rules still apply. See [remote control](remote-control.md) and [playlists](playlists.md).

## Static evidence

Addresses below are for the fingerprinted V2.57 `mq_player` only:

- `476e98` opens/parses a CUE sheet. `443160` (`add_cue_song`) inserts the
  expanded records, including path, CUE track, offset and duration. In the tested
  rows `IS_M3U` is NULL; this insertion path does not bind that field.
- `450d48`, source 1, calls `4388a0` to construct `LIST_SONG_0` from `SONG`.
  Its ordering puts ordinary tracks before CUE/ISO entries; the current queue
  owns its own row IDs rather than reusing all catalog IDs.
- `44538c` looks up an original `SONG.ID` using equality on path, `IS_CUE`,
  `IS_ISO`, `IS_M3U` and `TRACK`, binding the flags as integers. A NULL `IS_M3U`
  cannot match that equality. `421c78` (now-playing packing) falls back to the
  current source row ID when this lookup returns 0. Together with the observed
  NULL CUE rows, this explains why now-playing can mix catalog and queue IDs.
  The HTTP mark mismatch is independently observed; its complete implementation
  is not established by this lookup analysis alone.
- `421c78` also obtains decoder metadata for the audio file and overlays CUE
  information such as title/duration. The CUE file's track ordinal should not be
  inferred from the resulting `song_track` field.
- `469a00` scans directories and handles CUE expansion; `4d90cc` serializes the
  HTTP directory flags. These are distinct from the indexed song catalog.
- `44badc` has an SACD-specific branch calling `61c82c(path, track, open_mode, 0)`
  and a separate `AudioCodecOpen` path for other sources, including DSD files.
  That branch alone establishes a research entry point; the subsequent approved
  stereo ISO acceptance and its limits are documented separately in [SACD.md](../../research/docs/reports/sacd.md).

Reproduce with `research/ghidra/DecAt.java` and `RefsTo.java`; keep binaries/projects/raw
decompilation ignored. No firmware binary, database or shim patch is involved.

## Fixtures and reproduction

```sh
CI_SCENARIO=formats FW_VERSION=2.57 CI_LOGS="$PWD/work/formats-check" \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

`tests/fixtures/formats_fixture.py` writes deterministic original test patterns. DSF has
4096-byte per-channel blocks with zero-padded tails, an exact sample count and
an ID3 metadata offset; DFF uses big-endian sized chunks and stereo DSD data.
Layout references are the primary [FFmpeg DSF reader](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/dsfdec.c)
and [FFmpeg DSDIFF reader](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/iff.c).
The generator is independent code, not a copied demuxer. A host FFprobe check
independently recognized both formats, tags and approximately eight-second
durations (DSF's padded blocks can yield 8.011071 s there; stock reports 8000 ms).
FFprobe is an optional inspection tool, not a new emulator/CI dependency:

```sh
# The parent must exist; the generator refuses to overwrite its fixture folder.
python3 -B -m tests.fixtures.formats_fixture /path/to/ignored/test-parent
ffprobe -v error -show_format -show_streams '/path/to/ignored/test-parent/Formats CI Ё/Pattern.dsf'
```

Acceptance requires the disposable V2.57 stack and byte-exact original generated
SD files, scans through the stock network command, and compares TCP/HTTP catalogs,
read-only database rows and fresh selected metadata. It exercises both TCP/WS,
current-queue positions and two separate CUE favorites, then removes only its own
favorites/files, restores the original mode, pauses a valid original album and
rescans the original three tracks. Full integration runs it before natural EOF.
No new Dockerfile/normal Compose setting or image-only experiment is required.

Limits of this generated fixture: one external UTF-8, single-file/two-track WAV CUE;
one DSD64 stereo DSF and uncompressed DFF. SACD ISO has a [separate opt-in scenario](../../research/docs/reports/sacd.md).
Embedded/multi-file CUE, other text encodings,
DST, higher DSD rates, full CUE seek/EOF boundaries and hardware audio need their
own evidence. Current validation/failure history is in
[the research checkpoint](../../research/docs/status.md#cue-dsd-investigation-2026-09-16).
