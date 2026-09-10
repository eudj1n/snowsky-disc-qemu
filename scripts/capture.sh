#!/usr/bin/env bash
# Re-capture the current framebuffer to PNGs (guests from 20_boot.sh must be running).
# Usage: scripts/capture.sh [prefix]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
PREFIX="${1:-cap}"
mkdir -p "$SHOTS"
cp "$ROOTFS/dev/fb0" "$WORK/fb0.snap"
python3 "$REPO/tools/fb2png.py" "$WORK/fb0.snap" "$SHOTS" "$PREFIX"
