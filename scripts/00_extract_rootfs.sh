#!/usr/bin/env bash
# Verify and extract the selected exact firmware into a NEW rootfs.
# FW_VERSION defaults to 2.57. Use a separate work volume for each version.
# Never replace an existing rootfs or print the OTA password.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
OTA="${1:?usage: 00_extract_rootfs.sh <ota_chunk_dir>}"
log "Verifying and extracting firmware V$FW_VERSION -> $ROOTFS"
python3 -B "$REPO/tools/firmware_extract.py" "$OTA" "$ROOTFS" --version "$FW_VERSION"
log "Done. Next: scripts/10_setup_env.sh"
