# Screenshot provenance

The raw `readme-menu.png`, `readme-playing.png` and `readme-clock.png` images
were captured on 2026-09-15 from the validated V2.57 runtime on commit `b4461a5`,
during the documentation refresh.

- `readme-menu.png`, `readme-playing.png`, `readme-clock.png`: unmodified 360×360
  guest framebuffer PNGs returned by the viewer's `/frame` endpoint.
- `readme-viewer-qemu.png`: updated on 2026-09-17 with an actual browser screenshot
  of the CSS device and live V2.57 screen, physical edge buttons and bottom
  audio/USB/SD connectors; Debug collapsed and QEMU badge visible. The body has no
  logo or lettering. This replaces the earlier photo-skin presentation.
  Recaptured with the stock shade brightness slider at its maximum (40), verified
  as `brightness(1)` in the Viewer, so its screen is comparable to the WASM
  capture, which does not yet apply backlight brightness. The earlier capture
  used a lower Viewer brightness and appeared darker. No image brightening was
  applied after capture.

The final approved page UI was captured at a 1065×1037 browser viewport on
2026-09-17. The Viewer and WASM overview screenshots use the same viewport and
show the Browse files menu with the extra tools collapsed; no browser chrome,
image resizing or compositing was added.

Playback uses a temporary generated 90-second, 440 Hz stereo WAV (16-bit, 44.1 kHz),
named `README demo.wav`. FiiO Link independently reported that path, duration and
wire state `0` (playing) when the raw playback frame was captured. Browser sound
was disabled. The original 2026-09-15 viewer capture used stock brightness 38.

These images show the actual firmware and viewer; no interface elements or album
art were added. They illustrate appearance, not proof of every displayed feature.
For validation and older dated captures, see [STATUS.md](../STATUS.md).
The temporary audio fixture is not part of the repository.

## Idle / USB-power checkpoint, 2026-09-16

`18-usb-power-clock.png` is an unmodified 360×360 V2.57 guest framebuffer,
selected using `emu/fb-live` by `tests/integration/idle_check.py`. It shows the stock clock
lockscreen after 310 seconds paused with simulated USB power and a local Power
gesture to make the screen visible again. Playback metadata comes from the
generated `CI Album` fixture, not the owner's media. The picture itself does not
prove USB detection or elapsed time; the focused acceptance checks the native
power flag, counters, playback state and shutdown-request marker independently.

`19-idle-reboot-menu.png` is the same raw capture path after natural idle shutdown,
guest-only supervisor stop, explicit local Power boot, a fresh WS handshake and
a new deliberate album selection/play/pause check. The stock UI remains on its
Browse files carousel entry. Both captures belong to this local idle/USB checkpoint,
not the earlier `b4461a5` README capture session.

## Physical FiiO Control filters, 2026-09-16

`20-fiio-control-filters-en.png` is an unmodified copy of the owner's
`IMG_6817.PNG` (1290×2796), SHA-256
`f33856cc079202fb4a7cf178968c98adeb7106bb6a886fa0fdc75137a0adf2f1`.
It shows FiiO Control after switching to English, connected in the physical DISC
workflow, with row 2 selected. It is not an emulator render or a new packet trace.
English rows 5 and 6 have identical visible labels; the earlier Russian-language
walkthrough's TCP capture establishes their different codes. See
[mapping and evidence](../REMOTE_SETTINGS.md#physical-fiio-control-filter-mapping-2026-09-16).

## Browser experiment UI, 2026-09-17

`readme-browser.png` is an actual browser screenshot of the local WASM prototype
with the V2.57 main menu loaded. `browser-debug.png` captures the page scrolled
down to its expanded Debug and Prototype console panels, including the Back
shortcut inside Debug. Both use the same CSS device geometry as the
updated QEMU Viewer. The captured VM has no imported media; audio and peripheral
controls are visibly disabled. The WASM badge identifies the execution mode.
Screenshots establish appearance, not complete firmware or hardware support.
No firmware images or generated VM artifacts are included. Earlier dated skin
screenshots remain historical evidence in STATUS.md, not current UI instructions.

## Historical viewer photo

The device photo visible in the older Viewer screenshots was taken by the
repository owner, eudj1n, who confirmed authorship and approved public distribution
under the repository's MIT license on 2026-09-11. The standalone photo skin is no
longer needed by the CSS Viewer and has been removed. Dated screenshots remain as
historical evidence; depicted branding and vendor UI are not relicensed.

## diskOS V2.40 preview, 2026-09-17

`diskos-v240-preview.png` is an actual 1065×1037 browser capture of the source-built
diskOS UI at commit `85a327ca56af2676c850f24ddcba5f34135132d4`, running over the
fingerprint-validated stock V2.40 backend in the isolated preview stack. It shows
the idle home screen, with no imported media, inside the current QEMU Viewer.
The quick-panel brightness was set to maximum and the Viewer reported
`brightness(1)`; no image brightening or compositing was applied after capture.

The build, startup, main screen and quick-panel interaction were checked for this
capture; the 2026-09-13 playback and Power-cycle results were not repeated.
The image does not change the experiment's historical/unsupported status.
diskOS UI source is GPL-3.0-or-later; the screenshot does not relicense its depicted
interface. See [the preview report](../DISKOS_PREVIEW.md) for source and limitations.
