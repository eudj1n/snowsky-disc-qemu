"""Synthetic frame bytes and independent PNG decoder for acceptance tests."""
import struct
import zlib
from emulator.runtime.framebuffer import W, H

def pixels(blue, green=20, red=40, unused=0):
    return bytes((blue, green, red, unused)) * (W * H)


def decode_png(png):
    """Check exact pixel bytes independently of the encoder (RGB, filter 0)."""
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    compressed = b''
    offset = 8
    while offset < len(png):
        size = struct.unpack('>I', png[offset:offset + 4])[0]
        if png[offset + 4:offset + 8] == b'IDAT':
            compressed += png[offset + 8:offset + 8 + size]
        offset += size + 12
    data = zlib.decompress(compressed)
    stride = W * 3 + 1
    assert all(data[y * stride] == 0 for y in range(H))
    return b''.join(data[y * stride + 1:(y + 1) * stride] for y in range(H))
