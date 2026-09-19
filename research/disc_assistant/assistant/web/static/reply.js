// Speech delivery is independent of command execution. Never resubmit a command.
export class ReplyPlayer {
  constructor({token, status, fetcher = (...args) => fetch(...args), context = () => new AudioContext()}) {
    Object.assign(this, {token, status, fetcher, context});
    this.enabled = false;
    this.generation = 0;
  }
  async enable(enabled) {
    this.stop();
    this.enabled = enabled;
    if (!enabled) { this.status('Spoken replies off'); return; }
    try {
      this.audio ||= this.context();
      await this.audio.resume(); // Called directly from a user gesture.
      this.status('Spoken replies enabled');
    } catch { this.enabled = false; this.status('Audio unavailable in this browser'); }
  }
  report(id, outcome) {
    this.fetcher(`/api/reply-status?request_id=${encodeURIComponent(id)}&outcome=${outcome}`,
      {method: 'POST', headers: {'X-Disc-Token': this.token()}}).catch(() => {});
  }
  stop() {
    this.generation++;
    this.abort?.abort(); this.abort = null;
    if (this.source) {
      this.source.onended = null;
      this.source.stop(); this.source.disconnect(); this.source = null;
      this.report(this.requestId, 'cancelled');
    }
  }
  async play(result) {
    this.stop();
    if (!this.enabled || !result.response?.speak || !result.response?.text) return;
    const generation = this.generation, id = result.request_id;
    this.abort = new AbortController();
    this.status('Preparing spoken reply…');
    try {
      const response = await this.fetcher(`/api/reply?request_id=${encodeURIComponent(id)}`,
        {method: 'POST', headers: {'X-Disc-Token': this.token()}, signal: this.abort.signal});
      if (!response.ok) throw new Error(await response.text());
      const buffer = await this.audio.decodeAudioData(await response.arrayBuffer());
      if (generation !== this.generation || !this.enabled) return;
      if (this.audio.state !== 'running') {
        this.report(id, 'blocked');
        this.status('Browser blocked audio. Enable spoken replies again before the next command.');
        return;
      }
      const source = this.audio.createBufferSource();
      source.buffer = buffer; source.connect(this.audio.destination);
      this.source = source; this.requestId = id;
      source.onended = () => {
        if (generation !== this.generation) return;
        source.disconnect(); this.source = null;
        this.report(id, 'played'); this.status('Reply played');
      };
      source.start(); this.status('Speaking…');
    } catch (error) {
      if (generation !== this.generation || error.name === 'AbortError') return;
      this.report(id, 'failed');
      this.status('Spoken reply unavailable. The command result is unchanged.');
    }
  }
  close() { this.stop(); this.audio?.close(); }
}
