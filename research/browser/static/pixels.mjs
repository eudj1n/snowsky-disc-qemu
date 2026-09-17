export const WIDTH = 360;
export const FRAME_BYTES = WIDTH * WIDTH * 4;

export function bgrxToRgba(raw) {
    if (raw.byteLength !== FRAME_BYTES) throw new Error('Invalid framebuffer size');
    const input = new Uint8Array(raw);
    const rgba = new Uint8ClampedArray(FRAME_BYTES);
    for (let dst = 0, src = FRAME_BYTES - 4; dst < FRAME_BYTES; dst += 4, src -= 4) {
        rgba[dst] = input[src + 2];
        rgba[dst + 1] = input[src + 1];
        rgba[dst + 2] = input[src];
        rgba[dst + 3] = 255;
    }
    return rgba;
}
