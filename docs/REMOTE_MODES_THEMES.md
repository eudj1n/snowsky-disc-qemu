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

Custom POST sends the raw image body and all of these headers:

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
layout, opacity or colors on a physical screen. GIF remains unvalidated.

Physical `230929` confirms **system** opacity edits with empty POST bodies,
`file-source: lock_screen/system`, slot 1 and the other system metadata intact.
Displayed 100/49/0 map directly to `back-groud: alpha=100/49/0`; the final GET
confirms 100. The owner observes 0 hiding the image and changes appearing after
unlock/relock. This is opacity, not inverse transparency. System selection
preserves metadata; `update_system_lock_screen` now supplies verified edits.
Do not transfer this empty-body workflow to custom uploads.
[Capture and evidence limits](FIIO_CONTROL_APP.md#physical-system-theme-opacity-2026-09-16).

### System-theme editing

`update_system_lock_screen(http, slot, ...)` edits **and activates** one of
system slots 0..4. Optional `alpha`, `color`, `style`, `show_time`, `show_date`,
`show_battery`, `show_id3` change only those fields; omitted/None fields preserve
fresh device metadata. At least one edit is required. Alpha is integer 0..100,
RGB is three integer bytes, flags are booleans, styles are `default/0`,
`default/1`, `default/2`, `clock/0`. Style does not implicitly change overlays.

```python
from fiio_theme import update_system_lock_screen

saved = update_system_lock_screen(http, 1, alpha=49, color=(255, 169, 169))
saved = update_system_lock_screen(http, 1, show_date=False)
```

The helper reads original image/metadata (`preview-flag: 0`), preserves the
encoded stock alias and all untouched fields, sends an **empty-body** POST with
active flag 1, then reads again. It returns the verified GET reply only when all
sent metadata and original image bytes match. It does not rename system themes,
replace their artwork or modify custom slot 0. Existing selection still returns
a raw POST reply; custom upload retains its full-PNG contract.

Serialize writers: there is no compare-and-swap. A timeout/readback error may
follow a successful update; refresh state before deciding what to do. No
automatic retry, rollback or unlock/relock is performed. Saved readback does not
prove an already visible lock screen repainted; the owner observed refresh after
unlock/relock. Focused `themes` acceptance tests direct/proxy opacity/RGB, all
four styles and independent overlays, original image/SQLite state and restoration
of the initial system metadata and active selection. No physical replay.

### Alias limit (V2.57)

The **63-byte percent-encoded limit is a firmware constraint**, not an arbitrary
client cap. POST handler `48dd80` reads `alias` into a 64-byte buffer through
`496c60`, which copies at most `size - 1` bytes and terminates them. Only then
does `48b690` percent-decode and save the result. The larger decoded destination
does not make longer headers safe.

Fresh disposable `themes` acceptance checks direct/proxied HTTP and raw SQLite
bytes: 63 ASCII bytes and `Ё` × 10 + `ABC` (63 encoded bytes) persist losslessly;
64 ASCII bytes lose their last character. `Ё` × 11 (66 encoded bytes) and the
captured `Пользовательский` label (**96**, not the previously documented 90,
encoded bytes) are cut to 63 before decoding, leaving 21 stored bytes ending
in an incomplete UTF-8 character. HTTP still returns 200; custom GET still has
an empty alias and the complete PNG. Neither response proves name preservation.

The public helper therefore keeps its rejection before file/network access;
it neither silently truncates nor sends the app's over-limit alias. Only the
disposable diagnostic uses raw over-limit requests and immediately restores a
valid alias through stock HTTP. No firmware patch or physical write is needed.

### Custom styles (V2.57)

`upload_lock_screen(..., style='default/0')` now accepts exactly `default/0`,
`default/1`, `default/2`, `clock/0`. The default is unchanged. Unknown values are
rejected before reading the file or opening a connection. Only `msg-style`
changes; all four use `subclass: lock_screen/custom/default` and a full PNG body.
The [physical style capture](FIIO_CONTROL_APP.md#physical-custom-style-save-2026-09-16)
confirms POST and GET for all four values without changing the image.

Style and overlay flags remain independent helper arguments; do not silently
turn time on or clear another flag when changing styles. In the captured app
sequence, time changes from 0 to 1 with the analog-clock POST and stays 1 after
returning to `default/0`. The capture alone cannot distinguish automatic UI
coupling from a separate tap, and cannot prove visual output with flags off.
Keep the caller's explicit flags and verify readback.

```python
upload_lock_screen(http, png_path, style='clock/0', show_time=True,
                   show_date=False, show_battery=False, show_id3=False)
reply = read_lock_screen(http)  # verify metadata and complete original image
```

The physical test followed a requested sequential-thumbnail walkthrough, yielding
`default/0 → default/1 → default/2 → clock/0 → default/0`. Without a synchronized
action log, thumbnail-to-wire ordering is inferred from that walkthrough, not
encoded in the packets. The API uses wire strings rather than guessed UI indices.

Stock quirks confirmed by the regression scenario:

- A **custom POST with an empty body clears the stored image path**. The file can
  remain on disk, but GET becomes empty `image/none`. To edit custom metadata,
  resend the image too; no metadata-only helper is exposed. The owner's physical
  iOS capture on 2026-09-16 confirms that the app resends the identical full PNG
  for color/Date edits and reads it back with the updated metadata; see
  [packet evidence and alias limitation](FIIO_CONTROL_APP.md#physical-custom-theme-save-2026-09-16).
- **`flag-in-use: 0` still clears the other active theme.** It can leave no theme
  selected. It is not a harmless way to upload a draft.
- In-limit custom alias is saved correctly in SQLite, but V2.57 GET returns an empty alias
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

Focused V2.57 theme acceptance (no unrelated media/mode/power tests):

```sh
CI_SCENARIO=themes FW_VERSION=2.57 bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

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

Color/Date save investigation completed with the owner's 2026-09-16 HAR/PCAP:
full PNG retransmission and fresh metadata/image readback confirmed. The
[capture evidence](FIIO_CONTROL_APP.md#physical-custom-theme-save-2026-09-16)
records restoration limits and an app alias exceeding the verified firmware limit.
Six supplied screenshots confirm **Apply now**, background transparency, four
overlay checkboxes, four style thumbnails and two unlabeled color sliders.
See [screen coverage and gaps](FIIO_CONTROL_APP.md#wallpaper-screens-first-batch-2026-09-16).
The second capture confirms all four custom `msg-style` values with fresh GET
readback; the helper now exposes the allowlist documented above.
The sequence below is retained for reproduction, not a request to repeat the
completed color/Date or style captures. Remaining questions include the two
the official catalog and exact slider conversion formula. Later `231820`
identifies hue/lightness-like UI roles and exact RGB save/readback, without
recovering the numerical conversion. The later system
opacity capture resolves its percentage mapping; custom opacity rendering is not
established by it.
The long localized alias is resolved by the boundary tests above. Do not request another full walkthrough merely
to repeat already captured style values.
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


### Next capture: background transparency

Prepared 2026-09-16 after completing the library Delete captures. Target:
**FiiO Control 4.6.0 on iPhone → physical DISC**. Existing captures held alpha
at 100; they do not establish percentage conversion or the visible direction.
Historical requested scenario: the supplied `230929` capture instead edits
system slot 1, with values 100 → 49 → 0 → 100. Its
[analysis](FIIO_CONTROL_APP.md#physical-system-theme-opacity-2026-09-16) closes
the stock-theme percentage mapping and observed rendering direction. Do not
repeat this scenario merely to obtain 50 instead of 49. Custom-slot opacity
rendering is not established by that system-slot trace.

Use the existing recoverable custom image; keep its image, style, color and all
four overlay flags unchanged. Start Surge capture before opening its editor.

1. Record the initial displayed transparency and active theme. Open the custom
   editor to capture the starting read; do not upload a replacement image.
2. Set displayed transparency to **0%**, Apply now, leave and reopen the editor.
3. Repeat for **50%** and then **100%**, saving/reopening each time. If the slider
   cannot reach an exact percentage, record the actual displayed value.
4. Restore the original percentage and initially active theme; reopen to check.
   Stop capture and provide PCAP plus HAR, with any deviations from this order.

At each value, view the DISC lock screen and note whether the background picture
is visible/dimmed/absent. A photograph is useful if the difference is ambiguous.
The phone preview alone cannot establish physical rendering. If the custom image
cannot be restored, stop before changing it and report the limitation.

Analysis: pair displayed values with `back-groud: alpha=…`, compare unchanged
PNG hashes and other headers, distinguish save from fresh GET, and record the
restoration readback. Separate persisted metadata from physical appearance.
Do not infer color-slider mapping from this alpha-only trace.

The subsequent `231820` trace covers color changes; no repeat walkthrough is
needed. Official catalog research is now deferred to issue #11. If resumed,
retain relevant non-DISC traffic too: local-port-only filtering could
miss a catalog request. The Android snapshot contains cloud-service identifiers
and `get-theme-list?deviceId=`, but this is only a static search lead, not a
verified endpoint or evidence of any iOS request. No catalog host is assumed.


### Next capture: individual color sliders

Historical requested scenario, now followed by `231820` and screenshots
6822–6825. [Analysis](FIIO_CONTROL_APP.md#physical-system-theme-colors-2026-09-16)
records hue/lightness-like roles, four RGB saves and final pink color (not
restoration). Exact thumb conversion remains unknown; no repeat requested.

After `230929`, keep **FIIO Sheep / system slot 1**, opacity 100, image, style
and overlay flags fixed. The observed starting color was RGB 191/139/66; record
actual starting slider positions because the app may now have a different state.

1. Start capture before opening the color panel. Record the initial positions.
2. Change only the **upper** color slider noticeably, Apply now, leave/reopen.
   Record its position and the visible text/clock color after unlock/relock.
3. Restore the upper slider and save/reopen. Then change only the **lower**
   slider, save/reopen and record its position and the physical color.
4. Restore both original positions and save/reopen before stopping capture.

Provide PCAP/HAR and before/after screenshots of the sliders; describe actual
order if it differs. If exact restoration is not possible, report that rather
than claiming the original color returned. Never assume a hue/brightness or
RGB/HSV mapping from appearance alone. Compare `front-color` with all other
headers and fresh reads; log coupled changes if the UI moves the other slider.
Two isolated examples can establish each slider's effect, but may not recover
its full conversion formula. Official catalog loading is deferred to issue #11.


### Deferred: Official wallpapers and cloud synchronization

**Owner decision, 2026-09-16:** excluded from the current local DISC task and
tracked separately in [issue #11](https://github.com/eudj1n/snowsky-disc-qemu/issues/11). The owner reports
cloud synchronization is available after FiiO registration/sign-in; account
requirements/endpoints have not been validated here. No capture, registration
or login is currently requested. The earlier proposed scenario below is kept
only as historical context for the follow-up, not an active instruction.

After the opacity/color checkpoints, investigate the previously empty Official
page independently. Start Surge capture before opening **Wallpapers → Official**;
wait about 15–20 seconds, then refresh if an actual refresh control/gesture is
available. Otherwise leave and reopen once. Record whether the page remains
empty, shows an error or loads items; stop capture and supply PCAP/HAR.

Keep relevant non-DISC traffic: a capture filtered only to device ports 12100/
12103 may miss catalog loading. Do not install a theme, log in, or change settings
for this read-only scenario. An empty HAR or encrypted connection alone cannot
establish absence of a catalog request. Match endpoints/results if visible;
otherwise identify only supported connection/DNS/TLS evidence and its limits.
The Android `get-theme-list?deviceId=` string remains a candidate until observed
or linked by static control-flow analysis. Do not infer the host or query it from
an unverified combination of snapshot strings.
