#!/usr/bin/env bash
# Launch mq_ui + mq_player inside a PRIVATE mount namespace with /work/rootfs as the real root
# (pivot_root), so the guest's SD mount and its /proc/mounts check both see "/tmp/sdcard".
# Invoke detached:  docker exec -d <ctr> unshare --mount --propagation private bash /repo/scripts/ns_launch.sh
set -u
R=/work/rootfs
LOOP="$(losetup -j /work/sdcard.img 2>/dev/null | cut -d: -f1 | head -1)"
cp -f /usr/bin/qemu-mipsel-static "$R/usr/bin/qemu-mipsel-static" 2>/dev/null || true
mount --bind "$R" "$R"
mount -t proc   proc "$R/proc"       2>/dev/null || true
mount -t mqueue none "$R/dev/mqueue" 2>/dev/null || true
if [ -n "$LOOP" ]; then mkdir -p "$R/tmp/sdcard"; mount "$LOOP" "$R/tmp/sdcard" 2>/dev/null || true; fi
cd "$R"; mkdir -p .oldroot
pivot_root . .oldroot
umount -l /.oldroot 2>/dev/null || true
ulimit -q 268435256 2>/dev/null || true
ulimit -n 65536      2>/dev/null || true
rm -f /dev/mqueue/* 2>/dev/null || true
{ echo "== ns /proc/mounts sdcard =="; grep sdcard /proc/mounts; echo "== ns /tmp/sdcard =="; ls /tmp/sdcard; } > /ns_sd.txt 2>&1
/usr/bin/qemu-mipsel-static /usr/bin/mq_ui     >/mq_ui_ns.log 2>&1 &
sleep 4
/usr/bin/qemu-mipsel-static /usr/bin/mq_player >/mq_player_ns.log 2>&1 &
wait
