const {test} = require('node:test');
const assert = require('node:assert/strict');
const {PhysicalButton} = require('./keys.js');
function fixture(name = 'volume_up') {
  let now = 0, id = 0;
  const tasks = new Map(), events = [];
  const timers = {set: (fn, ms) => {tasks.set(++id, {fn, at: now + ms}); return id;},
    clear: id => tasks.delete(id)};
  function tick(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...tasks].sort((a, b) => a[1].at - b[1].at)[0];
      if (!next || next[1].at > end) break;
      tasks.delete(next[0]); now = next[1].at; next[1].fn();
    }
    now = end;
  }
  return {button: new PhysicalButton(name, (n, g) => events.push([n, g]), timers), events, tick};
}
test('single waits for double-click window', () => {
  const {button, events, tick} = fixture(); button.press(); tick(100); button.release();
  tick(279); assert.deepEqual(events, []); tick(1);
  assert.deepEqual(events, [['volume_up', 'single']]);
});
test('double emits only double', () => {
  const {button, events, tick} = fixture();
  button.press(); button.release(); tick(100); button.press(); button.release(); tick(1000);
  assert.deepEqual(events, [['volume_up', 'double']]);
});
test('hold repeats, releases without an extra click', () => {
  const {button, events, tick} = fixture(); button.press(); tick(1050); button.release(); tick(1000);
  assert.deepEqual(events.map(e => e[1]), ['hold', 'hold', 'hold', 'end']);
});
test('cancel on blur/pointer loss stops repeat and pending clicks', () => {
  const {button, events, tick} = fixture(); button.press(); tick(650); button.cancel(); tick(1000);
  assert.deepEqual(events.map(e => e[1]), ['hold', 'cancel']);
  const f = fixture(); f.button.press(); f.button.release(); f.button.cancel(); f.tick(1000);
  assert.deepEqual(f.events, []);
});
test('power short is immediate, long fires exactly once', () => {
  const {button, events, tick} = fixture('power'); button.press(); button.release();
  assert.deepEqual(events.map(e => e[1]), ['single']);
  button.press(); tick(1799); assert.equal(events.length, 1); tick(4000); button.release();
  assert.deepEqual(events.map(e => e[1]), ['single', 'hold', 'end']);
});
test('play hold is the stock no-op gesture, never repeating pause', () => {
  const {button, events, tick} = fixture('play_pause'); button.press(); tick(3000); button.release();
  assert.deepEqual(events.map(e => e[1]), ['hold', 'end']);
});
