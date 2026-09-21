"""Local microphone comparison of resident Sherpa and Whisper; no DISC connection."""
import argparse
import asyncio
import base64
from dataclasses import asdict
import importlib.metadata
import json
from pathlib import Path
import platform
import secrets
import socket
import sys
import tempfile
import time

from aiohttp import ClientError, ClientSession, ClientTimeout, web
from experiments.disc_assistant.assistant.speech import SpeechContext, InvalidSpeech
from experiments.disc_assistant.assistant.voice.files import wav_audio, audio_details
from experiments.disc_assistant.assistant.voice.resident import WhisperServer
from experiments.disc_assistant.evaluation.sherpa_setup import MODEL_ID, REVISION, FILES, REPO, digest, outside_repo

STATIC = Path(__file__).with_name('speech_web_static')
CAPTURE = Path(__file__).parents[1] / 'assistant/web/static'
MAX_UPLOAD = 1024 * 1024  # 30 seconds of PCM16 mono at 16 kHz, plus WAV headers.
RUNTIME = web.AppKey('runtime', object)


async def stop_process(process):
    if process is not None and process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), 3)
        except TimeoutError:
            process.kill()
            await process.wait()


class Runtime:
    def __init__(self, args):
        self.args = args
        self.token = secrets.token_urlsafe(32)
        self.worker = self.whisper_process = self.active = self.temporary = None
        self.first = {'sherpa': True, 'whisper': True}
        self.sequence = 0
        self.metadata = {}

    async def start(self):
        root = outside_repo(self.args.root)
        binary = Path(self.args.whisper_binary).expanduser().resolve(strict=True)
        model = Path(self.args.whisper_model).expanduser().resolve(strict=True)
        self.metadata = {
            'platform': platform.platform(), 'machine': platform.machine(), 'threads': self.args.threads,
            'sherpa': {'engine': importlib.metadata.version('sherpa-onnx'), 'model': MODEL_ID,
                       'revision': REVISION, 'sha256': FILES, 'decoder': 'greedy_search', 'tail_padding_ms': 300},
            'whisper': {'binary_sha256': digest(binary), 'model': model.name, 'model_sha256': digest(model),
                        'decoder': 'beam_size=5, best_of=5, CPU, no fallback'},
            'timing': 'Sequential resident CPU inference including local transport; no model loading. First requests may be slower.',
        }
        try:
            started = time.perf_counter()
            self.worker = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'experiments.disc_assistant.evaluation.speech_web_worker',
                '--root', str(root), '--threads', str(self.args.threads), cwd=REPO,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=1024 * 1024)
            ready = await asyncio.wait_for(self.worker.stdout.readline(), 120)
            if not ready or json.loads(ready) != {'ready': True}:
                raise RuntimeError('Sherpa startup failed; verify the installed environment and model hashes')
            self.metadata['sherpa']['load_ms'] = round((time.perf_counter() - started) * 1000, 2)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            self.temporary = tempfile.TemporaryDirectory(prefix='disc-speech-lab-')
            started = time.perf_counter()
            self.whisper_process = await asyncio.create_subprocess_exec(
                str(binary), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
                '-t', str(self.args.threads), '-ng', '-nf', '-nlp', '--public', self.temporary.name,
                cwd=self.temporary.name, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            url = f'http://127.0.0.1:{port}'
            async with ClientSession(timeout=ClientTimeout(total=2), trust_env=False) as session:
                deadline = time.monotonic() + 120
                while True:
                    if self.whisper_process.returncode is not None:
                        raise RuntimeError('Owned Whisper server exited during startup')
                    try:
                        async with session.get(url + '/health') as response:
                            if response.status == 200:
                                break
                    except (ClientError, OSError, TimeoutError):
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Whisper startup timed out')
                    await asyncio.sleep(.2)
            self.metadata['whisper']['load_ms'] = round((time.perf_counter() - started) * 1000, 2)
            self.whisper = WhisperServer({'model': str(model), 'server_url': url + '/inference', 'timeout': 120})
            self.whisper.evidence()  # Hash before measuring requests.
        except BaseException:
            await self.close()
            raise

    async def close(self):
        if self.active and not self.active.done():
            self.active.cancel()
            await asyncio.gather(self.active, return_exceptions=True)
        await stop_process(self.worker)
        await stop_process(self.whisper_process)
        if self.temporary:
            self.temporary.cleanup()

    async def sherpa(self, audio):
        if self.worker.returncode is not None:
            raise RuntimeError('Sherpa worker stopped; restart the lab')
        try:
            payload = json.dumps({'audio': base64.b64encode(audio.data).decode()}).encode() + b'\n'
            self.worker.stdin.write(payload)
            await asyncio.wait_for(self.worker.stdin.drain(), 120)
            line = await asyncio.wait_for(self.worker.stdout.readline(), 120)
            result = json.loads(line)
            if not isinstance(result.get('text'), str):
                raise ValueError('invalid worker response')
            return result
        except BaseException:
            await stop_process(self.worker)
            raise

    async def compare(self, audio):
        details = audio_details(audio)
        self.sequence += 1
        order = ['sherpa', 'whisper'] if self.sequence % 2 else ['whisper', 'sherpa']
        results = {}
        for name in order:
            started = time.perf_counter()
            row = {'first_request': self.first[name]}
            self.first[name] = False
            try:
                if name == 'sherpa':
                    value = await self.sherpa(audio)
                else:
                    if self.whisper_process.returncode is not None:
                        raise RuntimeError('Whisper stopped; restart the lab')
                    try:
                        value = asdict(await self.whisper.transcribe(audio, SpeechContext('ru', 'speech-lab')))
                    except Exception:
                        # A timed-out HTTP request may still be running server-side.
                        # Stop only our server before accepting another comparison.
                        await stop_process(self.whisper_process)
                        raise
                row.update(status='ok', text=value['text'], no_speech=value['no_speech'])
            except Exception as exc:
                row.update(status='error', error=type(exc).__name__, text=None)
            row['stt_ms'] = round((time.perf_counter() - started) * 1000, 2)
            row['rtf'] = round(row['stt_ms'] / details['duration_ms'], 4)
            results[name] = row
        return {'version': 1, 'scope': 'transcription only; no accuracy labels or device execution',
                'audio': details, 'order': order, 'results': results, 'environment': self.metadata}


def create_app(runtime, port):
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}

    @web.middleware
    async def boundary(request, handler):
        if (request.host not in hosts or request.headers.get('Origin') not in (None, f'http://{request.host}')
                or request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none')):
            raise web.HTTPForbidden(text='Open the lab on localhost.')
        if request.method != 'GET' and not secrets.compare_digest(request.headers.get('X-Lab-Token', ''), runtime.token):
            raise web.HTTPForbidden(text='Reload the lab page.')
        response = await handler(request)
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        })
        return response

    app = web.Application(middlewares=[boundary], client_max_size=MAX_UPLOAD)
    app[RUNTIME] = runtime

    async def lifecycle(app):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()
    app.cleanup_ctx.append(lifecycle)

    async def state(request):
        return web.json_response({'token': runtime.token, 'environment': runtime.metadata,
                                  'busy': bool(runtime.active and not runtime.active.done())})

    async def compare(request):
        if request.content_type != 'audio/wav':
            raise web.HTTPUnsupportedMediaType(text='Use a PCM WAV file.')
        if runtime.active and not runtime.active.done():
            raise web.HTTPConflict(text='A comparison is already running. Wait before submitting again.')
        try:
            audio = wav_audio(await request.read())
        except InvalidSpeech as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        # Recheck after upload: two concurrent bodies must not queue inference.
        if runtime.active and not runtime.active.done():
            raise web.HTTPConflict(text='A comparison is already running.')
        task = asyncio.create_task(runtime.compare(audio))
        runtime.active = task
        def release(completed):
            if runtime.active is completed:
                runtime.active = None
            if not completed.cancelled():
                completed.exception()  # Retrieve errors even after a browser disconnect.
        task.add_done_callback(release)
        # A disconnected browser does not free the worker for overlapping requests.
        result = await asyncio.shield(task)
        return web.json_response(result)

    async def asset(request):
        name = request.match_info.get('name', 'index.html')
        if name in {'audio.js', 'capture.js'}:
            return web.FileResponse(CAPTURE / name)
        if name not in {'index.html', 'app.js', 'style.css'}:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC / name)

    app.router.add_get('/', asset)
    app.router.add_get('/static/{name}', asset)
    app.router.add_get('/api/state', state)
    app.router.add_post('/api/compare', compare)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='~/disc-speech/sherpa-onnx')
    parser.add_argument('--whisper-binary', default='~/disc-speech/whisper.cpp/build/bin/whisper-server')
    parser.add_argument('--whisper-model', default='~/disc-speech/ggml-small.bin')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--port', type=int, default=8091)
    args = parser.parse_args()
    if not 1 <= args.threads <= 16 or not 1024 <= args.port <= 65535:
        parser.error('use 1..16 threads and a port in 1024..65535')
    web.run_app(create_app(Runtime(args), args.port), host='127.0.0.1', port=args.port, access_log=None)


if __name__ == '__main__':
    main()
