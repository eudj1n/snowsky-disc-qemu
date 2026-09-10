#!/usr/bin/env bash
# Prepare the runtime environment so the MIPS firmware can boot to its main UI
# under qemu-user. Idempotent: safe to re-run (e.g. after a container restart,
# which clears mounts + binfmt).
#
# Encodes every non-obvious fix required to reach the main screen — see docs/EMULATION.md.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
[ -d "$ROOTFS" ] || { err "no rootfs at $ROOTFS — run 00_extract_rootfs.sh first"; exit 1; }

# 1) binfmt_misc: register ONLY the mipsel interpreter, with a mask that ignores
#    ELF bytes 6-15 so it matches every MIPS32 LE guest binary (busybox etc.) but
#    NOTHING else. Do NOT use `qemu-binfmt --reset -p yes`: it registers qemu-aarch64
#    too and hijacks the host's own native binaries -> "exec format error".
log "binfmt_misc: mipsel interpreter"
mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc none /proc/sys/fs/binfmt_misc 2>/dev/null || true
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-mipsel ]; then
  MAGIC='\x7f\x45\x4c\x46\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x08\x00'
  MASK='\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xfe\xff\xff\xff'
  printf ":qemu-mipsel:M::${MAGIC}:${MASK}:${QEMU}:F" > /proc/sys/fs/binfmt_misc/register \
    && log "  registered" || err "  registration failed (already present?)"
fi

# 2) Build + install the framebuffer/input ioctl shim.
log "Building shims"
"$REPO/shim/build_shims.sh"
cp "$WORK/fbshim.so" "$ROOTFS/lib/fbshim.so"
echo "/lib/fbshim.so" > "$ROOTFS/etc/ld.so.preload"   # guest ld.so reads this (LD_PRELOAD won't survive popen)

# 3) Kernel filesystems the guest expects.
log "Mounts: /proc, /dev/mqueue in rootfs"
mkdir -p "$ROOTFS/proc" "$ROOTFS/dev/mqueue"
mountpoint -q "$ROOTFS/proc"       || mount -t proc   proc "$ROOTFS/proc"       2>/dev/null || true
mountpoint -q "$ROOTFS/dev/mqueue" || mount -t mqueue none "$ROOTFS/dev/mqueue" 2>/dev/null || true

# 4) /dev stubs. fb0 is a plain file (qemu mmaps it fine). event0/event1 are plain
#    files we append input_event structs to; their driver "name" is read from sysfs.
log "/dev stubs: fb0, input/event0 (x2000_key), input/event1 (cst816t)"
head -c $((SCR_W*SCR_VY*4)) /dev/zero > "$ROOTFS/dev/fb0"
mkdir -p "$ROOTFS/dev/input" \
         "$ROOTFS/sys/class/input/event0/device" \
         "$ROOTFS/sys/class/input/event1/device"
: > "$ROOTFS/dev/input/event0"; : > "$ROOTFS/dev/input/event1"
echo x2000_key > "$ROOTFS/sys/class/input/event0/device/name"   # GPIO keys
echo cst816t   > "$ROOTFS/sys/class/input/event1/device/name"   # capacitive touch

# 5) Battery fuel gauge (cw2215). Without a healthy capacity the UI shows the
#    "battery too low, shutting down" countdown instead of booting.
log "Battery sysfs: cw221X-bat = 100%, Full"
B="$ROOTFS/sys/class/power_supply/cw221X-bat"; mkdir -p "$B"
printf Battery > "$B/type";     printf 100 > "$B/capacity"; printf Full > "$B/status"
printf Good    > "$B/health";   printf 1   > "$B/present";  printf Li-ion > "$B/technology"
printf 4200000 > "$B/voltage_now"; printf 250 > "$B/temp";  printf 1 > "$B/online"

# 6) Config DB: disable the boot logo animation (it is an infinite-loop overlay
#    drawn on top of the already-built main screen; it never auto-clears under emu).
log "sysconfig.db: LOCAL_IMG_ANIM=0, BATTERY=100"
DB="$ROOTFS/usr/data/fiio/db/sysconfig.db"
if [ -f "$DB" ]; then
  sqlite3 "$DB" "UPDATE SYSCONFIG SET LOCAL_IMG_ANIM=0, BATTERY=100;" || err "  sqlite update failed"
else
  err "  $DB missing (fresh rootfs? it is created on first boot)"
fi

log "Environment ready. Next: scripts/20_boot.sh"
