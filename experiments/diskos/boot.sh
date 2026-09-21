#!/usr/bin/env bash
# Experimental diskOS UI over the verified stock backend. Run only in its own stack.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/emulator/scripts/lib.sh"
UI="${DISKOS_UI:-$REPO/work/diskos-preview/mq_ui}"
[ "${DISKOS_PREVIEW:-}" = 1 ] || { err 'Use the isolated diskOS preview stack'; exit 1; }
[ "$FW_VERSION" = 2.40 ] || { err 'Historical diskOS preview was validated only on V2.40'; exit 1; }
[ -s "$UI" ] || { err "Build the emulation UI first: $UI"; exit 1; }
# Preserve every stock fingerprint and initialise the backend using its stock UI.
bash "$REPO/emulator/scripts/20_boot.sh"
ROOTFS="$ROOTFS" python3 - <<'PY'
import os, signal
from pathlib import Path
from emulator.runtime.keys import Device
d = Device(os.environ['ROOTFS'])
for pid in d.processes():
    p = Path(f'/proc/{pid}')
    try:
        if b'/usr/bin/mq_ui' in (p/'cmdline').read_bytes().split(b'\0'):
            if (p/'root').resolve() == d.root:
                os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
PY
install -m 755 "$UI" "$ROOTFS/usr/data/mq_ui"
rm -f "$ROOTFS/usr/data/diskos_boot.log"
# diskOS writes the same backlight through the conventional /sys/class alias.
mkdir -p "$ROOTFS/sys/class/backlight"
ln -sfn ../../bus/platform/drivers/pwm-backlight/backlight/backlight/backlight \
  "$ROOTFS/sys/class/backlight/backlight"
apply_ulimits
# binfmt replaces argv[0] with the executable path. diskOS normalises it by
# re-execing itself, which loops under binfmt. Set it for this invocation only;
# QEMU_ARGV0 in the environment would also break its BusyBox children.
install -m 755 "$QEMU" "$ROOTFS/emu/qemu-mipsel-static"
DISKOS_EMU_WARM_PLAYER=1 guest_run "${GUEST_TTL:-1800}" /emu/qemu-mipsel-static -0 mq_ui /usr/data/mq_ui \
  >"$WORK/diskos-launch.log" 2>&1 &
ROOTFS="$ROOTFS" python3 - <<'PY'
import os, time
from pathlib import Path
root = Path(os.environ['ROOTFS'])
log = root/'usr/data/diskos_boot.log'
for _ in range(225):
    if log.exists() and 'diskos reached main loop' in log.read_text(errors='replace'):
        print('diskOS first frame painted; inspect usr/data/diskos_boot.log for details')
        break
    time.sleep(.2)
else:
    raise SystemExit('diskOS startup failed; inspect usr/data/diskos_boot.log')
PY
