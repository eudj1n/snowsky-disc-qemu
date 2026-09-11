# Viewer skin (optional, not committed)

`./run.sh view` renders the live round screen composited into a photo of the player, so
the browser viewer looks like the real device. Drop the photo here as **`skin.png`**:

- Any PNG works; the live 360×360 screen is overlaid on a circle inside it.
- **Best:** a PNG with a *transparent hole* over the screen glass — then the live screen
  shows through it pixel-perfectly.
- Tune the circle to your image with env vars (fractions of the image):
  `SKIN_CX` (centre X), `SKIN_CY` (centre Y), `SKIN_D` (diameter). Defaults suit the
  stock product photo. You can also nudge live via `http://localhost:8080/?...` is not
  wired — set the env in `scripts/40_stream.sh` or pass through the container.

`skin.png` is git-ignored (it may be a manufacturer/retailer photo — don't redistribute).
Without a skin the viewer falls back to a plain framed round screen.
