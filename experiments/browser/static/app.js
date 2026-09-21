import {bindPower} from './power.mjs';
import {bindGestures} from './gestures.mjs';
import {WIDTH, bgrxToRgba} from './pixels.mjs';

const byId = id => document.getElementById(id);
const canvas = byId('screen');
const context = canvas.getContext('2d');
let worker = null, ready = false, pending = false, sequence = 0, frames = 0;
let screenOn = null, failed = false;
let started = 0, readyAt = 0, firstFrameAt = 0;
let metricTimer = null, inputTimer = null;

function setStatus(text) { byId('status').textContent = text; }
function updateControls() {
    byId('back').disabled = !ready || pending || screenOn === false;
    const label = !worker ? 'Start player' : failed ? 'Restart player' : !ready ? 'Starting · hold to stop'
        : pending ? 'Input pending · hold to stop' : screenOn === false ? 'Wakeup' : 'Lock screen';
    byId('power-label').textContent = label;
    byId('power').setAttribute('aria-label', label);
    byId('power').title = label.includes('hold') ? label : `${label} · hold to stop the VM`;
    // Keep local Stop available even while booting or awaiting a guest acknowledgement.
    byId('power').disabled = false;
    canvas.classList.toggle('asleep', screenOn === false);
    canvas.classList.toggle('ready', ready && screenOn !== false);
}
function runningStatus() {
    return screenOn === false ? 'Screen asleep · press Power to wake' : 'Running · tap or drag the screen';
}
function log(text) {
    const el = byId('console');
    el.textContent = (el.textContent + text.replace(/\r/g, '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')).slice(-65536);
    el.scrollTop = el.scrollHeight;
}
function stop() {
    cancelGesture(); screenOn = null; failed = false;
    worker?.terminate(); worker = null; ready = false; pending = false;
    clearInterval(metricTimer); clearTimeout(inputTimer); updateControls();
    canvas.classList.remove('ready'); context.clearRect(0, 0, WIDTH, WIDTH);
    byId('start').disabled = false; byId('stop').disabled = true;
    byId('save').disabled = true; byId('send').disabled = true;
    setStatus('Stopped');
}
function updateMetrics() {
    const seconds = ((performance.now() - started) / 1000).toFixed(1);
    const boot = readyAt ? ` · inputs ready in ${((readyAt - started) / 1000).toFixed(1)} s` : '';
    byId('metrics').textContent = `${seconds} s elapsed · ${frames} frames${boot} · 512 MiB guest RAM`;
}
function start() {
    if (worker) return;
    sequence = frames = 0; readyAt = firstFrameAt = 0; started = performance.now();
    metricTimer = setInterval(updateMetrics, 1000);
    byId('console').textContent = '';
    setStatus('Booting Linux…'); byId('start').disabled = true; byId('stop').disabled = false;
    worker = new Worker('worker.js');
    failed = false; updateControls();
    const current = worker;
    worker.onmessage = ({data}) => {
        if (worker !== current) return;
        if (data.type === 'console') log(data.text);
        if (data.type === 'boot') { setStatus('Starting DISC…'); byId('send').disabled = false; }
        if (data.type === 'frame') {
            context.putImageData(new ImageData(bgrxToRgba(data.buffer), WIDTH, WIDTH), 0, 0);
            frames++; if (!firstFrameAt) firstFrameAt = performance.now();
            byId('save').disabled = false; updateMetrics();
        }
        if (data.type === 'status') {
            if (data.value.state === 'ready') {
                ready = true; if (!readyAt) readyAt = performance.now();
                canvas.classList.add('ready');
                if (data.value.sequence === sequence) { pending = false; clearTimeout(inputTimer); }
                updateControls();
                setStatus(data.value.ok === false ? 'Input failed; see console' : runningStatus());
            } else if (data.value.state === 'screen') {
                screenOn = data.value.screenOn;
                if (screenOn === false) cancelGesture();
                updateControls();
                if (ready && !pending) setStatus(runningStatus());
            } else if (data.value.state === 'failed') {
                failed = true; ready = false; pending = false; cancelGesture(); clearTimeout(inputTimer);
                updateControls();
                setStatus('Firmware stopped · press Power to restart');
            }
            updateMetrics();
        }
        if (data.type === 'error') vmError(data.message);
    };
    worker.onerror = event => { if (worker === current) vmError(event.message); };
    worker.postMessage({type:'start'});
}
function vmError(message) {
    failed = true; ready = false; pending = false; cancelGesture(); clearTimeout(inputTimer);
    updateControls(); setStatus('VM error · press Power to restart; see console'); log(message + '\n');
}
byId('start').addEventListener('click', start);
function sendGesture(gesture) {
    if (!worker || !ready || pending || (screenOn === false && gesture.kind !== 'power')) return;
    pending = true; sequence++; updateControls();
    setStatus(`Sending ${gesture.kind}…`);
    worker.postMessage({type:'gesture', sequence, ...gesture});
    inputTimer = setTimeout(() => {
        if (pending) setStatus('Input unconfirmed · stop and restart before retrying');
    }, 15000);
}
const cancelGesture = bindGestures(canvas, () => worker && ready && !pending && screenOn !== false, sendGesture);
byId('back').addEventListener('click', () =>
    sendGesture({kind:'swipe', x0:18, y0:180, x1:320, y1:180}));
bindPower(byId('power'), () => {
    if (failed) stop();
    if (!worker) start();
    else sendGesture({kind:'power', x0:0, y0:0, x1:0, y1:0});
}, () => { if (worker) stop(); });
byId('stop').addEventListener('click', stop);
byId('save').addEventListener('click', () => {
    canvas.toBlob(blob => {
        const url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = 'disc-browser.png'; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
});
byId('command-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!worker) return;
    worker.postMessage({type:'console', text:byId('command').value + '\n'});
    byId('command').value = '';
});
window.addEventListener('pagehide', stop);

updateControls();
