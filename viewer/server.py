#!/usr/bin/env python3
"""Live viewer + touch bridge for the emulated Snowsky Disc.

Runs INSIDE the container. Serves an HTTP page that shows the guest's framebuffer
(`$ROOTFS/dev/fb0`) as a live MJPEG-style stream, and turns pointer events on that
page into synthetic touches appended to `$ROOTFS/dev/input/event1` — i.e. you drive
the real stock UI from a browser on the host, no hardware.

  GET /            HTML page (stream + pointer capture)
  GET /stream      multipart/x-mixed-replace PNG stream (the live screen)
  GET /frame       single current PNG
  GET /tap?x&y     short tap at display coords (press, hold ~0.3s, release)
  GET /down?x&y    press (start of a drag/swipe)
  GET /move?x&y    move (during a drag; only between down and up)
  GET /up          release
  POST /button    physical button {name, gesture}; GET /device.json = power/screen state
  GET /events     SSE device snapshots on connect/change, with idle heartbeats
  GET /key?k=…    single press (volume_up|volume_down|play_pause|power), or safe ?code=<int>

Framebuffer facts (see docs/EMULATION.md): fb0 is 360x1080x4 (three 360x360 BGRX
sub-buffers); mq_ui alternates drawing to buf0/buf1 and does NOT pan, so the live
screen is the last-written sub-buffer, reported by fbshim in emu/fb-live (diff fallback
for older shims).
The panel is 180deg-rotated, so display = reverse of the raw pixels, and a tapped
display coord maps to raw touch (359-x, 359-y) — same flip as emulator/scripts/30_tap.sh.
"""
import os, sys, time, struct, threading, json
from pathlib import Path
from emulator.runtime.framebuffer import Framebuffer, FrameState
from emulator.runtime.touch import Touch
from emulator.runtime.audio import capture_info, read_chunk
from emulator.runtime.keys import Buttons, Device, CODES
from emulator.runtime.peripherals import Peripherals
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOTFS = os.environ.get("ROOTFS", "/work/rootfs")
PORT = int(os.environ.get("STREAM_PORT", "8080"))
FPS = float(os.environ.get("STREAM_FPS", "12"))
EVENT_HEARTBEAT = 15
FRAME_HEARTBEAT = 15               # infrequent full refresh / dead-client detection
FB = os.path.join(ROOTFS, "dev/fb0")
EV = os.path.join(ROOTFS, "dev/input/event1")   # cst816t touch
framebuffer = Framebuffer(ROOTFS)
touch = Touch(ROOTFS)
device = Device(ROOTFS, boot_script=os.environ.get('DEVICE_BOOT_SCRIPT'))
buttons = Buttons(ROOTFS, device)
viewer_controls = Peripherals(device)

# Optional device "skin": a photo of the player; the live round screen is composited
# over its screen area so the viewer looks like the real device. Drop a PNG at $SKIN
# (or /work/skin.png) — ideally with a transparent hole over the screen for pixel-perfect
# alignment. Circle geometry is a fraction of the image (tune via env or ?cx&cy&d).
SKIN = os.environ.get("SKIN", os.path.join(os.path.dirname(ROOTFS.rstrip('/')) or '/', "skin.png"))
SKIN_CX = float(os.environ.get("SKIN_CX", "0.500"))     # screen centre X / image width
SKIN_CY = float(os.environ.get("SKIN_CY", "0.500"))     # screen centre Y / image height
SKIN_D = float(os.environ.get("SKIN_D", "0.679"))       # screen diameter / image width

# ---- shared state: a grabber thread keeps the latest PNG ---------------------

class State(FrameState):
    def __init__(self):
        super().__init__()
        self.device = {'running': False, 'screen_on': False, 'transition': None, 'error': None}
        self.device_changed = threading.Condition()
        self.device_revision = 0

    def publish_device(self, snapshot):
        with self.device_changed:
            if snapshot != self.device:
                self.device = dict(snapshot)
                self.device_revision += 1
                self.device_changed.notify_all()

    def wait_device(self, revision, timeout):
        with self.device_changed:
            self.device_changed.wait_for(lambda: revision != self.device_revision, timeout)
            return self.device_revision, dict(self.device)


state = State()

# ---- optional device skin ----------------------------------------------------

def _load_skin():
    try:
        data = open(SKIN, 'rb').read()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            return None
        w, h = struct.unpack('>II', data[16:24])
        return data, w, h
    except OSError:
        return None

SKIN_DATA = _load_skin()

