# Remote DISC settings and PEQ

These are stock FiiO Link commands, usable through `Client` and `WSClient`.
The local disposable V2.40/V2.57 tests exercise network readback and persisted
configuration. This establishes the control path, not physical DAC/DSP performance
or USB/AirPlay/Bluetooth audio compatibility. No physical settings were changed in
this investigation.

## Tested settings

`client.device_setting(name)` reads and `client.set_device_setting(name, value)`
sends a setting. The async WS methods have the same names. Setters do not promise
completion; query until the requested value appears. Firmware can send an event
before its SQLite save finishes.

| Client name | Read tag | Set tag / wire values | Independent persisted readback |
|---|---|---|---|
| `gain` | `064a` | `0649`, 0/1 | `SYSCONFIG.VOL_MODE` (the column name is misleading) |
| `dre` | `0813` | `0812`, 0/1 | `DRE_STATUS` |
| `filter` | `0603` | `0653`, **9..14** | `FILTER_TYPE`, 0..5 |
| `spdif` | `0824` | `0823`, 0/1 | `SPDIF` |
| `balance` | `0712` | `0713`, packed direction/magnitude; helper accepts -20..20 | `BALANCE_VOL`, packed wire value |
| `eq_type` | `0639` | `0690`, network preset enum | `EQ_TYPE`, a different enum |
| `eq_master_db` | `0629` | `0630`, signed 16-bit tenths of dB | `song.db.PEQ.MASTER_GAIN` |
| `work_mode` | `0607` | `0657`, 1 USB DAC / 8 local / 10 AirPlay | See [mode mappings](REMOTE_MODES_THEMES.md#work-modes) |
| `bt_source_codec` | `06d4` | `06d3`, 0..4 | `BT_CODEC`; preference, not negotiated codec |

Queries above use empty payloads. Setters use four ASCII hex digits. For example:

```text
0812000C0001     DRE on
0653000C000A     filter index 1 (Link value 10)
0690000C00A0     first user EQ preset
0630000CFFF6     master gain -1.0 dB
```

Filter readback can include both device 0..5 and network 9..14 values in successive
`a603` notifications. The client normalizes both to 0..5. Do not copy a database enum
into a network setter blindly. Filter names and gain levels in dB are not inferred
from numeric values.

EQ network **255 = off**, **160..169 = user presets 1..10**. Those user presets map
to database `EQ_TYPE` **11..20**. Other observed mappings (network → database):
`0→1, 1→5, 2→2, 3→6, 4→3, 5→7, 6→4, 8→8, 9→9, 10→10`.
Acceptance exercises off/current restoration and first user preset, not every preset.

## Channel balance

`client.set_device_setting('balance', value)` accepts integer **-20..20**:
negative = left (L), positive = right (R), zero = center, matching the stock UI.
`client.device_setting('balance')` returns the same signed UI scale. These are
attenuation steps, not percentages or signed dB values.

The stock wire format is **not two's complement**: high byte `00` = left,
`01` = right; low byte = magnitude 0..20. The getter replies with `a712` and
the setter also emits `a712`. SQLite stores the packed integer unchanged.

| UI/helper value | Setter frame | DAC attenuation relative to center (L, R) |
| --- | --- | --- |
| L20 / -20 | `0713000C0014` | (0, +20) |
| L1 / -1 | `0713000C0001` | (0, +1) |
| Center / 0 | `0713000C0000` | (0, 0) |
| R1 / +1 | `0713000C0101` | (+1, 0) |
| R20 / +20 | `0713000C0114` | (+20, 0) |

The client rejects out-of-range values, floats and booleans before sending.
It accepts either `0000` or `0100` as a center readback and writes canonical
`0000`. Unknown direction bytes/magnitudes are rejected, not silently normalized.
`0711` is a neighboring setting, **not** the balance setter.

The firmware adds the magnitude to the opposite channel's attenuation, leaving
the favored channel and master volume unchanged. The existing CS43131 viewer
model interprets each step as 0.5 dB, so 20 steps means 10 dB attenuation, **not
full muting**. DAC writes are clamped at 255. Tests use a non-muted baseline below
the clamp and verify the exact per-channel ioctl mirrors (`emu/dac-left/right`),
network readback, SQLite and restoration. This validates the emulator control
path; it does not measure physical analog output. PCM capture is pre-DAC and is
not expected to contain this attenuation.

### Static evidence and reproduction

Addresses below belong only to the fingerprinted stock builds. Use the native
`mipsel-linux-gnu-objdump` in the repository's Docker image on an extracted ELF;
do not execute unreviewed firmware or reuse addresses for another version.

| Layer | V2.40 | V2.57 |
| --- | --- | --- |
| `0712` / `0713` command-table entries | `82cf90` / `82cf98` | `8388f0` / `8388f8` |
| Getter / setter dispatch wrappers | `412b90` / `412bb0` | `414380` / `4143a0` |
| Callback slots | `82e6a4` / `82e6a8` | `83a464` / `83a468` |
| Network getter / setter callbacks | `4e5368` / `4e53a0` | `4ee4ec` / `4ee524` |
| Hardware balance setter | `4e0f20` | `4e9c68` |

V2.57 `mq_ui`: `458480` formats positive values with `R%d`, negative with `L%d`
and sends `0713`; `458568` clamps button changes to ±20; `458bd0` sets the slider
range to -20..20; `458ce0` decodes the packed state. In `mq_player`, `4e91a0`
reads packed state at `83a750` and emits `a712`. Setter `4e9c68` stores channel
offsets at config+13/+14, applies them through `4e9ad0` → `4e81a8`, emits `a712`
and persists configuration field 19 (`BALANCE_VOL`). No binary patch is needed.
V2.40 UI equivalents are `477a70` (slider event, `R%d`/`L%d`, `0713`),
`4781c0` (slider range ±20) and `4782d0` (packed-state decoder).

For example, inside the build image, with an extracted firmware at `$ROOTFS`:

```sh
mipsel-linux-gnu-objdump -d --start-address=0x458480 --stop-address=0x4586d4 "$ROOTFS/usr/bin/mq_ui"
mipsel-linux-gnu-objdump -d --start-address=0x4e9c68 --stop-address=0x4e9d24 "$ROOTFS/usr/bin/mq_player"
```

These example addresses are **V2.57 only**. Resolve file offsets via ELF PT_LOAD
segments, not a guessed constant VA offset.

## PEQ bands

`client.peq()` reads tag **0628** and decodes the response. `client.set_peq(bands)`
requires a selected user EQ preset and sends **0678**. It rejects edits while a
factory preset or EQ-off is selected.

Example setter payload, after the eight-byte frame header:

```json
0001[{"position":0,"frequency":1000,"filterType":0,"gain":"-1.0","qValue":"1.5"}]
```

The leading four hex digits are the **number of supplied bands**, not the preset
number. Positions are 0..9. All five fields are required by our client:

- `frequency`: integer Hz.
- `gain` and `qValue`: **JSON strings** in the wire payload. The stock parser checks
  for strings; a JSON numeric value is not equivalent. The Python helper accepts
  numbers and performs this conversion.
- `filterType`: only **0** is exposed; the tested stock update path sets type 0.

The helper bounds frequency to 20..20000 Hz, gain to -24..12 dB and Q to 0.1..20.
These are conservative client bounds, not a claim that every edge was audio-tested.

The `a628` response contains a four-digit extension (`0000`), followed by ASCII hex
encoding of bytes:

```text
first position (1 byte), last position (1 byte),
then for each band: gain (signed BE16, /10), frequency (BE16 Hz),
                   Q (unsigned BE16, /100), filter type (1 byte)
```

The full 0..9 response is **148 ASCII payload bytes**: 4 + 2 × (2 + 10 × 7).
Initial EQ-off responses on a fresh guest can contain zero frequencies/Q; they are
reported as observed, not replaced with invented defaults. Selecting a user preset
initializes meaningful bands.

Firmware rounding matters: Q 0.71 was later reported as 0.70, and persisted band JSON
uses decimal formatting. Editing one band serializes the whole current user profile;
do not promise exact preservation of sub-decimal precision. Acceptance uses exactly
representable Q 1.5 and checks frequency 1000 Hz, -1 dB band/master gain, network
readback and the `STYLE_PRESET=11` row. It restores the captured user bands/master
and original EQ mode through stock commands.

## Playback preferences (V2.57)

Our validated remote API supports only **reading** gapless, folder jump and ReplayGain.
The six setter tags below belong to the shared local UI/player protocol, but
**none is admitted by the stock TCP receive allowlist**. A registered callback is
not proof of network reachability. The WS bridge forwards TCP and cannot bypass
this restriction. No write-only setters are exposed by our client.

Local UI payloads use four ASCII hex digits. Binary switches use **0 = off,
1 = on**, independent of their row positions in the device menu.

| Setting | Local-only set tag | Local UI values | Remote readback | SQLite column |
| --- | --- | --- | --- | --- |
| `gapless` | `0647` | 0 / 1 | `0501` → `a501.gaplessPlay` (JSON boolean) | `PLAY_GAP` |
| `folder_jump` | `0687` | 0 / 1 | `0501` → `a501.folderJump` (JSON boolean) | `FOLDER_JUMP` |
| `replay_gain` | `0718` | 0 off, **1 album, 2 track** | `0501` → `a501.replayGain` (JSON number) | `SYS_REPLAY_GAIN` |
| `artist_class_type` | `0648` | 0 track artist, 1 album artist | No validated getter | `ARTIST_CLASS_TYPE` |
| `track_display` | `064d` | 0 / 1: album CD-number display | No validated getter | `TRACK_DISPLAY` |
| `list_oper_mode` | `064e` | 0 long-press index / swipe-left batch; 1 long-press batch / swipe-left index | No validated getter | `LIST_OPER_MODE` |

`device_setting()` reads the first three from a **fresh common snapshot**, returning
integers (switches normalized to 0/1). It rejects reads of the other three before
any network I/O. Do not send an empty payload to a setter to try to read it: that
could change the setting. Missing/unknown JSON values are errors, not defaults.
`artist_sub_album: 1` in `0501` is a fixed capability advertisement, **not** the
current artist-grouping choice. List operation mode has **two paired choices**,
not four independent gesture modes; its first menu row writes 1, not 0.

These local callbacks can update player configuration/SQLite, but TCP rejects
their tags **before dispatch**, even with callbacks populated in the running guest.
Our client rejects all six attempted setters before network I/O. Do not infer a
getter from a neighboring tag or echo the last sent value as an acknowledgement.

On 2026-09-16 the owner reported not seeing the requested Gapless/ReplayGain
options in FiiO Control. No additional phone capture was requested for this item;
that observation is consistent with, but not the proof of, the TCP restriction.

Examples (same methods are async on `WSClient`):

```python
client.device_setting('gapless')       # fresh 0501 snapshot; returns 0 or 1
client.device_setting('folder_jump')   # fresh 0501 snapshot; returns 0 or 1
client.device_setting('replay_gain')   # 0 off, 1 album, 2 track
# set_device_setting('gapless', 1) raises ValueError: read-only.
# device_setting('list_oper_mode') raises ValueError: unsupported setting.
```

### Static evidence

TCP receiver `4db020` calls `4dabc4`, which checks tag strings against the
111-entry pointer table at **`6d84e0`**, terminated by NULL at `6d869c`,
before parsing/enqueueing the command. The six tags below are absent. An invalid
tag clears the current receive buffer, so coalesced later valid frames can be
discarded too. Do not pipeline negative probes with read requests.
Admission is necessary, not sufficient: admitted `0426` still has a NULL handler.

Reproduce the allowlist without running firmware:
`python3 tools/inspect_link_commands.py /path/to/mq_player --version 2.57`.
The tool validates the full binary fingerprint (normalizing only the permitted
key patch), PT_LOAD mappings, count, strings and NULL terminator; it sends nothing.

Exact-build V2.57 `mq_player` **shared local dispatch** mapping:

| Tag | Dispatch table entry | Wrapper / callback slot | Callback |
| --- | --- | --- | --- |
| `0647` | `838cf8` | `4153e0` / `83a684` | `4f1e2c` |
| `0687` | `838c78` | `4151e0` / `83a62c` | `4f1c58` |
| `0718` | `838d10` | `415440` / `83a690` | `4f1f74` |
| `0648` | `838d00` | `415400` / `83a688` | `4f1ed0` |
| `064d` | `838c88` | `415220` / `83a634` | `4f1cf8` |
| `064e` | `838c90` | `415240` / `83a638` | `4f1d98` |

Callbacks store the low byte of the parsed argument at offset `+0x10`; they do
not validate the UI enum. These callbacks are not reachable via the six TCP tags.
Persistence goes through `43db60` with fields 25/24/58/56/61/67 respectively. `4eca24` restores runtime
configuration on boot. `424e8c` constructs the `0501` snapshot; `4d82b4` serializes
its boolean/numeric fields. Neither the latter's fixed `artist_sub_album` field
nor the neighboring local-UI `0604` path establishes a getter for the other three.

V2.57 `mq_ui` menus: `4581bc` (gapless), `46d1bc` (folder jump), `465620`
(ReplayGain), `460f54` (artist grouping), `467ecc` (CD-number display), `45e2ac`
(list mode). Selection callbacks `465540` and `45e1e0` establish the ReplayGain
enum and reversed list-row mapping. The UI command senders start at `4580ac`,
`46d0ac`, `4654fc`, `460e3c`, `467d60`, `45e140`: include the two instructions
**before** their stack prologue, which load the selected byte.

Reuse `ghidra/DecAt.java` on these entries after analysis; see `ghidra/README.md`.
Binary copies, projects and raw decompilation stay under ignored `work/`, not Git.
Do not reuse these addresses for another firmware.

### Validation scope

`ci/preferences_check.py` first checks the fingerprinted TCP allowlist. It reads
the three available settings through TCP and WS, independently comparing SQLite,
player configuration and runtime. For each of the six local-only tags it then
sends an individually identified negative probe requesting a **different** valid
value, confirms no configuration change and checks that fresh reads still work.
It verifies populated callback slots to rule out missing initialization. Volume
is unchanged. No database, guest-memory or firmware writes are used.

The initial candidate-setter test failed when changing gapless from 0 to 1:
the unchanged default had made writing 0 look successful. Following the receive
path established the separate allowlist; candidate public setters were removed.
This negative result is retained as regression coverage, not bypassed with patches.

Unit tests cover all accepted read values and reject missing/malformed fields,
unsupported getters and all six setters before I/O. Runtime coverage establishes
the three current-value reads and six rejected network writes, **not** local UI
persistence, gapless continuity, ReplayGain amplitude, folder transitions, catalog
grouping or actual list gestures. Only active V2.57 was tested for this addition.

## Remaining hardware checks and other stock commands

Static V2.57 callback registration must be checked against TCP admission:

| Area | Tags / current evidence |
|---|---|
| Work-mode audio | Three app-visible control transitions now have [acceptance coverage](REMOTE_MODES_THEMES.md); actual USB/AirPlay audio remains unvalidated |
| Bluetooth connection | All five source preferences now have [readback/persistence coverage](REMOTE_MODES_THEMES.md); negotiation and transmitted audio remain unvalidated |
| Physical button assignments | `0820`, `0821`, `0822` are absent from the TCP allowlist (static evidence). Existing physical-control tests cover local assignments, not remote setters |
| Playback preference effects | See the [validated control contract and limits](#playback-preferences-v257); actual audio/transitions/grouping/gestures are separate behavioral checks |
| Cover/lyrics preferences | `064b`, `064c` are local callbacks but absent from the TCP allowlist (static evidence); online retrieval not tested |
| Reset library | App UI exists; a dedicated safe library-reset command is not yet established. **0800 performs a broader factory reset**, including Wi-Fi and theme/song databases; it is not an appropriate substitute |

Getter-looking tags can be no-ops or send only local UI events; `0604`, for example,
did not yield a network response in the emulator. A function in the shared command
table is not proof of a usable remote feature.

## Reproduce

`ci/settings_check.py` runs TCP and WS against the disposable integration guest,
changes/restores balance, gain, DRE, filter, SPDIF and user PEQ, and reads SQLite without writes.
Balance additionally checks both channel-attenuation mirrors at center, ±1 and ±20.
Use `CI_SCENARIO=settings` with `ci/integration.sh` for an isolated focused run;
the full integration scenario includes the same checks.
`CI_SCENARIO=preferences FW_VERSION=2.57` runs read-only preference and rejected-write
checks separately; full V2.57 integration includes them too.
`tools/test_fiio_settings.py` pins wire examples, signed gain, binary PEQ structure,
validation and the user-preset guard.

Static V2.57 references: filter `4ee628`, network EQ type `4ef174`, PEQ getter
`4ef61c`, setter `4ef774`, band application `45e9e4`, JSON parser `4d98e0`, master
getter/setter `4f00a4`/`4f022c`, gain `4f182c`/`4f18e0`, DRE `4f1770`/`4f17cc`,
SPDIF `4f0ed0`/`4f1074`. Registered callback slots were read from the fingerprinted
V2.57 test guest; no setters were discovered by sweeping unknown commands.
