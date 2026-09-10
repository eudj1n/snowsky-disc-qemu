#!/usr/bin/env bash
# Inject a touch tap at a SCREEN coordinate (as you see it in the PNG), then
# re-capture the framebuffer. The guests started by 20_boot.sh must be running.
#
# Usage:  scripts/30_tap.sh <x> <y>
#   e.g.  scripts/30_tap.sh 180 315   # tap the bottom-center button on the language screen
#
# Coordinates are the ones you SEE (top-left origin). They are flipped to raw touch
# coordinates internally (panel is 180deg-rotated). Press and release are separated
# in time so LVGL samples the press before the release (see docs/TOUCH.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
DX="${1:?usage: 30_tap.sh <x> <y>}"; DY="${2:?usage: 30_tap.sh <x> <y>}"
EV="$ROOTFS/dev/input/event1"
[ -e "$EV" ] || { err "no touch device stub $EV — run 10_setup_env.sh"; exit 1; }

read RX RY < <(rot "$DX" "$DY")
log "tap screen($DX,$DY) -> raw($RX,$RY)"
python3 "$REPO/tools/inject.py" press "$RX" "$RY" "$EV"
sleep 1                                   # let LVGL sample the pressed state
python3 "$REPO/tools/inject.py" release x x "$EV"
sleep 2                                    # let the UI react + redraw

mkdir -p "$SHOTS"
cp "$ROOTFS/dev/fb0" "$WORK/fb0.snap"
python3 "$REPO/tools/fb2png.py" "$WORK/fb0.snap" "$SHOTS" tap
log "Done. Check $SHOTS/tap-b0.png and tap-b1.png (current screen is whichever changed)."
