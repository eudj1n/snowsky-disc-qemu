#!/usr/bin/env bash
# Hardware state used by physical controls. No real host sysfs is mounted here.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
mkdir -p "$ROOTFS/sys/bus/platform/drivers/pwm-backlight/backlight/backlight/backlight" "$ROOTFS/emu"
printf '20\0\0' > "$ROOTFS/sys/bus/platform/drivers/pwm-backlight/backlight/backlight/backlight/brightness"
printf '11' > "$ROOTFS/emu/volume-buttons"
printf '\377' > "$ROOTFS/emu/fb-live"
printf '0' > "$ROOTFS/emu/power-request"
: > "$ROOTFS/dev/cst816t"
: > "$ROOTFS/dev/lcd_st77916"
# CS43131 attenuation registers, initialized muted until firmware configures the DAC.
printf '\377' > "$ROOTFS/emu/dac-left"
printf '\377' > "$ROOTFS/emu/dac-right"

# USB is a viewer charging stub only; keep the cable state across guest restarts.
B="$ROOTFS/sys/class/power_supply/cw221X-bat"
if [ -d "$B" ]; then
  if [ "$(cat "$ROOTFS/emu/usb-connected" 2>/dev/null || true)" = 1 ]; then
    printf 'Charging\n' > "$B/status"
  else
    printf 'Discharging\n' > "$B/status"
  fi
fi
