#!/usr/bin/env bash
# Enable physical-key handling in the emulated mq_player.
#
# The stock key dispatcher (echo_sys_key_handler, echo_sys_control.c) gates every key on a
# "key-enable" flag (DAT_0082e9c1) that is set by an init/IPC step which doesn't run headless,
# so injected key events (event0) are read but dropped. This flips the flag load to a constant 1
# so the dispatcher always proceeds. See docs/RE.md for the full reverse-engineering.
#
# Idempotent, and safe on a wrong build: it patches ONLY when it finds the exact V2.40 guard
# instruction sequence, and no-ops if already patched or if the pattern is absent (a new firmware
# version whose addresses shifted — re-run the RE from docs/RE.md and update the pattern).
#
# Runs INSIDE the container (called from 10_setup_env.sh). Toggle off with KEYS_ENABLE=0.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
BIN="$ROOTFS/usr/bin/mq_player"
[ -f "$BIN" ] || { err "no mq_player at $BIN"; exit 1; }
[ "${KEYS_ENABLE:-1}" = "1" ] || { log "KEYS_ENABLE=0 — leaving keys gated"; exit 0; }

python3 - "$BIN" <<'PY'
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read())
# guard prologue (V2.40): addiu s2,v0,-5760 (2452e980) ; lbu v0,65(s2) (92420041)
ANCHOR = bytes.fromhex("80e95224")          # addiu s2,v0,-5760  (LE)
ORIG   = bytes.fromhex("41004292")          # lbu  v0,65(s2)     (LE)
PATCH  = bytes.fromhex("01000224")          # li   v0,1          (LE) -> flag reads as 1
i = b.find(ANCHOR)
if i < 0:
    print("[patch_keys] guard pattern not found — firmware changed? see docs/RE.md; skipping")
    sys.exit(0)
j = i + 4
if b[j:j+4] == PATCH:
    print("[patch_keys] already patched (keys enabled)")
    sys.exit(0)
if b[j:j+4] != ORIG:
    print("[patch_keys] unexpected bytes after anchor (%s) — skipping" % b[j:j+4].hex())
    sys.exit(0)
b[j:j+4] = PATCH
open(p, "wb").write(b)
print("[patch_keys] enabled physical keys (patched lbu -> li v0,1 at file off 0x%x)" % j)
PY
