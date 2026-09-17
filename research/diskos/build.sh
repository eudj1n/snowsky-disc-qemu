#!/usr/bin/env bash
# Build local GPL diskOS sources with our link-time emulation adapter.
# No installer, image repacking, NAND writer or firmware download is involved.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$(cd "${1:?usage: build.sh /path/to/diskos}" && pwd)"
OUT="$REPO/work/diskos-preview"
REVISION="$(cat "$REPO/research/diskos/source-revision")"
git -C "$SOURCE" cat-file -e "$REVISION^{commit}" || {
  printf 'Fetch the reviewed diskOS commit first: %s\n' "$REVISION" >&2; exit 1;
}
mkdir -p "$OUT"
BUILD="$(mktemp -d "$OUT/build.XXXXXXXX")"
# Archive the reviewed commit, excluding local edits, ignored objects and config.mk.
git -C "$SOURCE" archive --format=tar "$REVISION" ui | tar -xf - -C "$BUILD" --strip-components=1
(cd "$REPO" && python3 -B -m research.diskos.prepare "$BUILD")
# Keep the adapter and its license beside the adapted upstream source.
mkdir -p "$BUILD/emulator-adapter"
cp "$REPO/research/diskos/emu_io.c" "$BUILD/emulator-adapter/emu_io.c"
cp "$REPO/LICENSE" "$BUILD/emulator-adapter/LICENSE"
docker build -t diskos-ui-builder "$BUILD"
docker run --rm --platform linux/amd64 --network none \
  -v "$BUILD:/src" diskos-ui-builder sh -c '
    set -eu
    make clean >/dev/null
    ${CROSS}gcc -Os -static -Wall -Wextra -c /src/emulator-adapter/emu_io.c -o /tmp/emu_io.o
    make -j4 CROSS="$CROSS" LDFLAGS="-static -pthread -Wl,--wrap=ioctl /tmp/emu_io.o"
  '
cp "$BUILD/mq_ui" "$OUT/mq_ui"
printf '%s\n' "$REVISION" > "$OUT/source-commit.txt"
printf 'Emulation-only binary: %s\nSource/build directory: %s\n' "$OUT/mq_ui" "$BUILD"
