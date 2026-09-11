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
  GET /key?k=…     physical key (menu_up|menu_down|play|play_pause), or ?code=<int>

Framebuffer facts (see docs/EMULATION.md): fb0 is 360x1080x4 (three 360x360 BGRX
sub-buffers); mq_ui alternates drawing to buf0/buf1 and does NOT pan, so the live
screen is whichever sub-buffer changed most recently — we pick it by diffing reads.
The panel is 180deg-rotated, so display = reverse of the raw pixels, and a tapped
display coord maps to raw touch (359-x, 359-y) — same flip as scripts/30_tap.sh.
"""
import os, sys, time, zlib, struct, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

W = H = 360
BUF = W * H * 4                      # one sub-buffer, BGRX
NBUF = 3
ROOTFS = os.environ.get("ROOTFS", "/work/rootfs")
PORT = int(os.environ.get("STREAM_PORT", "8080"))
FPS = float(os.environ.get("STREAM_FPS", "12"))
FB = os.path.join(ROOTFS, "dev/fb0")
EV = os.path.join(ROOTFS, "dev/input/event1")   # cst816t touch
EV0 = os.path.join(ROOTFS, "dev/input/event0")  # x2000_key physical keys

# Optional device "skin": a photo of the player; the live round screen is composited
# over its screen area so the viewer looks like the real device. Drop a PNG at $SKIN
# (or /work/skin.png) — ideally with a transparent hole over the screen for pixel-perfect
# alignment. Circle geometry is a fraction of the image (tune via env or ?cx&cy&d).
SKIN = os.environ.get("SKIN", os.path.join(os.path.dirname(ROOTFS.rstrip('/')) or '/', "skin.png"))
SKIN_CX = float(os.environ.get("SKIN_CX", "0.5"))     # screen centre X / image width
SKIN_CY = float(os.environ.get("SKIN_CY", "0.5"))     # screen centre Y / image height
SKIN_D = float(os.environ.get("SKIN_D", "0.7"))       # screen diameter / image width

# ---- framebuffer -> PNG ------------------------------------------------------

def _png(rgb):
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

def _to_rgb(buf):
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

# ---- shared state: a grabber thread keeps the latest PNG ---------------------

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.png = _png(bytes(W * H * 3))     # start black
        self.prev0 = self.prev1 = None
        self.live = 0

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
        t0 = time.time()
        try:
            with open(FB, 'rb') as f:
                raw = f.read(BUF * NBUF)
        except OSError:
            time.sleep(period); continue
        if len(raw) >= BUF * 2:
            b0, b1 = raw[:BUF], raw[BUF:BUF * 2]
            if state.prev0 is None:            # first read: pick the fuller buffer
                state.live = 0 if _nonblack(b0) >= _nonblack(b1) else 1
            elif b0 != state.prev0:            # buf0 was just redrawn -> it's live
                state.live = 0
            elif b1 != state.prev1:
                state.live = 1
            # else: neither changed -> keep last live buffer
            state.prev0, state.prev1 = b0, b1
            png = _png(_to_rgb(b0 if state.live == 0 else b1))
            with state.lock:
                state.png = png
        dt = time.time() - t0
        if dt < period:
            time.sleep(period - dt)

# ---- touch injection ---------------------------------------------------------

_ev_lock = threading.Lock()
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, BTN_TOUCH = 0, 0x14a
ABS_X, ABS_Y = 0, 1
ABS_MT_TRACKING_ID, ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x39, 0x35, 0x36

def _ev(t, c, v):
    return struct.pack('<iiHHi', 0, 0, t, c, v)

def _flip(x, y):
    x = max(0, min(W - 1, int(x))); y = max(0, min(H - 1, int(y)))
    return (W - 1) - x, (H - 1) - y            # panel is 180deg-rotated

def _append(data):
    with _ev_lock:
        with open(EV, 'ab') as f:
            f.write(data)

def press(dx, dy):
    rx, ry = _flip(dx, dy)
    _append(_ev(EV_ABS, ABS_MT_TRACKING_ID, 0) + _ev(EV_ABS, ABS_MT_POSITION_X, rx)
            + _ev(EV_ABS, ABS_MT_POSITION_Y, ry) + _ev(EV_ABS, ABS_X, rx)
            + _ev(EV_ABS, ABS_Y, ry) + _ev(EV_KEY, BTN_TOUCH, 1) + _ev(EV_SYN, SYN_REPORT, 0))

def move(dx, dy):
    rx, ry = _flip(dx, dy)
    _append(_ev(EV_ABS, ABS_MT_POSITION_X, rx) + _ev(EV_ABS, ABS_MT_POSITION_Y, ry)
            + _ev(EV_ABS, ABS_X, rx) + _ev(EV_ABS, ABS_Y, ry) + _ev(EV_SYN, SYN_REPORT, 0))

def release():
    _append(_ev(EV_ABS, ABS_MT_TRACKING_ID, -1) + _ev(EV_KEY, BTN_TOUCH, 0)
            + _ev(EV_SYN, SYN_REPORT, 0))

def tap(dx, dy):
    # A plain click: the read-cb drains all queued events per poll and reports the
    # NET state, so press+release in one batch = no tap. Hold ~0.3s so LVGL samples
    # the pressed state first (see docs/TOUCH.md).
    press(dx, dy)
    time.sleep(0.30)
    release()

def swipe(x0, y0, x1, y1, steps=12, hold=0.028):
    """Server-side smooth swipe: press, interpolated moves over wall-clock time,
    release. Reliable for LVGL gestures (pull-down shade, back = left->right) where
    a hand-drawn drag is fiddly. Coords are display-space; each is flipped."""
    press(x0, y0)
    time.sleep(hold)
    for i in range(1, steps + 1):
        move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        time.sleep(hold)
    release()

# Physical keys — x2000_key on event0, custom codes (see docs/RE.md). Needs the key-enable
# patch (scripts/patch_keys.sh) or the firmware drops them. The stock handler does its own
# single/double/long-click detection by timing, so a ~0.12s press = single click.
# Only codes with a confirmed action in echo_sys_key_handler (docs/RE.md). NOTE: there is no
# power key on event0 — power is MCU-mediated (not emulated). 0xfa is a silent back/exit, omitted.
KEYS = {'menu_up': 0x107, 'menu_down': 0x106, 'play': 0x10c, 'play_pause': 0x103}

def key(code):
    _append_ev0(_ev(EV_KEY, code, 1) + _ev(EV_SYN, SYN_REPORT, 0))
    time.sleep(0.12)
    _append_ev0(_ev(EV_KEY, code, 0) + _ev(EV_SYN, SYN_REPORT, 0))

def _append_ev0(data):
    with _ev_lock:
        with open(EV0, 'ab') as f:
            f.write(data)

# Named gestures, in DISPLAY coords (what you see). 360x360 round panel.
GESTURES = {
    'down':  (180, 18, 180, 300),    # pull the shade / status panel down from the top
    'up':    (180, 342, 180, 60),    # push it back up
    'back':  (18, 180, 320, 180),    # swipe left->right = go back
    'left':  (342, 180, 40, 180),    # swipe right->left
}

# ---- HTTP --------------------------------------------------------------------

PAGE = ("""<!doctype html><meta charset=utf-8>
<title>Snowsky Disc</title>
<style>
 html,body{margin:0;background:#fff;color:#333;font:13px system-ui;text-align:center}
 #wrap{display:inline-block;margin:20px auto}
 /* device-skin mode: photo of the player with the live round screen over the glass */
 #stage{position:relative;width:__STAGE__px;margin:0 auto}
 #stage.skin #skin{display:block;width:100%}
 #stage.skin #scr{position:absolute;left:__L__%;top:__T__%;width:__D__%;aspect-ratio:1/1;
        height:auto;border-radius:50%;object-fit:cover}
 /* plain mode (no skin): a framed round screen */
 #stage.plain{width:360px}
 #stage.plain #skin{display:none}
 #stage.plain #scr{width:360px;height:360px;border-radius:50%;background:#000;
        box-shadow:0 0 0 6px #ddd,0 0 30px rgba(0,0,0,.15)}
 #scr{image-rendering:pixelated;touch-action:none;cursor:crosshair;display:block}
 .hint{color:#888;margin-top:14px}
 .bar{margin-top:12px}
 .bar button{background:#f4f4f5;color:#333;border:1px solid #d5d5d8;border-radius:9px;
      padding:7px 13px;margin:3px;font:13px system-ui;cursor:pointer}
 .bar button:hover{background:#eaeaec}
</style>
<div id=wrap>
 <div id="stage" class="__MODE__">
  <img id=skin src="/skin" draggable=false alt="">
  <img id=scr src="/stream" draggable=false>
 </div>
 <div class=hint>click = tap · drag = swipe · long-press to hold</div>
 <div class=bar>
  <button onclick="go('/swipe?dir=down')">▼ shade</button>
  <button onclick="go('/swipe?dir=up')">▲ up</button>
  <button onclick="go('/swipe?dir=back')">↩ back (→)</button>
  <button onclick="go('/swipe?dir=left')">◀ left</button>
  <button id=alignbtn onclick="align.on=!align.on;draw()">⊹ align</button>
 </div>
 <div class=bar>
  <button onclick="go('/key?k=menu_up')">▲ menu-up</button>
  <button onclick="go('/key?k=menu_down')">▼ menu-down</button>
  <button onclick="go('/key?k=play')">▶ play</button>
  <button onclick="go('/key?k=play_pause')">⏯ play/pause</button>
 </div>
 <div id=readout class=hint></div>
</div>
<script>
const img=document.getElementById('scr');
const R=360, TH=6;                       // display px, drag threshold
// --- skin align: nudge the round screen over the photo, read off cx/cy/d ---
const align={on:false, cx:__CX__, cy:__CY__, d:__DD__, ar:__AR__};
function draw(){
  const l=(align.cx-align.d/2)*100, t=(align.cy-align.d*align.ar/2)*100;
  img.style.left=l.toFixed(2)+'%'; img.style.top=t.toFixed(2)+'%'; img.style.width=(align.d*100).toFixed(2)+'%';
  document.getElementById('alignbtn').style.background=align.on?'#d9e8b0':'';
  document.getElementById('readout').textContent=align.on
    ? `align: Alt+arrows move · +/- size · cx=${align.cx.toFixed(3)} cy=${align.cy.toFixed(3)} d=${align.d.toFixed(3)}  →  SKIN_CX=${align.cx.toFixed(3)} SKIN_CY=${align.cy.toFixed(3)} SKIN_D=${align.d.toFixed(3)}`
    : '';
}
addEventListener('keydown',e=>{if(!align.on)return;const s=e.shiftKey?0.005:0.001;let h=true;
  if(e.altKey&&e.key==='ArrowLeft')align.cx-=s; else if(e.altKey&&e.key==='ArrowRight')align.cx+=s;
  else if(e.altKey&&e.key==='ArrowUp')align.cy-=s; else if(e.altKey&&e.key==='ArrowDown')align.cy+=s;
  else if(e.key==='+'||e.key==='=')align.d+=s; else if(e.key==='-'||e.key==='_')align.d-=s; else h=false;
  if(h){e.preventDefault();draw();}});
if('__MODE__'==='skin')draw();
let down=false, moved=false, sx=0, sy=0, lastMove=0;
function pt(e){const r=img.getBoundingClientRect();
  return [Math.round((e.clientX-r.left)*R/r.width),
          Math.round((e.clientY-r.top )*R/r.height)];}
function go(u){fetch(u).catch(()=>{});}
img.addEventListener('pointerdown',e=>{e.preventDefault();
  [sx,sy]=pt(e);down=true;moved=false;img.setPointerCapture(e.pointerId);});
img.addEventListener('pointermove',e=>{if(!down)return;
  const [x,y]=pt(e);
  if(!moved && Math.abs(x-sx)+Math.abs(y-sy)>TH){moved=true;go(`/down?x=${sx}&y=${sy}`);}
  if(moved){const t=performance.now();if(t-lastMove>30){lastMove=t;go(`/move?x=${x}&y=${y}`);}}});
img.addEventListener('pointerup',e=>{if(!down)return;down=false;
  if(moved){const [x,y]=pt(e);go(`/move?x=${x}&y=${y}`);setTimeout(()=>go('/up'),20);}
  else{go(`/tap?x=${sx}&y=${sy}`);}});
</script>
""")

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _q(self, qs, k):
        return int(float(qs.get(k, ['0'])[0]))

    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        if p == '/':
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
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            period = 1.0 / FPS
            try:
                while True:
                    with state.lock:
                        png = state.png
                    self.wfile.write(b'--FRAME\r\nContent-Type: image/png\r\n'
                                     b'Content-Length: %d\r\n\r\n' % len(png))
                    self.wfile.write(png)
                    self.wfile.write(b'\r\n')
                    time.sleep(period)
            except (BrokenPipeError, ConnectionResetError):
                return
        elif p == '/key':
            k = qs.get('k', [''])[0]
            code = KEYS.get(k)
            if code is None and qs.get('code'):
                try:
                    code = int(qs['code'][0], 0)
                except ValueError:
                    code = None
            if code is not None:
                key(code)
            self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers()
        elif p in ('/tap', '/down', '/move', '/up', '/swipe'):
            if p == '/tap':
                tap(self._q(qs, 'x'), self._q(qs, 'y'))
            elif p == '/down':
                press(self._q(qs, 'x'), self._q(qs, 'y'))
            elif p == '/move':
                move(self._q(qs, 'x'), self._q(qs, 'y'))
            elif p == '/swipe':
                d = qs.get('dir', [''])[0]
                if d in GESTURES:
                    swipe(*GESTURES[d])
                else:
                    swipe(self._q(qs, 'x0'), self._q(qs, 'y0'),
                          self._q(qs, 'x1'), self._q(qs, 'y1'))
            else:
                release()
            self.send_response(204)
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()

def main():
    if not os.path.exists(FB):
        print("no framebuffer %s — boot first (scripts/20_boot.sh)" % FB, file=sys.stderr)
    threading.Thread(target=grab_loop, daemon=True).start()
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print("stream: http://0.0.0.0:%d  (fb=%s ev=%s %gfps)" % (PORT, FB, EV, FPS))
    srv.serve_forever()

if __name__ == '__main__':
    main()
