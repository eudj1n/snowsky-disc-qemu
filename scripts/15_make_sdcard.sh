#!/usr/bin/env bash
# OPTIONAL: put a tiny test library where the file browser looks (/tmp/sdcard inside
# the rootfs), so the File Browser app shows something. Not required to reach the main
# screen — the device boots to main with no SD (USB-DAC mode). Uses `sox` to synthesize
# a short tone as one track under an artist folder.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
[ -d "$ROOTFS" ] || { err "no rootfs — run 00_extract_rootfs.sh first"; exit 1; }

SD="$ROOTFS/tmp/sdcard"
ART="$SD/Test Artist"
mkdir -p "$ART"
log "Generating a test track under $ART"
# 3s 440Hz tone -> 16-bit/44.1k WAV (kept small; swap for a real FLAC/MP3 if you want tags)
sox -n -r 44100 -b 16 -c 2 "$ART/Test Track.wav" synth 3 sine 440 vol 0.3
log "SD content:"; find "$SD" -maxdepth 2 -print
log "Open it in the emulator via the File Browser app on the main menu."
