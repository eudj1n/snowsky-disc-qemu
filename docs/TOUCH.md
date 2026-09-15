# Touch injection

How to drive the emulated GUI by feeding synthetic touch events, derived from the
decompiled LVGL input read-callback in `mq_ui` (`FUN_0055db8c` in V2.40,
see `ghidra/`). Touch injection is also validated on V2.57; raw function addresses
in this investigation are version-specific.

## Mechanism

`mq_ui` opens `/dev/input/event1` (the `cst816t` device — its driver name comes from
`/sys/class/input/event1/device/name`) with `O_RDWR|O_NONBLOCK` and `read()`s 16-byte
`input_event` structs. The stub is a **plain file**; it keeps `read()`ing past EOF and
picks up whatever we **append**. (Verified in an strace: after appending, the touch thread
returns `read(fd,,16)=16` for each event.)

`input_event` on MIPS o32 LE is 16 bytes:

```
struct.pack('<iiHHi', tv_sec, tv_usec, type, code, value)
#            |  |  |    |      |
#            sec usec type   code  value
```

## Event grammar the callback understands

Decompiled `FUN_0055db8c` accepts either the multitouch type-B protocol or the simple
single-touch one, and also plain absolute coords:

| purpose | event |
|---------|-------|
| set X | `EV_ABS ABS_MT_POSITION_X(0x35)=x`  or  `EV_ABS ABS_X(0x00)=x` |
| set Y | `EV_ABS ABS_MT_POSITION_Y(0x36)=y`  or  `EV_ABS ABS_Y(0x01)=y` |
| **press** | `EV_ABS ABS_MT_TRACKING_ID(0x39)=0`  or  `EV_KEY BTN_TOUCH(0x14a)=1` |
| **release** | `EV_ABS ABS_MT_TRACKING_ID(0x39)=-1`  or  `EV_KEY BTN_TOUCH(0x14a)=0` |
| frame end | `EV_SYN SYN_REPORT(0)=0` (ignored, harmless) |

Coordinate scaling in the callback is `lvgl_x = disp_w * rawX / 360`; at 360×360 it is the
identity, so **the value you inject is the LVGL coordinate**. `tools/inject.py` emits a
robust press (MT position + tracking-id 0 **and** ABS_X/Y **and** BTN_TOUCH 1) and a matching
release.

## Gotcha 1 — separate press and release in TIME

The callback **drains all queued events in one call**, then reports the final state to LVGL.
If you append press+release together, LVGL only ever samples the net result (released) and
sees **no tap**. You must:

```
inject press x y ; sleep ~1s (let LVGL poll the pressed state) ; inject release
```

`scripts/30_tap.sh` does this.

## Gotcha 2 — coordinates are 180°-ROTATED vs. what you see

The panel and LVGL display are rotated 180°; the touch path itself applies no rotation.
So the tap point is the **flip** of the on-screen position:

```
raw_x = 359 - displayed_x
raw_y = 359 - displayed_y
```

Example that reached the main screen: the 确定 (Confirm) button sits at the bottom-center,
displayed ≈ (180, 315). Tapping it means injecting raw **(180, 44)**. Injecting at (180, 315)
instead lands on the scrollable list and just scrolls it.

`scripts/30_tap.sh <x> <y>` takes the **displayed** coordinate and flips it for you
(via `rot()` in `lib.sh`), so you pass what you see in the PNG.

## Gotcha 3 — press DURATION: click vs. long-press

The firmware distinguishes a short click from a long-press by how long the press is held.
`30_tap.sh` holds the press ~1 s (Gotcha 1), which for **buttons** (e.g. the wizard's Confirm)
is just a click on release — fine. But on a **list row** (a file/folder in the File Browser)
~1 s crosses the long-press threshold and opens the item's **context menu** (select ◉ /
delete 🗑 / add-to-playlist) instead of opening it. To *open* a folder/track, hold the press
only ~0.3 s:

```
inject press x y ; sleep 0.3 ; inject release      # short click: opens the item
inject press x y ; sleep 1   ; inject release      # long press: opens the context menu
```

So use `30_tap.sh` for buttons; for navigating into folders, inject a short (~0.3 s) tap.

## Recipe

```sh
# guests already booted (scripts/20_boot.sh) and sitting on the language screen:
scripts/30_tap.sh 180 315     # tap Confirm (displayed coords) -> advances to main menu
scripts/capture.sh main       # re-render the framebuffer
```

Swipes (carousel) would need intermediate position events spread over time so LVGL samples
the motion between press and release — not yet scripted.
