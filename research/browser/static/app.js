import {WIDTH, bgrxToRgba} from './pixels.mjs';

const byId = id => document.getElementById(id);
const canvas = byId('screen');
const context = canvas.getContext('2d');
let worker = null, ready = false, pending = false, sequence = 0, frames = 0;
let started = 0, readyAt = 0, firstFrameAt = 0;
let metricTimer = null, tapTimer = null;

function setStatus(text) { byId('status').textContent = text; }
function log(text) {
    const el = byId('console');
    el.textContent = (el.textContent + text.replace(/\r/g, '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')).slice(-65536);
    el.scrollTop = el.scrollHeight;
}
function stop() {
    worker?.terminate(); worker = null; ready = false; pending = false;
    clearInterval(metricTimer); clearTimeout(tapTimer);
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
byId('start').addEventListener('click', () => {
    if (worker) return;
    sequence = frames = 0; readyAt = firstFrameAt = 0; started = performance.now();
    metricTimer = setInterval(updateMetrics, 1000);
    byId('console').textContent = '';
    setStatus('Booting Linux…'); byId('start').disabled = true; byId('stop').disabled = false;
    worker = new Worker('worker.js');
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
                if (data.value.tap === sequence) { pending = false; clearTimeout(tapTimer); }
                setStatus(data.value.ok === false ? 'Tap failed; see console' : 'Running · click the screen');
            } else if (data.value.state === 'failed') {
                ready = false; pending = false; canvas.classList.remove('ready');
                setStatus('Firmware stopped; see console');
            }
            updateMetrics();
        }
        if (data.type === 'error') { setStatus('VM error; see console'); log(data.message + '\n'); }
    };
    worker.onerror = event => { setStatus('VM error; see console'); log(event.message + '\n'); };
    worker.postMessage({type:'start'});
});
canvas.addEventListener('click', event => {
    if (!worker || !ready || pending) return;
    const r = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - r.left) * WIDTH / r.width);
    const y = Math.floor((event.clientY - r.top) * WIDTH / r.height);
    if (x < 0 || x >= WIDTH || y < 0 || y >= WIDTH) return;
    pending = true; sequence++; setStatus('Sending tap…');
    worker.postMessage({type:'tap', sequence, x, y});
    tapTimer = setTimeout(() => {
        if (pending) setStatus('Tap unconfirmed · stop and restart before retrying');
    }, 15000);
});
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
