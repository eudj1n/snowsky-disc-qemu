# Stock DISC modes, Bluetooth source codec and lock screen

This extends [REMOTE_SETTINGS.md](REMOTE_SETTINGS.md) and [HTTP_API.md](HTTP_API.md).
Evidence comes from disposable stock-firmware guests, with network readback and
read-only SQLite checks. USB host enumeration, received AirPlay audio, Bluetooth
negotiation and visual rendering on physical DISC remain separate hardware checks.
No physical player was changed by these emulator experiments. Separately, the
user's iOS app trace below records stock-theme selections on physical DISC.

On 2026-09-15, full local integrations passed on **V2.40 and V2.57**, including
the new TCP/WS and direct/proxy scenarios. Firmware-free checks passed with
**164 Python tests, 23 JavaScript tests**, shell checks and all four shim builds.
The initial V2.40 attempt hit the stock listener's reconnect gap; the test now waits
for connection availability without replaying commands, and the full rerun passed.

## Work modes

`client.set_device_setting('work_mode', value)` uses `0657`; read with
`client.device_setting('work_mode')` (`0607`, reply `a607`). TCP and WS share the
same helpers. Only these three app-visible modes are exposed:

| Mode | Link value | `SYSCONFIG.WORK_MODE` | `SYSCONFIG.INPUT_MODE` | Internal player |
|---|---:|---:|---:|---|
| USB DAC | 1 | 1 | 1 | UAC (4) |
| Local playback | 8 | 0 | 8 | LOCALPLAYER (1) |
| AirPlay | 10 | 5 | 10 | AIRPLAY (6) |

Example: `0657000C000A` selects AirPlay; `0657000C0008` returns to local.
The test cycles local → USB → local → AirPlay → local and checks both configuration
columns. The stock handler closes/reopens its player; do not treat a mode change
as preserving current playback. Fresh local boot can report Link 8 while stored
`INPUT_MODE` is still 1; an explicit local selection normalizes it to 8.

