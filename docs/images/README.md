# Screenshot provenance

The `readme-*.png` images were captured on 2026-09-15 from the validated V2.57
runtime on commit `b4461a5`, during the documentation refresh.

- `readme-menu.png`, `readme-playing.png`, `readme-clock.png`: unmodified 360×360
  guest framebuffer PNGs returned by the viewer's `/frame` endpoint.
- `readme-viewer.png`: actual browser screenshot with the included device-photo
  skin, physical-button hotspots and headphone/USB/SD controls; Debug collapsed.

Playback uses a temporary generated 90-second, 440 Hz stereo WAV (16-bit, 44.1 kHz),
named `README demo.wav`. FiiO Link independently reported that path, duration and
wire state `0` (playing) when the raw playback frame was captured. Browser sound
was disabled. The skin screenshot uses stock brightness 38 for readability.

These images show the actual firmware and viewer; no interface elements or album
art were added. They illustrate appearance, not proof of every displayed feature.
For validation and older dated captures, see [STATUS.md](../STATUS.md).
The temporary audio fixture is not part of the repository.

## Idle / USB-power checkpoint, 2026-09-16

`18-usb-power-clock.png` is an unmodified 360×360 V2.57 guest framebuffer,
selected using `emu/fb-live` by `ci/idle_check.py`. It shows the stock clock
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
