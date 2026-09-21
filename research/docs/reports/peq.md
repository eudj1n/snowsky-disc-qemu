# DISC PEQ investigation (V2.57)

[Issue #9](https://github.com/eudj1n/snowsky-disc-qemu/issues/9) resumed by the
owner on 2026-09-17. The existing [settings contract](../../../docs/protocol/remote-settings.md#peq-bands)
remains valid. This work separates device controls from FiiO Control's local
preset storage, Auto EQ computation and account/catalog services.
Physical captures resumed later on 2026-09-17 with the preset/BYPASS sequence
below. The later device-edit/Save/Reset capture is also analyzed here; local
Save and Auto EQ remain separate checks in this workstream.

**Current scope accepted for PR #20 / `2.x` on 2026-09-19.** Remaining Auto EQ,
editor and storage investigations stay as optional backlog in #9, not merge
blockers. No new device action is requested; the recovery limit below remains.

**Paused by owner after capture `225312` on 2026-09-17; continue later.**
Preset/device/local workflows are analyzed below, including the reproduced
Local Apply format mismatch. Auto EQ Save screenshot 6851 shows nonzero bands
and master −4.6, but its write/readback and final cleanup were not captured.
Current physical Custom 10 state remains unknown. On resumption, read it after
reconnect **before Reset**, without replaying Save; then reset/readback/Off.
Share/login is explicitly deferred. No action or scheduled follow-up now.
See the [pause handoff](../status.md#paused-by-owner--peq-checkpoint-2026-09-17-after-capture-225312).

## Static device contract

Fingerprint: V2.57 stock `mq_player` SHA-256
`a5a6740435758bb3f3d008a4306c93a463c6634318957bbf32086bd7b00fabbc`.
The local analysis copy matches after normalizing only the reviewed key patch.

`4ef174` maps network preset codes to `SYSCONFIG.EQ_TYPE`:

| Wire | Stored | Stock device label |
| --- | --- | --- |
| 255 | 0 | Off |
| 0 | 1 | Jazz |
| 2 | 2 | Rock |
| 4 | 3 | R&B |
| 6 | 4 | HIP-HOP |
| 1 | 5 | Pop |
| 3 | 6 | Dance |
| 5 | 7 | Classical |
| 8 | 8 | Retro |
| 9 | 9 | Sibilance attenuation 1 |
| 10 | 10 | Sibilance attenuation 2 |
| 160..169 | 11..20 | USER1..USER10 |

Stock labels come from `set_menu/equalizer.json`, selected by UI page `4670ac`
using explicit row values 0..20; callback `466b7c` stores that value in `8e1720`.
These are device labels, not a transcription of the iPhone tiles. Physical
capture now identifies the app's BYPASS as 240 (`00F0`), but there is no BYPASS
case in this setter. Unknown values leave the stored selection unchanged while
the handler echoes the supplied value. Do not expose 240 as a supported device
mode or send guessed codes 7/254; see the captured/static distinction below.

`45e000` selects the device mode; user slots call `45d66c`, which loads their
saved parameters or initializes defaults. `4ef774` accepts JSON band writes;
`45e9e4` applies positions and explicitly sets filter type to zero, then `434fb8`
serializes the current profile. `434c94` updates `PARAMS_JSON` by `STYLE_PRESET`;
`434bc0` updates `MASTER_GAIN` with one decimal. `4f022c` → `45ed2c` persists
master gain. The physical Save-associated `0626` is a no-op in this build;
parameter writes already persist, as detailed below.
Keep the public band helper's type-0 restriction and conservative bounds.

## Disposable acceptance

```sh
CI_SCENARIO=peq FW_VERSION=2.57 \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The scenario checks supported preset codes against SQLite, then edits first and
last bands in each of ten user slots, verifies unchanged other bands/slots,
master gain, re-selection and restoration through both TCP and WS. It performs
no database writes. A failure aborts rather than retrying a mutation; the guest
and volume are disposable. Selection of a previously absent user slot can itself
initialize a saved profile, so this scenario must not target a personal device.
Its immediate first-use reply has Q=0.71 while the newly serialized database row
already stores Q=0.7. A later selection reloads Q=0.7. The acceptance therefore
backs up a fresh reloaded profile and requires exact restoration of that baseline;
it does not pretend the original transient precision survives serialization.
Validation results are recorded in [the research tracker](../status.md).

## Physical preset/BYPASS capture (2026-09-17)

Owner-supplied `2026-09-17-203157.pcap`, SHA-256
`e4344cc33bdb4b1fa67859f9d85252d7de06465c5c0f6883c0232fc271ca5945`.
Classic little-endian PCAP, BSD NULL link headers, 1,855 packets over 50.472 s,
none capture-truncated. Both directions of the selected TCP streams have
contiguous sequence coverage and complete Link frames. Of 316 packets on
12100, an earlier connection carries one unacknowledged `0690/0000` (packet
1447); the new connection starts with `0599` / `a599/0306`. Its `a501` reports
`soc_version=257` (1464). The 51 HTTP 12103 packets contain one cover-image GET,
not a PEQ save. Raw traffic/artwork remain outside Git.

Initial `0639` receives `a639/00FF` (1466, Off). Subsequent selections receive
matching `a639` notifications and fresh band/master responses:

| Selection order | Wire values | Evidence |
| --- | --- | --- |
| Ten factory presets | `0000,0001,0002,0003,0004,0005,0006,0008,0009,000A` | Stock labels: Jazz, Pop, Rock, Dance, R&B, Classical, HIP-HOP, Retro, Sibilance attenuation 1/2. Exact ordered app-label spelling not supplied. |
| USER1–USER10 | `00A0`–`00A9` | All ten receive band/master replies. |
| BYPASS | `00F0` | Owner confirms this was the penultimate selection. Request 1813 / reply 1815, 20:32:42 local (UTC+05:00). |
| Off | `00FF` | Request 1825 / reply 1827, 20:32:44. Matches initial mode, but no later fresh `0639` or reconnect establishes persisted restoration. |

This establishes **BYPASS's app command**, not a separate firmware bypass mode.
Fingerprint-checked `4ef174` stores the raw request at `898a0c`, but only the
21 reviewed values change the selected-mode byte `83a77c`. `00F0` falls through
`4ef314` → `4ef1b8` without changing that byte. The common path calls `45e000`
with the previous mode, reports that mode locally, echoes the raw request to
TCP and persists the unchanged selection. Thus this path reapplies USER10 in
this sequence; its `a639/00F0` is insufficient evidence of a DSP bypass.

Physical readback is consistent with that reload: USER10 has Q=0.71 in all ten
bands (1811); after BYPASS it has Q=0.70 (1823), with unchanged frequencies,
zero gains/filter types and 0 dB master. Final Off retains those same reported
parameters (1835). Readable bands alone therefore do not prove EQ is enabled.
There is no `0678` band edit or `0630` master write in this capture. Selecting
User slots can initialize their storage, so this is not proof that all saved
profile rows were untouched or restored.

Sanitized [fixture](../../../controller/tests/fixtures/fiio_control_ios_peq_presets.json)
retains relevant request/reply frames and final profile reads, without factory
curves or personal data. The settings regression compares supported TCP/WS
setters with the capture, decodes the Q change and ensures 240 remains rejected
for writes despite being readable in an echoed reply. Hardware audio and
persistence across reconnect are not established by this capture.

Validation: all 19 settings tests and the full firmware-free suite passed
(Python, 37 JavaScript tests, shell syntax and four shim builds), using the
existing local `diskos-qemu-ci` image. No new guest or physical mutation was run
by the agent for this capture analysis. On 2026-09-17 the owner approved USER10
as the disposable slot for the next device-Save capture; capture fresh reloaded
bands/master before editing, then restore and verify that baseline and Off.

## Physical device editing, Save and Reset (2026-09-17)

Analyzed newest first, as requested by the owner. Both PCAPs have complete
records, no capture-truncated packets, contiguous selected TCP byte streams and
complete Link frames. Each has one HTTP cover-image GET and no PEQ HTTP request.
Their fresh `a501` snapshots report `soc_version=257`.

| Capture | SHA-256 | Local time (UTC+05:00) | Packets |
| --- | --- | --- | --- |
| `2026-09-17-214316.pcap` | `5dedf190b726ff51dbff85b378efe04e6267096bcb4a6a1d0000efd7305c5b39` | 21:43:17.374–21:45:20.750 | 1,476; 94 TCP 12100, 51 HTTP 12103 |
| `2026-09-17-214151.pcap` | `4145608697da60a36bbb1c23f9130c3a3ce83e67ddbc3e6e9573c4ff7c75c6ae` | 21:41:51.572–21:43:11.896 | 1,518; 84 TCP 12100, 53 HTTP 12103 |

The earlier file is a separate preceding edit/reset sequence: USER10 → Off →
USER10, one first-band frequency write requesting 2036 Hz / 0 dB / Q .70,
then Reset and Off. It has no master write or `0626`. The captures do not
overlap; the later file first attempts a USER10 selection on the old connection
without a Link reply, then completes a new handshake and reads Off.

Latest-file timeline (packet numbers are local to `214316`):

| Time | Packets | Observed operation |
| --- | --- | --- |
| 21:43:35.548 | 309–343 | USER10 selected; all ten default frequencies, zero gains/master and Q .70 read back. |
| 21:43:53.522 | 814 | `0678` compact first-band write, gain −3.4 dB, 32 Hz, Q .70, type/position zero. No immediate TCP band reply. |
| 21:44:10.944 | 832 / 834 | Master `0630/FFC3` → `a629/FFC3` (−6.1 dB). |
| 21:44:26.916 | 933 | `0626/0000`, associated with Save → device by the owner's walkthrough. No slot identifier or reply. |
| 21:44:56.537 | 943 / 945 / 947 | Reset `0675/0000`; all ten default bands returned with gain zero, Q .71 and master zero. |
| 21:44:59.838 | 949 | Another `0626/0000`, after Reset. |
| 21:45:04.655 | 969–987 | Off selected; returned bands still have Q .71 and zero gains/master. |
| 21:45:09.031 | 1414–1424 | USER10 selected again; default bands now Q .70, gains/master zero. Matches the fresh pre-edit baseline. |
| 21:45:17.237 | 1464 | Third `0626/0000`. No later Off selection is captured. |

Screenshots corroborate the UI: `IMG_6830.PNG` shows Custom 10, master −6.1
and first-band gain −3.4; `IMG_6831.PNG` shows 32 Hz, Peak, −3.4 dB and Q .7;
`IMG_6832.PNG` shows zero visible gains/master after Reset. The owner confirms
choosing **Save → device**, then navigating back without disconnecting. No
target-slot dialog is confirmed. No fresh band getter between the edit and
Reset proves physical edited-band readback; screenshots alone do not establish
device persistence. The final captured selection is USER10, not initial Off.
The editor displays frequency bounds 20..20k Hz, gain −24..12 dB and Q .25..8.00;
Peak is the selected filter. These labels do not establish wire validation
bounds, every filter option or physical DSP behavior.

### Compact write and command semantics

The captured first-band request is `0678001e00000000FFDE0020004600`.
After the four-character extension `0000`, the handler consumes an 8-byte
ASCII-hex record: **filter type, position, signed BE16 gain/10, BE16 frequency,
BE16 Q/100**. A trailing `00` is present in this app request. Fingerprinted
`4ef774` detects hex input, takes `floor(hex_length / 16)` records, converts
them to JSON and calls the existing persisting `45e9e4` path. The final byte is
outside that one record; do not generalize it into a second range bound or
count. Gain sign extension is explicit at `4efed0`. Hex-format band replies
are directed to local UI (`4ddaec` destination 1), whereas JSON writes notify
TCP (destination 0); a fresh getter is needed to verify this physical edit.
The public helper keeps its validated JSON encoder and type-0 restriction.

`0626` is admitted and dispatches through `414920` / callback slot `83a518`
to **`4ef604`, which only returns zero**. There is no extra device save, slot
copy or transaction in that handler. The app's Save UI can still do local
work; the capture does not establish that behavior or a local file format.

Reset `0675` dispatches through `414900` / `83a514` to `4ef498` → `45ee30`.
The latter is guarded to stored User modes 11..20, resets ten bands plus master,
and serializes the current profile via `434fb8`. Reset returns fresh band and
master notifications. It is not a global settings/library/factory reset.
Q=.71 immediately versus persisted/reloaded .70 is the same serialization
behavior seen earlier. The physical sequence includes `0626` after Reset;
the static no-op alone distinguishes that button from the persisting reset.

Sanitized [fixture](../../../controller/tests/fixtures/fiio_control_ios_peq_save_reset.json)
keeps only PEQ/handshake frames and screenshot hashes. Regression checks pin
compact signed fields, existing JSON/master encodings and complete reset reads.
`CI_SCENARIO=peq` also exercises the captured raw commands on disposable USER10:
readback/SQLite before Save, actual reconnect, Save no-op, reset of first/last
band changes plus master, persistence without Save, reselection/reconnect,
other-slot isolation and restoration of the original profile/selection.

Validation: fresh disposable V2.57 `peq` passed all previous 21-code/ten-slot
checks plus this workflow through **TCP and WS**, including immediate SQLite
persistence, actual reconnect before Save, Save no-op, Reset without Save and
exact baseline restoration. Stack and volume cleanup completed (exit 0).
Firmware-free checks passed **324 Python / 37 JavaScript tests**, shell syntax
and four shim builds. Local logs are ignored under `work/peq-captures/`:
`save-reset-acceptance.log` and `save-reset-unit.log`. The obsolete local image
first failed to import `firmware.profile` before any guest launch; building the
current `snowsky-disc-qemu-ci` image resolved the environment issue. No shared
runtime behavior changed and no unrelated full/idle acceptance is claimed.

## Physical local Save, incomplete Apply capture (2026-09-17)

`2026-09-17-215948.pcap`, SHA-256
`6eb208b8e179aed0c592515c4e41c4745bbec68a4d48efcf92f022bd4df08322`,
runs **21:59:48.665–22:02:48.064 UTC+05:00**: 2,805 packets, none truncated,
123 on TCP 12100 and 55 on HTTP 12103. Selected TCP byte sequences are contiguous
and all Link frames complete. Initial handshake and `soc_version=257` are
present. There is one cover-image HTTP GET; no device PEQ HTTP request.

Screenshots `IMG_6833`–`6837` show a 32 Hz / Peak / Q .7 first band with gain
−3.5 dB, master −6.5 dB, and **Save this PEQ** with tuning name `p1` and
description `p2`. The input counters display 20 and 200 limits, without proving
their character/byte semantics. Local → My custom then shows that named card,
its curve, an Apply button and an overflow menu. “Login to synchronize” remains
visible; neither credentials nor cloud synchronization were tested. The stored
file schema, export format and persistence across an app restart are unknown.

Device evidence:

| Time | Packet(s) | Observation |
| --- | --- | --- |
| 22:00:04.929 | 611 | Fresh USER10 baseline: ten default frequencies, gain/master zero, Q .70. |
| 22:00:22.819 | 960 | Compact `0678` requests first-band gain −3.5 dB, 32 Hz / Q .70. |
| 22:00:33.917 | 972 / 974 | `0630/FFBF` → `a629/FFBF`, master −6.5 dB. |
| 22:01:18.569 | 1131–1141 | Off selection followed by getters returns the edited band and master. |
| 22:01:55.510 | 2050–2060 | USER10 reselected; fresh getters confirm −3.5 dB / −6.5 dB and otherwise unchanged ten-band baseline. |
| 22:02:25.780 | 2086–2090 | Reset, then zero band gains/master, default frequencies and immediate Q .71. |
| 22:02:37.850 | 2586–2596 | Off → USER10 completes; fresh reads match the original baseline, including Q .70. |

There is only one band write, one master write and one Reset in the entire
capture, with **no `0626`**. Thus the screenshot-associated local Save is distinct
from the device Save action, and does not add a captured device mutation. The
existing edited profile survives reselection. This also supplies the previously
missing physical edited-band readback and Reset-without-Save readback; it does
not establish a true physical disconnect/reconnect.

**Apply remains uncaptured:** `IMG_6838` and `IMG_6839` show 22:03, after the PCAP
ends. Both show −3.5 dB / −6.5 dB; `6838` has normal frequency labels while `6839`
shows `32,32,64,125,250,500,1000` in the visible band columns. No Apply request,
applied-profile getter or final cleanup/Off is present in the supplied PCAP.
Do not classify the duplicate/shifted frequency labels as either device profile
corruption or merely an app display defect without the missing device readback.
Do not claim the last captured reset baseline describes the later screenshots.
The owner suspects a packet/time capture limit and offered to increase it for
a short follow-up; the cause of the cutoff is not confirmed. No later file has
been supplied. Capture only a fresh USER10 reset baseline, existing `p1` Apply,
Off → USER10 full readback and reset/Off cleanup.

The [sanitized fixture](../../../controller/tests/fixtures/fiio_control_ios_peq_local_save.json)
retains initial, edited and reset profile reads, signed writes, request-tag
inventory and screenshot hashes. Its regression verifies exact untouched bands,
master conversion, no device Save command and complete baseline restoration
within the captured interval. Raw screenshots/capture remain outside Git.
Validation: **325 Python / 37 JavaScript tests**, shell syntax and four shim
builds passed (`work/peq-captures/local-save-unit.log`, ignored). This follow-up
adds evidence/tests only; the preceding disposable `peq` acceptance remains the
runtime result, and local Apply is not claimed tested.

## Physical Local Apply and V2.57 format mismatch (2026-09-17)

Follow-up `2026-09-17-221148.pcap`, SHA-256
`f21288d4a6ba5e57920bf60363c4c0a6ddc2b6263f745aefaded75f44e82b355`,
covers 22:11:49.282–22:12:48.973 UTC+05:00. All 1,942 packets are complete;
130 use TCP 12100, 54 HTTP 12103 (one cover-image GET). Selected stream byte
coverage is contiguous and Link frames complete. Handshake and V2.57 snapshot
are captured. `IMG_6841.PNG` shows Custom 10, first visible gain −3.5 dB,
master −6.5 dB and normal visible frequency labels; no slot dialog is supplied.

After Reset → Off → USER10, the fresh baseline (1043) is the ten default bands,
Q .70, zero gains/master. At **22:12:22.577**, Local Apply sends:

1. `0630/FFBF` (1423): master −6.5 dB, acknowledged in `a629/FFBF` (1427).
2. `0678` (1425), about one millisecond later: extension `0000`, then **72 hex-encoded
   bytes with range 0..9 and ten 7-byte band records**, exactly the `a628` layout.
   Interpreted as that layout, its intended curve is first band 32 Hz/−3.5 dB,
   nine unchanged default bands, all Q .70/type zero.

There is no intervening slot-selection request: the selected device slot is
USER10. Nor is there a `0626` Save. However, **there is no fresh band getter or
reselection between Apply and Reset at 22:12:33.391**. The screenshot therefore
does not prove that the device received the intended ten-band profile.

This payload conflicts with the stock setter's compact decoder described above:
`4ef774` treats it as **nine 8-byte records**, not a range and ten 7-byte records.
The leading `00 09` becomes filter type 0 / **position 9**, moving the intended
first band's 32 Hz/−3.5 dB to the last band. Subsequent records become misaligned.
The earlier single-first-band edit happened to align type/position zero and its
seven parameter bytes; that success did not establish the bulk range format.

Replaying the exact captured Apply on disposable V2.57 exposes two stages in
fresh band readback and SQLite:

- Immediately after Apply, the first band is **32768 Hz / +6.2 dB / Q 179.2**,
  and the last is **32 Hz / −3.5 dB / Q .70** instead of 16000 Hz / 0 dB.
  Bands 1..8 are unchanged; master is correctly −6.5 dB.
- After Off → USER10, the database loader `45d66c` resets the invalid first
  band to **32 Hz / 0 dB / Q .71**, persisted as Q .70. Its explicit invalid-band
  branch restores that band's defaults and calls `434fb8` to persist them.
  The valid but misplaced last-band cut survives, leaving two 32 Hz bands.

The two exploratory test failures conflated these immediate and reselected
states. The final regression pins each stage separately, without widening
tolerances. This is a reproduced app/firmware protocol
incompatibility, not a physical DSP measurement or direct physical post-Apply
readback. It is consistent with the earlier duplicate-frequency screenshot but
does not prove that screenshot's complete underlying state.

Physical cleanup **is** observed: Reset returns ten default bands and zero
master; Off → USER10 reads the complete original baseline again (1806/1804).
Final Off receives `a639/00FF` (1921), with zero-master/default-band reads after
it (1927/1929). No post-cleanup reconnect is captured.

The [sanitized fixture](../../../controller/tests/fixtures/fiio_control_ios_peq_local_apply.json)
keeps exact Apply commands, reset/baseline/final-Off reads and screenshot hash.
The public client retains **JSON `set_peq()`**, encoding explicit positions
and all ten intended bands; it must not replay this malformed bulk hex payload.
Disposable acceptance checks wrong-layout persistence, Reset recovery, correct
JSON application of the intended profile, other-slot isolation and restoration.
The complete focused `peq` scenario passed on TCP and WebSocket with disposable
stack cleanup (exit 0, ignored `work/peq-captures/local-apply-final.log`).
Firmware-free checks passed **326 Python / 37 JavaScript** tests, shell syntax
and four shim builds (`local-apply-unit.log`). No shared runtime change or
unrelated full/idle acceptance is claimed.
No public app-local storage/export format is inferred from the wire payload.

## Local preset overflow menu (2026-09-17)

`IMG_6842.PNG` (22:25, SHA-256
`286cf4c7a9e181617b2416aa08a827c91c19e4cefbdc79eaeb64eeb09e31db3f`)
shows the Local → My custom card `p1`/`p2` with its overflow menu open.
The exact visible labels are **Deleted**, **Share**, **Rename**. The screen
still shows Apply and “Login to synchronize”. This is menu evidence only:
no deletion or rename result is supplied. The owner subsequently reports that
Share displays **“Please login first”** and explicitly excludes this flow from
the task. Share/account work is deferred with issue #11; do not request login
or further Share captures. File export, retrieval codes and publication format
remain unknown, not established by the login prompt.

## Auto EQ measurement selector (2026-09-17)

`IMG_6843.PNG` / `IMG_6844.PNG` show the headphone measurement selector open
without an account prompt. The owner reports thousands of entries; no exact
catalog count is established. The initial view includes Flat and named models
with source attribution (e.g. HypetheSonics, Innerfidelity and Regan Cipher).
Searching `ft1` shows separate **FiiO FT1 by FIIO** and **FiiO FT1 by oratory1990**
rows, plus FT1 Pro and FT13/FT15 variants. Preserve model/source distinctions;
do not deduplicate by model name or infer the search algorithm from one query.
These screenshots establish selection UI, not a bundled/downloaded catalog,
an upstream dataset identity, generation algorithm or device application.
No full catalog walkthrough is needed.

`IMG_6845.PNG` shows the target selector: Flat, AutoEq in-ear,
crinacle EARS + 711 Harman over-ear 2018, Diffuse Field 5128 (-1 dB/oct),
Harman in-ear 2019, Harman over-ear 2018, HMS II.3 AutoEq in-ear and
HMS II.3 Harman in-ear 2019. The owner reports a large list without search;
these are visible examples, not an exhaustive inventory. Names do not prove
numerical curve identity or compatibility with a particular measurement rig.

Next bounded capture uses **FiiO FT1 by FIIO + Harman over-ear 2018** as a
repeatable protocol fixture, not a listening recommendation. Start capture
before selecting USER10 and the pair, observe the resulting screen, then open
Save as and capture its dialog without confirming a destination. Do not use
Random or assume selecting the pair is purely local; generation and device
writes remain to be distinguished from the traffic. Any account prompt ends
that branch under the owner's existing exclusion.

Screenshot SHA-256:

- `IMG_6843.PNG`: `28d3c76ff3fed4d4ff716397a4f35ca0fe2ab0ed09e5c7b48c4720f4540769f6`
- `IMG_6844.PNG`: `6301b62b231c851381d8b52577e0cfaff6c9cf18dbb34f2cd1e174348a2c8237`
- `IMG_6845.PNG`: `539beae85062cca7db320eaf89935d378b2edc971fe33acc2e083ce1800db6ee`

## Auto EQ selection and Save as dialog capture (2026-09-17)

`2026-09-17-224117.pcap`, SHA-256
`206f78fa6bf7dcd7fcdba31ddbcdd9f4de61c01529c116f22c7996debd498d3d`,
covers 22:41:17.654–22:42:28.736 UTC+05:00: 977 complete packets, 40 on TCP
12100 and 53 on HTTP 12103. Selected TCP streams are contiguous and complete.
The V2.57 handshake reads USER10 (`a639/00A9`), zero master and all ten default
bands with Q .70. Last band read is at 22:41:26.223. The entire Link request
sequence contains only handshake/state reads; no `0690`, `0678`, `0630`,
`0626` or `0675` occurs. Device HTTP is one cover-image GET. Thus there is no
captured device PEQ write; no final post-selection readback or Off is claimed.

`IMG_6846.PNG` shows FiiO FT1 and Harman over-ear 2018 selected. The collapsed
model label omits the measurement author (the requested fixture was by FIIO).
Purple Headphone curve and green Result curves appear, but the red PEQ line
is flat at zero. Visible first four rows remain 32/64/125/250 Hz, gains 0.0,
Q .7. This does not establish calculated correction bands or explain what the
green Result represents; do not infer an optimization algorithm from the graph.

`IMG_6847.PNG` shows Save as opening **Save this PEQ**, with **Save to device**
checked, **Save to personal**, Cancel and Confirm. Confirmation was not part
of the requested capture; neither destination's behavior is established here.
There is no login prompt in the supplied dialog; this does not prove that
Save to personal works without an account. The screenshots show minute 22:42,
so exact alignment with capture end is not available from their visible clocks.

The [sanitized fixture](../../../controller/tests/fixtures/fiio_control_ios_auto_eq_selection.json)
keeps all nine app requests, relevant profile replies and screenshot hashes;
unrelated state, network identifiers and artwork are omitted. This is capture
evidence only, with no production change requiring a new firmware run.

The subsequent Random probe below resolves the selector behavior; do not repeat
that press to investigate saving.

## Auto EQ Random capture (2026-09-17)

`2026-09-17-224456.pcap`, SHA-256
`96b218b0199f14586873008aa76bf416ee914c3371ed6120093be010326d04ba`,
covers 22:44:57.111–22:45:27.585 UTC+05:00: 684 complete packets, 40 on TCP
12100 and 46 on HTTP 12103. Selected TCP streams are contiguous and Link frames
complete. The nine app requests and four relevant profile replies are byte-for-byte
the same as `224117`: handshake/state reads, USER10, zero master/default bands,
with one HTTP cover-image GET. No PEQ mutation or Save command is captured.
The last band read is 22:45:02.211; no post-action final read or Off is claimed.

After the requested single Random press, `IMG_6848.PNG` shows both selectors
changed to **Massdrop Nobel X** and **KRK SYSTEMS KNS 8400(Innerfidelity)**.
The latter appears in the target selector, despite being a headphone-model
name. Red PEQ remains flat at zero; the visible first four frequencies/gains/Q
remain 32/64/125/250 Hz, 0.0 and .7. Thus this observed Random action replaces
the selected measurement/target pair, with no evidence of nonzero correction
generation or device application. One trial does not establish its random
distribution, complete candidate pool or the meaning of the green Result curve.

The [sanitized fixture](../../../controller/tests/fixtures/fiio_control_ios_auto_eq_random.json)
records the request sequence/profile reads and screenshot SHA-256
`54d16410a6a01c340842f26fd8bbc76bd271bdcacd12d2452bb96d92aad08fbb`.
No production change or additional firmware acceptance is needed for this
read-only capture analysis.

Next capture **Save as → Save to device → Confirm** for the deterministic
FT1 by FIIO/Harman over-ear 2018 pair, using only approved Custom 10. If a slot
dialog appears, choose Custom 10. Capture the resulting screen and fresh device
profile via Off → Custom 10 before Reset. Then Reset that slot, repeat Off →
Custom 10 readback, and finish Off. This will distinguish possible save-time
generation/application from the currently zero displayed PEQ; do not promise
that Save generates bands or copy the known malformed Local Apply layout.

## Auto EQ Save result and interrupted connection (2026-09-17)

Owner reports a disconnect after step 4 (the Save-result screenshot) of the
requested Save-to-device sequence. `IMG_6851.PNG` shows Custom 10, a non-flat
curve, master **−4.6 dB**, and visible frequency/gain pairs:
29/+0.9, 135/−2.0, 277/−1.0, 307/+1.0, 424/+2.6, 674/−0.9,
1602/−2.5. Remaining bands and Q values are not visible. This is evidence of
nonzero values in the app, not proof of the persisted device profile or the
exact generation trigger/algorithm.

`2026-09-17-225312.pcap`, SHA-256
`b94145d096cad59bb4fd122792b4088e27ad9cb017c76395b7519d700457a73d`,
covers 22:53:13.092–22:54:01.069 UTC+05:00, 1,057 complete packets. Only 14
packets use TCP 12100; none use HTTP 12103. Two TCP handshakes complete and
send Link `0599/0000` at 22:53:54.984 and 22:53:58.356. TCP ACKs are captured,
but **no `a599` or any device application payload** arrives. The first client
sends FIN at 22:53:58.353; both connections receive RST at 22:54:01.065–.066.
Selected stream bytes are contiguous; there is no Save command, PEQ write,
profile read, Reset or final Off in this file. The original disconnect and
Save operation are not captured; do not equate absence of a write here with
Save failure. Capture/proxy behavior may affect connection events; no firmware
crash, app defect, timeout cause or reboot is established.

The [sanitized fixture](../../../controller/tests/fixtures/fiio_control_ios_auto_eq_disconnect.json)
keeps both Link requests, screenshot observations and SHA-256
`b0267ce5b35588e1a7f0aeb8ac1c95623118fa4f14ddc5f61d335d953534702f`.
No device restoration is claimed. Next restore connectivity and capture fresh
Custom 10 reads **before Reset**, without replaying Save or selecting a new
Auto EQ pair. Then reset only approved Custom 10, read it again via Off →
Custom 10, and finish Off. Stop if the app cannot reconnect; do not repeatedly
send Save or silently reboot to recover an uncertain mutation.

## Physical capture sequence

Use TCP 12100 **and** HTTP 12103. Keep raw PCAP/HAR/screenshots in ignored local
storage. Do not sign in or supply account credentials for these checks.

1. **Preset mapping — captured:** the trace above covers all supported codes and
   the owner-identified BYPASS/Off commands. Do not repeat the full preset sweep.
   Exact app-label spelling can be supplied separately without more mutations.
2. **Device edit/Save/Reset — captured:** owner-approved USER10 sequence above
   establishes the app commands and reset readback; fingerprinted code resolves
   immediate persistence and the Save no-op. No repeat full sequence is needed.
   Physical edited-band readback is now captured after reselection in `215948`;
   a true disconnect/reconnect remains unobserved.
3. **Local Save/Apply — captured:** local `p1`/`p2` card exists; Save adds no
   captured device mutation. Follow-up Apply reveals the bulk-format mismatch
   above; no repeat full Save/Apply capture is needed. Physical post-Apply
   readback remains absent, but exact packet reproduction establishes the
   V2.57 problem. Overflow offers Deleted/Share/Rename (`IMG_6842`); Share
   requires login per owner and is explicitly deferred. Storage/export schema
   and app-restart persistence remain unknown; no more Share capture is needed.
4. **Editor / Auto EQ:** owner confirms (2026-09-17) that Custom 10 → Advanced
   settings → Filter type offers **only Peak** in iOS FiiO Control 4.6.0.
   This matches the reviewed type-zero client/update path; it does not establish
   filter choices for other products or app versions. No repeat dropdown capture
   is needed. Record remaining units/displayed rounding,
   measurement/target choices, generation, Save as and explicit application to
   the disposable device slot. App-side generation and actual device commands
   require separate evidence. Keep unsupported bounds/types rejected meanwhile.
5. **Catalog scope:** classify Local, Selected/retrieval-code and Official from
   observed behavior. Account/cloud sync remains separate issue #11. A retrieval
   prompt is not device TCP authentication.

No claim of physical DSP response, exact app parity, Auto EQ implementation or
BYPASS equivalence follows from device readback alone.
