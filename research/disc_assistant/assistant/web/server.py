"""Loopback web adapter with one application owner and bounded, serialized work."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import replace
import json
from pathlib import Path
import secrets

from aiohttp import web

from research.disc_assistant.assistant.application import Application
from research.disc_assistant.assistant.responses import exception_result, validate_locales
from research.disc_assistant.assistant.voice.files import MAX_BYTES
from research.disc_assistant.assistant.voice.replies import ReplySynthesizer, delivery_event

STATIC = Path(__file__).with_name('static')
ACTIONS = {'connect', 'disconnect', 'sync', 'index', 'queue', 'language', 'response'}
RUNTIME = web.AppKey('runtime', object)


class Runtime:
    def __init__(self, config, *, factory=Application, language=None, bootstrap=False, synthesizer=None):
        self.config, self.factory = config, factory
        self.language, self.bootstrap = language, bootstrap
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='disc-web')
        self.busy = False
        self.listeners = set()
        self.snapshot = {}
        self.last_result = None
        self.token = secrets.token_urlsafe(32)
        self.poller = None
        self.active = None
        self.service = None
        self.synthesizer = synthesizer or ReplySynthesizer()
        self.reply_busy = False
        self.reply_id = None

    def publish(self, kind, value):
        event = {'type': kind, 'data': value}
        for queue in tuple(self.listeners):
            if queue.full():
                queue.get_nowait()  # Debug consumers must never block device work.
            queue.put_nowait(event)

    def open(self):
        self.service = self.factory(self.config, source='web', language=self.language,
                                    debug=True, debug_output=lambda event:
                                    self.loop.call_soon_threadsafe(self.publish, 'trace', event))
        self.service.__enter__()
        try:
            if self.bootstrap:
                self.service.session.wait_ready(self.config.timeout * 4 + 1)
            return self.describe()
        except BaseException:
            self.service.__exit__(None, None, None)
            self.service = None
            raise

    def describe(self):
        return {**self.service.status(), 'device': self.service.device()['device'],
                'locales': validate_locales()['locales'],
                'max_seconds': self.service.config.speech.get('max_seconds', 30),
                'speech': {'provider': self.config.speech.get('provider', 'whisper'),
                           'backend': 'server', 'server_url': self.config.speech.get('server_url')},
                'tts': {'backend': self.config.tts.get('backend', 'none')}}

    async def worker(self, fn):
        return await self.loop.run_in_executor(self.pool, fn)

    async def start(self):
        self.loop = asyncio.get_running_loop()
        try:
            self.snapshot = await self.worker(self.open)
        except BaseException:
            self.pool.shutdown(wait=True)
            raise
        self.poller = asyncio.create_task(self.poll())
        if self.bootstrap:
            await self.perform({'action': 'sync'})
            if self.last_result['result'].get('status') not in ('error', 'not_sent', 'uncertain'):
                await self.perform({'action': 'index'})

    async def close(self):
        if self.poller:
            self.poller.cancel()
            with suppress(asyncio.CancelledError):
                await self.poller
        if self.active:
            await asyncio.shield(self.active)
        try:
            if self.service:
                await self.worker(lambda: self.service.__exit__(None, None, None))
        finally:
            self.pool.shutdown(wait=True)

    async def poll(self):
        while True:
            await asyncio.sleep(1)
            if not self.busy:
                self.snapshot = await self.worker(self.describe)
            else:
                # Controller owns and synchronizes its observation; SQLite stays on the worker.
                self.snapshot['session'] = self.service.session.status()
            self.publish('state', {**self.snapshot, 'busy': self.busy})

    def dispatch(self, payload, audio):
        try:
            if 'action' in payload:
                action = payload['action']
                if action not in ACTIONS:
                    raise ValueError('unsupported web action')
                suffix = ''
                if action == 'language':
                    locale = payload.get('locale')
                    if locale not in {r['code'] for r in validate_locales()['locales']}:
                        raise ValueError('unknown locale')
                    suffix = ' ' + locale
                if action == 'response':
                    suffix = ' mode ' + payload['mode']
                return self.service.request('/' + action + suffix)
            return self.service.input_request(text=payload.get('text'), audio=audio,
                                               mode=payload.get('mode', 'preview'))
        except Exception as exc:
            return exception_result(self.service.config, exc, source='web')

    async def finish(self, payload, audio):
        try:
            result = await self.worker(lambda: self.dispatch(payload, audio))
            self.last_result = {'result': result}
            self.reply_id = result.get('request_id')
            self.publish('result', self.last_result)
            self.snapshot = await self.worker(self.describe)
            return self.last_result
        finally:
            self.busy = False
            self.publish('state', {**self.snapshot, 'busy': False})

    async def perform(self, payload, audio=None):
        if self.busy:
            raise web.HTTPConflict(text='Another request is running; no command was queued.')
        self.reply_id = None  # Invalidate obsolete speech before accepting new work.
        self.busy = True
        self.publish('state', {**self.snapshot, 'busy': True})
        self.active = asyncio.create_task(self.finish(payload, audio))
        # Browser loss does not cancel/replay a possibly sent device operation.
        return await asyncio.shield(self.active)

    async def reply(self, request_id):
        if self.busy or self.reply_busy:
            raise web.HTTPConflict(text='Speech or command processing is busy.')
        if not request_id or request_id != self.reply_id or not self.last_result:
            raise web.HTTPGone(text='Response is no longer current.')
        result = self.last_result['result']
        if not result.get('response', {}).get('speak'):
            raise web.HTTPConflict(text='This response is silent.')
        self.reply_busy = True
        config = self.service.config
        try:
            await asyncio.to_thread(delivery_event, config, request_id, 'reply_synthesis_started', {})
            audio, metadata = await asyncio.wait_for(self.synthesizer.synthesize(config, result),
                                                     config.tts.get('timeout', 30))
            await asyncio.to_thread(delivery_event, config, request_id, 'reply_synthesized', metadata)
            if request_id != self.reply_id:
                raise web.HTTPGone(text='Response was superseded; audio discarded.')
            return web.Response(body=audio.data, content_type='audio/wav', headers={'X-Request-ID': request_id})
        except web.HTTPException:
            raise
        except Exception as exc:
            with suppress(Exception):
                await asyncio.to_thread(delivery_event, config, request_id, 'reply_synthesis_failed',
                                        {'error_type': type(exc).__name__})
            raise web.HTTPServiceUnavailable(text='Speech unavailable. Command result is unchanged.')
        finally:
            self.reply_busy = False


def create_app(config, *, port=8090, factory=Application, language=None, bootstrap=False, synthesizer=None):
    # Web uses the selected resident provider. Legacy configs still select Whisper.
    if config.speech.get('provider') == 'gigaam' and (
            not config.speech.get('server_url') or config.services.get('speech')):
        raise ValueError('GigaAM needs an explicit external server with services.speech=false')
    speech = {**config.speech, 'backend': 'server',
              'server_url': config.speech.get('server_url', 'http://127.0.0.1:18119/inference')}
    config = replace(config, speech=speech)
    if speech.get('provider') == 'gigaam':
        config = replace(config, speech={**speech, 'max_seconds': min(speech.get('max_seconds', 30), 25)})
    runtime = Runtime(config, factory=factory, language=language, bootstrap=bootstrap, synthesizer=synthesizer)
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}

    @web.middleware
    async def boundary(request, handler):
        # No LAN binding, CORS or arbitrary Host: prevent cross-site writes and DNS rebinding.
        if request.host not in hosts:
            raise web.HTTPForbidden(text='Use the local Assistant address.')
        origin = request.headers.get('Origin')
        if origin is not None and origin != f'http://{request.host}':
            raise web.HTTPForbidden(text='Cross-origin requests are disabled.')
        if request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            raise web.HTTPForbidden(text='Cross-site requests are disabled.')
        if request.method != 'GET' and not secrets.compare_digest(
                request.headers.get('X-Disc-Token', ''), runtime.token):
            raise web.HTTPForbidden(text='Reload the Assistant page.')
        response = await handler(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; "
                                 "connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})
        return response

    app = web.Application(middlewares=[boundary], client_max_size=MAX_BYTES)
    app[RUNTIME] = runtime

    async def lifecycle(app):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()
    app.cleanup_ctx.append(lifecycle)

    async def state(request):
        return web.json_response({**runtime.snapshot, 'busy': runtime.busy,
                                  'token': runtime.token, 'last_result': runtime.last_result})

    async def command(request):
        if request.content_type != 'application/json':
            raise web.HTTPUnsupportedMediaType()
        if request.content_length is not None and request.content_length > 8192:
            raise web.HTTPRequestEntityTooLarge(max_size=8192, actual_size=request.content_length)
        data = bytearray()
        async for chunk in request.content.iter_chunked(8192):
            data.extend(chunk)
            if len(data) > 8192:
                raise web.HTTPBadRequest(text='Command body is too large.')
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeError):
            raise web.HTTPBadRequest(text='Invalid JSON.')
        if not isinstance(payload, dict) or set(payload) - {'action', 'locale', 'text', 'mode'}:
            raise web.HTTPBadRequest(text='Invalid command fields.')
        if 'action' in payload and (not isinstance(payload['action'], str)
                                    or payload['action'] not in ACTIONS):
            raise web.HTTPBadRequest(text='Unsupported action.')
        if 'action' in payload:
            allowed = ({'action', 'locale'} if payload['action'] == 'language' else
                       {'action', 'mode'} if payload['action'] == 'response' else {'action'})
            if set(payload) - allowed:
                raise web.HTTPBadRequest(text='Do not combine administrative and natural commands.')
            if payload['action'] == 'language' and payload.get('locale') not in [
                    row['code'] for row in validate_locales()['locales']]:
                raise web.HTTPBadRequest(text='Unknown locale.')
            if payload['action'] == 'response' and payload.get('mode') not in ('none', 'errors', 'all'):
                raise web.HTTPBadRequest(text='Unknown response mode.')
        elif (not isinstance(payload.get('text'), str) or len(payload['text']) > 1000
                or payload.get('mode', 'preview') not in ('preview', 'execute')
                or 'locale' in payload):
            raise web.HTTPBadRequest(text='Provide text (up to 1000 characters) and preview or execute mode.')
        return web.json_response(await runtime.perform(payload))

    async def audio(request):
        if request.content_type != 'audio/wav':
            raise web.HTTPUnsupportedMediaType(text='Upload PCM WAV audio.')
        mode = request.query.get('mode', 'preview')
        if mode not in ('preview', 'execute', 'transcribe'):
            raise web.HTTPBadRequest(text='Invalid audio mode.')
        data = await request.read()
        return web.json_response(await runtime.perform({'mode': mode}, data))

    async def events(request):
        if len(runtime.listeners) >= 8:
            raise web.HTTPServiceUnavailable(text='Too many event listeners.')
        response = web.StreamResponse(headers={'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store'})
        await response.prepare(request)
        queue = asyncio.Queue(maxsize=128)
        runtime.listeners.add(queue)
        try:
            await response.write(('data: ' + json.dumps({'type': 'state', 'data': {
                **runtime.snapshot, 'busy': runtime.busy}}) + '\n\n').encode())
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), 10)
                    data = 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
                except TimeoutError:
                    data = ': heartbeat\n\n'
                await asyncio.wait_for(response.write(data.encode()), 5)
        except (ConnectionError, TimeoutError, asyncio.CancelledError):
            pass
        finally:
            runtime.listeners.discard(queue)
        return response

    async def reply(request):
        # ID only: the browser cannot submit arbitrary synthesis text or replay commands.
        return await runtime.reply(request.query.get('request_id'))

    async def delivered(request):
        request_id, outcome = request.query.get('request_id'), request.query.get('outcome')
        if request_id != runtime.reply_id or outcome not in ('played', 'blocked', 'failed', 'cancelled'):
            raise web.HTTPBadRequest(text='Invalid delivery report.')
        await asyncio.to_thread(delivery_event, runtime.service.config, request_id, 'reply_playback',
                                {'outcome': outcome, 'evidence': 'browser_reported'})
        return web.json_response({'status': 'recorded'})

    async def asset(request):
        name = request.match_info.get('name', 'index.html')
        if name not in {'index.html', 'app.js', 'audio.js', 'capture.js', 'style.css', 'reply.js'}:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC / name)

    app.router.add_get('/', asset)
    app.router.add_get('/static/{name}', asset)
    app.router.add_get('/api/state', state)
    app.router.add_get('/api/events', events)
    app.router.add_post('/api/command', command)
    app.router.add_post('/api/audio', audio)
    app.router.add_post('/api/reply', reply)
    app.router.add_post('/api/reply-status', delivered)
    return app


def run(config, *, port=8090, language=None, bootstrap=False):
    if not 1024 <= port <= 65535:
        raise ValueError('web port must be in 1024..65535')
    web.run_app(create_app(config, port=port, language=language, bootstrap=bootstrap),
                host='127.0.0.1', port=port, access_log=None, shutdown_timeout=5)
    return 0
