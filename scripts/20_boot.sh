#!/usr/bin/env bash
# Boot the firmware under qemu-user and capture the screen.
#
# Starts mq_ui FIRST (it creates the POSIX mqueue "ui"), then mq_player (the
# backend, which connects to "ui" and pushes state). Waits for the UI to settle,
# then dumps the framebuffer to PNGs in $SHOTS.
#
# Usage:  scripts/20_boot.sh [seconds]      (default 26; qemu is slow, allow >=24)
#
# Leaves both guest processes RUNNING so you can inject taps with 30_tap.sh, then
# re-capture with `scripts/capture.sh`. Run `scripts/99_stop.sh` when done.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
WAIT="${1:-26}"
[ -d "$ROOTFS" ] || { err "no rootfs — run 00/10 first"; exit 1; }
[ -f "$ROOTFS/lib/fbshim.so" ] || { err "shim not installed — run 10_setup_env.sh"; exit 1; }

apply_ulimits
kill_guest
rm -f "$ROOTFS/dev/mqueue/"* 2>/dev/null || true
head -c $((SCR_W*SCR_VY*4)) /dev/zero > "$ROOTFS/dev/fb0"
: > "$ROOTFS/dev/input/event1"; : > "$ROOTFS/dev/input/event0"

log "Starting mq_ui (creates 'ui' queue)"
timeout $((WAIT+40)) chroot "$ROOTFS" /usr/bin/mq_ui  >"$WORK/mq_ui.log"     2>&1 &
sleep 4
log "Starting mq_player (backend)"
timeout $((WAIT+36)) chroot "$ROOTFS" /usr/bin/mq_player >"$WORK/mq_player.log" 2>&1 &

log "Waiting ${WAIT}s for the UI to reach the main screen..."
sleep "$WAIT"

mkdir -p "$SHOTS"
cp "$ROOTFS/dev/fb0" "$WORK/fb0.snap"
log "Framebuffer captured. Rendering PNGs:"
python3 "$REPO/tools/fb2png.py" "$WORK/fb0.snap" "$SHOTS" boot
log "Guests left running. Inject taps: scripts/30_tap.sh <x> <y>   Stop: scripts/99_stop.sh"
