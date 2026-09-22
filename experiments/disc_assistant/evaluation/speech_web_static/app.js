import {Recorder} from '/static/audio.js';

const $ = id => document.getElementById(id);
let token, recorder = null, recording = false, busy = false, audio = null, audioUrl, reportUrl;
function notice(text = '') { $('notice').textContent = text; $('notice').hidden = !text; }
function controls() {
  $('record').disabled = !token || busy || (!!recorder && !recording);
  $('record').textContent = recording ? '■ Завершить запись' : '● Записать фразу';
  $('cancel').hidden = !recorder;
  for (const id of ['devices', 'microphone', 'file']) $(id).disabled = busy || !!recorder;
  $('compare').disabled = !audio || busy || !!recorder || !token;
}
function resetResults() {
  if (reportUrl) URL.revokeObjectURL(reportUrl);
  reportUrl = null; $('download-report').hidden = true;
  for (const name of ['sherpa', 'whisper']) {
    $(name + '-text').textContent = 'Здесь появится расшифровка';
    $(name + '-time').textContent = '—'; $(name + '-meta').textContent = 'Готово к сравнению';
  }
}
function setAudio(blob, name) {
  $('playback').pause();
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audio = blob; audioUrl = URL.createObjectURL(blob);
  $('playback').src = audioUrl; $('download-wav').href = audioUrl;
  $('file-name').textContent = name; $('recording').hidden = false;
  $('comparison-status').textContent = 'Прослушайте запись и нажмите «Сравнить модели».';
  resetResults(); controls();
}
async function listDevices() {
  const previous = $('microphone').value;
  const devices = await navigator.mediaDevices.enumerateDevices();
  $('microphone').replaceChildren(new Option('По умолчанию', ''), ...devices.filter(d => d.kind === 'audioinput' && d.deviceId).map((d, i) => new Option(d.label || `Микрофон ${i + 1}`, d.deviceId)));
  if ([...$('microphone').options].some(o => o.value === previous)) $('microphone').value = previous;
}
$('devices').onclick = async () => {
  notice();
  try {
    const permission = await navigator.mediaDevices.getUserMedia({audio: true});
    permission.getTracks().forEach(t => t.stop()); await listDevices();
  } catch (error) { notice('Нет доступа к микрофону: ' + error.message); }
};
async function stopRecording() {
  if (!recorder || !recording) return;
  const current = recorder; recording = false; controls();
  try {
    const blob = await current.stop();
    if (recorder !== current) return;
    setAudio(blob, 'Запись с микрофона');
    $('record-status').textContent = 'Запись готова';
  } catch (error) { if (recorder === current) notice(error.message); }
  finally { if (recorder === current) recorder = null; $('level').value = 0; controls(); }
}
$('record').onclick = async () => {
  if (recording) return stopRecording();
  notice(); $('playback').pause();
  const current = new Recorder(); recorder = current; controls();
  try {
    await current.start($('microphone').value, 30, (level, seconds) => {
      $('level').value = level; $('record-status').textContent = `${seconds.toFixed(1)} / 30 с`;
    }, stopRecording);
    if (recorder !== current) return;
    recording = true; $('record-status').textContent = 'Говорите…'; controls();
  } catch (error) {
    current.cancel(); if (recorder === current) recorder = null;
    notice('Не удалось начать запись: ' + error.message); controls();
  }
};
$('cancel').onclick = () => {
  recorder?.cancel(); recorder = null; recording = false; $('level').value = 0;
  $('record-status').textContent = 'Запись отменена'; controls();
};
$('file').onchange = () => {
  notice(); const file = $('file').files[0]; if (!file) return;
  if (file.size > 1024 * 1024) { notice('Выберите WAV до 30 секунд: PCM 16 бит, моно, 16 кГц.'); return; }
  setAudio(file, file.name);
};
$('compare').onclick = async () => {
  if (!audio || busy) return;
  busy = true; notice(); resetResults(); controls(); $('playback').pause();
  $('comparison-status').textContent = 'Обрабатываем одну запись двумя моделями…';
  for (const name of ['sherpa', 'whisper']) $(name + '-text').textContent = 'Распознавание…';
  try {
    const response = await fetch('/api/compare', {method: 'POST', headers: {'Content-Type': 'audio/wav', 'X-Lab-Token': token}, body: audio});
    if (!response.ok) throw new Error(await response.text());
    const report = await response.json();
    for (const name of ['sherpa', 'whisper']) {
      const row = report.results[name];
      $(name + '-text').textContent = row.status === 'ok' ? (row.text || 'Речь не распознана') : `Ошибка: ${row.error}. Перезапустите стенд, если ошибка повторяется.`;
      $(name + '-time').textContent = row.status === 'ok' ? `${(row.stt_ms / 1000).toFixed(3)} с` : 'ошибка';
      $(name + '-meta').textContent = `${row.first_request ? 'Первый запрос · ' : ''}RTF ${row.rtf.toFixed(3)} · ${row.status === 'ok' ? 'готово' : 'сбой'}`;
    }
    reportUrl = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
    $('download-report').href = reportUrl; $('download-report').hidden = false;
    $('comparison-status').textContent = `Аудио ${(report.audio.duration_ms / 1000).toFixed(2)} с · порядок: ${report.order.join(' → ')}${report.audio.digital_silence ? ' · цифровая тишина' : ''}`;
  } catch (error) {
    notice(error.message); $('comparison-status').textContent = 'Сравнение не завершено. Автоматического повтора нет.';
    for (const name of ['sherpa', 'whisper']) $(name + '-text').textContent = 'Нет результата';
  } finally { busy = false; controls(); }
};
window.addEventListener('pagehide', () => { recorder?.cancel(); if (audioUrl) URL.revokeObjectURL(audioUrl); if (reportUrl) URL.revokeObjectURL(reportUrl); });
try {
  const response = await fetch('/api/state');
  if (!response.ok) throw new Error(await response.text());
  const state = await response.json(); token = state.token;
  $('whisper-model').textContent = state.environment.whisper.model;
  $('environment').textContent = JSON.stringify(state.environment, null, 2);
  $('record-status').textContent = 'Микрофон выключен'; controls();
} catch (error) { notice('Стенд недоступен: ' + error.message); }
