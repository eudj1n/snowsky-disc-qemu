const {test} = require('node:test');
const assert = require('node:assert/strict');
async function fixture() {
    const {bindPower} = await import('../browser/static/power.mjs');
    const listeners = {}, windowListeners = {}, tasks = new Map();
    let now = 1000, next = 0, taps = 0, holds = 0;
    const button = {disabled:false, classList:{add(){}, remove(){}}, focus(){}, setPointerCapture(){},
        addEventListener(name, fn){listeners[name] = fn;}};
    const timers = {now:()=>now, set(fn){tasks.set(++next,fn);return next;}, clear(id){tasks.delete(id);}};
    bindPower(button,()=>taps++,()=>holds++,timers,{addEventListener(name,fn){windowListeners[name]=fn;}});
    const fire = (name, extra={}) => listeners[name]({button:0,pointerId:1,preventDefault(){},...extra});
    return {fire, blur:()=>windowListeners.blur(), elapsed:(ms)=>{now+=ms;},
        hold:()=>{now+=1800;for(const fn of [...tasks.values()])fn();}, result:()=>[taps,holds]};
}
test('Power short press acts once despite native click; long press never adds a tap', async () => {
    const f = await fixture();
    f.fire('pointerdown'); f.fire('pointerup'); f.fire('click');
    assert.deepEqual(f.result(),[1,0]);
    f.elapsed(600);f.fire('pointerdown'); f.hold(); f.fire('pointerup'); f.fire('click');
    assert.deepEqual(f.result(),[1,1]);
});
test('Power cancels on pointer loss and blur and ignores a second finger', async () => {
    for (const cancel of ['pointercancel','lostpointercapture','blur']) {
        const f = await fixture(); f.fire('pointerdown');
        f.fire('pointerup',{pointerId:2}); assert.deepEqual(f.result(),[0,0]);
        if(cancel==='blur') f.blur();else f.fire(cancel);
        f.hold();f.fire('pointerup'); assert.deepEqual(f.result(),[0,0]);
    }
});
test('Power keyboard gestures suppress repeats and generated clicks; click-only access works', async () => {
    const f = await fixture();
    f.fire('click'); assert.deepEqual(f.result(),[1,0]);
    f.fire('keydown',{key:'Enter'}); f.fire('keydown',{key:'Enter',repeat:true});
    f.fire('keyup',{key:'Enter'});f.fire('click',{detail:0});
    assert.deepEqual(f.result(),[2,0]);
    f.elapsed(600);f.fire('keydown',{key:' '});f.hold();f.fire('keyup',{key:' '});f.fire('click');
    assert.deepEqual(f.result(),[2,1]);
});
