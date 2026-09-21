import assert from 'node:assert/strict';
import {ReplyPlayer} from './static/reply.js';
let calls = [], started = 0, stopped = 0, messages = [];
const context = {
  state: 'running', resume: async () => {}, decodeAudioData: async data => data,
  createBufferSource: () => ({connect() {}, disconnect() {}, start() { started++; }, stop() { stopped++; }}), close() {}
};
const result = {request_id: 'fixture', response: {speak: true, text: 'Paused'}};
const success = {ok: true, arrayBuffer: async () => new ArrayBuffer(8)};
let responder = async () => success;
const replies = new ReplyPlayer({token: () => 'fixture-token', context: () => context,
  status: message => messages.push(message), fetcher: async (url, options) => { calls.push({url, options}); return responder(url); }});
await replies.play(result);
assert.equal(calls.length, 0); // Off by default, including a reloaded tab.
await replies.enable(true);
await replies.play({...result, response: {...result.response, speak: false}});
assert.equal(calls.length, 0);
await replies.play(result);
assert.equal(started, 1);
assert.equal(calls[0].options.headers['X-Disc-Token'], 'fixture-token');
replies.source.onended();
assert.ok(calls.some(c => c.url.endsWith('outcome=played')));
await replies.play(result); replies.stop(); assert.equal(stopped, 1);
let release;
responder = url => url.includes('/api/reply?') ? new Promise(resolve => { release = resolve; }) : success;
const pending = replies.play(result);
replies.stop(); release(success); await pending;
assert.equal(started, 2); // Superseded synthesis cannot start playback.
responder = async () => ({ok: false, text: async () => 'unavailable'});
await replies.play(result);
assert.ok(messages.at(-1).includes('result is unchanged'));
assert.ok(calls.every(c => !c.url.includes('/api/command')));
await replies.enable(false);
replies.close();
console.log('Reply opt-in, silent policy, playback evidence, cancellation and failure isolation passed.');
// WebKit requires the native fetch receiver; storing bare fetch as a method fails.
const originalFetch = globalThis.fetch;
try {
  globalThis.fetch = async function () { assert.equal(this, undefined); return success; };
  const nativeBinding = new ReplyPlayer({token: () => 'fixture', status() {}, context: () => context});
  await nativeBinding.enable(true); await nativeBinding.play(result);
  assert.ok(nativeBinding.source);
  nativeBinding.close();
} finally { globalThis.fetch = originalFetch; }
