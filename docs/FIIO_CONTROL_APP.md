# FiiO Control application evidence

## Android 4.6.0 input (2026-09-15)

User-provided `FiiOControl V4.6.0.apk`:

- Manifest package: `com.fiio.control`.
- Manifest version: `4.6.0`, version code **105** (verified with Android SDK `aapt2`).
- APK SHA-256: `516c6d882a6723b03d7860f8ab000ce8dc600d9fabe986bfe187ba15d37d110c`.
- ARM64 `libapp.so` SHA-256: `c8364937febff7ddd493f3874c38580908433ae9bb42388cc5d79a3785265f6c`.
- Flutter engine contains Dart **3.10.9**, Android ARM64 release.
- Three DEX files plus Flutter AOT libraries. Java analysis alone does not recover
  the Dart Link command builder. JADX 1.5.6 completed with 51 decompilation errors;
  its output is partial, not a complete source reconstruction.

The user reports iOS app version 4.6.0 too. This identifies a useful comparison
version; it does not establish the same build, wire commands or platform behavior.

## Concrete AOT leads

These strings and package paths are present in the ARM64 snapshot. Their presence
identifies analysis targets, not a recovered call graph or validated command:

| Area | Observed names |
|---|---|
| Link command builder | `linkmodule/utils/link_command_builder.dart` |
| Library operations | `getUpdateLibraryMsg`, `getCancelUpdateLibraryMsg`, `getResetLibraryMsg` |
| Modes | `getWorkModeMsg`, `getSetWorkModeMsg` |
| File transfer | `linkmodule/linked_device/service/wifi_music_http_service.dart` |
| Themes | `linkmodule/linked_device/service/wallpaper_http_service.dart` |
| Newer local catalog | `fiio_v2/link_device_v2/service/local_play_http_service.dart`, `local_dir_http_service.dart` |
| Theme contract strings | `/image/lock_screen/`, `back-groud`, `lock_screen/system`, `lock_screen/custom`, `lock_screen/custom/default` |

The theme strings agree with already tested firmware endpoints. No reset tag
has been recovered from this APK, and no reset was sent to physical DISC.
Separately, V2.57 firmware analysis and disposable tests established dedicated
`0621/0000`: see [library reset](LIBRARY_RESET.md). The owner confirms the app
offers library reset (2026-09-16), but its exact frame/follow-up sequence is still
unobserved; firmware evidence is not an app capture.
Generic Dart runtime proxy strings also occur; they do not prove that FiiO Control
honors the phone's HTTP proxy configuration.

