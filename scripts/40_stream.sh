#!/usr/bin/env bash
# Live viewer + touch bridge: serve the guest framebuffer as a browser-viewable
# stream and turn pointer events on it into synthetic touches. Run INSIDE the
# container (via `./run.sh view`). The guests from 20_boot.sh should be running —
# if not, the page shows black until you boot; boot in another shell and watch it
# come up.
#
# Usage:  scripts/40_stream.sh [port]        (default 8080; also honours $STREAM_PORT)
#
# Foreground by default (Ctrl-C to stop). `./run.sh view` launches it detached.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
export STREAM_PORT="${1:-${STREAM_PORT:-8080}}"

[ -e "$ROOTFS/dev/input/event1" ] || { err "no touch stub — run 10_setup_env.sh"; exit 1; }

# Device skin (optional): a photo of the player, composited behind the live screen so the
# viewer looks like the real device. Prefer the repo asset (may be a transparent-hole PNG),
# fall back to one dropped in the /work volume. See assets/README.md.
if   [ -f "$REPO/assets/skin.png" ]; then export SKIN="$REPO/assets/skin.png"
elif [ -f "$WORK/skin.png" ];        then export SKIN="$WORK/skin.png"
fi
[ -n "${SKIN:-}" ] && log "skin: $SKIN (tune with SKIN_CX/SKIN_CY/SKIN_D)"
pgrep -f 'tools/stream.py' >/dev/null 2>&1 && { pkill -f 'tools/stream.py' || true; sleep 1; }
sd_mount   # keep the SD mounted so the File Browser has content while you click around

if pgrep -f qemu-mipsel >/dev/null 2>&1; then
  log "guests running — the stream shows the live screen"
else
  err "guests not running — boot first (./run.sh boot); the page will be black until then"
fi
log "serving on :$STREAM_PORT  (open http://localhost:$STREAM_PORT on the host)"
exec env ROOTFS="$ROOTFS" python3 "$REPO/tools/stream.py"
