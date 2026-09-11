# Live viewer + touch bridge

`./run.sh view` turns the emulator into an **interactive** stand: it streams the guest
framebuffer to a browser and turns pointer events on that page into synthetic touches, so
you drive the real stock UI from the host with no hardware. Optionally it composites the
live round screen into a photo of the player so it looks like the real device.

```sh
./run.sh boot          # start the guests (they now stay alive ~30 min, see GUEST_TTL)
./run.sh view          # -> http://localhost:8080   (add a port arg to change it)
```

Then, in the browser: **click = tap**, **drag = swipe**, **long-press = hold**, and the
buttons do the common gestures (shade down, back = left→right, …).

## How it works

`tools/stream.py` runs inside the container (wrapped by `scripts/40_stream.sh`, launched
detached by `./run.sh view`) and serves:

| route | purpose |
|---|---|
| `GET /` | the viewer page (stream + pointer capture + gesture buttons) |
| `GET /stream` | `multipart/x-mixed-replace` PNG stream of the live screen |
| `GET /frame` | a single current PNG (handy for scripting) |
| `GET /skin` | the device photo, if a skin is present |
| `GET /tap?x&y` | short tap at display coords (press, hold ~0.3 s, release) |
| `GET /down?x&y` · `/move?x&y` · `/up` | manual press / drag / release |
| `GET /swipe?dir=down\|up\|back\|left` (or `?x0&y0&x1&y1`) | server-side smooth swipe |
| `GET /key?k=menu_up\|menu_down\|play\|play_pause` (or `?code=<int>`) | physical key on `event0` |

**Framebuffer** (see [EMULATION.md](EMULATION.md)): `fb0` is a plain file, three 360×360
BGRX sub-buffers. `mq_ui` alternates buf0/buf1 and never pans, so a background thread reads
`fb0`, picks the sub-buffer that **changed since the last read** (the live one), converts
BGRX→RGB + 180° rotation, and PNG-encodes it. Port published in `docker-compose.yml` (8080).

**Touch** (see [TOUCH.md](TOUCH.md)): pointer coords are mapped to the 360² screen, flipped
to raw touch (`359−x, 359−y`), and appended to `/dev/input/event1` as `input_event`s. A plain
click uses `/tap` which holds ~0.3 s (the read-cb drains all queued events per poll, so a
press+release in one batch is seen as a net release = no tap). A drag sends `down → move… →
up` over real wall-clock time, which is also how **swipes** work — the shade pull-down and the
left→right back gesture are just server-side interpolated swipes, one click each.

## Device skin (the "cool" look)

If a skin PNG is present (repo `assets/skin.png`, else `/work/skin.png`), the page shows the
photo with the live round screen overlaid on the glass. Align the circle to your image live:
click **⊹ align**, then **Alt+arrows** to move / **+/-** to resize (Shift = bigger step) — the
readout shows the exact `SKIN_CX / SKIN_CY / SKIN_D`. Those can also be passed as query params
(`/?cx=0.5&cy=0.5&d=0.7`) or env vars to `scripts/40_stream.sh`; defaults live in `tools/stream.py`.
A PNG with a **transparent hole** over the screen gives the cleanest result. Without a skin the
viewer falls back to a plain framed round screen. See `assets/README.md`.

## Notes / limits

- Needs `./run.sh boot` first; until then the page is black (boot in another shell and watch
  it come up). `./run.sh stop` also stops the viewer.
- FPS is qemu-bound (~5–15). This is a userspace emulator — good for UI/navigation/logic, not
  hardware-accurate timing.
- **Physical keys** (`x2000_key` on `event0`) work via the buttons (▲ menu-up, ▼ menu-down,
  ▶ play, ⏯ play/pause). They need the key-enable patch (`scripts/patch_keys.sh`, applied by
  `10_setup_env.sh`); the custom codes and the full reverse-engineering are in [RE.md](RE.md).
  Their visible effect is context-dependent (keys act in the playback/volume context; the menu
  carousel is touch/swipe). There is **no power key on `event0`** — power is MCU-mediated and the
  MCU (`/dev/ttyS0`) isn't emulated, so a "power" button would do nothing.
