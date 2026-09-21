#!/usr/bin/env bash
# Live viewer + touch bridge: serve the guest framebuffer as a browser-viewable
# stream and turn pointer events on it into synthetic touches. Run INSIDE the
# container (via `./emulator/run.sh view`). The guests from 20_boot.sh should be running —
# if not, the page shows black until you boot; boot in another shell and watch it
# come up.
#
# Usage:  viewer/scripts/40_stream.sh [port]        (default 8080; also honours $STREAM_PORT)
#
# Foreground by default (Ctrl-C to stop). `./emulator/run.sh view` launches it detached.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/../../emulator/scripts/lib.sh"
export STREAM_PORT="${1:-${STREAM_PORT:-8080}}"

[ -e "$ROOTFS/dev/input/event1" ] || { err "no touch stub — run 10_setup_env.sh"; exit 1; }

pgrep -f 'python3 -m viewer[.]server' >/dev/null 2>&1 && { pkill -f 'python3 -m viewer[.]server' || true; sleep 1; }
sd_mount   # keep the SD mounted so the File Browser has content while you click around

if pgrep -f qemu-mipsel >/dev/null 2>&1; then
  log "guests running — the stream shows the live screen"
else
  err "guests not running — boot first (./emulator/run.sh boot); the page will be black until then"
fi
log "serving on :$STREAM_PORT  (open http://localhost:$STREAM_PORT on the host)"
exec env ROOTFS="$ROOTFS" python3 -m viewer.server
