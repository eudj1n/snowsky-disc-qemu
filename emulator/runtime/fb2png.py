#!/usr/bin/env python3
"""Convert the emulated framebuffer file to PNG(s). Pure stdlib (no PIL).

The device fb0 is 360 x 1080 x 4 (BGRX) = three 360x360 sub-buffers. mq_ui does
NOT pan; it alternates drawing to buf0/buf1, so the *current* screen is whichever
sub-buffer was flushed last (a static screen is not re-flushed, so the other holds
a stale frame). This tool emits every non-empty sub-buffer; pick the meaningful one
(the script prints each buffer's non-black pixel count to help).

The panel + LVGL display are rotated 180deg, so we reverse pixel order for viewing.

Usage:  fb2png.py <fb0-file> <out-dir> [prefix]
"""
import sys, zlib, struct

W = H = 360
BUF = W * H * 4

def png(rgb, path):
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    rows = b''.join(b'\x00' + rgb[y*W*3:(y+1)*W*3] for y in range(H))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))

def convert(buf):
    """BGRX -> RGB with 180deg rotation."""
    out = bytearray(W * H * 3)
    for i in range(W * H):
        b, g, r = buf[i*4], buf[i*4+1], buf[i*4+2]
        j = W * H - 1 - i
        out[j*3], out[j*3+1], out[j*3+2] = r, g, b
    return bytes(out)

def main():
    fb, outdir = sys.argv[1], sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else 'fb'
    raw = open(fb, 'rb').read()
    import os; os.makedirs(outdir, exist_ok=True)
    for idx in range(3):
        buf = raw[idx*BUF:(idx+1)*BUF]
        if len(buf) < BUF:
            break
        nz = sum(1 for k in range(0, len(buf), 4) if buf[k] or buf[k+1] or buf[k+2])
        path = f"{outdir}/{prefix}-b{idx}.png"
        png(convert(buf), path)
        print(f"{path}  non_black_px={nz}")

if __name__ == '__main__':
    main()
