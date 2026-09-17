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
            setAttribute(name, value) { this[name] = value; },
            getContext: () => ({clearRect() {}}),
        });
        return elements.get(id);
    };
    let worker, powerTap, powerHold, stopped = 0;
    const context = {
        document: {getElementById: element},
        window: {addEventListener() {}},
        Worker: class { constructor() { worker = this; } postMessage(m) { messages.push(m); } terminate() { stopped++; } },
        bindPower: (button, tap, hold) => { powerTap = tap; powerHold = hold; },
        bindGestures: () => () => {}, WIDTH:360,
        performance: {now: () => 1}, setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {},
    };
    const source = fs.readFileSync(require.resolve('../browser/static/app.js'), 'utf8')
        .replace(/^import .*;\n/gm, '');
    vm.runInNewContext(source, context);
    const click = id => { assert.equal(element(id).disabled, false); if (id === 'power') powerTap(); else element(id).listeners.click(); };
    element('start').disabled = false; click('start');
    const status = value => worker.onmessage({data:{type:'status', value}});
    status({state:'ready'});
    return {element, click, status, messages, hold:() => powerHold(), stopped:() => stopped};
}

test('sleep disables touch navigation but leaves Wakeup available; wake uses one power command', () => {
    const {element, click, status, messages} = page();
    status({state:'screen', screenOn:false});
    assert.equal(element('power-label').textContent, 'Wakeup');
    assert.equal(element('back').disabled, true);
    click('power');
    assert.equal(messages.at(-1).kind, 'power');
    assert.equal(element('power').disabled, false); // local hold-to-stop remains available
    status({state:'ready', sequence:1, ok:true});
    assert.equal(element('back').disabled, true); // injection ack is not proof of wake
    status({state:'screen', screenOn:true});
    assert.equal(element('power-label').textContent, 'Lock screen');
    assert.equal(element('back').disabled, false);
});
test('screen updates cannot release an unacknowledged power command', () => {
    const {element, click, status, messages} = page();
    click('power');
    const count = messages.length;
    status({state:'screen', screenOn:true});
    assert.equal(element('power').disabled, false); // local hold-to-stop remains available
    click('power');
    assert.equal(messages.length, count);
    status({state:'ready', sequence:42, ok:true});
    click('power');
    assert.equal(messages.length, count);
    assert.equal(element('power').disabled, false); // local hold-to-stop remains available
});
test('failed firmware restarts only by explicit Power and never injects another key', () => {
    const {element, status, click, messages, stopped} = page();
    status({state:'failed'});
    assert.equal(element('power').disabled, false); // local hold-to-stop remains available
    assert.match(element('status').textContent, /Power to restart/);
    const count = messages.length;
    click('power');
    assert.equal(stopped(), 1);
    assert.equal(messages.length, count + 1);
    assert.equal(messages.at(-1).type, 'start');
});

test('Power hold terminates the VM; next short press starts a fresh one', () => {
    const {hold, stopped, element, click, messages} = page();
    hold();
    assert.equal(stopped(), 1);
    assert.equal(element('power-label').textContent, 'Start player');
    click('power');
    assert.equal(messages.at(-1).type, 'start');
});