def _skin_fields(cx=None, cy=None, d=None):
    """Placeholder values for the page: mode + overlay geometry. cx/cy/d override the
    defaults (fractions of the image) so the screen can be aligned live (?cx&cy&d)."""
    if not SKIN_DATA:
        return dict(MODE='plain', STAGE='360', L='0', T='0', D='100',
                    CX='0', CY='0', DD='0', AR='1')
    _, w, h = SKIN_DATA
    cx = SKIN_CX if cx is None else cx
    cy = SKIN_CY if cy is None else cy
    d = SKIN_D if d is None else d
    ar = w / h                              # so JS can recompute top% from a height-diameter
    dh = d * ar
    # Size the stage so the live circle renders at native 360px (1:1) — no downscale, so the UI
    # text stays crisp (identical to the PNG). The photo is scaled to suit; a higher-res skin
    # keeps the casing sharp too.
    stage = max(360, min(1000, round(360.0 / d)))
    return dict(MODE='skin', STAGE='%d' % stage,
                L='%.2f' % ((cx - d / 2) * 100),
                T='%.2f' % ((cy - dh / 2) * 100),
                D='%.2f' % (d * 100),
                CX='%.4f' % cx, CY='%.4f' % cy, DD='%.4f' % d, AR='%.4f' % ar)


def grab_loop():
    period = 1.0 / FPS
    while True:
        t0 = time.monotonic()
        try:
            sample = framebuffer.read()
        except OSError:
            time.sleep(period); continue
        if sample:
            state.update_frame(*sample, state.device['screen_on'])
        dt = time.monotonic() - t0
        if dt < period:
            time.sleep(period - dt)

# Compatibility diagnostic API. Unknown/unsafe raw codes are rejected by Buttons.
KEYS = {name: gestures['single'] for name, gestures in CODES.items()}

def key(code):
    buttons.pulse(code)


# Named gestures, in DISPLAY coords (what you see). 360x360 round panel.
GESTURES = {
    'down':  (180, 18, 180, 300),    # pull the shade / status panel down from the top
    'up':    (180, 342, 180, 60),    # push it back up
    'back':  (18, 180, 320, 180),    # swipe left->right = go back
    'left':  (342, 180, 40, 180),    # swipe right->left
}

# ---- HTTP --------------------------------------------------------------------

