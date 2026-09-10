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

# char-device stubs mq_player opens (0-byte files: open() succeeds, later ioctls fail
# harmlessly). Without /dev/gpio, mq_player aborts at "failed to open device" BEFORE it
# inits the DAC and pushes UI state, so the UI never leaves the splash.
: > "$ROOTFS/dev/gpio"
: > "$ROOTFS/dev/jz_adc_aux_0"
: > "$ROOTFS/dev/jz_watchdog"
: > "$ROOTFS/dev/key_ioctl"   # physical-key handler (echo_key_handler); non-fatal but noisy

# SD card: the File Browser reads the guest's /tmp/sdcard. compose bind-mounts the host
# ./sdcard folder to /sdcard (outside the rootfs volume, so it can't clobber the unpack);
# here we bind it into the rootfs at /tmp/sdcard AFTER extraction. Drop media into ./sdcard
# and it shows up in the browser (re-boot to rescan). Idempotent; re-done each setup.
if [ -d /sdcard ]; then
  # (1) Content: bind ./sdcard onto the guest's /tmp/sdcard (chroot => $ROOTFS/tmp/sdcard),
  #     which is where the File Browser reads. /tmp is a real dir in this rootfs.
  mkdir -p "$ROOTFS/tmp/sdcard"
  mountpoint -q "$ROOTFS/tmp/sdcard" || mount --bind /sdcard "$ROOTFS/tmp/sdcard"
  # (2) /proc/mounts match: the guest verifies the card by searching /proc/mounts for the exact
  #     mountpoint "/tmp/sdcard" (FUN_004147ac). Under chroot it otherwise sees only
  #     "$ROOTFS/tmp/sdcard". So ALSO bind the same source at the container's own /tmp/sdcard.
  mkdir -p /tmp/sdcard
  mountpoint -q /tmp/sdcard || mount --bind /sdcard /tmp/sdcard
  # (3) "card inserted" flag: mq_ui init runs system("[ -e /dev/mmcblk0 ]") (FUN_004891b8).
  : > "$ROOTFS/dev/mmcblk0"
  : > "$ROOTFS/dev/mmcblk0p1"
  M1=no; mountpoint -q "$ROOTFS/tmp/sdcard" && M1=yes
  M2=no; mountpoint -q /tmp/sdcard && M2=yes
  log "SD: guest-bind=$M1 procmounts-bind=$M2 + mmcblk stubs"
fi

# 5) Battery fuel gauge (cw2215). Without a healthy capacity the UI shows the
#    "battery too low, shutting down" countdown instead of booting.
log "Battery sysfs: cw221X-bat = 100%, Full"
B="$ROOTFS/sys/class/power_supply/cw221X-bat"; mkdir -p "$B"
printf Battery > "$B/type";     printf 100 > "$B/capacity"; printf Full > "$B/status"
printf Good    > "$B/health";   printf 1   > "$B/present";  printf Li-ion > "$B/technology"
printf 4200000 > "$B/voltage_now"; printf 250 > "$B/temp";  printf 1 > "$B/online"

# 5b) Seed /usr/data as the device's first boot does. On hardware /usr/data is a blank
#     UBIFS partition that init scripts S98FIIO + fiio_init.sh populate from templates
#     shipped in the rootfs. We don't run init, so replicate the essential parts — above
#     all the zlog configs: without them mq_player's zlog_init() fails ("Error: zlog_init"),
#     the backend never starts, and sysconfig.db is never created (UI stays on the splash).
log "Seeding /usr/data (zlog configs + db templates), like S98FIIO/fiio_init.sh"
mkdir -p "$ROOTFS/usr/data/fiio/log" "$ROOTFS/usr/data/fiio/db" "$ROOTFS/usr/data/fiio/wifi"
cp -f "$ROOTFS/usr/project/config/zlog_player.conf" "$ROOTFS/usr/data/fiio/log/" 2>/dev/null || err "  zlog_player.conf template missing"
cp -f "$ROOTFS/usr/project/config/zlog_ui.conf"     "$ROOTFS/usr/data/fiio/log/" 2>/dev/null || err "  zlog_ui.conf template missing"
cp -f "$ROOTFS"/usr/project/db/*          "$ROOTFS/usr/data/fiio/db/"   2>/dev/null || true  # dic.db etc.
cp -f "$ROOTFS"/usr/project/config/wifi/* "$ROOTFS/usr/data/fiio/wifi/" 2>/dev/null || true
cp -f "$ROOTFS/etc/hostapd.conf"          "$ROOTFS/usr/data/"           2>/dev/null || true

# 6) Config DB: disable the boot logo animation (an infinite-loop overlay drawn on top
#    of the already-built main screen; it never auto-clears under emu).
#    /usr/data is a SEPARATE UBIFS partition on the device (S21mount_ubifs) and is empty
#    in the squashfs, so on a fresh rootfs sysconfig.db does not exist yet — mq_player
#    creates it on first boot with LOCAL_IMG_ANIM=1. We must prime it (one throwaway boot
#    to create the DB) BEFORE we can set the flag; otherwise the very first real boot is
#    stuck on the splash. Idempotent: skipped once the DB exists.
DB="$ROOTFS/usr/data/fiio/db/sysconfig.db"
if [ ! -f "$DB" ]; then
  log "sysconfig.db absent (fresh /usr/data) — priming boot to create it (~20s)..."
  apply_ulimits
  rm -f "$ROOTFS/dev/mqueue/"* 2>/dev/null || true
  timeout 45 chroot "$ROOTFS" /usr/bin/mq_ui     >/dev/null 2>&1 &
  sleep 3
  timeout 42 chroot "$ROOTFS" /usr/bin/mq_player >/dev/null 2>&1 &
  for i in $(seq 1 35); do [ -f "$DB" ] && break; sleep 1; done
  kill_guest
  [ -f "$DB" ] && log "  sysconfig.db created" || err "  DB still absent after priming (see $WORK/*.log)"
fi
if [ -f "$DB" ]; then
  # LANGUAGE is a 0-based index (switch in mq_ui FUN_004776e4): 0 zh(简体) 1 tw(繁體) 2 en
  # 3 ja 4 ko 5 es 6 it 7 de 8 pt 9 ru. Any in-range value ALSO skips the first-boot language
  # wizard (the wizard shows only while LANGUAGE is out of range, e.g. the fresh default 100).
  # Default 2 = English. Override with LANG_CODE=<n>.
  LANG_CODE="${LANG_CODE:-2}"
  log "sysconfig.db: LOCAL_IMG_ANIM=0, BATTERY=100, LANGUAGE=$LANG_CODE"
  sqlite3 "$DB" "UPDATE SYSCONFIG SET LOCAL_IMG_ANIM=0, BATTERY=100, LANGUAGE=$LANG_CODE;" || err "  sqlite update failed"
else
  err "  could not create/find sysconfig.db — first real boot may stay on the splash"
fi

log "Environment ready. Next: scripts/20_boot.sh"
