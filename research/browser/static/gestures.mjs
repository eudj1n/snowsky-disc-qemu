// Record one pointer, then submit one complete gesture. No input on cancellation.
export function bindGestures(canvas, enabled, send) {
    let pointer = null;
    const point = event => {
        const r = canvas.getBoundingClientRect();
        return [event.clientX - r.left, event.clientY - r.top].map((v, i) =>
            Math.max(0, Math.min(359, Math.floor(v * 360 / (i ? r.height : r.width)))));
    };
    canvas.addEventListener('pointerdown', event => {
        if (pointer || !enabled() || !event.isPrimary || event.button !== 0) return;
        event.preventDefault();
        pointer = {id: event.pointerId, start: point(event), distance: 0};
        canvas.setPointerCapture(event.pointerId);
    });
    const update = event => {
        if (!pointer || event.pointerId !== pointer.id) return;
        const end = point(event);
        pointer.distance = Math.max(pointer.distance,
            Math.hypot(end[0] - pointer.start[0], end[1] - pointer.start[1]));
        return end;
    };
    canvas.addEventListener('pointermove', update);
    canvas.addEventListener('pointerup', event => {
        const end = update(event);
        if (!end) return;
        const {start, distance, id} = pointer;
        pointer = null;
        canvas.releasePointerCapture(id);
        if (!enabled()) return;
        if (distance < 12) send({kind: 'tap', x0: start[0], y0: start[1], x1: start[0], y1: start[1]});
        else if (Math.hypot(end[0] - start[0], end[1] - start[1]) >= 12)
            send({kind: 'swipe', x0: start[0], y0: start[1], x1: end[0], y1: end[1]});
    });
    const cancel = event => { if (pointer?.id === event.pointerId) pointer = null; };
    canvas.addEventListener('pointercancel', cancel);
    canvas.addEventListener('lostpointercapture', cancel);
    return () => { pointer = null; };
}
