#!/usr/bin/env bash
# Firmware-free checks, run inside the same image as the emulator.
set -euo pipefail
cd /repo
bash -n run.sh
while IFS= read -r -d '' script; do bash -n "$script"; done < <(
  find emulator viewer controller firmware research tests ci -type f -name '*.sh' -print0
)
python3 -B -m ci.unit
mapfile -d '' js_tests < <(find emulator viewer controller firmware research tests -type f -name 'test_*.js' -print0 | sort -z)
[ "${#js_tests[@]}" -gt 0 ]
node --test "${js_tests[@]}"
bash emulator/shims/build_shims.sh
