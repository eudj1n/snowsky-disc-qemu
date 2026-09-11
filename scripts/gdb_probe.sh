#!/usr/bin/env bash
# Runtime inspection of mq_player via qemu-user's gdbstub — observe LIVE state before patching.
# (Lesson from the audio task: static decompilation alone whack-a-moles a hardware state machine;
#  read the actual globals/branches at runtime instead. See docs/RE.md.)
#
# Boots mq_ui normally, launches mq_player under the gdbstub (explicit `qemu -g`, so QEMU_GDB is
# NOT inherited by its popen children — they run via binfmt as usual), then runs gdb-multiarch with
# your command file. Leave a background tapper driving playback if your breakpoint is on the audio
# path (it only fires when a track plays).
#
# Usage:  scripts/gdb_probe.sh <gdb-cmd-file> [port]     (run INSIDE the container)
#   e.g.  scripts/gdb_probe.sh /repo/ghidra/probe_out_device.gdb
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
CMD="${1:?usage: gdb_probe.sh <gdb-cmd-file> [port]}"; PORT="${2:-1234}"
command -v gdb-multiarch >/dev/null || { err "gdb-multiarch not installed"; exit 1; }

apply_ulimits; kill_guest
rm -f "$ROOTFS/dev/mqueue/"* 2>/dev/null || true
head -c $((SCR_W*SCR_VY*4)) /dev/zero > "$ROOTFS/dev/fb0"
: > "$ROOTFS/dev/input/event1"; : > "$ROOTFS/dev/input/event0"

log "Starting mq_ui"
guest_run 360 /usr/bin/mq_ui >"$WORK/mq_ui.log" 2>&1 &
sleep 4
log "Starting mq_player under gdbstub :$PORT (waits for gdb)"
# explicit qemu with -g; children spawned by mq_player go through binfmt (no gdbstub)
guest_run 360 /usr/bin/qemu-mipsel-static -g "$PORT" /usr/bin/mq_player \
  >"$WORK/mq_player.log" 2>&1 &
sleep 2
if sd_node >/dev/null; then sd_mount; fi
log "Attaching gdb-multiarch with $CMD"
# set the MIPS32r2 LE arch + load the binary for symbols BEFORE connecting, else gdb-multiarch
# mis-sizes the register packet ("Truncated register" ) and can't read regs/memory.
gdb-multiarch -q -nx -batch \
  -ex "set architecture mips:isa32r2" \
  -ex "set endian little" \
  -ex "file $ROOTFS/usr/bin/mq_player" \
  -ex "target remote :$PORT" \
  -x "$CMD"
