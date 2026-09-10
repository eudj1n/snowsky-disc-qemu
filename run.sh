#!/usr/bin/env bash
# Host-side orchestrator for the Snowsky Disc qemu emulator.
# Works on macOS or Linux with Docker installed.
#
#   ./run.sh up <path-to-ota_v240-dir>   build image, (re)create container, extract rootfs, set up env
#   ./run.sh shell                       open a shell inside the running container
#   ./run.sh boot [seconds]              boot to the main screen and capture PNGs into ./shots/
#   ./run.sh tap <x> <y>                 inject a tap at a screen coordinate, re-capture into ./shots/
#   ./run.sh stop                        stop the guest processes
#   ./run.sh down                        stop & remove the container (the /work volume is kept)
#   ./run.sh nuke                        also delete the /work volume (rootfs)
#
# The firmware is NOT included — see firmware/README.md to obtain it.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="diskos-qemu"
CTR="diskos-qemu"
VOL="diskos-work"                # named volume for /work (rootfs + state), survives container recreation

need_ctr(){ docker ps --format '{{.Names}}' | grep -qx "$CTR" || { echo "container '$CTR' not running — run: ./run.sh up <ota_dir>"; exit 1; }; }

cmd="${1:-}"; shift || true
case "$cmd" in
  up)
    OTA="${1:?usage: ./run.sh up <path-to-ota_v240-dir>}"
    OTA="$(cd "$OTA" && pwd)"
    ls "$OTA"/rootfs.squashfs.*.enc >/dev/null 2>&1 || { echo "no rootfs.squashfs.*.enc in $OTA (point at main_os/ota_v240)"; exit 1; }
    echo "==> building image"; docker build -t "$IMAGE" "$REPO_DIR/docker"
    docker volume create "$VOL" >/dev/null
    docker rm -f "$CTR" >/dev/null 2>&1 || true
    echo "==> starting container (privileged)"
    docker run -d --name "$CTR" --privileged \
      -v "$OTA":/ota:ro -v "$REPO_DIR":/repo -v "$VOL":/work \
      "$IMAGE" sleep infinity >/dev/null
    echo "==> extracting rootfs (first run only takes a minute)"
    docker exec "$CTR" bash -lc '[ -x /repo/scripts/00_extract_rootfs.sh ] && \
      { [ -e /work/rootfs/usr/bin/mq_ui ] || /repo/scripts/00_extract_rootfs.sh /ota; }'
    echo "==> setting up environment"
    docker exec "$CTR" bash -lc '/repo/scripts/10_setup_env.sh'
    echo "==> ready. Try: ./run.sh boot"
    ;;
  shell) need_ctr; docker exec -it "$CTR" bash ;;
  boot)
    need_ctr
    docker exec "$CTR" bash -lc "/repo/scripts/10_setup_env.sh >/dev/null && /repo/scripts/20_boot.sh ${1:-26}"
    mkdir -p "$REPO_DIR/shots"; docker cp "$CTR":/work/shots/. "$REPO_DIR/shots/" 2>/dev/null || true
    echo "==> PNGs copied to $REPO_DIR/shots/"
    ;;
  tap)
    need_ctr
    docker exec "$CTR" bash -lc "/repo/scripts/30_tap.sh ${1:?x} ${2:?y}"
    mkdir -p "$REPO_DIR/shots"; docker cp "$CTR":/work/shots/. "$REPO_DIR/shots/" 2>/dev/null || true
    echo "==> PNGs copied to $REPO_DIR/shots/"
    ;;
  stop) need_ctr; docker exec "$CTR" bash -lc '/repo/scripts/99_stop.sh' ;;
  down) docker rm -f "$CTR" >/dev/null 2>&1 || true; echo "container removed (volume '$VOL' kept)";;
  nuke) docker rm -f "$CTR" >/dev/null 2>&1 || true; docker volume rm "$VOL" >/dev/null 2>&1 || true; echo "container + volume removed";;
  *) sed -n '2,20p' "$0" ;;
esac
