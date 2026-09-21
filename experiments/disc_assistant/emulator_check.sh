#!/usr/bin/env bash
# Isolated firmware acceptance for the experimental Assistant; never interactive volumes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export OTA_DIR="$(cd "${1:?path to reviewed V2.57 OTA chunks}" && pwd)"
assistant_scenario="${2:-all}"
case "$assistant_scenario" in all|persistent) ;; *) echo 'Expected all or persistent scenario' >&2; exit 2;; esac
export FW_VERSION=2.57
export EMU_IMAGE="${EMU_IMAGE:-snowsky-disc-qemu-ci}"
assistant_tmp="$(mktemp -d "${TMPDIR:-/tmp}/disc-assistant-emu.XXXXXXXX")"
assistant_project="disc-assistant-$(basename "$assistant_tmp" | tr '[:upper:].' '[:lower:]-')"
export EMU_CONTAINER_NAME="$assistant_project-emu"
export WORK_VOLUME="$assistant_project-work"
export SD_DIR="$assistant_tmp/sdcard"
mkdir "$SD_DIR"
compose() { docker compose --project-directory "$PWD" --env-file /dev/null -p "$assistant_project" -f emulator/compose.yaml -f ci/compose.yml "$@"; }
cleanup() {
  if [[ -n ${ASSISTANT_LOGS:-} ]]; then
    mkdir -p "$ASSISTANT_LOGS"
    compose cp emulator:/work/mq_player.log "$ASSISTANT_LOGS/mq_player.log" || true
    compose cp emulator:/work/mq_ui.log "$ASSISTANT_LOGS/mq_ui.log" || true
  fi
  compose exec -T emulator bash /repo/ci/cleanup.sh || true
  compose down --volumes --timeout 5
  docker run --rm --network none -v "$assistant_tmp:/cleanup" "$EMU_IMAGE" \
    python3 -c 'import shutil; shutil.rmtree("/cleanup/sdcard")'
  rmdir "$assistant_tmp"
}
trap cleanup EXIT
compose config --quiet
docker run --rm --network none -v "$PWD:/repo:ro" -v "$SD_DIR:/fixtures" "$EMU_IMAGE" \
  bash -c 'cd /repo && python3 -B -m experiments.disc_assistant.emulator_check --fixtures /fixtures'
compose up -d --no-build --wait --wait-timeout 60 emulator
compose exec -T emulator bash /repo/emulator/scripts/00_extract_rootfs.sh /ota
compose exec -T emulator bash /repo/emulator/scripts/10_setup_env.sh
compose exec -T emulator python3 -B -m tests.integration.awake_check --configure
compose exec -T emulator bash /repo/emulator/scripts/20_boot.sh
compose exec -T emulator python3 -B -m tests.integration.awake_check
if [[ "$assistant_scenario" == persistent ]]; then
  compose exec -T emulator python3 -B -m experiments.disc_assistant.emulator_check --persistent-only
else
  compose exec -T emulator python3 -B -m experiments.disc_assistant.emulator_check
fi
