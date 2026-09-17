#!/usr/bin/env bash
# Only in the disposable integration guest, AFTER playback checks.
set -euo pipefail
source /repo/emulator/scripts/lib.sh
verify_firmware
# Force lazy symbols to resolve without invoking reboot. Keep verbose bindings local.
guest_run 10 /bin/busybox env LD_DEBUG=bindings LD_BIND_NOW=1 /bin/busybox true \
  > /dev/null 2> "$WORK/busybox-bindings.log"
python3 - "$WORK/busybox-bindings.log" <<'PY'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
assert any('/bin/busybox' in line and '/lib/fbshim.so' in line and
           'reboot' in line and 'binding file' in line for line in lines), 'reboot shim binding absent'
print('BusyBox reboot dynamically binds to fbshim; no kernel reboot needed for this check.')
PY
