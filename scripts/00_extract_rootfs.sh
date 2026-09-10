#!/usr/bin/env bash
# Decrypt + assemble + unpack the V2.40 rootfs from the OTA firmware.
#
# Usage (inside container):  scripts/00_extract_rootfs.sh /ota
#   where /ota is the directory that contains the OTA chunks, i.e. the
#   `main_os/ota_v240/` folder from the extracted firmware ZIP (see firmware/README.md).
#
# Output: $ROOTFS  (default /work/rootfs), the extracted firmware root filesystem.
#
# The firmware itself is NOT in this repo. Download it from FiiO (firmware/README.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"

OTA="${1:?usage: 00_extract_rootfs.sh <ota_v240_dir>}"
PASS="fo123"                            # OTA chunk AES password (public knowledge)
SQUASH="$WORK/rootfs.squashfs"

[ -d "$OTA" ] || { err "OTA dir not found: $OTA"; exit 1; }
ls "$OTA"/rootfs.squashfs.*.enc >/dev/null 2>&1 || { err "no rootfs.squashfs.*.enc chunks in $OTA"; exit 1; }

mkdir -p "$WORK"
log "Decrypting + concatenating rootfs chunks (AES-256-CBC / PBKDF2 / password '$PASS')..."
: > "$SQUASH"
# chunks are named rootfs.squashfs.<NNNN>.<sha>.enc — assemble in numeric index order
for f in $(ls "$OTA"/rootfs.squashfs.*.enc | sort -t. -k3 -n); do
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 10000 -k "$PASS" -in "$f" >> "$SQUASH"
done

log "Verifying rootfs.squashfs sha256..."
GOT="$(sha256sum "$SQUASH" | awk '{print $1}')"
if [ "$GOT" != "$ROOTFS_SHA256" ]; then
  err "sha256 mismatch! got $GOT expected $ROOTFS_SHA256"
  err "(firmware version other than V2.40? update ROOTFS_SHA256 in lib.sh)"
  exit 1
fi
log "OK: $(du -h "$SQUASH" | cut -f1) squashfs, sha256 verified."

log "Unpacking squashfs -> $ROOTFS ..."
rm -rf "$ROOTFS"
unsquashfs -d "$ROOTFS" "$SQUASH" >/dev/null
log "Done. rootfs at $ROOTFS ($(du -sh "$ROOTFS" | cut -f1))."
log "Next: scripts/10_setup_env.sh"
