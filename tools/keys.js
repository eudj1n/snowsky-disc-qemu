/* Physical gestures are classified here; their assignments remain in stock firmware. */
class PhysicalButton {
  constructor(name, send, timers = {set: (fn, ms) => setTimeout(fn, ms), clear: id => clearTimeout(id)}) {
    this.name = name; this.send = send; this.timers = timers;
    this.down = false; this.held = false; this.pending = false;
  }
  clear(which) { this.timers.clear(this[which]); this[which] = null; }
  press() {
    if (this.down) return;
    this.down = true; this.held = false;
    this.clear('clickTimer');
    this.holdTimer = this.timers.set(() => {
      this.held = true; this.pending = false;
      this.send(this.name, 'hold');
      if (this.name.startsWith('volume_')) this.repeat();
    }, this.name === 'power' ? 1800 : 650);
  }
  repeat() {
    this.repeatTimer = this.timers.set(() => {
      if (!this.down) return;
      this.send(this.name, 'hold'); this.repeat();
    }, 200);
  }
  release() {
    if (!this.down) return;
    this.down = false;
    this.clear('holdTimer'); this.clear('repeatTimer');
    if (this.held) { this.send(this.name, 'end'); return; }
    if (this.name === 'power') { this.send(this.name, 'single'); return; }
    if (this.pending) {
      this.pending = false; this.send(this.name, 'double');
    } else {
      this.pending = true;
      this.clickTimer = this.timers.set(() => {
        this.pending = false; this.send(this.name, 'single');
      }, 280);
    }
  }
  cancel() {
    this.clear('holdTimer'); this.clear('repeatTimer'); this.clear('clickTimer');
    this.down = this.pending = false;
    if (this.held) this.send(this.name, 'cancel');
    this.held = false;
  }
}

if (typeof module !== 'undefined') module.exports = {PhysicalButton};
if (typeof document !== 'undefined') {
  const message = document.getElementById('key-status');
  const action = document.getElementById('key-action');
  let queue = Promise.resolve();
  const send = (name, gesture) => {
    queue = queue.then(async () => {
      const response = await fetch('/button', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, gesture})});
      if (!response.ok) throw new Error(await response.text());
      if (!['end', 'cancel'].includes(gesture)) action.textContent = `${name.replaceAll('_', ' ')} · ${gesture}`;
    }).catch(error => { action.textContent = error.message; });
  };
  const controls = [];
  document.querySelectorAll('[data-key]').forEach(button => {
    const control = new PhysicalButton(button.dataset.key, send);
    let lastPhysicalEvent = -Infinity;
    controls.push(control);
    button.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      lastPhysicalEvent = performance.now();
      event.preventDefault(); button.focus();
      button.setPointerCapture(event.pointerId); control.press();
    });
    button.addEventListener('pointerup', () => {
      lastPhysicalEvent = performance.now(); control.release();
    });
    button.addEventListener('pointercancel', () => control.cancel());
    button.addEventListener('lostpointercapture', () => { if (control.down) control.cancel(); });
    button.addEventListener('keydown', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault(); if (!event.repeat) control.press();
      }
    });
    button.addEventListener('keyup', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        lastPhysicalEvent = performance.now(); event.preventDefault(); control.release();
      }
    });
    button.addEventListener('blur', () => control.cancel());
    button.addEventListener('click', event => {
      // Assistive technology / click-only clients; don't duplicate a physical release.
      if (performance.now() - lastPhysicalEvent > 500) { control.press(); control.release(); }
    });
  });
  const cancel = () => controls.forEach(control => control.cancel());
  window.addEventListener('blur', cancel);
  document.addEventListener('visibilitychange', () => { if (document.hidden) cancel(); });
  async function status() {
    try {
      const response = await fetch('/device.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('Device status unavailable');
      const state = await response.json();
      message.textContent = state.error || (state.transition === 'starting' ? 'Starting player… (~30 seconds)'
        : state.transition === 'stopping' ? 'Stopping player…'
        : !state.running ? 'Player off — press Power to start'
        : !state.screen_on ? 'Screen locked — press Power to wake' : 'Player on');
      document.querySelectorAll('[data-key]').forEach(button => {
        button.disabled = Boolean(state.transition) || (!state.running && button.dataset.key !== 'power');
      });
    } catch (error) { message.textContent = error.message; }
    setTimeout(status, 1000);
  }
  status();
}
