#!/usr/bin/env bash
# Prepare a fresh, paused DISC rootfs using the reviewed emulator pipeline.
# Uses a disposable Compose stack, no published ports, no user's media/state.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export OTA_DIR="$(cd "${1:?usage: prepare-firmware.sh /path/to/main_os/ota_v257}" && pwd)"
export FW_VERSION="$(cat firmware/active-version)"
export EMU_IMAGE="${EMU_IMAGE:-snowsky-disc-qemu-ci}"
OUTPUT="$PWD/work/browser-disc"
mkdir -p "$OUTPUT/empty-sd"
export SD_DIR="$OUTPUT/empty-sd"
PREP_ID="snowsky-browser-prep-$$"
export EMU_CONTAINER_NAME="$PREP_ID-emu"
export WORK_VOLUME="$PREP_ID-work"
compose() { docker compose --project-directory "$PWD" --env-file /dev/null -p "$PREP_ID" -f emulator/compose.yaml -f ci/compose.yml "$@"; }
cleanup() {
    compose exec -T emulator bash /repo/ci/cleanup.sh || true
    compose down --volumes --timeout 5
}
trap cleanup EXIT
compose up -d --no-build emulator
compose exec -T emulator bash /repo/emulator/scripts/00_extract_rootfs.sh /ota
compose exec -T emulator bash /repo/emulator/scripts/10_setup_env.sh
compose exec -T emulator python3 -B -m firmware.profile validate /work/rootfs
# 10_setup_env's priming guest has already stopped. Omit mounted kernel views.
compose exec -T emulator tar --one-file-system --exclude='./proc/*' --exclude='./dev/mqueue/*' \
    -C /work/rootfs -cf /repo/work/browser-disc/disc-prepared.tar.tmp .
mv "$OUTPUT/disc-prepared.tar.tmp" "$OUTPUT/disc-prepared.tar"
printf 'Prepared %s\n' "$OUTPUT/disc-prepared.tar"
