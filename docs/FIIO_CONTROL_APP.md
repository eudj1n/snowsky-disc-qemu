# FiiO Control application evidence

## Screen coverage audit

Started 2026-09-16; first wallpaper screenshots received and inventoried below.
Scope: the DISC interface of FiiO Control, not every other supported product.
Record the app version, platform and DISC firmware with each batch; do not
assume an unchanged build.

Start with theme selection and every custom-theme editor panel. Then inventory
the other screens, including scrolled portions, nested settings, option dialogs,
context menus and disabled controls where visible. Opening a destructive-action
confirmation is enough to record its UI; do not reset/delete/update merely to
complete screenshots. Redact personal names, network identifiers and paths.

For each screen/control, record: screenshot reference and navigation path, visible
action and choices, matching helper/endpoint, evidence/test link, coverage status
and next evidence needed. Separate these statuses:

- Implemented and validated in the emulator.
- Observed in a physical-app capture (record separately from emulator coverage).
- Read-only or rejected by the tested DISC network interface.
- Visible but unverified / missing client implementation.
- Hardware-only or outside the current emulator scope.

Screenshot inventory completeness and protocol/hardware validation are separate;
a visible control alone is not proof of a supported command. The future web
remote frontend is not implemented just because a helper exists. Request focused
traffic captures only where existing contracts do not resolve a specific gap.