Selected binaries, partial decompilation and inventory remain in ignored
`work/fiio-control-460/`. No APK, app assets or decompiled sources belong in Git.
The [Blutter project](https://github.com/worawit/blutter) was inspected as a route to
Dart AOT function/object-pool analysis; it has not yet been built or run here.

## iOS 4.6.0 observed HTTP (2026-09-15)

The user captured FiiO Control and Surge on the same iPhone. The HAR creator is
Surge iOS **5.22.0**; the app reports `Dart/3.10 (dart:io)` as User-Agent. App
version 4.6.0 is user-reported, not encoded in that User-Agent.

`2026-09-15-231411.har` contains **10 requests**, all to physical DISC HTTP port
12103, all with status 200. Entries are stored newest first; ordering below uses
`startedDateTime` (UTC+05:00). Encoded response bodies decode completely and match
their recorded lengths.

| Time | Request | Observed result |
|---|---|---|
| 23:15:20 | GET `/image/cover/` | 48,864-byte JPEG |
| 23:15:26 | GET `/localdir/tmp/` | `start-pos: 0`, `num-max: 100`; one `sdcard` directory, `total-num: 1`, `mark-pos: 0` |
| 23:16:47 | Six GET `/image/lock_screen/` | System slots 0..4 and custom slot 0; all 360×360 PNGs |
| 23:16:52 | POST `/image/lock_screen/` | Select system slot 1, `FIIO%20Sheep`, empty body |
| 23:16:57 | POST `/image/lock_screen/` | Select system slot 0, `Clock`, empty body |

Theme GETs identify the slot through `x-fields-to-update` and `file-source`.
The app omits `preview-flag`, using the stock preview default. Our helper explicitly
requests the original image instead. Both selection POSTs echo the corresponding
GET metadata, setting `flag-in-use: 1` and preserving the already percent-encoded
alias. This matches `select_system_lock_screen()` without runtime changes.

The initial GET reports Clock active. The final POST requests Clock again, but
there is **no subsequent GET** proving the final active state. No custom image
upload, mode/codec command or library reset is present. The custom GET has an empty
alias; this agrees with the previously observed emulator behavior.

The curated [fixture](../tools/fixtures/fiio_control_ios_460_themes.json) retains
only the two selections' protocol metadata and source hash. A regression test in
`tools/test_fiio_theme.py` compares generated POST headers and empty bodies with
these actual iOS requests. Images, personal cover artwork and raw HARs are omitted.
The expanded firmware-free suite passed: **165 Python tests, 23 JavaScript tests**,
shell checks and four shim builds.

`2026-09-15-231846.har` is 88 bytes with `entries: []`. The user repeated the same
actions after removing ports from Surge rules and also tried Packet Capture.
This empty HTTP export does not establish a device failure or a TCP-only action.
If the removed port was in `force-http-engine-hosts`, the documented default of
port 80 explains why DISC's 12103 traffic would no longer match that option.
The exact edited profile was not supplied. Neither HAR contains the Link stream
on 12100 or raw packet data.

## iOS raw TCP capture (2026-09-15)

User-supplied `2026-09-15-233337.pcap`, SHA-256
`ac46002c2e579c075f46c0d2df7b34fa06f2c2b570f5f55cd59cb3defdf804f8`, is a classic
little-endian PCAP with BSD NULL link headers. It spans 23:33:37.714–23:34:25.796
(UTC+05:00), contains 773 packets, and has no capture-truncated packets. Only
DISC's 12100 traffic was decoded; unrelated phone traffic stays out of fixtures.
There are 70 DISC packets and no HTTP 12103 packets in this capture.

An already-existing connection first sends `0657000c0001` at 23:33:50.592 and
receives a TCP reset, with no Link response. Its connection setup predates the
capture. This does **not** establish that the command reached the player or that
USB DAC caused a failure: Surge's virtual-interface capture is not a simultaneous
capture on the physical DISC interface.

A new connection at 23:34:05.511 completes TCP setup, then exchanges
`0599000c0000` → `a599000C0306`. Its bidirectional payload sequences are contiguous,
with no gaps, retransmissions or leftover partial Link frames: **160 app bytes /
14 frames**, **790 device bytes / 20 frames**. It stays connected throughout all
four mode transitions; a reset appears only at 23:34:25.785, at the end of the trace.
The cause of that final reset is not established.

### Initialization and advertised capabilities

After handshake the app sends, in order:

```text
05010008
0607000c0000
062700100000A0A9
0639000c0000
02020008
0629000c0000
0628001000000009
```

`0627` and `0639` share one TCP payload; Link framing must handle coalescing.
The initial mode response is `a607000C0008` (local); EQ is off (`a639/00FF`),
master is zero (`a629/0000`), and the PEQ response contains ten bands with zero
frequency, gain and Q. Our decoder accepts this observed disabled state, while
the custom-EQ writer still rejects zero frequency/Q. No dedicated `a627` reply
appears. `a60a/0010` is observed during initialization, with its meaning unresolved.

The `a501` JSON includes:

| Field | Observed value |
|---|---|
| `soc_version`, `maxVolume` | 257, 120 |
| `http_replace_link`, `http_custom_list` | 1, 1 |
| `cus_count`, `sys_count` | 1, 5 |
| `width`, `height`, `quality`, `rgb` | 364, 364, 100, 888 |
| `image` | String containing JSON array `["png", "gif"]` |
| `video` | String containing JSON array `["mp4"]` |

These are advertised capabilities, not proof of working GIF/MP4 uploads. In
particular, advertised 364×364 differs from the actual 360×360 PNG responses in
the earlier HAR. Retain the tested 360×360 PNG upload contract until alternate
formats/dimensions are independently exercised. The HTTP flags agree with the
already tested HTTP library and playlist routes; this trace itself has no HTTP.

### Physical mode cycle

| App time | Request | Device response | Meaning |
|---|---|---|---|
| 23:34:10.416 | `0657000c0001` | `a607000C0001` at 10.452 | USB DAC |
| 23:34:15.634 | `0657000c0008` | `a607000C0008` at 15.686 | Local |
| 23:34:17.768 | `0657000c000A` | `a607000C000A` at 17.836 | AirPlay |
| 23:34:21.652 | `0657000c0008` | `a607000C0008` at 21.881 | Local |

Each setter produces a matching mode notification **without a subsequent `0607`
query**. FiiO Control requests `02020008` after both returns to local, but no
`a202` occurs anywhere in this trace. Do not substitute a known paused/stopped
state for the missing snapshot. Other notifications are `a824/0000` and paired
`a714`/`a502` values, first `003C`, later `0020`; no app volume setter is captured.
Mode response values validate our existing wire mapping on physical DISC, but
do not prove USB audio enumeration or AirPlay audio playback.

The [curated fixture](../tools/fixtures/fiio_control_ios_460_modes.json) retains
handshake, mode requests/replies, disabled PEQ and a subset of capability metadata.
The app uses lowercase hex length digits (`000c`); our encoder uses uppercase
(`000C`). Tests normalize header case only, preserving payload bytes.
Regression tests compare TCP/WS setters with app frames, decode physical
mode replies, and check the disabled PEQ state. No runtime client changes were
needed. At this stage codec selection, custom-image metadata saves and library
reset were unobserved; the later capture below supplies the codec sequence.

Validation: the firmware-free suite passed **167 Python tests, 23 JavaScript
tests**, shell checks and four shim builds. After preserving the original hex
header case in the fixture, the 16 settings/framing tests passed again.

## iOS codec capture (2026-09-15)

`2026-09-15-234051.pcap`, SHA-256
`824f1f598070e75c27045afde4420d600ebb242b95d14de0cc18c6c90afa64d8`, contains 409
packets over 23:40:51.809–23:41:37.065 (UTC+05:00), none capture-truncated.
68 packets belong to one DISC TCP 12100 connection; no 12103 packets are present.
Its payload sequences are contiguous, without gaps/retransmissions or trailing
partial Link frames: 240 app bytes / 20 frames, 790 device bytes / 20 frames.
TCP setup and `0599` → `a599/0306` are captured. A reset appears at the end;
all codec requests and replies precede it.

Initial mode is local (`a607/0008`). The startup sequence matches the previous
capture, including disabled PEQ and no `a202` response to `0202`. Opening the
settings page sends the following read requests (not setters):

| Query | Response(s) | Interpretation |
|---|---|---|
| `064a/0000` | `a64a/0001` | Gain value 1 |
| `06d4/0000` | `a6d4/0004` | LDAC sound quality preference |
| `0824/0000` | `a824/0000` | SPDIF off |
| `0603/0000` | `a603/0001`, then `a603/000A` | Same filter in device enum and Link enum (+9) |
| `0813/0000` | `a813/0001` | DRE on |
| `0712/0000` | `a712/0000` | Observed setting query; meaning not established by this trace |

A second codec query at 23:41:09.794 again returns 4. The user reports selecting
the codec rows bottom-to-top, then restoring the initial row. The accompanying
screenshot selects the bottom LDAC sound-quality row. The wire sequence is:

| Request time | Exact app frame | Exact DISC reply | UI choice |
|---|---|---|---|
| 23:41:18.630 | `06d3000c0003` | `a6d4000C0003` | LDAC balanced |
| 23:41:21.880 | `06d3000c0002` | `a6d4000C0002` | LDAC connection stability |
| 23:41:24.964 | `06d3000c0001` | `a6d4000C0001` | AAC |
| 23:41:27.782 | `06d3000c0000` | `a6d4000C0000` | SBC |
| 23:41:30.565 | `06d3000c0004` | `a6d4000C0004` | LDAC sound quality, restored |

There is no setter for the initially selected bottom row before value 3. Each
setter receives a matching notification without a new `06d4` getter. The final
`a6d4/0004` arrives at 23:41:31.386, confirming the returned preference, not just
an outgoing request. Response delays range from about 44 to 821 ms in this trace;
do not treat that sample as a universal timeout bound.

The [curated fixture](../tools/fixtures/fiio_control_ios_460_codecs.json) preserves
both initial reads and all five transitions, with original hex case. The regression
test compares our TCP/WS setters with parsed app frames and decodes every physical
reply. Existing mappings need no runtime change. Actual negotiated Bluetooth codec,
bitrate and audio quality remain untested by this network capture.

Validation: all **17 settings/framing tests passed**, including the new capture
regression. Runtime code is unchanged; the full firmware integrations were not
repeated for this fixture/documentation change.

## iOS playback and favorites capture (2026-09-15)

`2026-09-15-234648.pcap`, SHA-256
`d915be7d66c070da3f8a4bd93ab774dcbb16cbd36477de5e673ff9a5c6b32961`, contains 586
packets over 23:46:49.148–23:47:42.811 (UTC+05:00), none capture-truncated.
90 packets belong to one DISC TCP 12100 connection and 71 to HTTP 12103.
The Link streams have contiguous sequence numbers, no retransmissions/gaps or
incomplete trailing frames: 172 app bytes / 14 frames, 2948 device bytes / 31 frames.
The user performed the requested playback cycle and added like/unlike at the end.

| Time | App action/frame | Observed response |
|---|---|---|
| 23:46:52.841 | Initial `02020008` | No `a202` before selection |
| 23:47:07.223 | `0100001000000001`, first all-tracks position | Full `a202` at 07.632, `state: 2`, `love: false` |
| 23:47:09.782, 09.885 | No new app query | Two `a202` deltas, `state: 0` |
| 23:47:18.509 | `0201000c0000`, pause | Two `a202` deltas, `state: 1` |
| 23:47:21.859 | `0201000c0000`, resume | Two `a202` deltas, `state: 0` |
| 23:47:25.360 | `0201000c0000`, pause | Two `a202` deltas, `state: 1` |
| 23:47:33.462 | `0104000c0001`, like | Full `a202` at 33.643, `love: true`, `state: 1` |
| 23:47:36.246 | `0104000c0000`, unlike | Full `a202` at 36.298, `love: false`, `state: 1` |

The three full snapshots have identical nested song metadata. `song` is a string
containing JSON, `love` is a Boolean, and state-only deltas contain no track fields.
`a103` ticks report 1000..8000 ms before pause, then 9000..12000 ms after resume;
none occur between the first pause and resume or after the final pause. A single
`aa05/0001` also appears during startup; its meaning is not established here.

No `0202` is sent after track selection, including when the current-track screen
is used. Treat subsequent full snapshots as asynchronous updates; this trace
cannot establish why the initial query is silent or whether querying during
playback would succeed. Like/unlike set an explicit current-track flag, unlike
the play/pause toggle. Their confirmation is the updated `love` field, not an
`a104` acknowledgement. No favorite-list HTTP request appears after either action.

HTTP streams also reassemble contiguously; all three requests return status 200
with complete Content-Length bodies:

- `GET /localdir/tmp/`: `start-pos: 0`, `num-max: 100`; one `sdcard` directory.
- `GET /song_category_tree/`: `type: all/song`, `start-pos: 0`, `num-max: 100`,
  empty `artist`, `album`, `style` headers; 100 records with keys `pos`, `name`,
  `author`, `count`. Response also supplies `total-num` and `mark-pos`.
- `GET /image/cover/`: 48,864-byte JPEG with valid start/end markers.

This shows the stock app combining HTTP catalog/cover retrieval with TCP track
selection and playback/favorite notifications. Catalog contents and cover artwork
remain private. The [fixture](../tools/fixtures/fiio_control_ios_460_playback.json)
retains actual commands, deltas and position values; full snapshots replace song
metadata and queue size with synthetic values and recalculate frame lengths.
Tests cover decoding the nested song, Boolean favorite transitions, repeated
state deltas, position units and TCP/WS toggle equivalence. Runtime clients are
unchanged; the stock favorite command was already exercised in emulator integration.

Validation: **17 remote-control/framing tests passed**, including the new trace
regression. Full firmware integrations were not repeated for this fixture/doc change.

## iOS paused seek and play-order capture (2026-09-15)

`2026-09-15-235540.pcap`, SHA-256
`00da5a3a19bc08d4ed0bb954ae616f79adb8341d914fbb998b32690ee5eb99bd`, contains 861
packets over 23:55:41.542–23:56:59.448 (UTC+05:00), none capture-truncated.
106 packets belong to a single DISC TCP 12100 connection; 40 belong to HTTP 12103.
The Link payload sequences are contiguous, with no gaps/retransmissions or trailing
partial frames: 332 app bytes / 25 frames, 1607 device bytes / 28 frames.
HTTP contains one `GET /image/cover/`, status 200, complete 48,864-byte body.

### Current-track query succeeds on pause

Startup includes `0501` reporting play mode 1, then `02020008` at 23:55:59.836.
A full `a202` arrives at 59.890 with `state: 1`, `love: false`, `work_mode: LOCAL`
and nested song metadata, before any control commands. This is a successful
current-track query while paused. Earlier initial-query silence is not a general
limitation of pause or FiiO Control compatibility. A track-context dependency is
plausible but has not been isolated experimentally. `0202` still has no request ID,
and future clients must also accept unrelated asynchronous `a202` updates.

### Two batches of paused seek attempts

The user reports that the slider did not move while paused, prompting repeated
attempts, then moved on resume. All eight attempts are visible as `0103` frames
with eight ASCII-hex **millisecond** digits:

| Request time | Exact frame | Requested milliseconds |
|---|---|---:|
| 23:56:10.240 | `0103001000003eda` | 16090 |
| 23:56:11.690 | `010300100001d651` | 120401 |
| 23:56:14.740 | `010300100001a768` | 108392 |
| 23:56:16.007 | `0103001000025191` | 151953 |
| 23:56:31.029 | `0103001000026a67` | 158311 |
| 23:56:31.593 | `01030010000334c1` | 210113 |
| 23:56:33.462 | `01030010000267a4` | 157604 |
| 23:56:34.010 | `0103001000034cab` | 216235 |

There are no Link position or state replies during either batch. After the first
resume (`0201/0000` at 20.605), duplicate playing deltas arrive at 22.339/22.343,
then ticks 152000, 153000, 154000, 155000 ms. The pause at 26.991 produces duplicate
paused deltas. After the second resume at 35.026, duplicate playing deltas are
followed by ticks 217000 and 218000 ms; the final pause at 37.543 again returns
two paused deltas. Both resumptions are consistent with the **last** requested
position in their batch. The trace does not tell when the decoder internally
applies the seek, nor prove a precise rounding rule from the first delayed tick.

The future remote should distinguish a user-requested pending seek position from
device-confirmed progress. It can keep the slider at the requested position on
pause and reconcile it when progress resumes. Lack of an immediate `a103` is not
evidence that a seek failed and is not a reason for automatic retries.

### Play-order cycle and icons

From initial mode 1, the app sends `0102/0002`, `0003`, `0004`, `0000`, `0001` at
23:56:47.095, 48.962, 51.346, 53.296, 55.030. Each receives a matching `a102`
within about 20–25 ms. Final random mode is confirmed, and no playback resume
occurs during these changes. The six screenshots map to 1 → 2 → 3 → 4 → 0 → 1
by the supplied ordering; their displayed 00:00 time is later than this trace.
See the [icon/behavior table](REMOTE_CONTROL.md#commands). End-of-track/list
behavior is described from stock code analysis, not exercised by this capture.

The [fixture](../tools/fixtures/fiio_control_ios_460_seek_modes.json) retains exact
seek/mode/toggle/delta/position frames and a minimal initial-state summary, with no
song metadata or images. iOS seek payloads use lowercase hex; client comparisons
normalize case only for these numeric commands. Regression coverage compares
both TCP and WS encoders, checks absence of paused position replies, both first
post-resume positions, all mode confirmations and final paused/random state.

Validation: **18 remote-control/framing tests passed**. Runtime clients are
unchanged; firmware integration runs were not repeated for this fixture/doc change.

## iOS current-queue capture (2026-09-16)

`2026-09-16-001300.pcap`, SHA-256
`ba7160176115f2b7c07d72235e8e8953902af1384a95b79691e1eba3080567e8`, contains
1400 packets over 00:13:00.883–00:14:10.649 (UTC+05:00), none capture-truncated.
152 packets belong to DISC TCP 12100, 373 to HTTP 12103. Link payload sequences
are contiguous with no gaps/retransmissions or trailing partial frames: 252 app
bytes / 13 frames, 4833 device bytes / 63 frames. HTTP payload sequences are also
contiguous and all response Content-Length bodies are complete.

Startup performs the known handshake and gets a full paused current-track reply
to `0202`. `0501.playMode` is **1 (random)** throughout this capture; the app sends
no play-mode setter. The selected album has 15 tracks.

| Time | App request | Confirmed result |
|---|---|---|
| 00:13:24.252 | `0101`, payload `0003` + album name | Full `a202`: album source 3, `playing_num: 1/15`, `pos_id: 1` |
| 00:13:43.741 | `0100003b00020000Список воспроизведения` | Full `a202`: queue source 0, `3/15`, `pos_id: 3` |
| 00:13:51.442 | `0201000c0001` | Full `a202` at 53.175: `11/15`, `pos_id: 11` |
| 00:13:58.977 | `0201000c0002` | Full `a202` at 59.099: `3/15`, same song as the selected third row |
| 00:14:05.445 | `0201000c0000` | Two `a202` state-only replies with state 1 |

All selection/navigation snapshots initially report state 2 and are followed by
duplicate state-0 notifications and position ticks. Old-track ticks continue
between the next command and its new full snapshot; the observed 1.73-s response
delay is another reason not to retry navigation blindly.

The nine HTTP requests are five cover GETs, one `/localdir/tmp/`, and three
`/song_category_tree/` GETs with types `album`, `album/song`, `curlist/song`.
All return 200. Catalog requests use offset 0, limit 100; artist/style are blank,
and album is percent-encoded only for `album/song`. The album and queue responses
contain identical 15-row arrays (`pos`, `name`, `author`, `count`), while their
marks differ: album/song -1 before playback, queue 0 after album playback starts.
The app does **not** issue TCP `0406`, `0426` or `0105` here.

For all four post-album full snapshots, the one-based `pos_id`/`playing_num`
matches the name/artist of the zero-based HTTP queue row. These snapshots give
positions 1 → 3 → 11 → 3. No new queue fetch occurs after the type-0 selection;
the old HTTP `mark-pos` cannot be treated as live state. The observed next/previous
positions are consistent with random mode, not sequential index arithmetic.
No general shuffle-history or queue mutation rule is proven by this sequence.

Type-0 selection on DISC is now physically observed, with a localized queue-label
suffix and UTF-8 byte length **0x3b = 59**. Do not replace this with the Android
M21 header length. This capture alone cannot establish whether the label is
required. The later [emulator checks](REMOTE_CONTROL.md#validated-current-queue-helper)
compare Russian, absent and arbitrary labels and introduce a guarded dedicated
helper; generic `play_index()` still rejects type 0.

The [fixture](../tools/fixtures/fiio_control_ios_460_queue.json) retains exact queue
selection/navigation commands and HTTP request metadata. Catalog text and song
identities are synthetic; snapshots are reduced to the fields needed to compare
row positions and source types. Raw album/track names, artwork and unrelated phone
traffic are omitted. Regression coverage exercises the HTTP queue reader, Unicode
selector framing, physical position/source transitions and TCP/WS navigation.

Validation: **27 HTTP/remote-control/framing tests passed**. No runtime client
behavior was changed and full firmware integrations were not repeated.

## Capture follow-up

Use the action checklist in [REMOTE_MODES_THEMES.md](REMOTE_MODES_THEMES.md#fiio-control-capture-checklist).
For Surge, first distinguish missing LAN takeover from an existing connection not
parsed as HTTP. Official references:

- [Surge general options](https://manual.nssurge.com/profile/general.html): iOS LAN takeover and host/port matching.
- [HTTP processing](https://manual.nssurge.com/http/overview.html): nonstandard HTTP ports versus raw TCP.
- [Surge iOS release notes](https://kb.nssurge.com/surge-knowledge-base/release-notes/surge-ios):
  Network Layer Packet Capture exports TCP/UDP/ICMP in `.pcap`; HTTP capture exports HAR.

Keep an explicit `force-http-engine-hosts = 192.0.2.21:12103` match for HTTP,
replacing this documentation address with the DISC's actual LAN address.
Do not force the Link port 12100 through the HTTP engine. To reproduce this capture,
start Network Layer Packet Capture before reopening FiiO Control and connecting
to DISC, perform the mode cycle in the checklist, then stop and export **`.pcap`**.
This recovered both connection setup and bidirectional Link frames in the supplied
PCAP. Work modes, codec, playback, favorites, paused seeks and play-order changes
are now captured, as is HTTP current-queue browsing and TCP type-0 selection.
The recent traces also confirm a successful paused `0202` query;
the earlier silence remains a narrower track-context question. Custom-theme
metadata saves still need the backup/restore scenario in the checklist; library
reset remains unobserved. Further mode captures are unnecessary to establish
the app's enum mapping; actual end-of-track/list behavior is a separate check.
Type-0 label/empty/replaced-queue checks now have a dedicated disposable scenario
and client helper, described in the remote-control contract.
`0105`/`0426` are not observed in these DISC app traces. They were subsequently
investigated directly in the emulator: [read-command results](REMOTE_CONTROL.md#remaining-queue-related-reads-0105-and-0426).

Record both app versions and actual capture topology alongside a trace. A successful
HTTP capture does not establish capture of the separate Link TCP stream on 12100.
