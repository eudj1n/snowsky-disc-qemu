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
    let pointer = null;
    const press = () => { control.press(); button.classList.add('is-pressed'); };
    const release = () => { control.release(); button.classList.remove('is-pressed'); };
    const cancel = () => { pointer = null; control.cancel(); button.classList.remove('is-pressed'); };
    let lastPhysicalEvent = -Infinity;
    controls.push({button, cancel});
    button.addEventListener('pointerdown', event => {
      if (event.button !== 0 || button.disabled || control.down) return;
      lastPhysicalEvent = performance.now();
      event.preventDefault(); button.focus();
      pointer = event.pointerId;
      button.setPointerCapture(event.pointerId); press();
    });
    button.addEventListener('pointerup', event => {
      if (event.pointerId !== pointer) return;
      pointer = null;
      lastPhysicalEvent = performance.now(); release();
    });
    button.addEventListener('pointercancel', cancel);
    button.addEventListener('lostpointercapture', () => { if (control.down) cancel(); });
    button.addEventListener('keydown', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault(); if (!event.repeat && !button.disabled) press();
      }
    });
    button.addEventListener('keyup', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        lastPhysicalEvent = performance.now(); event.preventDefault(); release();
      }
    });
    button.addEventListener('blur', cancel);
    button.addEventListener('click', event => {
      // Assistive technology / click-only clients; don't duplicate a physical release.
      if (!button.disabled && performance.now() - lastPhysicalEvent > 500) { press(); release(); }
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
      controls.forEach(({button, cancel}) => {
        button.disabled = Boolean(state.transition) || (!state.running && button.dataset.key !== 'power');
        if (button.disabled) cancel();
      });
    } catch (error) { message.textContent = error.message; }
    setTimeout(status, 1000);
  }
  status();
}
