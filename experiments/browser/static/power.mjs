// Local VM lifecycle gesture; never sends the firmware's raw power-off event.
export function bindPower(button, tap, hold, timers = {set:(fn, ms) => setTimeout(fn, ms), clear:id => clearTimeout(id), now:() => performance.now()}, target = window) {
    let down = false, held = false, pointer = null, timer = null, lastPhysicalEvent = -Infinity;
    function cancel() {
        timers.clear(timer); timer = null; down = held = false; pointer = null;
        button.classList.remove('is-pressed');
    }
    function press() {
        if (down || button.disabled) return;
        down = true; held = false; lastPhysicalEvent = timers.now();
        button.classList.add('is-pressed');
        timer = timers.set(() => { if (down) { held = true; hold(); } }, 1800);
    }
    function release() {
        if (!down) return;
        lastPhysicalEvent = timers.now();
        const wasHeld = held;
        cancel();
        if (!wasHeld) tap();
    }
    button.addEventListener('pointerdown', event => {
        if (event.button !== 0 || down || button.disabled) return;
        event.preventDefault(); button.focus();
        pointer = event.pointerId; button.setPointerCapture(pointer); press();
    });
    button.addEventListener('pointerup', event => { if (event.pointerId === pointer) release(); });
    button.addEventListener('pointercancel', cancel);
    button.addEventListener('lostpointercapture', () => { if (down) cancel(); });
    button.addEventListener('keydown', event => {
        if (event.key !== ' ' && event.key !== 'Enter') return;
        event.preventDefault(); if (!event.repeat) press();
    });
    button.addEventListener('keyup', event => {
        if (event.key !== ' ' && event.key !== 'Enter') return;
        event.preventDefault(); release();
    });
    button.addEventListener('click', () => {
        // Do not duplicate native pointer/keyboard release with its generated click.
        if (!button.disabled && timers.now() - lastPhysicalEvent > 500) tap();
    });
    button.addEventListener('blur', cancel);
    target.addEventListener('blur', cancel);
    target.addEventListener('pagehide', cancel);
    return cancel;
}
