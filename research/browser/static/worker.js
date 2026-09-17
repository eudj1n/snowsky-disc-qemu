/* TinyEMU executes on this worker, including Linux and both firmware processes. */
var net_state = null;
var graphic_display = null;
let consoleTail = '', entropySent = false;
function importBytes(name, bytes) {
    const ptr = Module._malloc(bytes.length);
    Module.HEAPU8.set(bytes, ptr);
    Module.ccall('fs_import_file', null, ['string','number','number'], [name, ptr, bytes.length]);
}
var term = {
    write: text => {
        postMessage({type:'console', text});
        consoleTail = (consoleTail + text).slice(-512);
        if (!entropySent && consoleTail.includes('BROWSER_DISC: exchange ready')) {
            entropySent = true;
            // Schedule after the current WASM callback; avoid re-entering its allocator.
            setTimeout(() => importBytes('entropy', crypto.getRandomValues(new Uint8Array(64))), 0);
        }
    },
    getSize: () => [100, 30],
};
function update_downloading() {}
function discExport(name, bytes) {
    if (name === 'frame.bgrx') {
        const buffer = bytes.slice().buffer;
        postMessage({type:'frame', buffer}, [buffer]);
    } else if (name === 'status.json') {
        try { postMessage({type:'status', value:JSON.parse(new TextDecoder().decode(bytes))}); }
        catch (error) { postMessage({type:'error', message:String(error)}); }
    }
}
var Module = {
    print: text => term.write(text + '\n'),
    printErr: text => term.write(text + '\n'),
    onAbort: reason => postMessage({type:'error', message:String(reason)}),
    preRun: [function () {
        Module.ccall('vm_start', null,
            ['string','number','string','string','number','number','number','string'],
            [new URL('disc.cfg', self.location.href).href, 512, '', null, 0, 0, 0, '']);
        postMessage({type:'boot'});
    }],
};
let loaded = false;
self.onmessage = ({data}) => {
    if (data.type === 'start' && !loaded) {
        loaded = true;
        importScripts('riscvemu64-wasm.js');
    } else if (data.type === 'console' && loaded) {
        for (const c of data.text) Module.ccall('console_queue_char', null, ['number'], [c.charCodeAt(0)]);
    } else if (data.type === 'tap' && loaded) {
        if (![data.x, data.y, data.sequence].every(Number.isInteger) ||
            data.x < 0 || data.x >= 360 || data.y < 0 || data.y >= 360 || data.sequence < 1) return;
        const bytes = new TextEncoder().encode(`${data.x} ${data.y}\n`);
        // fs_import_file owns/frees this allocation; the import stays inside WASM.
        importBytes(`tap-${data.sequence}`, bytes);
    }
};
