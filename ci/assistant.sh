#!/usr/bin/env bash
# Opt-in, disposable Assistant → Typesense → stock firmware scenarios.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export OTA_DIR="$(cd "${1:?usage: bash ci/assistant.sh OTA_DIR NEW_REPORT_DIR [--case ID ...]}" && pwd)"
report_arg="${2:?new report directory required}"
shift 2
mkdir -m 700 "$report_arg"
export ASSISTANT_REPORT_DIR="$(cd "$report_arg" && pwd)"
exec > >(tee "$ASSISTANT_REPORT_DIR/run.log") 2>&1
export FW_VERSION="$(cat firmware/active-version)"
[[ "$FW_VERSION" == 2.57 ]] || { echo 'Assistant fixture is reviewed for V2.57 only' >&2; exit 2; }
export EMU_IMAGE="${EMU_IMAGE:-snowsky-disc-qemu-ci}"
task_tmp="$(mktemp -d "${TMPDIR:-/tmp}/disc-assistant-ci.XXXXXXXX")"
task_id="disc-assistant-$(basename "$task_tmp" | tr '[:upper:].' '[:lower:]-')"
export EMU_CONTAINER_NAME="$task_id-emu" WORK_VOLUME="$task_id-work"
export SD_DIR="$task_tmp/media" GUEST_TTL=3600 LANG_CODE=2 DEVICE_BOOT_SCRIPT=""
export ASSISTANT_TEST_KEY="$(openssl rand -hex 24)"
export ASSISTANT_SOURCE_REVISION="$(git rev-parse HEAD)"
mkdir "$SD_DIR"
compose() { docker compose --env-file /dev/null -p "$task_id" -f compose.yaml -f ci/compose.yml -f ci/assistant.compose.yml "$@"; }
cleanup() {
  result=$?
  trap - EXIT
  compose cp emu:/work/mq_player.log "$ASSISTANT_REPORT_DIR/mq_player.log" >/dev/null 2>&1 || true
  compose cp emu:/work/mq_ui.log "$ASSISTANT_REPORT_DIR/mq_ui.log" >/dev/null 2>&1 || true
  compose exec -T emu bash /repo/ci/cleanup.sh >/dev/null 2>&1 || true
  compose down --volumes --timeout 5 || true
  # Remove only this run's mktemp directory and generated media.
  rm -rf -- "$task_tmp"
  echo "Assistant evidence: $ASSISTANT_REPORT_DIR"
  exit "$result"
}
trap cleanup EXIT
git diff --binary HEAD > "$ASSISTANT_REPORT_DIR/source.patch"
git status --short > "$ASSISTANT_REPORT_DIR/source-status.txt"
compose config --quiet
compose build assistant
docker run --rm --network none -v "$PWD:/repo:ro" -v "$SD_DIR:/fixtures" "$EMU_IMAGE" \
  python3 -B -m tests.fixtures.assistant_fixture /fixtures
compose up -d --no-build emu typesense
docker image inspect --format '{{.Id}} {{json .RepoDigests}}' "$EMU_IMAGE" \
  disc-assistant-acceptance:local typesense/typesense:30.2 > "$ASSISTANT_REPORT_DIR/images.txt"
compose exec -T emu bash /repo/emulator/scripts/00_extract_rootfs.sh /ota
compose exec -T emu bash /repo/emulator/scripts/10_setup_env.sh
compose exec -T emu python3 -B -m tests.integration.awake_check --configure
compose exec -T emu bash /repo/emulator/scripts/20_boot.sh
compose exec -T emu python3 -B -m tests.integration.awake_check
compose exec -T emu python3 -B -m tests.integration.assistant_prepare
# Dismiss the scanner UI using the same lifecycle as existing integration tests.
compose exec -T emu bash /repo/emulator/scripts/20_boot.sh
compose exec -T emu python3 -B -m tests.integration.assistant_prepare --show-player
compose run --rm --no-deps assistant python -m tests.integration.assistant_check "$@"
