# SACD ISO metadata and selection (V2.57)

[Issue #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8) resumed on
2026-09-17 with an owner-approved local ISO. The test uses an isolated copy,
never the interactive library. No source audio, titles, private paths or firmware
data belong in Git or hosted artifacts.

Owner accepted this limited checkpoint for PR #20 / `2.x` on 2026-09-19.
Remaining cases below are optional follow-ups retained in #8, not blockers for
integrating the current work. No new media run or hardware-support claim follows.

## Status audit (2026-09-17)

The implementation is already published in commit `f5c08b7`, with the shared
checkpoint in `d4aebe4`, on `codex/api-sacd-peq-checkpoints` / PR #20 against
`2.x`. The issue's original unchecked checklist predates these results.
The approved sample, scanner/decoder trace, index/metadata comparison, first/last
catalog/queue/favorite selection, guarded queue bound, same-path title replacement
and restoration are complete for the documented stereo image. Source replacement
coverage is **metadata-only**: both TOCs change title while track count, layout
and audio remain unchanged. Do not call that a different-image/layout test.

Issue #8 remains open for the outstanding replacement/coverage follow-ups below;
the completed limited checkpoint should not be repeated merely to refresh status.
First remaining source-replacement case: a separately approved image with a
different track layout at the same path, followed by rescan, fresh positional
selection and restoration. No new sample use or mutation starts in this audit.
Seek/EOF, a redistributable playable fixture, DST/multichannel and hardware output
are separate extensions, not failures of the completed stereo metadata tests.

This audit compared committed code, tests, docs and GitHub status. Prior focused
TCP/WS acceptance is recorded below; the referenced old local SACD logs are not
present in this checkout, so no independent log reinspection or fresh firmware
run is claimed. The later 326 Python / 37 JavaScript branch suite passed after
the PEQ additions; it does not expand SACD's tested media/runtime scope.

## Input and structural scope

Input SHA-256: `1c5f017feb212151c7307159ec59e982a037ece9901eee65bfb9369bb39debe9`.
Size: 1,618,677,760 bytes. The primary area has ten tracks, two channels, DSD64
(2,822,400 Hz), frame format 2 (uncompressed DSD), and a backup stereo TOC.
There is no multichannel area. This sample does not validate DST, multichannel,
native DSD/DoP output, bit-exact decoding or physical audio.

`python3 -B -m research.diagnostics.inspect_sacd /path/to/approved.iso` prints
only structural facts and a streaming SHA-256. It reads primary 2048-byte-sector
TOCs and track-time records, following the documented layout in
[SACD Ripper's header](https://github.com/sacd-ripper/sacd-ripper/blob/master/libs/libsacd/scarletbook.h).
It is a narrow independent inspection tool, not a complete image validator or
audio decoder. Header-only unit fixtures contain original synthetic data.

## Observed stock behavior

- HTTP directory browsing exposes one ISO file. Scanning expands it to ten
  logical songs, alongside the three generated ordinary test songs.
- Indexed rows share the ISO path, with `TRACK=1..10`, `IS_ISO=1`, `IS_CUE=0`,
  `IS_DSD=0`, `OFFSET=0`, `IS_M3U=NULL`. Decoder metadata instead reports both
  `is_sacd=true` and `is_dsd=true`; these fields describe different layers.
- First/last track selections report ordinal 1/10, stereo DSD64/one-bit source
  metadata and the shared path. Both can be selected and paused from the catalog,
  current queue and two separate favorites through TCP and WS.
- Catalog, TCP queue and stock HTTP have list positions. Read **every page**:
  the fixture has thirteen rows, exceeding a single queue response. Do not
  deduplicate logical tracks by the shared path or assume returned IDs are stable.
- Favorites retain the two ISO ordinals in `MY_LOVE`, but `0415` replies have
  `track=0`, `isSacd=false` and an empty `songPath`. Both favorite positions still
  play the matching logical track. Do not reconstruct identity from those fields.
- The index's duration field treats the SACD frame fraction as centiseconds:
  for a track lasting `F` units of 1/75 second, the observed stored milliseconds
  are `(F // 75) * 1000 + (F % 75) * 10`. Selected metadata is truncated to whole
  seconds. First/last indexed durations are 207250/173670 ms, while selected
  metadata is 207000/173000 ms. Do not silently reinterpret these as exact
  source duration or evidence of playback boundary accuracy.

The existing snapshot/position identity rules in [FORMATS.md](FORMATS.md) still
apply. A fresh queue bounds check rejects position equal to its total before
sending a command. No raw out-of-range ISO selector is sent to the device.

## Static trace

Fingerprint-normalized V2.57 `mq_player` is checked against the stock profile.
`468bd8` calls ISO scanner `468698`: `61f310` obtains ISO metadata,
`46b4dc` parses the track records, `46b280` converts colon-separated duration
with `seconds * 1000 + fraction * 10`, and `443894` inserts the expanded songs.
Playback `44badc` selects the SACD branch and invokes `61c82c(path, track,
open_mode, 0)`. The binary contains the Scarlet Book reader and a DST decoder;
their presence does not prove runtime DST support.

## Repeatable local acceptance

```sh
CI_SCENARIO=sacd FW_VERSION=2.57 CI_SACD_ISO=/absolute/path/to/approved.iso \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

This opt-in scenario requires an explicit local ISO. It is excluded from `full`
and hosted workflows. The harness copies the image under a neutral filename in
its temporary SD directory; setup sizes the FAT image from that directory.
The test checks its hash against the mounted source copy, scans and compares
catalog/SQLite/queue/selected metadata, adds/selects/removes first and last ISO
favorites, restores play mode, leaves an ordinary generated track paused, checks
the image bytes, removes only the guest's ISO copy and rescans the three original
generated songs. The temporary copy, guest stack and volume are removed.

Raw guest logs can contain tags and playback paths even though success output
omits them. Keep `CI_LOGS` local/ignored and do not upload this run's logs or PCM.
Results and failures are recorded in [PROTOCOL_RESEARCH.md](PROTOCOL_RESEARCH.md).

Final focused acceptance passed over TCP/WS, including replacing the first title
with equal-length original ASCII text in both stereo TOCs, fresh scans/selection,
exact input-hash restoration, removal/rescan and disposable-stack cleanup. Text
positions may span multiple TOC sectors; the fixture tests the approved image’s
4096-byte offset and plans both changes before any write.

Remaining extensions: replacement by a different audio/track layout, a playable
original fixture suitable for hosted tests, multichannel/DST samples and exact
seek/EOF boundaries. Only the first/last tracks are selected; all ten are checked
in the index. Native DSD/DoP and hardware output remain outside this scope. No
general SACD compatibility claim is made.
