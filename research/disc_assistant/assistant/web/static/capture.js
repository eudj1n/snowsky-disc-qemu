/* Capture at the actual AudioContext rate, with a hard frame limit. Output is silent. */
class DiscCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.remaining = Math.floor(sampleRate * options.processorOptions.maxSeconds);
    this.running = true;
    this.port.onmessage = () => this.finish();
  }
  finish() {
    if (!this.running) return;
    this.running = false;
    this.port.postMessage({done: true});
  }
  process(inputs) {
    if (!this.running) return false;
    const channels = inputs[0];
    if (!channels.length) return true;
    const count = Math.min(channels[0].length, this.remaining);
    const mono = new Float32Array(count);
    for (const channel of channels) for (let i = 0; i < count; i++) mono[i] += channel[i] / channels.length;
    this.port.postMessage({samples: mono}, [mono.buffer]);
    this.remaining -= count;
    if (this.remaining <= 0) this.finish();
    return this.running;
  }
}
registerProcessor('disc-capture', DiscCapture);
