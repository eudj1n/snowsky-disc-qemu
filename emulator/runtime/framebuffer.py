"""Guest framebuffer sampling and lossless frame publication; no HTTP dependencies."""
from pathlib import Path
import struct
import threading
import zlib

W = H = 360
BUF = W * H * 4
BLACK_RGB = bytes(W * H * 3)

def png(rgb):
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    rows = bytearray((W * 3 + 1) * H)
    stride = W * 3
    for y in range(H):                       # prepend the per-row filter byte (0)
        o = y * (stride + 1)
        rows[o] = 0
        rows[o + 1:o + 1 + stride] = rgb[y * stride:(y + 1) * stride]
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(bytes(rows), 1)) + chunk(b'IEND', b''))

def to_rgb(buf):
    """BGRX sub-buffer -> RGB bytes, 180deg-rotated (reverse pixel order)."""
    mv = memoryview(buf)
    r = bytes(mv[2::4])[::-1]                 # reverse pixel order == 180deg rotate
    g = bytes(mv[1::4])[::-1]
    b = bytes(mv[0::4])[::-1]
    out = bytearray(W * H * 3)
    out[0::3] = r
    out[1::3] = g
    out[2::3] = b
    return bytes(out)

def _nonblack(buf):
    mv = memoryview(buf)
    # cheap: count non-zero in the blue plane; good enough to seed the live pick
    return sum(1 for x in mv[0::4] if x)

class FrameState:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_changed = threading.Condition(self.lock)
        self.frame_revision = 0
        self.rgb = BLACK_RGB
        self.png = png(self.rgb)           # start black
        self.prev0 = self.prev1 = None
        self.live = 0
        self.prev_visible = None
        self.was_screen_on = False

    def update_frame(self, raw, active, screen_on):
        """Single grabber publishes complete, lossless frames only when RGB changes."""
        if len(raw) < BUF * 2:
            return False
        b0, b1 = raw[:BUF], raw[BUF:BUF * 2]
        if active in (0, 1):
            self.live = active
        elif self.prev0 is None:
            self.live = 0 if _nonblack(b0) >= _nonblack(b1) else 1
        elif b0 != self.prev0:
            self.live = 0
        elif b1 != self.prev1:
            self.live = 1
        self.prev0, self.prev1 = b0, b1
        visible = b0 if self.live == 0 else b1
        if screen_on and self.was_screen_on and visible == self.prev_visible:
            return False
        self.prev_visible, self.was_screen_on = visible, screen_on
        rgb = to_rgb(visible) if screen_on else BLACK_RGB
        if rgb == self.rgb:
            return False  # Also ignore changes confined to the unused X byte.
        encoded = png(rgb)  # Encode once for all clients, outside their shared lock.
        with self.frame_changed:
            self.rgb, self.png = rgb, encoded
            self.frame_revision += 1
            self.frame_changed.notify_all()
        return True

    def wait_frame(self, revision, timeout):
        with self.frame_changed:
            self.frame_changed.wait_for(lambda: revision != self.frame_revision, timeout)
            return self.frame_revision, self.png


class Framebuffer:
    def __init__(self, rootfs):
        self.root = Path(rootfs)
        self.path = self.root / 'dev/fb0'

    def active_buffer(self):
        try:
            with (self.root / 'emu/fb-live').open('rb') as marker:
                value = marker.read(1)
            return value[0] if value in (b'\x00', b'\x01') else None
        except OSError:
            return None

    def read(self):
        # A consistency check, not a firmware frame-completion fence. Same-buffer
        # writes still require sampling even when the marker is unchanged.
        for _ in range(2):
            before = self.active_buffer()
            with self.path.open('rb') as handle:
                raw = handle.read(BUF * 2)
            after = self.active_buffer()
            if before == after:
                return raw, after
        return None
