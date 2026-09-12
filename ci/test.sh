#!/usr/bin/env bash
# Firmware-free checks, run inside the same image as the emulator.
set -euo pipefail
cd /repo
for script in run.sh scripts/*.sh shim/*.sh ci/*.sh; do bash -n "$script"; done
python3 -B ci/unit.py
node --test tools/test_keys.js tools/test_audio_browser.js tools/test_frames.js tools/test_controls.js
bash shim/build_shims.sh
