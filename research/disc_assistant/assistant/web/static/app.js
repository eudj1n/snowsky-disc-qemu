import {Recorder} from './audio.js';
const $ = id => document.getElementById(id);
let token, state = {}, localBusy = false, recorder = null, recording = false, stream = null, traces = [];
const notice = message => { $('notice').textContent = message; $('notice').hidden = !message; };
const badge = (id, text) => { $(id).textContent = text; $(id).dataset.state = text; };
const json = value => JSON.stringify(value, null, 2);

function controls() {
  const busy = localBusy || state.busy || !token;
  const locked = busy || !!recorder;
  document.querySelectorAll('[data-action], #locale, #mode, #text, #microphone, #refresh-mics').forEach(el => { el.disabled = locked; });
  $('send').disabled = locked || $('mode').value === 'transcribe';
  $('record').disabled = busy || (!!recorder && !recording);
  $('cancel').hidden = !recorder;
  badge('activity', busy ? 'busy' : recorder ? 'recording' : 'Ready');
}
function showState(value) {
  state = value;
  $('device').textContent = state.device?.key || '—';
  $('endpoint').textContent = state.device ? `${state.device.host} · TCP ${state.device.tcp_port}` : 'Service unavailable';
  badge('connection', state.session?.connection || 'unknown');
  const observation = state.session?.observation || {}, song = observation.state?.song || {};
  $('playback').textContent = observation.playback || 'unknown';
  $('song').textContent = song.song_name || 'No observed track'; $('artist').textContent = song.song_artist_name || '—';
  const seconds = Number.isFinite(observation.position_ms) ? Math.floor(observation.position_ms / 1000) : null;
  $('position').textContent = seconds === null ? '—' : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  if (state.locales && $('locale').options[0]?.value === 'Loading…') {
    $('locale').replaceChildren(...state.locales.map(locale => new Option(locale.native_name, locale.code)));
  }
  if (state.language) $('locale').value = state.language.locale;
  const library = state.library;
  $('catalog').textContent = library ? `${library.track_count || 0} tracks · index ${library.index_current ? 'current' : 'needs rebuilding'}` : 'Library status unavailable';
  controls();
}
function showResult(envelope) {
  const result = envelope.result;
  if (!result) return;
  badge('result-status', result.status || 'completed');
  $('reply').textContent = result.response?.text || result.reason || 'Request completed. Details below.';
  $('transcript').textContent = result.transcription?.text || '—';
  const selected = result.selected || result.candidates?.[0];
  $('selection').textContent = selected ? [selected.artist, selected.title || selected.album || selected.kind].filter(Boolean).join(' — ') : result.action || '—';
  $('timing').textContent = result.timing ? `${result.timing.total_ms.toFixed(0)} ms total${result.transcription ? ` · ${result.transcription.transcription_ms.toFixed(0)} ms STT` : ''}` : '—';
  $('json').textContent = json(result);
}
async function send(url, body, type = 'application/json') {
  if (localBusy || state.busy) return;
  localBusy = true; traces = []; $('trace').textContent = 'Processing…'; notice(''); controls();
  try {
    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': type, 'X-Disc-Token': token}, body});
    if (!response.ok) throw new Error(await response.text());
    showResult(await response.json());
  } catch (error) {
    notice(`${error.message} Request was not retried. Check the last result and player state before sending again.`);
  } finally { localBusy = false; controls(); }
}
$('command-form').onsubmit = event => {
  event.preventDefault();
  const text = $('text').value.trim();
  if (text) send('/api/command', json({text, mode: $('mode').value}));
};
document.querySelectorAll('[data-action]').forEach(button => {
  button.onclick = () => send('/api/command', json({action: button.dataset.action}));
});
$('locale').onchange = () => send('/api/command', json({action: 'language', locale: $('locale').value}));
$('mode').onchange = () => {
  $('mode-hint').textContent = ({preview: 'Preview does not change playback or language.', execute: 'Each submitted command will be executed on the selected player.', transcribe: 'Recognize speech only. No interpretation or playback.'})[$('mode').value];
  controls();
};
async function microphones() {
  const old = $('microphone').value;
  const devices = await navigator.mediaDevices.enumerateDevices();
  $('microphone').replaceChildren(new Option('Default microphone', ''), ...devices.filter(d => d.kind === 'audioinput' && d.deviceId).map((d, i) => new Option(d.label || `Microphone ${i + 1}`, d.deviceId)));
  if ([...$('microphone').options].some(o => o.value === old)) $('microphone').value = old;
}
$('refresh-mics').onclick = async () => {
  localBusy = true; controls(); notice('');
  try {
    const permission = await navigator.mediaDevices.getUserMedia({audio: true});
    permission.getTracks().forEach(track => track.stop()); await microphones();
  } catch (error) { notice(`Microphone unavailable: ${error.message}`); }
  finally { localBusy = false; controls(); }
};
function resetRecording() {
  recorder = null; recording = false;
  $('record').innerHTML = '<span aria-hidden="true">●</span> Record command';
  $('record').classList.remove('is-recording'); $('record').setAttribute('aria-label', 'Start recording');
  $('level').value = 0; $('record-status').textContent = 'Microphone off · click Record to begin'; controls();
}
async function finishRecording() {
  if (!recorder || !recording) return;
  const current = recorder, mode = $('mode').value;
  recording = false; controls();
  try {
    const audio = await current.stop();
    if (current.cancelled) return;
    resetRecording();
    await send(`/api/audio?mode=${mode}`, audio, 'audio/wav');
  } catch (error) { notice(error.message); }
  finally { if (recorder === current) resetRecording(); }
}
$('record').onclick = async () => {
  if (recording) { await finishRecording(); return; }
  notice(''); const current = new Recorder(); recorder = current; controls();
  $('record-status').textContent = 'Waiting for microphone permission…';
  try {
    await current.start($('microphone').value, state.max_seconds || 30, (level, seconds) => {
      $('level').value = level; $('record-status').textContent = `Recording ${seconds.toFixed(1)} s · stop to submit · maximum ${state.max_seconds || 30} s`;
    }, finishRecording);
    if (current.cancelled) return;
    recording = true; $('record').textContent = '■ Stop & submit'; $('record').classList.add('is-recording');
    $('record').setAttribute('aria-label', 'Stop recording and submit'); controls();
    await microphones();
  } catch (error) { current.cancel(); if (recorder === current) resetRecording(); notice(`Microphone unavailable: ${error.message}`); }
};
$('cancel').onclick = () => { recorder?.cancel(); resetRecording(); };
addEventListener('pagehide', () => { recorder?.cancel(); stream?.close(); });
async function initialize() {
  try {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error('Assistant service unavailable.');
    const value = await response.json(); token = value.token; showState(value);
    if (value.last_result) showResult(value.last_result);
    stream = new EventSource('/api/events');
    stream.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.type === 'state') showState(message.data);
      if (message.type === 'result') showResult(message.data);
      if (message.type === 'trace') {
        traces.push(message.data); if (traces.length > 128) traces.shift();
        $('trace').textContent = traces.map(e => `${e.elapsed_ms} ms · ${e.phase}\n${json(e.payload)}`).join('\n\n');
      }
    };
    stream.onerror = () => { badge('connection', 'web disconnected'); token = null; controls(); };
    stream.onopen = async () => {
      // Refresh the token after a server restart; never resubmit a command.
      try { const response = await fetch('/api/state'); if (!response.ok) return;
        const fresh = await response.json(); token = fresh.token; showState(fresh);
        if (fresh.last_result) showResult(fresh.last_result);
      } catch { /* EventSource reconnects observation only. */ }
    };
  } catch (error) { notice(error.message); }
}
controls(); initialize();
