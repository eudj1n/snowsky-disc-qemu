const test = require('node:test');
const assert = require('node:assert/strict');

test('browser adapter preserves color and rotates opposite framebuffer corners', async () => {
    const {FRAME_BYTES, bgrxToRgba} = await import('../static/pixels.mjs');
    const raw = new Uint8Array(FRAME_BYTES);
    // Top-left guest pixel is red; bottom-right is blue. X is unused, not alpha.
    raw.set([0, 0, 255, 12], 0);
    raw.set([255, 0, 0, 90], FRAME_BYTES - 4);
    const rendered = bgrxToRgba(raw.buffer);
    assert.deepEqual([...rendered.slice(0, 4)], [0, 0, 255, 255]);
    assert.deepEqual([...rendered.slice(-4)], [255, 0, 0, 255]);
    assert.deepEqual([...rendered.slice(4, 8)], [0, 0, 0, 255]);
});

test('browser adapter rejects incomplete or concatenated frames', async () => {
    const {FRAME_BYTES, bgrxToRgba} = await import('../static/pixels.mjs');
    assert.throws(() => bgrxToRgba(new ArrayBuffer(FRAME_BYTES - 1)), /size/);
    assert.throws(() => bgrxToRgba(new ArrayBuffer(FRAME_BYTES * 2)), /size/);
});
