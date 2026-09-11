#!/usr/bin/env bash
# Temporary generated audio for testing Auto update. Never overwrite user media.
# Run INSIDE the container, then run setup/boot to rebuild the emulated SD.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
fixture=/sdcard/__emulator_auto_update_probe.wav
record="$WORK/media-fixture.sha256"
case "${1:-}" in
  add)
    [ ! -e "$fixture" ] && [ ! -L "$fixture" ] || { err "fixture already exists: $fixture"; exit 1; }
    sox -n -r 44100 -c 2 -b 16 "$fixture" synth 10 sine 660 gain -30
    sha256sum "$fixture" > "$record"
    log "Generated $fixture; rebuild SD with setup/boot"
    ;;
  remove)
    [ -f "$record" ] || { err 'no fixture ownership record'; exit 1; }
    [ "$(sha256sum "$fixture")" = "$(cat "$record")" ] || {
      err 'fixture changed: refusing removal'; exit 1;
    }
    rm -- "$fixture" "$record"
    log 'Removed the generated test WAV; rebuild SD with setup/boot'
    ;;
  *) err 'usage: media_fixture.sh add|remove'; exit 2 ;;
esac
