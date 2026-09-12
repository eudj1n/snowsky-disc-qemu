/* Peripheral controls and display backlight follow device SSE snapshots. */
if (typeof document !== 'undefined') (() => {
  const byId = id => document.getElementById(id);
  const error = text => { byId('control-error').textContent = text; };
  const post = async (path, body) => {
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  };
  let state = {}, online = false, peripheralBusy = false;
  function render() {
    const busy = !online || peripheralBusy || Boolean(state.transition || state.peripheral_transition);
    if (state.brightness != null) {
      const brightness = Math.max(1, Math.min(40, state.brightness));
      byId('scr').style.filter = `brightness(${.2 + .8 * brightness / 40})`;
    }
    const sd = byId('sd-toggle'), usb = byId('usb-toggle');
    sd.disabled = busy || !state.sd_available;
    usb.disabled = busy;
    sd.classList.toggle('is-ejected', !state.sd_inserted);
    sd.setAttribute('aria-pressed', String(Boolean(state.sd_inserted)));
    const sdLabel = state.sd_inserted ? 'Eject SD card' : 'Insert SD card';
    sd.setAttribute('aria-label', sdLabel); sd.querySelector('.key-label').textContent = sdLabel;
    usb.classList.toggle('is-connected', Boolean(state.usb_connected));
    usb.setAttribute('aria-pressed', String(Boolean(state.usb_connected)));
    const usbLabel = state.usb_connected ? 'Disconnect USB · charging' : 'Connect USB charging cable';
    usb.setAttribute('aria-label', usbLabel); usb.querySelector('.key-label').textContent = usbLabel;
  }
  async function peripheral(body) {
    if (peripheralBusy) return;
    peripheralBusy = true; render();
    try {
      state = await post('/peripheral', body);
      error('');
    } catch (reason) { error(reason.message); }
    finally { peripheralBusy = false; render(); }
  }
  byId('sd-toggle').onclick = () => peripheral({name:'sd', inserted:!state.sd_inserted});
  byId('usb-toggle').onclick = () => peripheral({name:'usb', connected:!state.usb_connected});
  window.viewerControls = {
    update(value) { state = value; online = true; render(); },
    unavailable() { online = false; render(); },
    error
  };
  render();
})();
