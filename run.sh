#!/usr/bin/env bash
# Host-side orchestrator for the Snowsky Disc qemu emulator.
# Works on macOS or Linux with Docker installed.
#
#   ./run.sh up <path-to-ota_v240-dir>   build image, create/reuse container, extract rootfs, set up env
#   ./run.sh start                       start the existing (stopped) container without re-extracting
#   ./run.sh shell                       open a shell inside the running container
#   ./run.sh boot [seconds]              boot to the main screen and capture PNGs into ./shots/
#   ./run.sh tap <x> <y>                 inject a tap at a screen coordinate, re-capture into ./shots/
#   ./run.sh view [port]                 live viewer + touch/swipe bridge in the browser (default :8080)
#   ./run.sh capture [prefix]            re-capture the current framebuffer into ./shots/
#   ./run.sh audio                      export current audio capture into ./shots/audio.wav
#   ./run.sh diag                        touch diagnostic (leaves guests running)
#   ./run.sh wscheck [--control]          compare WebSocket with TCP (control leaves playback paused)
#   ./run.sh stop                        stop the guest processes
#   ./run.sh down                        stop & remove the container (the /work volume is kept)
#   ./run.sh nuke                        also delete the /work volume (rootfs)
#
# The firmware is NOT included — see firmware/README.md to obtain it.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTR="diskos-qemu"                # container_name set in docker-compose.yml

running(){ docker ps --format '{{.Names}}' | grep -qx "$CTR"; }
exists(){  docker ps -a --format '{{.Names}}' | grep -qx "$CTR"; }
need_ctr(){
  running && return 0
  if exists; then echo "==> starting stopped container '$CTR'"; docker start "$CTR" >/dev/null && return 0; fi
  echo "container '$CTR' not running — run: ./run.sh up <ota_dir>"; exit 1
}

cmd="${1:-}"; shift || true
case "$cmd" in
  up)
    # OTA dir from arg, else $OTA_DIR, else .env
    OTA="${1:-${OTA_DIR:-}}"
    [ -n "$OTA" ] || OTA="$(sed -n 's/^OTA_DIR=//p' "$REPO_DIR/.env" 2>/dev/null | head -1)"
    [ -n "$OTA" ] || { echo "usage: ./run.sh up <path-to-ota_v240-dir>   (or set OTA_DIR in .env — see .env.example)"; exit 1; }
    OTA="$(cd "$OTA" && pwd)"
    ls "$OTA"/rootfs.squashfs.*.enc >/dev/null 2>&1 || { echo "no rootfs.squashfs.*.enc in $OTA (point at main_os/ota_v240)"; exit 1; }
    grep -qx "OTA_DIR=$OTA" "$REPO_DIR/.env" 2>/dev/null || printf 'OTA_DIR=%s\n' "$OTA" > "$REPO_DIR/.env"
    echo "==> docker compose up (build)"
    ( cd "$REPO_DIR" && OTA_DIR="$OTA" docker compose up -d --build )
    echo "==> extracting rootfs (first run only takes a minute)"
    docker exec "$CTR" bash -lc '[ -e /work/rootfs/usr/bin/mq_ui ] || /repo/scripts/00_extract_rootfs.sh /ota'
    echo "==> setting up environment"
    docker exec "$CTR" bash -lc '/repo/scripts/10_setup_env.sh'
    echo "==> ready. Try: ./run.sh boot"
    ;;
  start) need_ctr; ( cd "$REPO_DIR" && docker compose up -d --no-deps wsbridge ); echo "container '$CTR' running";;
  shell) need_ctr; docker exec -it "$CTR" bash ;;
  boot)
    need_ctr
    ( cd "$REPO_DIR" && docker compose up -d --no-deps wsbridge )
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
  diag)
    need_ctr
    docker exec "$CTR" bash -lc '/repo/scripts/10_setup_env.sh >/dev/null 2>&1; /repo/scripts/diag_tap.sh'
    mkdir -p "$REPO_DIR/shots"; docker cp "$CTR":/work/shots/. "$REPO_DIR/shots/" 2>/dev/null || true
    echo "==> PNGs copied to $REPO_DIR/shots/ (see d0-*.png before, d1-*.png after)"
    ;;
  capture)
    need_ctr
    docker exec "$CTR" bash -lc "/repo/scripts/capture.sh ${1:-cap}"
    mkdir -p "$REPO_DIR/shots"; docker cp "$CTR":/work/shots/. "$REPO_DIR/shots/" 2>/dev/null || true
    echo "==> PNGs copied to $REPO_DIR/shots/"
    ;;
  audio)
    need_ctr
    docker exec "$CTR" python3 /repo/tools/audio.py /work/audio.wav
    mkdir -p "$REPO_DIR/shots"
    docker cp "$CTR":/work/audio.wav "$REPO_DIR/shots/audio.wav"
    echo "==> WAV copied to $REPO_DIR/shots/audio.wav"
    ;;
  view)
    need_ctr
    PORT="${1:-8080}"
    docker exec -d "$CTR" bash -lc "/repo/scripts/40_stream.sh $PORT >/work/stream.log 2>&1"
    sleep 1
    echo "==> live viewer: http://localhost:$PORT   (click = tap · drag = swipe · buttons for gestures/keys)"
    echo "    (needs ./run.sh boot for a live screen; log: docker exec $CTR cat /work/stream.log)"
    ;;
  stop) need_ctr; docker exec "$CTR" bash -lc '/repo/scripts/99_stop.sh' ;;
  wscheck)
    need_ctr
    ( cd "$REPO_DIR" && docker compose exec -T wsbridge python3 -B /repo/tools/verify_websocket.py --tcp-host emu "$@" )
    ;;
  down) ( cd "$REPO_DIR" && OTA_DIR="${OTA_DIR:-unused}" docker compose down );          echo "container stopped & removed (work volume kept)";;
  nuke) ( cd "$REPO_DIR" && OTA_DIR="${OTA_DIR:-unused}" docker compose down -v );       echo "container + work volume removed";;
  *) sed -n '2,20p' "$0" ;;
esac
