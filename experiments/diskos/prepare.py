"""Patch a build COPY of diskOS for the stock-initialised emulator handoff."""
from pathlib import Path
import sys

source = Path(sys.argv[1]) / 'main.c'
text = source.read_text()
anchor = 'static void v240_workmode_cb(lv_timer_t *t){\n'
if text.count(anchor) != 1:
    raise SystemExit('diskOS startup changed; review the warm-player adaptation before building')
text = text.replace(anchor, anchor + '''    /* Emulator-only warm handoff: stock UI has already initialised the backend.
     * Reinitialising its route after the first a1 frame interrupts a playing track.
     * The normal diskOS hardware startup path is unchanged without this flag. */
    if(getenv("DISKOS_EMU_WARM_PLAYER")){ lv_timer_del(t); return; }
''')
source.write_text(text)
