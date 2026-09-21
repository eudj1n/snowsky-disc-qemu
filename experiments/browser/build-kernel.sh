#!/usr/bin/env bash
# Run in snowsky-disc-browser-build; all output remains in ignored work/.
set -euo pipefail
cd /repo/work/browser-disc
LINUX=riscv-linux-a3b1e7acc6a181e04e9a943942084395df4498dd
if [ ! -d "$LINUX" ]; then tar -xzf downloads/linux-tinyemu.tar.gz; fi
cd "$LINUX"
if [ ! -f .browser-patched ]; then
    patch -p1 < ../diskimage-linux-riscv-2018-09-23/patches/riscv-linux.diff
    # Modern binutils separates CSR/fence instructions from the base ISA.
    python3 - <<'PY'
from pathlib import Path
p = Path('arch/riscv/Makefile')
s = p.read_text()
assert s.count('$(KBUILD_ARCH_C)\n') == 2
p.write_text(s.replace('$(KBUILD_ARCH_C)\n', '$(KBUILD_ARCH_C)_zicsr_zifencei\n'))
PY
    touch .browser-patched
fi
python3 - <<'PY'
from pathlib import Path
p = Path('arch/riscv/kernel/vdso/Makefile')
s = p.read_text()
p.write_text(s.replace('$(KCFLAGS) -nostdlib', '$(KCFLAGS) -no-pie -nostdlib'))
PY
cp ../diskimage-linux-riscv-2018-09-23/patches/config_linux_riscv64 .config
scripts/config --enable BINFMT_MISC --enable POSIX_MQUEUE --enable SYSVIPC \
    --enable IKCONFIG --enable IKCONFIG_PROC
make ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
make -j"${BUILD_JOBS:-4}" ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- \
    HOSTCFLAGS='-O2 -fcommon' KCFLAGS=-fno-pie vmlinux
riscv64-linux-gnu-objcopy -O binary vmlinux ../kernel-browser.bin
