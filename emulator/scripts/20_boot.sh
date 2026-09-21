#!/usr/bin/env bash
# Boot the firmware under qemu-user and capture the screen.
#
# Starts mq_ui FIRST (it creates the POSIX mqueue "ui"), then mq_player (the
# backend, which connects to "ui" and pushes state). Waits for input and framebuffer readiness,
# then dumps the framebuffer to PNGs in $SHOTS.
#
# Usage:  emulator/scripts/20_boot.sh [seconds]      (optional extra delay before capture)
#
# Leaves both guest processes RUNNING so you can inject taps with 30_tap.sh, then
# re-capture with `emulator/scripts/capture.sh`. Run `emulator/scripts/99_stop.sh` when done.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
WAIT="${1:-0}"
[ -d "$ROOTFS" ] || { err "no rootfs — run 00/10 first"; exit 1; }
[ -f "$ROOTFS/lib/fbshim.so" ] || { err "shim not installed — run 10_setup_env.sh"; exit 1; }
verify_firmware

apply_ulimits
kill_guest
bash "$REPO/emulator/scripts/15_controls.sh"
bash "$REPO/emulator/scripts/16_network.sh" prepare
rm -f "$ROOTFS/dev/mqueue/"* 2>/dev/null || true
head -c $((SCR_W*SCR_VY*4)) /dev/zero > "$ROOTFS/dev/fb0"
: > "$ROOTFS/dev/input/event1"; : > "$ROOTFS/dev/input/event0"

# Guest lifetime is decoupled from the capture wait so the guests stay alive for the
# interactive viewer (./emulator/run.sh view), not just long enough for one screenshot. Override
# with GUEST_TTL (seconds); the timeout only bounds leaked qemu processes.
GUEST_TTL="${GUEST_TTL:-1800}"
log "Starting mq_ui (creates 'ui' queue)"
guest_run "$GUEST_TTL" /usr/bin/mq_ui  >"$WORK/mq_ui.log"     2>&1 &
sleep 4
log "Starting mq_player (backend)"
guest_run "$GUEST_TTL" /usr/bin/mq_player >"$WORK/mq_player.log" 2>&1 &

# Announce as soon as the stock network detector subscribes, overlapping UI startup.
bash "$REPO/emulator/scripts/16_network.sh" announce
log "Waiting for guest input devices and the first framebuffer flush..."
ROOTFS="$ROOTFS" python3 -m emulator.runtime.boot_ready

# mq_ui umounts /tmp/sdcard during startup (it expects a hotplug remount that never comes
# under emulation). Re-mount the card now, after that umount, so the File Browser — which
# scans /tmp/sdcard live on entry — shows the ./emulator/sdcard content. No-op when there is no card.
if sd_node >/dev/null; then sd_mount; log "SD re-mounted at /tmp/sdcard (File Browser ready)"; fi

sleep "$WAIT"  # explicit CLI capture delay only; the viewer uses no fixed pause

mkdir -p "$SHOTS"; rm -f "$SHOTS"/*.png "$SHOTS"/*.snap 2>/dev/null || true  # fresh set each boot
cp "$ROOTFS/dev/fb0" "$WORK/fb0.snap"
log "Framebuffer captured. Rendering PNGs:"
python3 -m emulator.runtime.fb2png "$WORK/fb0.snap" "$SHOTS" boot
log "Guests left running. Inject taps: emulator/scripts/30_tap.sh <x> <y>   Stop: emulator/scripts/99_stop.sh"