The user's iOS 4.6.0 PCAP now confirms this exact cycle on physical V2.57: each
`0657` setter receives a matching `a607` notification, with no getter needed to
trigger the notification. All four transitions use one TCP connection. See the
[packet evidence](FIIO_CONTROL_APP.md#ios-raw-tcp-capture-2026-09-15) and
[wire fixture](../tools/fixtures/fiio_control_ios_460_modes.json). USB/AirPlay audio
operation is still outside what the trace establishes.

Other values occur in the shared handler, including modes absent from the DISC app.
Their presence does not establish product support. The client rejects them.

## Bluetooth source codec

`bt_source_codec`: setter **06d3**, getter **06d4**, reply **a6d4**.
Four hexadecimal digits encode the preference; the same integer is persisted in
`SYSCONFIG.BT_CODEC`.

| Value | Stock codec / quality strings | FiiO Control choice |
|---:|---|---|
| 0 | `sbc` | SBC |
| 1 | `aac` | AAC |
| 2 | `ldac`, `mobile` | LDAC: connection stability priority |
| 3 | `ldac`, `standard` | LDAC: balance between sound and connection |
| 4 | `ldac`, `high` | LDAC: sound quality priority |

All five preferences are exercised. This is the configured **source preference**,
not a report of the codec negotiated with headphones. No Bluetooth connection is
present in these tests. Stock closes the current player and reopens LOCALPLAYER
when setting the codec, without necessarily updating the Link work-mode field.
The client requires local mode before this setter. This command can
interrupt playback. Restoring a saved mode must follow restoring the codec.

The user's iOS 4.6.0 capture `2026-09-15-234051.pcap` and screenshot `IMG_6778.PNG`
confirm all five choices on physical V2.57. Two initial `06d4` queries return 4;
the app then sends `06d3` values **3 → 2 → 1 → 0 → 4**, each followed by the matching
`a6d4` notification without another getter. The final response confirms restoration
of the screenshot's LDAC sound-quality preference. These are preference changes,
not evidence of headphone negotiation or achieved bitrate. See
[capture details](FIIO_CONTROL_APP.md#ios-codec-capture-2026-09-15) and the
[regression fixture](../tools/fixtures/fiio_control_ios_460_codecs.json).

## Lock-screen HTTP

Both `GET` and `POST` use **`/image/lock_screen/`**. This is distinct from V2.57's
general `/image/<SD path>` upload. `tools/fiio_theme.py` supplies read, full custom
PNG upload/activation, and stock-theme selection helpers.

GET headers:

| Header | Meaning |
|---|---|
| `x-fields-to-update` | Decimal slot position, despite its name; custom 0 or system 0..4 |
| `file-source` | `lock_screen/custom` or `lock_screen/system` |
| `preview-flag` | 0 gets original image; 1 gets preview (stock default) |

The response body is the image, with metadata in headers. The acceptance test uses
`preview-flag: 0` and compares the entire response with the stored file.

POST sends the raw image body and all of these headers:

| Header | Tested example |
|---|---|
| `content-type` | `image/png` |
| `x-fields-to-update` | `0` |
| `alias` | Percent-encoded UTF-8; literal plus must be `%2B` |
| `back-groud` | **Exact stock spelling**, `alpha=70` |
| `lock-screen` | `time=1;date=1;battery=1;id3=0` |
| `front-color` | `r=12;g=34;b=56` |
| `msg-style` | `default/0`; the stock Clock theme returns `clock/0` |
| `flag-in-use` | `1` activates this theme |
| `file-source` | `lock_screen/custom` |
| `subclass` | `lock_screen/custom/default` |

The helper exposes one custom slot, 360×360 PNG, alias (at most 63 percent-encoded
bytes), alpha 0..100, four overlay flags and RGB color. It always uploads the full
file and activates the result. Byte preservation, headers, decoded alias and
`CUSTOM_THEME` fields are checked independently. This does not measure overlay
layout, opacity or colors on a physical screen. GIF and other styles remain leads.

Stock quirks confirmed by the regression scenario:

- A **custom POST with an empty body clears the stored image path**. The file can
  remain on disk, but GET becomes empty `image/none`. To edit custom metadata,
  resend the image too; no metadata-only helper is exposed.
- **`flag-in-use: 0` still clears the other active theme.** It can leave no theme
  selected. It is not a harmless way to upload a draft.
- Custom alias is saved correctly in SQLite, but V2.57 GET returns an empty alias
  header. Do not interpret that header as proof that the name was lost.
- Custom image upload uses a slot-derived path under
  `/usr/data/fiio/wifi_transfer/pic/lock_screen/`, replacing prior image extensions
  for that slot. This is not the SD card media-transfer path.
- System and custom slot 0 are distinct records. System selection reads that
  slot's complete metadata, then POSTs it with `flag-in-use: 1` and an empty body.
  This preserves the system image path. All five system selections are exercised.

HTTP 200 still needs readback. There are no automatic mutation retries. The test
restores the initially active system theme and verifies all system rows, while
custom test data is discarded with the disposable volume.

## Physical iOS app trace

The user's 2026-09-15 HAR records reads of all five system themes and custom slot 0,
then empty-body system-selection POSTs for slot 1 (`FIIO%20Sheep`) and slot 0
(`Clock`). Both POSTs carry the preceding GET metadata with `flag-in-use: 1`,
matching our helper. The app omits `preview-flag`; all six responses are 360×360
PNGs. The custom alias is empty. There is no final readback or custom upload in
this trace, so it does not extend the custom mutation guarantees above.

See [app evidence](FIIO_CONTROL_APP.md#ios-460-observed-http-2026-09-15) and the
[metadata fixture](../tools/fixtures/fiio_control_ios_460_themes.json). Its regression
test brings the passing firmware-free suite to 165 Python tests and 23 JavaScript
tests, with shell checks and four shim builds. The subsequent raw TCP capture
confirms the mode app frames above; the later codec capture confirms all five
codec preferences as documented above.

## Reproduction

`ci/modes_themes_check.py`, called by `ci/integration.sh`, runs modes/codecs over
TCP and WS, then themes over direct and proxied HTTP. `tools/test_fiio_theme.py`
and `tools/test_fiio_settings.py` cover wire values, metadata encoding, complete
selection readback and invalid-input rejection.

V2.57 static references: mode setter `4f1110`, getter `4eeaa4`, mode map `6e0b70`,
player selection `466a70`; codec setter/getter `4f0aec`/`4f0c58`; theme GET `48d268`,
POST `48dd80`, metadata application `48b690`. These are build-specific addresses.

## FiiO Control capture checklist

For exact app behavior, capture **both TCP 12100 and HTTP 12103** between the phone
and DISC. A phone HTTP proxy alone may miss raw TCP control. Record bidirectional
payloads and timestamps, without truncating bodies. Prefer a PCAP/PCAPNG capture;
HTTP request/response exports are also useful if their bodies and headers survive.
The network capture must be on the traffic path (phone capture, router/AP, or an
explicit forwarding proxy). Merely running Wireshark on another Wi-Fi client does
not guarantee visibility. Existing emulator bridge ports bind localhost and are
not a phone-facing capture proxy.

Use separate short captures, note app/firmware versions, and record action times:

1. Open DISC in FiiO Control. Pause playback. Select USB DAC, return to local,
   select AirPlay, then return to local; wait for each UI transition.
2. In local mode, note the original codec, select SBC then AAC, restore the original.
   A separate test with connected headphones can establish negotiated behavior.
3. Open Lock screen, select another **stock** theme, then restore the original.
4. If replacing the custom slot is acceptable, first retain its original image and
   settings. Upload a disposable image, change just its color/overlay setting, save,
   then restore the original. The metadata-only save sequence is especially useful.
5. Open the library-reset confirmation and cancel. This may identify the UI flow
   but will not prove the actual reset command. Do not confirm a reset on a personal
   library merely to get a trace. Actual reset requires disposable/backup state.

Disconnect our Link inspector/client before FiiO Control: stock accepts one TCP
control client. Captures can contain track names, paths and images; keep raw dumps
in ignored `work/`, and document only the minimal protocol evidence.

### Custom-theme metadata-save capture

Active investigation, 2026-09-16; awaiting a new owner-provided traffic capture.
Six supplied screenshots confirm **Apply now**, background transparency, four
overlay checkboxes, four style thumbnails and two unlabeled color sliders.
See [screen coverage and gaps](FIIO_CONTROL_APP.md#wallpaper-screens-first-batch-2026-09-16).
The custom helper currently fixes `msg-style` to `default/0`; the four visible
choices must be mapped from traffic before exposing additional style values.
Previously captured modes, codecs and stock-theme selections need not be repeated.

Use a recoverable custom slot: retain the original image, all settings and the
initially active theme. If the original cannot be restored, stop before replacing
it. Use a non-personal test image if an initial upload is needed. Record app and
firmware versions, then capture TCP 12100 and HTTP 12103 throughout this sequence:

1. Open the theme editor and record the starting settings. If needed, upload and
   save the test image once, recording that as the baseline upload.
2. Change **only the text/front color**, leaving the image and overlays unchanged;
   use **Apply now**. Note the action time and slider positions (no numeric color
   value is shown in the supplied screenshots). Capture before moving a slider
   too, since automatic writes have not been ruled out.
3. Leave and reopen the editor to trigger fresh reads and verify the image and
   selected color survived. Record the actual result, including any missing image.
4. Change only **Date**, use **Apply now**, leave and reopen again. Keep
   opacity/image/style/other fields unchanged.
5. Restore the original custom image/settings and previously active theme, then
   reopen to verify restoration before stopping the capture.

Allow each operation to settle; do not combine color and overlay changes into
one save. If leaving/reopening produces no network read, note that explicitly:
cached app UI is not device readback. No direct helper writes to the physical
player or new LAN bridge are needed for this phone-to-device capture.

Provide the bidirectional PCAP/PCAPNG and, if available, HAR with complete bodies
and headers, plus screenshots before/after and a short action/time list. Analysis
must distinguish full-image retransmission, empty-body POST, a different HTTP
route and TCP metadata commands. Compare image-body lengths/hashes and metadata
between upload and later saves; retain only sanitized protocol fields in Git.
Do not expose a metadata-only helper until the observed path has been reproduced
on a disposable V2.57 guest with image preservation and fresh readback checks.
