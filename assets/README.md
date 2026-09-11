# Viewer skin (optional)

`./run.sh view` renders the live round screen composited into a photo of the player, so
the browser viewer looks like the real device. Drop the photo here as **`skin.png`**:

- Any PNG works; the live 360×360 screen is overlaid on a circle inside it.
- **Best:** a PNG with a *transparent hole* over the screen glass — then the live screen
  shows through it pixel-perfectly.
- Tune the circle to your image: open the viewer, expand **Debug**, click **⊹ align**, then **Alt+arrows**
  to move and **+/-** to resize (Shift = bigger step); the readout shows the exact
  `SKIN_CX / SKIN_CY / SKIN_D`. You can also pass them as query params
  (`http://localhost:8080/?cx=0.5&cy=0.5&d=0.7`) or as env vars to `scripts/40_stream.sh`.
  Defaults live in `tools/stream.py`.

`skin.png` here is a photo of the player (this repo is private). Without a skin the viewer
falls back to a plain framed round screen.

The skin's physical buttons have translucent HTML hotspots; the PNG is unchanged.
For another photo, adjust their `--x`/`--y` percentages in `tools/stream.py` too.
See [VIEWER.md](../docs/VIEWER.md) for positions and gesture behavior.
