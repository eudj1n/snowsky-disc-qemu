export function encodeWav(samples) {
  const bytes = new ArrayBuffer(44 + samples.length * 2), view = new DataView(bytes);
  const label = (offset, text) => [...text].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
  label(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); label(8, 'WAVE');
  label(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  label(36, 'data'); view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => {
    const value = Math.max(-1, Math.min(1, sample));
    view.setInt16(44 + i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
  });
  return new Blob([bytes], {type: 'audio/wav'});
}

export class Recorder {
  constructor() { this.cancelled = false; this.chunks = []; this.frames = 0; }
  async start(deviceId, maxSeconds, onLevel, onLimit) {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      throw new Error('Microphone capture needs a supported browser on localhost or HTTPS.');
    }
    this.stream = await navigator.mediaDevices.getUserMedia({audio: {
      ...(deviceId ? {deviceId: {exact: deviceId}} : {}), channelCount: 1,
      echoCancellation: false, noiseSuppression: false, autoGainControl: false
    }});
    if (this.cancelled) { this.close(); return; }
    this.context = new AudioContext();
    await this.context.audioWorklet.addModule('/static/capture.js');
    if (this.cancelled) { this.close(); return; }
    this.node = new AudioWorkletNode(this.context, 'disc-capture', {processorOptions: {maxSeconds}});
    this.done = new Promise(resolve => { this.resolve = resolve; });
    const rate = this.context.sampleRate;
    this.node.port.onmessage = ({data}) => {
      if (this.cancelled) return;
      if (data.done) { this.resolve(); if (!this.stopping) onLimit(); return; }
      if (data.samples) {
        this.chunks.push(data.samples); this.frames += data.samples.length;
        if (this.frames % 2048 < data.samples.length) {
          let sum = 0; for (const value of data.samples) sum += value * value;
          onLevel(Math.min(1, Math.sqrt(sum / data.samples.length) * 5), this.frames / rate);
        }
      }
    };
    this.source = this.context.createMediaStreamSource(this.stream);
    this.source.connect(this.node); this.node.connect(this.context.destination);
    await this.context.resume();
    if (!this.cancelled) this.watchdog = setTimeout(onLimit, maxSeconds * 1000 + 500);
  }
  close() {
    clearTimeout(this.watchdog);
    this.stream?.getTracks().forEach(track => track.stop());
    this.source?.disconnect(); this.node?.disconnect();
    if (this.context && this.context.state !== 'closed') this.context.close().catch(() => {});
  }
  cancel() { this.cancelled = true; this.resolve?.(); this.close(); this.chunks = []; }
  async stop() {
    this.stopping = true;
    this.node.port.postMessage('stop');
    let timer;
    try {
      await Promise.race([this.done, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Audio capture stopped responding. Recording discarded.')), 3000);
      })]);
      if (this.cancelled || !this.frames) throw new Error('No audio was recorded.');
      const rate = this.context.sampleRate;
      const pcm = new Float32Array(this.frames); let offset = 0;
      for (const chunk of this.chunks) { pcm.set(chunk, offset); offset += chunk.length; }
      this.close(); this.chunks = [];
      // Browser-native resampling applies filtering before conversion to 16 kHz PCM.
      const offline = new OfflineAudioContext(1, Math.max(1, Math.floor(this.frames * 16000 / rate)), 16000);
      const buffer = offline.createBuffer(1, pcm.length, rate); buffer.copyToChannel(pcm, 0);
      const source = offline.createBufferSource(); source.buffer = buffer; source.connect(offline.destination); source.start();
      const rendered = await offline.startRendering();
      return encodeWav(rendered.getChannelData(0));
    } finally { clearTimeout(timer); this.close(); }
  }
}
