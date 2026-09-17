#!/usr/bin/env bash
# Exact-build guarded key-enable patch. Unknown binaries fail closed; see docs/PORTING.md.
# Full stock hash (normalizing only the one allowed patch) and PT_LOAD mapping are checked.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
[ "${KEYS_ENABLE:-1}" = "1" ] || { log "KEYS_ENABLE=0 — leaving keys gated"; exit 0; }
python3 -B -m firmware.profile patch-keys "$ROOTFS" --version "$FW_VERSION"
