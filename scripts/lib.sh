#!/usr/bin/env bash
# Shared paths + helpers for the Snowsky Disc qemu emulation scripts.
# Sourced by the numbered scripts. Run everything INSIDE the container.
set -euo pipefail

# --- paths -------------------------------------------------------------------
WORK="${WORK:-/work}"                 # persistent state (mount a host dir/volume here)
ROOTFS="${ROOTFS:-$WORK/rootfs}"      # extracted firmware rootfs
REPO="${REPO:-/repo}"                 # this repository (mounted)
SHOTS="${SHOTS:-$WORK/shots}"         # captured PNG framebuffers
QEMU="${QEMU:-/usr/bin/qemu-mipsel-static}"

# Explicit runtime selection, defaulting to the released baseline. Pins live in firmware/v*.json.
FW_VERSION="${FW_VERSION:-2.57}"
verify_firmware(){ python3 -B "$REPO/tools/firmware_profile.py" validate "$ROOTFS" --version "$FW_VERSION"; }

# Screen geometry (360x360 round panel, 32bpp; virtual y = 3 sub-buffers).
SCR_W=360; SCR_H=360; SCR_VY=1080

log(){ printf '\033[1;36m[*]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }

# Raise the two limits qemu-user needs, in the current shell.
apply_ulimits(){
  ulimit -q 268435256 2>/dev/null || ulimit -q unlimited 2>/dev/null || true  # RLIMIT_MSGQUEUE
  ulimit -n 65536      2>/dev/null || true                                    # RLIMIT_NOFILE
}

# Stop only processes chrooted into this guest, including its popen children.
# Do not pkill every qemu process: another rootfs may be running in this container.
kill_guest(){ ROOTFS="$ROOTFS" python3 "$REPO/tools/keys.py" stop; }

# qemu-user shares the Docker VM kernel. Firmware children must not reconfigure
# interfaces, set wall/RTC clocks, reboot the VM, or load modules. Keep SYS_ADMIN
# for the existing guest SD mount workflow; this is not a complete sandbox.
guest_run(){
  local ttl="$1"; shift
  timeout "$ttl" setpriv --bounding-set=-net_admin,-sys_time,-sys_boot,-sys_module,-sys_rawio \
    --no-new-privs chroot "$ROOTFS" "$@"
}

# --- SD card -----------------------------------------------------------------
# The firmware's mq_ui (util/src/mount_storage_dev.c) UMOUNTS /tmp/sdcard once at
# startup: on hardware a hotplug handler then remounts the card, but under emulation
# nothing does, so /tmp/sdcard ends up empty and the File Browser shows nothing.
# The File Browser scans /tmp/sdcard *live on entry*, so all we have to do is keep
# the card mounted. sd_mount() (re-)mounts /dev/mmcblk0p1 exactly like the guest would
# (`mount -o iocharset=utf8`) at BOTH the guest rootfs path (content the browser reads)
# and the container's own /tmp/sdcard (so /proc/mounts carries the exact "/tmp/sdcard"
# line FUN_004147ac scans for). Idempotent; a no-op when there is no card. Call it
# after the boot-time umount (end of 20_boot.sh) and before injecting taps (30_tap.sh).
sd_node(){ [ -b "$ROOTFS/dev/mmcblk0p1" ] && printf '%s' "$ROOTFS/dev/mmcblk0p1"; }
sd_mount(){
  local node; node="$(sd_node)" || return 0
  [ -n "$node" ] || return 0
  mkdir -p "$ROOTFS/tmp/sdcard" /tmp/sdcard
  # The scanner checks access(source) for each /proc/mounts entry. A mount made
  # with the container path /work/rootfs/dev/mmcblk0p1 leaves that inaccessible
  # source string in the guest's mount table. Mount INSIDE chroot so the source
  # is /dev/mmcblk0p1, accessible to both the scanner and Browse files.
  if mountpoint -q "$ROOTFS/tmp/sdcard" &&
     [ "$(findmnt -n -o SOURCE --target "$ROOTFS/tmp/sdcard")" = "$node" ]; then
    umount "$ROOTFS/tmp/sdcard" || { err 'SD source migration busy; stop guest first'; return 1; }
  fi
  mountpoint -q "$ROOTFS/tmp/sdcard" || \
    guest_run 10 /bin/mount -t vfat -o iocharset=utf8 /dev/mmcblk0p1 /tmp/sdcard
  mountpoint -q /tmp/sdcard          || mount -t vfat -o iocharset=utf8 "$node" /tmp/sdcard          2>/dev/null || true
  # Both mmc nodes alias one loop device. Stock blkid enumeration initially
  # caches only mmcblk0, while hotplug runs `blkid | grep /dev/mmcblk0p1`.
  # Probe the partition explicitly so stock remove/add can remount it itself.
  # Keep real filesystem detection and its cache; do not synthesize blkid output.
  sd_probe
}

sd_probe(){
  guest_run 10 /sbin/blkid /dev/mmcblk0p1 >/dev/null || {
    err 'SD filesystem discovery failed'; return 1;
  }
}

# Convert a screen (as-you-see-it) coordinate to the raw touch coordinate.
# The panel + LVGL display are rotated 180deg; the touch path applies no rotation,
# so tap points must be flipped: raw = 359 - displayed.  (see docs/TOUCH.md)
rot(){ echo $(( (SCR_W-1) - $1 )) $(( (SCR_H-1) - $2 )); }
