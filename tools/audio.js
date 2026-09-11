/* Stream the guest's captured PCM with a small Web Audio scheduling buffer. */
(() => {
  const toggle = document.getElementById('audio-toggle');
  const replay = document.getElementById('audio-replay');
  const status = document.getElementById('audio-status');
  let context, enabled = false, generation = null, offset = 0, next = 0, epoch = 0;
  const sources = new Set();
  function clear() {
    epoch++;
    for (const source of sources) source.stop();
    sources.clear();
    next = 0;
  }
  async function enable() {
    context ||= new AudioContext();
    await context.resume();
    enabled = true;
    toggle.textContent = 'Mute sound';
  }
  toggle.onclick = async () => {
    if (enabled) {
      enabled = false;
      clear();
      toggle.textContent = 'Enable sound';
      status.textContent = 'Sound off';
    } else {
      try { await enable(); } catch (e) { status.textContent = e.message; }
    }
  };
  replay.onclick = async () => {
    clear();
    generation = null;
    offset = 0;
    try { await enable(); } catch (e) { status.textContent = e.message; }
  };
  async function poll() {
    if (!enabled) return;
    const ticket = epoch;
    const info = await (await fetch('/audio.json')).json();
    if (!enabled || ticket !== epoch) return;
    if (!info.generation) { status.textContent = 'Waiting for a track…'; return; }
    if (info.generation !== generation || info.bytes < offset) {
      clear();
      generation = info.generation;
      offset = 0;
    }
    const current = epoch;
    const buffered = Math.max(0, next - context.currentTime);
    status.textContent = `${info.rate / 1000} kHz · ${info.channels} ch · ${info.seconds.toFixed(1)} s captured`;
    if (buffered > 0.7 || info.bytes <= offset) return;
    const response = await fetch(`/audio.pcm?generation=${encodeURIComponent(generation)}&offset=${offset}`);
    if (!response.ok) return;
    const raw = await response.arrayBuffer();
    if (!enabled || current !== epoch || !raw.byteLength) return;
    const width = info.sample_bytes, channels = info.channels;
    const frames = raw.byteLength / (width * channels);
    const buffer = context.createBuffer(channels, frames, info.rate);
    const view = new DataView(raw);
    for (let c = 0; c < channels; c++) {
      const out = buffer.getChannelData(c);
      for (let i = 0; i < frames; i++) {
        const p = (i * channels + c) * width;
        if (width === 4) out[i] = view.getInt32(p, true) / 2147483648;
        else if (width === 3) out[i] = ((view.getUint8(p) | (view.getUint8(p+1)<<8) | (view.getInt8(p+2)<<16))) / 8388608;
        else if (width === 2) out[i] = view.getInt16(p, true) / 32768;
        else out[i] = view.getInt8(p) / 128;
      }
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    source.onended = () => sources.delete(source);
    sources.add(source);
    next = Math.max(next, context.currentTime + 0.08);
    source.start(next);
    next += frames / info.rate;
    offset += raw.byteLength;
  }
  async function loop() {
    try { await poll(); } catch (e) { if (enabled) status.textContent = `Audio: ${e.message}`; }
    setTimeout(loop, 150);
  }
  loop();
})();
