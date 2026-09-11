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

function domFixture() {
  const vm = require('node:vm'), fs = require('node:fs');
  const events = {}, classes = new Set(), tasks = new Map();
  let id = 0, now = 0;
  const button = {dataset: {key: 'volume_up'}, disabled: false,
    classList: {add: c => classes.add(c), remove: c => classes.delete(c)},
    focus() {}, setPointerCapture() {}, addEventListener: (name, fn) => { events[name] = fn; }};
  const windowEvents = {}, nodes = {'key-status': {}, 'key-action': {}};
  vm.runInNewContext(fs.readFileSync(require.resolve('./keys.js'), 'utf8'), {
    document: {getElementById: id => nodes[id], querySelectorAll: () => [button], addEventListener() {}},
    window: {addEventListener: (name, fn) => { windowEvents[name] = fn; }},
    performance: {now: () => now},
    setTimeout: fn => { tasks.set(++id, fn); return id; }, clearTimeout: id => tasks.delete(id),
    fetch: () => new Promise(() => {}) // status stays pending; no network in unit tests
  });
  return {button, classes, tasks, windowEvents,
    event(name, data = {}) { now += 10; events[name]({button: 0, pointerId: 1, preventDefault() {}, ...data}); }};
}
test('skin pointer state clears on release, cancellation and window blur', () => {
  for (const end of ['pointerup', 'pointercancel', 'lostpointercapture', 'blur']) {
    const f = domFixture(); f.event('pointerdown'); assert(f.classes.has('is-pressed'));
    f.event(end); assert(!f.classes.has('is-pressed'));
    if (end !== 'pointerup') assert.equal(f.tasks.size, 0);
  }
  const f = domFixture(); f.event('pointerdown'); f.windowEvents.blur();
  assert(!f.classes.has('is-pressed')); assert.equal(f.tasks.size, 0);
});
test('keyboard gets pressed feedback and generated click does not duplicate it', () => {
  const f = domFixture(); f.event('keydown', {key: ' '}); assert(f.classes.has('is-pressed'));
  f.event('keyup', {key: ' '}); assert(!f.classes.has('is-pressed'));
  const timers = [...f.tasks.keys()]; f.event('click'); assert.deepEqual([...f.tasks.keys()], timers);
  f.button.disabled = true; f.event('keydown', {key: 'Enter'}); assert(!f.classes.has('is-pressed'));
});
test('another finger cannot release a held hotspot, right click cannot press it', () => {
  const f = domFixture(); f.event('pointerdown', {button: 2}); assert(!f.classes.has('is-pressed'));
  f.event('pointerdown'); f.event('pointerup', {pointerId: 2}); assert(f.classes.has('is-pressed'));
  f.event('pointerup'); assert(!f.classes.has('is-pressed'));
});