Raw screenshots/captures stay in ignored `shots/` or `work/`. Commit only minimal,
sanitized evidence; approved curated screenshots belong in `docs/images/`, not
links to ignored local files. The first concrete protocol question is the
[custom-theme save sequence](REMOTE_MODES_THEMES.md#custom-theme-metadata-save-capture).

### Wallpaper screens: first batch (2026-09-16)

Owner-provided iPhone screenshots `IMG_6789.PNG` through `IMG_6794.PNG`, Russian
UI, show 17:30–17:31. The owner explicitly confirms this inspection used the
**physical DISC**, not the emulator. These are phone-app screens while connected
to that device, not photographs of the player's display or a network capture.
App/firmware versions are not visible; the earlier reported
iOS 4.6.0 / DISC V2.57 context is not fresh version evidence. Images are not copied
into Git; filenames identify the supplied evidence, not repository links.

| Screen/control | Screenshot | Existing coverage and remaining evidence |
| --- | --- | --- |
| Wallpapers → My wallpapers carousel / All | 6789, 6791 | One custom and five system tiles match the tested slot counts. `read_lock_screen()` reads each slot. No separate list/catalog helper or remote frontend. |
| Apply / Applied | 6789, 6791 | Clock is marked applied in the app. `select_system_lock_screen()` covers system selection; custom upload also activates. Screenshot alone does not prove device readback or a standalone custom-activation request. |
| Official wallpapers | 6790 | Shows “No wallpapers”. No catalog helper; source/endpoint and reason for the empty list unknown. Do not infer a cloud source, unsupported API or zero available wallpapers globally. |
| Custom → tap image to change / Apply now | 6792–6794 | Full 360×360 PNG replacement/activation implemented. Image picker, crop and conversion flow are not shown or implemented by the helper. Existing-image reapply sequence awaits capture. |
| Background transparency, displayed 100% | 6792 | Helper exposes `alpha=0..100` via `back-groud`; emulator checks persistence. UI percentage-to-wire mapping and opacity direction on the physical display remain unverified. |
| Time, Date, Battery, Track information | 6793 | All four appear checked. Helper exposes `time/date/battery/id3`; metadata is emulator-tested. Exact iOS save sequence and physical rendering still require evidence. |
| Style selection, four thumbnails | 6794 | Three digital layouts and one analog clock are visible; the first thumbnail is selected. Initially a fixed-style helper gap; now four wire values are captured and emulator-tested (see style-save evidence below). Thumbnail ordering is inferred from the requested walkthrough, not encoded in packets. |
| Two unlabeled color-gradient sliders | 6794 | Helper accepts RGB via `front-color`. Exact slider semantics, color conversion, endpoints and save sequence unknown; do not label them RGB/HSV components from appearance alone. |

The two tiles labelled FIIO Sheep have different artwork; names are not unique
theme identities. Clock is the selected wallpaper in the list, while the first
custom layout is selected in its editor: these are different selection levels.
The custom image preview lacks overlays even though all four checkboxes appear
checked; this does not prove a rendering failure or that flags are ignored.

The subsequent [physical capture](#physical-custom-theme-save-2026-09-16) resolves
the color/Date save sequence: the app resends the complete image. The second
[style capture](#physical-custom-style-save-2026-09-16) confirms four custom
style values and unchanged subclass, with a time-flag change in the request.
Official-catalog loading and image-picker/cropping remain separate gaps.

### Physical custom-theme save (2026-09-16)

Inputs: `2026-09-16-173912.har` and matching `.pcap`, captured by the owner on
physical DISC. Surge HAR creator: iOS 5.22.0. App/firmware versions were not
newly confirmed. Source hashes and sanitized fields are in the
[regression fixture](../tools/fixtures/fiio_control_ios_custom_theme_save.json).
Raw captures and PNG bodies are not committed.

Of 17 HAR entries, 14 target DISC HTTP 12103, all `/image/lock_screen/`:
six initial GETs, four custom POSTs, three custom readbacks and one system POST.
All 14 have HTTP 200 responses. Other traffic is excluded from the evidence.
The PCAP has matching 14 HTTP connections and **no TCP 12100 packets**; it does
not establish that the app never uses TCP for other theme actions.

TCP payloads were reassembled by sequence number in each direction: no gaps or
conflicting overlaps, all relevant payload packets untruncated, and all 28 HTTP
messages' bodies match Content-Length. Request/response body multisets match the
HAR exactly. All nonempty bodies are 360×360 PNGs. HAR timestamps have only
whole-second precision and entries are not reliably chronological within a
second; the PCAP establishes POST-before-GET ordering below. Times are UTC+05:00
and identify the start of each request, not completion of the large upload.

| Time | Operation | Observed result |
| --- | --- | --- |
| 17:39:23 | Read custom and five system slots | Clock active; custom inactive, white RGB, alpha 100, all four overlay flags 0, `default/0` |
| 17:39:46.832 | Custom POST: color `(0,96,226)` | Complete original PNG resent; activates custom slot. GET at 17:39:47.283 confirms color, active flag and identical image |
| 17:40:05.075 | Custom POST: date 0 → 1 | Color unchanged, other flags 0; same complete PNG. GET at 17:40:05.382 confirms date and image |
| 17:40:14.736 | Identical custom POST repeated | Same metadata and image; 200, no immediate readback. No action log to distinguish another tap from app behavior |
| 17:40:31.940 | Custom POST: white color and date 0 | Same PNG. GET at 17:40:32.157 confirms original custom metadata/image, still active |
| 17:40:35.832 | Select system Clock, slot 0 | Empty-body system POST, 200; no final GET proving active-theme restoration |

Every custom POST and custom GET contains the same **203,218-byte** PNG, SHA-256
`ef76ab578f8daa06a5ff1b52101259420cb5da701d276cc4dce87757409e1442`.
There is no metadata-only write in this trace: color/Date changes use ordinary
full-image replacement plus all metadata. This agrees with `upload_lock_screen()`
and the previously tested empty-custom-body path-clearing quirk. No new endpoint,
TCP command or speculative metadata-only helper is necessary for these actions.

Two important limits remain:

- App POST alias is the percent-encoded label `Пользовательский` (96 encoded
  bytes; the earlier count of 90 was incorrect). Custom GET returns empty alias.
  Follow-up [boundary tests](REMOTE_MODES_THEMES.md#alias-limit-v257) prove stock
  truncation before decoding, including incomplete UTF-8 in SQLite. The 63-byte
  guard is retained. Tests compare other semantic headers and deliberately
  reject the app's unsafe alias; this is not exact whole-request parity.
- Initial wire overlay flags are all **0**, despite the earlier screenshot's
  checked-looking circles. The inputs are not simultaneous and there is no action
  log connecting them; neither a UI bug nor ignored flags is established.

System GET metadata contains `clock/0`, `default/0`, `default/1`, `default/2`,
but every custom save here uses `default/0`. These system values are leads, not
validation of the other custom styles or their visual-thumbnail mapping. Alpha
never changes; the two color sliders' individual semantics remain unobserved.

Validation: all five `tools/test_fiio_theme.py` tests pass, including synthetic
full-image saves for the four captured metadata states and long-alias rejection.
The container firmware-free suite passed: **259 Python / 23 JavaScript tests**,
shell checks and four shim builds. No runtime/helper change or physical write by
our tools was needed. Firmware integration and long power tests were not rerun
for this fixture/test/documentation change; prior emulator evidence is identified
separately above, not reported as a fresh firmware run.

### Physical custom-style save (2026-09-16)

Inputs: `2026-09-16-174708.har` / `.pcap`, continuation of the physical DISC
walkthrough. The [sanitized fixture](../tools/fixtures/fiio_control_ios_custom_theme_styles.json)
records source hashes, request times, styles and flags without image bytes or
addresses. Versions were not newly confirmed by these files.

All 17 HAR entries are `/image/lock_screen/` on HTTP 12103: six initial reads,
five custom saves and five readbacks, then one system selection. All receive 200.
PCAP sequence reassembly verifies complete, nonconflicting byte coverage and
Content-Length for 34 HTTP messages; HAR/PCAP request and response body multisets
match. No TCP 12100 packets occur. PCAP resolves the within-second ordering which
the HAR alone cannot establish. Each custom POST is followed by its GET.

| POST start (UTC+05:00) | Custom style | Time flag | Subsequent GET start |
| --- | --- | --- | --- |
| 17:47:22.463 | `default/0` | 0 | 17:47:22.716 |
| 17:47:32.790 | `default/1` | 0 | 17:47:33.043 |
| 17:47:38.350 | `default/2` | 0 | 17:47:38.536 |
| 17:47:44.101 | `clock/0` | 1 | 17:47:44.302 |
| 17:48:00.313 | `default/0` | 1 | 17:48:00.501 |

Each GET confirms the posted style, time flag and active custom slot. Date,
battery and ID3 flags remain 0; alpha remains 100, RGB white, and subclass always
`lock_screen/custom/default`. Every custom POST/GET carries the same 203,218-byte
PNG as the preceding capture, with SHA-256
`ef76ab578f8daa06a5ff1b52101259420cb5da701d276cc4dce87757409e1442`.
Clock system selection at 17:48:03.856 is empty-body and receives 200; there is
again no final GET proving active-theme restoration. The custom time flag is 1
at the end versus 0 at entry: restoration of all custom settings is **not** proven.

The app's clock POST already contains time=1, so firmware did not introduce that
particular change in its response. A separate tap versus automatic app coupling
cannot be determined from packets. The requested sequential-thumbnail walkthrough
suggests three digital styles in order followed by the analog clock, but there
is no synchronized action log; expose wire strings, not undocumented UI indices.

Implementation: `upload_lock_screen(..., style=...)` allowlists these four values
and preserves independent flags, full image, current subclass and alias guard.
The earlier long Russian app alias still exceeds the helper bound; fixture tests
compare the remaining semantic headers and generated image bytes, not claim
whole-request equality or copy private artwork.

Validation: focused fresh **V2.57 `themes` passed** directly and through the HTTP
proxy, including every style with time=0 and time=1, unchanged image and metadata,
SQLite flag values, five system slots, unsafe empty-body behavior and restoration
of the original active system theme. Stock preserves time=0 even for `clock/0`;
this is persistence/readback evidence, not physical rendering evidence.
The test uses a generated PNG, disposable volume, no published ports and no edits
to the interactive or physical player. Stack and volume were removed afterwards.
Firmware-free suite: **261 Python / 23 JavaScript tests**, shell checks and four
shim builds passed. No full integration, legacy-profile integration or long power
rerun for this narrowly scoped helper change. No Dockerfile/Compose changes:
the existing image/dependencies and tracked scenario reproduce the experiment.

### Library, PEQ and settings screens: second batch (2026-09-16)

Owner-supplied `IMG_6795.PNG`–`IMG_6806.PNG`, 18:07–18:08, continue the physical
DISC app audit. The pictures do not independently identify firmware/app versions
or provide network readback. Raw screenshots and personal library contents are
not copied into Git. Coverage below means existing protocol helpers and their
tests, **not** a completed replacement frontend or validation of every app action.

| Screen/control | Screenshot | Existing coverage / gap |
| --- | --- | --- |
| All songs | 6795 | TCP `library('tracks')`, HTTP `catalog('all/song')`, positional selection and all-song playback exist. App's batch-selection actions are not shown. |
| Artists | 6796 | TCP artist/artist-track reads and named artist selection/play-all are tested; HTTP artist/sub-album categories exist, but not every nested category has behavioral acceptance. Header-level “Play all” must not be assumed equivalent to playing a named artist. |
| Albums | 6797 | Catalog, named album tracks and positional/whole-album playback are tested. Root-page “Play all” and batch actions need their own app evidence. |
| Genres | 6798 | TCP genre listing and HTTP `style`, `style/song`, `style/album` categories are exposed. **Gap:** no validated genre selection/play-all helper; generic playback rejects that context. Reads do not prove playback. |
| Folder → sdcard | 6799 | `/localdir/` browsing exists (root `/localdir/tmp/` observed in earlier app HAR; helper starts at `/tmp/sdcard`). **Gap:** no guarded folder/file playback helper. Native touchscreen file playback is a different path. |
| Favorites | 6800 | Empty state shown. Explicit current-track favorite on/off and V2.57 favorite-index selection/readback are tested. No general batch favorite-by-ID helper or favorite play-all helper. Empty screenshot does not establish those operations. |
| Custom Playlist and New Playlist dialog | 6801–6802 | Empty state, plus button and name/confirm/cancel dialog shown. HTTP create/rename/add/remove/delete and guarded whole-list/index playback are tested; this image does not prove creation succeeded or show populated-list menus. |
| Mini-player | 6795–6801 | Track/artist metadata, play/pause and next have physical captures and emulator tests. Placeholder artwork alone does not prove cover retrieval failed. Opening the full player is frontend navigation, not a new protocol command. |
| PEQ, off/save, graph, master and band controls | 6803 | `eq_type`, `peq()`, `set_peq()` and `eq_master_db` exist; first user preset, one band and master gain are integration-tested. **Partial coverage:** exact app preset selection, Save sequence and remaining editor fields are not shown/captured here. |
| Update / Reset music library | 6804 | `scan_library()`, cooperative cancel and dedicated `reset_library(confirm=True)` are tested. Actual app reset command sequence is unobserved; do not reset a personal library merely for this audit. |
| Gain | 6804–6805 | High/Low choices, High checked. Follow-up stock UI tracing establishes **0 Low / 1 High**, both TCP/WS values and SQLite tested. The screenshot alone does not establish that mapping or measure dB. |
| Bluetooth codec, SPDIF, balance, DRE | 6804 | Existing settings helpers/tested control paths; five source-codec choices already physically captured. SPDIF appears off and DRE on; balance/codec subpages are not included in this batch. No claim about physical audio/DSP output. |
| Filter | 6806, 6816, 6817 | Six choices; slow minimum-phase checked. Physical walkthrough maps all six app rows to helper 0..5 / wire 9..14 and confirms restoration. Subsequent English screenshot supplies full labels, but rows 5/6 both say “Reference super slow roll-off” despite different codes. Russian endings remain clipped. [Physical mapping](REMOTE_SETTINGS.md#physical-fiio-control-filter-mapping-2026-09-16). |
| User Feedback | 6804 | Entry visible only. No implementation; classify as app/support functionality unless capture demonstrates a device operation. Destination and submitted data unknown. |

PEQ screenshot: visible scale -24..+12 dB, master control, graph labels 31..16k,
zero-valued gains/frequencies and an off-labelled button. The view is clipped at
the right/bottom; do not derive the total band count from visible sliders. The
ten-band contract comes from protocol evidence. Zero frequency/Q readback with EQ
off is already known; this image alone neither diagnoses a bug nor justifies
relaxing setter validation. The safe helper still requires a user preset before
editing, and only exposes validated peaking filter type 0.

Repeated/similar album and genre labels and multi-artist labels are visible.
Preserve returned rows/positions and literal names; do not deduplicate, trim or
split labels based on screenshots. Displayed similarity cannot establish whether
underlying tags differ, nor prove an index defect.

Follow-up emulator validation on 2026-09-16: guarded `play_genre` (including
genre-scoped album), `play_folder` and `add_selection_to_playlist` now cover the
genre/folder playback and bulk-add gaps above. Fresh V2.57 TCP/WS and direct/proxy
tests are recorded in [LIBRARY_BROWSING.md](LIBRARY_BROWSING.md). This does not
identify the app's exact commands from screenshots. The initially deferred
physical genre capture has now arrived; see the follow-up below. The app's
folder selection, Delete workflow and folder-to-playlist expansion remain unvalidated.

The third batch below supplies genre/album batch toolbars and PEQ selection/save
screens. Folder contents and individual-item menus remain unseen. Request
targeted TCP/HTTP captures for concrete gaps, not repeat screenshots already supplied.
The later `2026-09-16-192141` physical filter capture plus `IMG_6816.PNG` closes
the six-row label/code mapping: reported actions 3→4→5→6→1→2 match setters and
replies, followed by fresh restoration readback. HAR is empty; PCAP carries the
evidence. [Timeline, fixture and limits](REMOTE_SETTINGS.md#physical-fiio-control-filter-mapping-2026-09-16).
Do not sweep unknown codes or change physical gain with active listening.

### Genre hierarchy, batch actions and PEQ: third batch (2026-09-16)

Owner-supplied `IMG_6807.PNG`–`IMG_6815.PNG`, 18:12–18:15, continuation of the
physical DISC audit. These are screenshots, not evidence that any shown action
was submitted or persisted. Versions are not displayed. No raw screenshots or
personal library contents are committed.

Owner decision, 2026-09-16: **PEQ is a separate workstream**, tracked in
[issue #9](https://github.com/eudj1n/snowsky-disc-qemu/issues/9). Record its screens
here, but do not request further PEQ captures or implement its missing workflows
as part of the current library audit. Existing PEQ helpers/tests remain intact.

| Screen/control | Screenshot | Coverage and interpretation |
| --- | --- | --- |
| Genre detail → album rows | 6807 | Six visible album-like rows, each with its own track count. Matches the shape expected for `style/album`, but only traffic can establish the actual request/filter. Genre-to-album-to-track browsing must not be flattened into a genre song list. |
| Album detail → tracks, Play all | 6808 | Matches existing named-album playback concept. A genre-scoped album selection may need both genre and album; do not assume the generic album-name helper preserves the genre restriction, especially for repeated names. |
| Select all / Cancel / per-row selection | 6809–6810 | Two red selected rows, others outlined. No command is inferred merely from selection marks. The same visual toolbar appears at album-group and track levels. |
| Add to Playlist | 6809–6810 | Existing `add_to_playlist()` accepts category/filter/ranges, but integration covers all-song ranges, **not** expansion of selected genre-album groups or genre-scoped track ranges. Destination-list picker and resulting contents are not shown. Capture exact category, filters and positional range semantics before claiming parity. |
| Delete | 6809–6810 | Visible at both levels; confirmation and source-file scope unknown. Client deliberately does not expose arbitrary category/source batch deletion. Do not substitute custom-playlist removal (`delete_source: 0`) or issue physical deletes just to obtain evidence. |
| Save this PEQ → device / local data | 6811 | Separate destinations are now visible; device option is red. Backend has device band/master setters, but the app's Save transaction and target-preset choice remain unknown. Local preset storage/import/export/sync is not implemented; neither option's actual writes are established by this dialog. |
| EQ Device presets | 6812 | Off, ten named factory tiles, User 1..10 and **BYPASS** are visible. Helper has numeric `eq_type` values and user slots, but no validated full label mapping. **BYPASS is a separate visible choice, not proven equivalent to Off or any guessed enum.** First-user/off acceptance is not coverage of every preset. |
| Auto EQ | 6813 | Headphone measurement and target-curve selectors, Random / Save as / Reset, response graph and frequency/gain/Q rows. No curve catalog, matching algorithm, generation/save or device-application helper. Existing `set_peq()` can send validated bands, but does not implement Auto EQ. The graph's ±18 scale is not proof of accepted device gain limits. |
| Local | 6814 | Sign-in-for-sync text, My settings and Download sections; no entries shown. Storage and synchronization behavior unverified; do not assume this tab is the player's ten user slots. No account login or external sync requested. |
| Selected | 6815 | Empty view with a truncated password/retrieval prompt. Meaning and endpoint unknown; this is not evidence of TCP 12100 authentication, an unlock password or a firmware secret. |
| Official | 6814–6815 | Tab label only; its contents are not provided. Do not treat the blank Selected screen as the official catalog. |

The genre heading says “total songs: 6” while the six rows look like albums
with larger individual counts. Record the nesting, not an inferred six-track
library or a diagnosed index defect; wire schemas/counts must resolve the units.
Outlined checkmarks are also used on unselected batch rows. As with the theme
screens, a tick outline alone is not reliable proof of an enabled setting.

The requested genre capture is now analyzed below; no repeat is needed for
the observed hierarchy and scoped-album commands. Folder selection and
root-category Play all remain unobserved. No deletion, media reset, cloud login
or preset overwrite is needed to investigate those selectors.
Separate later library captures can cover adding a few rows to a disposable
custom list. PEQ captures/changes belong to issue #9 when explicitly resumed;
do not combine them into the current library trace.

### Physical genre flow (2026-09-16)

Inputs: `2026-09-16-185016.pcap` and `.har`, supplied for the previously requested
physical genre workflow. Firmware 257 is confirmed by fresh settings; app version
is not reconfirmed. [Sanitized fixture](../tools/fixtures/fiio_control_ios_genres.json)
contains source hashes and frame references; raw captures/artwork stay outside Git.

- PCAP has 13 device HTTP requests versus 3 in HAR. Browsing proceeds through
  `style` → `style/album` → `style/album/song`; the last carries both genre/album.
- Scoped-album indexed and whole-list playback match our type-8 helper. Position
  15 selects the 16th of 19 tracks; two Next commands select 17/19 and 18/19.
- Whole-genre Play all uses type **8 with an empty album**; physical readback
  shows a 54-track queue. Follow-up disposable TCP/WS comparison with type 10
  passes in modes 0/4, and the helper now uses the captured form for Play all.
  Indexed whole-genre selection retains type 10; it is not covered by this capture.
- The first genre attempts six CUE entries with zero duration, loading state and
  repeated `a60a/000D`, without playback progress. Do not call that successful EOF
  or infer a decoder/file defect without further evidence. Ordinary tracks in the
  second genre do reach playing state and progress.
- No folder-track selection, bulk mutation or root-category Play all is present.
  A root folder GET alone does not validate folder playback.

See [timeline, client differences and reproduction](LIBRARY_BROWSING.md#physical-genre-flow-2026-09-16).
Firmware-free tests cover matching HTTP filters/scoped selectors and the captured
Play-all form, keeping indexed genre selection on its independently tested path.

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
