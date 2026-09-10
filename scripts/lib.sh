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

# rootfs squashfs known-good sha256 (V2.40); assembly is verified against it.
ROOTFS_SHA256="b479e159db5134325819b5f6e5a54388f3adefae373a4ee60680f02d5dcf0bb8"

# Screen geometry (360x360 round panel, 32bpp; virtual y = 3 sub-buffers).
SCR_W=360; SCR_H=360; SCR_VY=1080

log(){ printf '\033[1;36m[*]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }

# Raise the two limits qemu-user needs, in the current shell.
apply_ulimits(){
  ulimit -q 268435256 2>/dev/null || ulimit -q unlimited 2>/dev/null || true  # RLIMIT_MSGQUEUE
  ulimit -n 65536      2>/dev/null || true                                    # RLIMIT_NOFILE
}

# Kill any running guest processes.
kill_guest(){ pkill -f qemu-mipsel 2>/dev/null || true; sleep 1; }

# Convert a screen (as-you-see-it) coordinate to the raw touch coordinate.
# The panel + LVGL display are rotated 180deg; the touch path applies no rotation,
# so tap points must be flipped: raw = 359 - displayed.  (see docs/TOUCH.md)
rot(){ echo $(( (SCR_W-1) - $1 )) $(( (SCR_H-1) - $2 )); }
