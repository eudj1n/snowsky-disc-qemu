import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {encodeWav} from './static/audio.js';

const blob = encodeWav(new Float32Array([-2, -1, 0, 1, 2]));
const data = new DataView(await blob.arrayBuffer());
assert.equal(blob.type, 'audio/wav');
assert.equal(data.getUint32(24, true), 16000);
assert.equal(data.getUint16(22, true), 1);
assert.equal(data.getUint16(34, true), 16);
assert.deepEqual(Array.from({length: 5}, (_, i) => data.getInt16(44 + 2 * i, true)), [-32768, -32768, 0, 32767, 32767]);

let Capture;
vm.runInNewContext(readFileSync(new URL('./static/capture.js', import.meta.url), 'utf8'), {
  sampleRate: 48000, Float32Array,
  AudioWorkletProcessor: class { constructor() { this.port = {postMessage: message => messages.push(message)}; } },
  registerProcessor: (_, implementation) => { Capture = implementation; }
});
let messages = [];
const capture = new Capture({processorOptions: {maxSeconds: 1}});
let iterations = 0;
while (capture.process([[new Float32Array(128).fill(.25), new Float32Array(128).fill(.75)]])) {
  assert.ok(++iterations < 500);
}
assert.equal(messages.filter(m => m.samples).reduce((n, m) => n + m.samples.length, 0), 48000);
assert.ok(messages.filter(m => m.samples).every(m => m.samples.every(v => v === .5)));
assert.equal(messages.filter(m => m.done).length, 1);
capture.finish(); assert.equal(messages.filter(m => m.done).length, 1);
messages = [];
const cancelled = new Capture({processorOptions: {maxSeconds: 30}});
cancelled.port.onmessage();
assert.equal(cancelled.process([[new Float32Array(128)]]), false);
assert.equal(messages.filter(m => m.samples).length, 0);
console.log('Audio encoding, channel mixing, duration bound and capture stop passed.');
