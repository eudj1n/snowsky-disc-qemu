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

## Remaining hardware checks and other stock commands

Static V2.57 callback registration gives further concrete leads:

| Area | Tags / current evidence |
|---|---|
| Work-mode audio | Three app-visible control transitions now have [acceptance coverage](REMOTE_MODES_THEMES.md); actual USB/AirPlay audio remains unvalidated |
| Bluetooth connection | All five source preferences now have [readback/persistence coverage](REMOTE_MODES_THEMES.md); negotiation and transmitted audio remain unvalidated |
| Physical button assignments | `0820`, `0821`, `0822`; single/double/hold. Existing physical-control tests cover assignments through the device configuration, not these remote setters |
| Playback preferences | `0687` folder jump, `0647` gapless, `0718` replay gain, `0648` artist grouping, `064d` CD/track display, `064e` list interaction mode |
| Cover/lyrics preferences | `064b`, `064c`; remote setters found, online retrieval not tested |
| Reset library | App UI exists; a dedicated safe library-reset command is not yet established. **0800 performs a broader factory reset**, including Wi-Fi and theme/song databases; it is not an appropriate substitute |

Getter-looking tags can be no-ops or send only local UI events; `0604`, for example,
did not yield a network response in the emulator. A function in the shared command
table is not proof of a usable remote feature.

## Reproduce

`ci/settings_check.py` runs TCP and WS against the disposable integration guest,
changes/restores gain, DRE, filter, SPDIF and user PEQ, and reads SQLite without writes.
`tools/test_fiio_settings.py` pins wire examples, signed gain, binary PEQ structure,
validation and the user-preset guard.

Static V2.57 references: filter `4ee628`, network EQ type `4ef174`, PEQ getter
`4ef61c`, setter `4ef774`, band application `45e9e4`, JSON parser `4d98e0`, master
getter/setter `4f00a4`/`4f022c`, gain `4f182c`/`4f18e0`, DRE `4f1770`/`4f17cc`,
SPDIF `4f0ed0`/`4f1074`. Registered callback slots were read from the fingerprinted
V2.57 test guest; no setters were discovered by sweeping unknown commands.
