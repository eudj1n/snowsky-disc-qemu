# Firmware selection and compatibility

A firmware update changes two things independently: the local emulator build and
the protocol spoken by a connected player. Neither is inferred from a newer
version number. New firmware needs reviewed inputs and validation before promotion.

## One active version

`firmware/active-version` is the single tracked default. Compose passes the optional
`FW_VERSION` override into the container; the shared shell library and Python
selection helper resolve an empty value through that file. `.env.example` leaves
`FW_VERSION` empty. Existing `.env` files with `FW_VERSION=2.57` remain explicitly
pinned and are not rewritten when the active version changes.

The shell environment takes precedence over `.env` in Compose. CI uses its own
explicit selection and disposable volumes, ignoring the interactive `.env`.
`FW_VERSION` is a runtime profile selector, not a Docker build argument: the image
contains a shared toolchain. Changing the selection requires recreating the
container and using a matching extracted rootfs in a separate work volume.
A version mismatch fails validation; no rootfs migration occurs.

From the repository root:

```sh
python3 -m firmware.profile get version
python3 -m firmware.profile get capabilities --version 2.57
python3 -m firmware.profile require-scenario idle --version 2.57
```

The CLI honors `FW_VERSION` from the process environment; it does not parse `.env`.
An explicit `--version` takes precedence. Python `load_profile(version)` reads the
requested profile; `selected_profile()` resolves the environment/default selector.

## Reviewed runtime profiles

Only `firmware/v<version>.json` files enable runtime selection. The downloader and
fingerprint detector discover these files; `firmware/inventory/` is observation
history and never enables execution. The profile includes:

- Product/main/recovery identity, rootfs digest, six binary fingerprints and the
  narrowly permitted key patch.
- `diagnostics`: verified mq_player and mq_ui fields, callbacks and context offsets.
  Memory access remains guarded by the selected binary's fingerprint and mappings.
- `capabilities`: individually reviewed behavior such as USB power detection,
  insertion-triggered SD scanning, image uploads and theme styles.
- `acceptance`: allowed focused scenarios. An unknown scenario/profile fails
  before a disposable stack is created.
- `full_scenarios`: additional acceptance scenarios included in the shared full
  sequence. These must also appear in `acceptance`. Long `idle`/`idle-usb` checks
  remain explicit gates; they are not added automatically to `full`.

The shared scenarios consume these fields instead of comparing a version with
`2.57`. Missing capabilities are not granted. Historical test captures and binary
fixtures retain their original version labels; they must not be mass-replaced.

GitHub firmware integration reads the active version and that profile's `url_secret`.
Only the named secret is passed as `FIRMWARE_URL` to the downloader; it is removed
from the environment before download and is never printed. Direct local use still
accepts the profile's per-version secret environment variable. The workflow remains
manual and restricted to trusted `2.x`; no secret-backed PR execution is enabled.

## Independent controller contract

`controller/compatibility.py` records reviewed DISC protocol capabilities by the
integer `soc_version` returned by the device. TCP and WS use the same checks.
No emulator environment variable, rootfs, firmware profile or Docker installation
is required to use that contract.

This registry consolidates the existing guards for favorite positions and
playlist/artist/genre/folder playback, plus the network diagnostic. It is not a
complete feature negotiation protocol and does not add version checks to every
raw command or existing helper. Unknown or malformed device versions cannot pass
these guarded operations. There is no `>= 257` rule or implicit inheritance.

## Adding and promoting a firmware

1. Follow [porting](PORTING.md): inventory inputs and independently locate/verify
   new fingerprints, patch bytes, addresses and behavior. Preserve previous
   firmware releases and inventories.
2. Add the reviewed runtime profile. Copy structure as a starting point, but do
   not treat copied addresses or capabilities as validation. Select the candidate
   explicitly with a new work volume while the active default stays unchanged.
3. Review the device protocol separately. Add only confirmed capabilities to the
   controller contract for that device version. Shared encoders and scenarios need
   code changes only when behavior actually differs.
4. Run firmware-free, full and relevant focused acceptance. Power/USB changes and
   a new firmware profile also require the real idle and idle-usb observations.
5. After acceptance, change `firmware/active-version` and add the corresponding
   GitHub secret. The workflow reads its name from the profile. Update release and
   support documentation; existing explicitly pinned installations stay pinned.

This supports the current single-active-firmware policy. It does not require
backports or long-term maintenance of old runtime profiles. Removal of the
remaining V2.40 profile is a separate task.

## Local validation — 2026-09-17

- 312 Python tests and 23 JavaScript tests passed; shell syntax and all four shim
  builds passed. New checks cover default/override selection, a synthetic promotion
  without script edits, inventory isolation, secret cleanup, and rejection of
  unreviewed device operations and scenarios without runners.
- Compose preserves both an empty default selector and an explicit version pin.
  The existing interactive `.env` remains pinned to V2.57.
- All pre-existing metadata, fingerprints, patch bytes and diagnostic fields are
  unchanged. Relocated UI/storage, power and preference tables retain their values.
- Fresh disposable V2.57 `full`, `idle` and `idle-usb` scenarios passed. This includes
  viewer/frame/PCM/input and guest lifecycle; TCP/WS protocol and library checks;
  actual idle shutdown and explicit Power/reconnect on both transports; and the
  full 310-second paused, screen-off USB observation with unplug recovery.
- The three disposable stacks and work volumes were removed. These are local
  results, not a hosted workflow run or acceptance of any new firmware version.


Assistant session startup, catalog snapshots, playback controls, queue observation
and navigation, current-track questions/favorites and volume now require named
Controller capabilities. `require_client()` checks the DISC handshake and fresh
`soc_version`; raw version literals no longer gate these Assistant paths.
A future version such as 260 must be explicitly reviewed and registered with the
capabilities it actually supports. No 260 runtime support is enabled by this change.
