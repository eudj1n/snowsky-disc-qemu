#!/usr/bin/env bash
# Diagnostic: boot under QEMU_STRACE, tap the language-screen Confirm button, report
# whether mq_ui actually consumed the injected touch events, and capture before/after PNGs.
# Run via: ./run.sh diag   (see run.sh)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
apply_ulimits; kill_guest
rm -f "$ROOTFS/dev/mqueue/"* 2>/dev/null || true
head -c $((SCR_W*SCR_VY*4)) /dev/zero > "$ROOTFS/dev/fb0"
: > "$ROOTFS/dev/input/event1"
mkdir -p "$SHOTS"; rm -f "$SHOTS"/*.png "$SHOTS"/*.snap 2>/dev/null || true

log "boot mq_ui (strace) + mq_player"
QEMU_STRACE=1 guest_run 50 /usr/bin/mq_ui 2>"$WORK/ui_str.log" >/dev/null &
sleep 4
guest_run 46 /usr/bin/mq_player >/dev/null 2>&1 &
sleep 22

cp "$ROOTFS/dev/fb0" "$WORK/d0.snap"; python3 "$REPO/tools/fb2png.py" "$WORK/d0.snap" "$SHOTS" d0

read RX RY < <(rot 180 315)               # Confirm button: displayed (180,315) -> raw
log "injecting tap at raw($RX,$RY)"
python3 "$REPO/tools/inject.py" press "$RX" "$RY" "$ROOTFS/dev/input/event1"; sleep 1
python3 "$REPO/tools/inject.py" release x x "$ROOTFS/dev/input/event1"; sleep 2

N=$(grep -acE "read\([0-9]+,0x[0-9a-f]+,16\) = 16" "$WORK/ui_str.log" 2>/dev/null || echo 0)
echo "=========================================="
echo " touch events consumed by mq_ui (16B reads): $N"
echo "   >0  => events reach mq_ui (coordinate/logic issue)"
echo "   ==0 => events NOT read (mechanism issue)"
echo "=========================================="
cp "$ROOTFS/dev/fb0" "$WORK/d1.snap"; python3 "$REPO/tools/fb2png.py" "$WORK/d1.snap" "$SHOTS" d1
log "guests left running — you can now ./run.sh tap <x> <y> or ./run.sh capture"
