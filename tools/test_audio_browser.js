const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('browser routes PCM through DAC gains, updates them and stops when guest powers off', async () => {
  const elements = {}, timers = [], gains = [], sources = [];
  let splitter, info = {generation:'test', bytes:8, channels:2, sample_bytes:4,
    rate:44100, seconds:1, output_gain:[.25,.5], running:true};
  function node() {return {connections:[], connect(...args) {this.connections.push(args);}};}
  class AudioContext {
    constructor() {this.currentTime=0; this.destination=node();}
    async resume() {}
    createChannelSplitter() {splitter=node(); return splitter;}
    createChannelMerger() {return node();}
    createGain() {
      const n=node(); n.gain={value:1, setTargetAtTime(value) {this.value=value;}};
      gains.push(n);return n;
    }
    createBuffer(channels, frames) {return {getChannelData:() => new Float32Array(frames)};}
    createBufferSource() {
      const n=node(); n.start=()=>{}; n.stop=()=>{n.stopped=true;}; sources.push(n);return n;
    }
  }
  const context = vm.createContext({AudioContext, DataView, Set,
    document:{getElementById: id => elements[id] ||= {setAttribute() {},classList:{toggle() {}},querySelector:()=>({})}},
    fetch:async path => ({ok:true, json:async()=>info, arrayBuffer:async()=>new ArrayBuffer(8)}),
    setTimeout:fn=>timers.push(fn)});
  vm.runInContext(fs.readFileSync(require.resolve('./audio.js'),'utf8'), context);
  await new Promise(resolve=>setImmediate(resolve));
  await elements['audio-toggle'].onclick();
  await timers.shift()();
  assert.deepEqual(gains.map(n=>n.gain.value), [.25,.5]);
  assert.equal(sources[0].connections[0][0], splitter);
  info={...info, output_gain:[.1,.2]};
  await timers.shift()();
  assert.deepEqual(gains.map(n=>n.gain.value), [.1,.2]);
  info={...info, running:false};
  await timers.shift()();
  assert.equal(sources[0].stopped, true);
  assert.equal(elements['audio-status'].textContent, 'Player off');
});
