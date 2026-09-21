const {test} = require('node:test');
const assert = require('node:assert/strict');

async function setup() {
    const {bindGestures} = await import('../static/gestures.mjs');
    const listeners = {}, sent = [];
    let enabled = true;
    const canvas = {
        addEventListener: (type, fn) => { listeners[type] = fn; },
        getBoundingClientRect: () => ({left:10, top:20, width:180, height:180}),
        setPointerCapture() {}, releasePointerCapture() {},
    };
    const cancel = bindGestures(canvas, () => enabled, g => sent.push(g));
    const fire = (type, x, y, extra = {}) => listeners[type]({
        clientX:x, clientY:y, pointerId:1, isPrimary:true, button:0, preventDefault() {}, ...extra,
    });
    return {sent, fire, cancel, disable: () => { enabled = false; }};
}

test('small pointer jitter remains one tap in display coordinates', async () => {
    const {sent, fire} = await setup();
    fire('pointerdown', 100, 110); fire('pointerup', 102, 111);
    assert.deepEqual(sent, [{kind:'tap', x0:180, y0:180, x1:180, y1:180}]);
});
test('drag submits a swipe and clamps release outside the captured canvas', async () => {
    const {sent, fire} = await setup();
    fire('pointerdown', 19, 110); fire('pointermove', 130, 110); fire('pointerup', 230, 110);
    assert.deepEqual(sent, [{kind:'swipe', x0:18, y0:180, x1:359, y1:180}]);
});
test('cancelled, lost and stopped gestures do not send input', async () => {
    for (const event of ['pointercancel', 'lostpointercapture', 'stop']) {
        const {sent, fire, cancel} = await setup();
        fire('pointerdown', 100, 110);
        if (event === 'stop') cancel(); else fire(event, 100, 110);
        fire('pointerup', 170, 110);
        assert.deepEqual(sent, []);
    }
});
test('second pointer and input disabled during drag cannot dispatch', async () => {
    const {sent, fire, disable} = await setup();
    fire('pointerdown', 100, 110);
    fire('pointerup', 170, 110, {pointerId:2});
    assert.deepEqual(sent, []);
    disable(); fire('pointerup', 170, 110);
    assert.deepEqual(sent, []);
});
test('out-and-back drag does not accidentally activate an item', async () => {
    const {sent, fire} = await setup();
    fire('pointerdown', 100, 110); fire('pointermove', 170, 110); fire('pointerup', 100, 110);
    assert.deepEqual(sent, []);
});
