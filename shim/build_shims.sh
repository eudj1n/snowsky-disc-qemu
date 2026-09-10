#!/usr/bin/env bash
# Cross-compile the freestanding MIPS shims and set the nan2008 ELF flag so the
# device's ld-linux-mipsn8 loader will map them (the stock rootfs is nan2008).
#
# Output: $WORK/fbshim.so  (and mqshim.so, a diagnostic-only mq_open interposer).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-/work}"
CC="${CC:-mipsel-linux-gnu-gcc}"
CFLAGS="-shared -fPIC -mabi=32 -march=mips32r2 -nostdlib"

build(){ # <src> <out>
  "$CC" $CFLAGS -o "$WORK/$2" "$HERE/$1"
  # set EI flags byte / e_flags nan2008 bit: e_flags is at file offset 36 (0x24)
  # for a 32-bit LE ELF; 0x70001407 = nan2008|o32|mips32r2|pic|cpic.
  printf '\x07\x14\x00\x70' | dd of="$WORK/$2" bs=1 seek=36 count=4 conv=notrunc status=none
  echo "  built $WORK/$2"
}

build fbshim.c fbshim.so
[ -f "$HERE/mqshim.c" ] && build mqshim.c mqshim.so || true
