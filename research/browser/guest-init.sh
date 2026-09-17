#!/bin/sh
# PID 1 inside the browser's RISC-V Linux, never on the Docker host.
export PATH=/bin:/sbin:/usr/bin:/usr/sbin HOME=/root TERM=vt100
mount -a
mkdir -p /sys /exchange /var/log /proc/sys/fs/binfmt_misc
mount -t sysfs sysfs /sys
mount -t binfmt_misc none /proc/sys/fs/binfmt_misc || exec sh
# Match MIPS32 LE only. The F flag keeps the RISC-V interpreter open across chroot.
printf '%s' ':qemu-mipsel:M::\x7f\x45\x4c\x46\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x08\x00:\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xfe\xff\xff\xff:/usr/bin/qemu-mipsel:F' > /proc/sys/fs/binfmt_misc/register || exec sh
mount -t proc proc /disc/proc
mount -t mqueue none /disc/dev/mqueue
ifconfig lo 127.0.0.1
# TinyEMU 9P resides in WASM memory; this does not write to the HTTP server.
mount -t 9p -o trans=virtio,version=9p2000.L,cache=none /dev/root /exchange || exec sh
printf 'set_import_dir .' > /exchange/.fscmd
echo 'BROWSER_DISC: exchange ready'
echo 'BROWSER_DISC: Linux and binfmt ready'
/usr/bin/qemu-mipsel --version
/usr/bin/disc-bridge &
while true; do setsid sh -c 'exec sh < /dev/hvc0 > /dev/hvc0 2>&1'; done