PAGE = (Path(__file__).parent / 'static/index.html').read_text(encoding='utf-8')


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _q(self, qs, k):
        return int(float(qs.get(k, ['0'])[0]))

    def do_POST(self):
        if self.path not in ('/button', '/peripheral'):
            self._audio_response(404, 'text/plain', b'Not found'); return
        # JSON-only and same-origin: another website must not power-cycle this guest.
        origin = self.headers.get('Origin')
        if (origin and urlparse(origin).netloc != self.headers.get('Host')) or \
                self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self._audio_response(403, 'text/plain', b'Same-origin JSON required'); return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 1024:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            if self.path == '/peripheral':
                if data['name'] == 'sd':
                    viewer_controls.set_sd(data['inserted'])
                elif data['name'] == 'usb':
                    viewer_controls.set_usb(data['connected'])
                else:
                    raise ValueError('Unknown peripheral')
            else:
                if viewer_controls.operation and data['gesture'] not in ('end', 'cancel'):
                    raise ValueError('Wait for the SD operation')
                buttons.gesture(data['name'], data['gesture'])
            if self.path == '/peripheral':
                snapshot = {**device.status(), **viewer_controls.snapshot()}
                state.publish_device(snapshot)
                self._audio_response(200, 'application/json', json.dumps(snapshot).encode())
            else:
                self._audio_response(200, 'application/json', b'{"ok":true}')
        except (ValueError, KeyError, TypeError) as exc:
            self._audio_response(400, 'text/plain', str(exc).encode())
        except OSError as exc:
            self._audio_response(503, 'text/plain', str(exc).encode())

    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        if p in ('/audio.js', '/keys.js', '/frames.js', '/controls.js'):
            data = open(os.path.join(os.path.dirname(__file__), 'static', p[1:]), 'rb').read()
            self._audio_response(200, 'text/javascript', data)
        elif p == '/device.json':
            self._audio_response(200, 'application/json', json.dumps(state.device).encode())
        elif p == '/events':
            self._device_events()
        elif p == '/audio.json':
            try:
                info = capture_info(ROOTFS)
            except (OSError, ValueError, struct.error):
                info = {'generation': None, 'bytes': 0}
            info['output_gain'] = device.gains()
            info['running'] = state.device['running']
            self._audio_response(200, 'application/json', json.dumps(info).encode())
        elif p == '/audio.pcm':
            try:
                data = read_chunk(ROOTFS, qs.get('generation', [''])[0],
                                  int(qs.get('offset', ['0'])[0]))
                self._audio_response(200, 'application/octet-stream', data)
            except (OSError, ValueError, struct.error):
                self._audio_response(409, 'text/plain', b'Capture changed or invalid offset')
        elif p == '/':
            def qf(k):
                v = qs.get(k)
                try:
                    return float(v[0]) if v else None
                except ValueError:
                    return None
            page = PAGE
            for k, v in _skin_fields(qf('cx'), qf('cy'), qf('d')).items():
                page = page.replace('__%s__' % k, v)
            body = page.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        elif p == '/skin':
            if not SKIN_DATA:
                self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
            png = SKIN_DATA[0]
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(png)))
            self.send_header('Cache-Control', 'max-age=3600')
            self.end_headers()
            self.wfile.write(png)
        elif p == '/frame':
            with state.lock:
                png = state.png
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(png)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(png)
        elif p == '/stream':
            self._frame_stream()
        elif p == '/key':
            k = qs.get('k', [''])[0]
            code = KEYS.get(k)
            if code is None and qs.get('code'):
                try:
                    code = int(qs['code'][0], 0)
                except ValueError:
                    code = None
            try:
                if not device.running() or device.transition or viewer_controls.operation:
                    raise ValueError('Player is not ready')
                key(code)
            except (ValueError, OSError) as exc:
                self._audio_response(400, 'text/plain', str(exc).encode()); return
            self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers()
        elif p in ('/tap', '/down', '/move', '/up', '/swipe'):
            if p != '/up' and (not state.device['screen_on'] or device.transition or viewer_controls.operation):
                self._audio_response(409, 'text/plain', b'Screen is off; press Power'); return
            if p == '/tap':
                touch.tap(self._q(qs, 'x'), self._q(qs, 'y'))
            elif p == '/down':
                touch.press(self._q(qs, 'x'), self._q(qs, 'y'))
            elif p == '/move':
                touch.move(self._q(qs, 'x'), self._q(qs, 'y'))
            elif p == '/swipe':
                d = qs.get('dir', [''])[0]
                if d in GESTURES:
                    touch.swipe(*GESTURES[d])
                else:
                    touch.swipe(self._q(qs, 'x0'), self._q(qs, 'y0'),
                          self._q(qs, 'x1'), self._q(qs, 'y1'))
            else:
                touch.release()
            self.send_response(204)
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()

    def _frame_stream(self):
        self.close_connection = True
        self.connection.settimeout(5)  # Bound blocked writes to slow/disconnected clients.
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.send_header('Cache-Control', 'no-store, no-transform')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Connection', 'close')
            self.end_headers()
            revision = None
            while True:
                revision, png = state.wait_frame(revision, FRAME_HEARTBEAT)
                self.wfile.write(b'--FRAME\r\nContent-Type: image/png\r\n'
                                 b'Content-Length: %d\r\n\r\n' % len(png))
                self.wfile.write(png)
                # frames.js decodes each Content-Length-delimited PNG immediately;
                # it does not wait for the next MIME boundary to display the frame.
                self.wfile.write(b'\r\n')
                self.wfile.flush()
                # Slow readers get the latest complete snapshot next, not a queue.
        except OSError:
            return

    def _device_events(self):
        # This response lasts until disconnect. Never hold the condition during I/O:
        # a slow client must not block the supervisor or other viewers. Retain only
        # the latest snapshot, rather than an unbounded per-client event backlog.
        self.close_connection = True
        self.connection.settimeout(10)
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-transform')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b'retry: 1000\n\n')
            revision = None  # Always send current state, including on reconnection.
            while True:
                current, snapshot = state.wait_device(revision, EVENT_HEARTBEAT)
                if current != revision:
                    payload = json.dumps(snapshot, ensure_ascii=False).encode('utf-8')
                    self.wfile.write(b'event: device\ndata: ' + payload + b'\n\n')
                    revision = current
                else:
                    self.wfile.write(b': heartbeat\n\n')
                self.wfile.flush()
        except OSError:
            return  # Includes disconnected readers and bounded slow-client writes.

    def _audio_response(self, status, content_type, data):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

def main():
    if not os.path.exists(FB):
        print("no framebuffer %s — boot first (emulator/scripts/20_boot.sh)" % FB, file=sys.stderr)
    try:
        buttons.reset()
    except OSError:
        pass  # First setup has not yet created the hardware state files.
    def control_loop():
        while True:
            try:
                buttons.expire()
                device.service_requests()
                state.publish_device({**device.status(), **viewer_controls.snapshot()})
            except OSError as exc:
                state.publish_device({**state.device, 'error': str(exc)})
            time.sleep(.2)
    threading.Thread(target=control_loop, daemon=True).start()
    threading.Thread(target=grab_loop, daemon=True).start()
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print("stream: http://0.0.0.0:%d  (fb=%s ev=%s %gfps)" % (PORT, FB, EV, FPS))
    srv.serve_forever()

if __name__ == '__main__':
    main()
