const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function page() {
    const elements = new Map(), messages = [];
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            disabled: true, textContent: '', listeners: {},
            classList: {add() {}, remove() {}, toggle() {}},
            addEventListener(type, callback) { this.listeners[type] = callback; },
            getContext: () => ({clearRect() {}}),
        });
        return elements.get(id);
    };
    let worker;
    const context = {
        document: {getElementById: element},
        window: {addEventListener() {}},
        Worker: class { constructor() { worker = this; } postMessage(m) { messages.push(m); } terminate() {} },
        bindGestures: () => () => {}, WIDTH:360,
        performance: {now: () => 1}, setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {},
    };
    const source = fs.readFileSync(require.resolve('../browser/static/app.js'), 'utf8')
        .replace(/^import .*;\n/gm, '');
    vm.runInNewContext(source, context);
    const click = id => { assert.equal(element(id).disabled, false); element(id).listeners.click(); };
    element('start').disabled = false; click('start');
    const status = value => worker.onmessage({data:{type:'status', value}});
    status({state:'ready'});
    return {element, click, status, messages};
}

test('sleep disables touch navigation but leaves Wakeup available; wake uses one power command', () => {
    const {element, click, status, messages} = page();
    status({state:'screen', screenOn:false});
    assert.equal(element('power').textContent, 'Wakeup');
    assert.equal(element('back').disabled, true);
    click('power');
    assert.equal(messages.at(-1).kind, 'power');
    assert.equal(element('power').disabled, true);
    status({state:'ready', sequence:1, ok:true});
    assert.equal(element('back').disabled, true); // injection ack is not proof of wake
    status({state:'screen', screenOn:true});
    assert.equal(element('power').textContent, 'Lock screen');
    assert.equal(element('back').disabled, false);
});
test('screen updates cannot release an unacknowledged power command', () => {
    const {element, click, status} = page();
    click('power');
    status({state:'screen', screenOn:true});
    assert.equal(element('power').disabled, true);
    status({state:'ready', sequence:42, ok:true});
    assert.equal(element('power').disabled, true);
});
test('stopped firmware cannot be woken by injecting another key', () => {
    const {element, status} = page();
    status({state:'failed'});
    assert.equal(element('power').disabled, true);
    assert.match(element('status').textContent, /Stop → Start/);
});
