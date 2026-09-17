"""Display-coordinate touch injection into one emulated guest."""
from pathlib import Path
import struct
import threading
import time

W = H = 360
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, BTN_TOUCH = 0, 0x14a
ABS_X, ABS_Y = 0, 1
ABS_MT_TRACKING_ID, ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x39, 0x35, 0x36

def _ev(t, c, v):
    return struct.pack('<iiHHi', 0, 0, t, c, v)

def _flip(x, y):
    x = max(0, min(W - 1, int(x))); y = max(0, min(H - 1, int(y)))
    return (W - 1) - x, (H - 1) - y            # panel is 180deg-rotated


class Touch:
    def __init__(self, rootfs):
        self.path = Path(rootfs) / 'dev/input/event1'
        self.lock = threading.Lock()

    def _append(self, data):
        with self.lock:
            with self.path.open('ab') as handle:
                handle.write(data)

    def press(self, dx, dy):
        rx, ry = _flip(dx, dy)
        self._append(_ev(EV_ABS, ABS_MT_TRACKING_ID, 0) + _ev(EV_ABS, ABS_MT_POSITION_X, rx)
                + _ev(EV_ABS, ABS_MT_POSITION_Y, ry) + _ev(EV_ABS, ABS_X, rx)
                + _ev(EV_ABS, ABS_Y, ry) + _ev(EV_KEY, BTN_TOUCH, 1) + _ev(EV_SYN, SYN_REPORT, 0))

    def move(self, dx, dy):
        rx, ry = _flip(dx, dy)
        self._append(_ev(EV_ABS, ABS_MT_POSITION_X, rx) + _ev(EV_ABS, ABS_MT_POSITION_Y, ry)
                + _ev(EV_ABS, ABS_X, rx) + _ev(EV_ABS, ABS_Y, ry) + _ev(EV_SYN, SYN_REPORT, 0))

    def release(self):
        self._append(_ev(EV_ABS, ABS_MT_TRACKING_ID, -1) + _ev(EV_KEY, BTN_TOUCH, 0)
                + _ev(EV_SYN, SYN_REPORT, 0))

    def tap(self, dx, dy):
        # A plain click: the read-cb drains all queued events per poll and reports the
        # NET state, so press+release in one batch = no tap. Hold ~0.3s so LVGL samples
        # the pressed state first (see docs/TOUCH.md).
        self.press(dx, dy)
        time.sleep(0.30)
        self.release()

    def swipe(self, x0, y0, x1, y1, steps=12, hold=0.028):
        """Server-side smooth swipe: press, interpolated moves over wall-clock time,
        release. Reliable for LVGL gestures (pull-down shade, back = left->right) where
        a hand-drawn drag is fiddly. Coords are display-space; each is flipped."""
        self.press(x0, y0)
        time.sleep(hold)
        for i in range(1, steps + 1):
            self.move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
            time.sleep(hold)
        self.release()
