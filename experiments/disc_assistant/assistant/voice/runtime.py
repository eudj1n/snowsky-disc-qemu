"""Lazy application-owned speech instances on a stable event loop.

Synchronous application requests may create separate asyncio.run loops. Model and
HTTP resources instead stay on this runtime's loop until explicit shutdown.
"""
import asyncio
from dataclasses import asdict
import json
import threading
import time

from experiments.disc_assistant.assistant.voice.contracts import Capabilities, InvalidSpeech, SpeechUnavailable
from experiments.disc_assistant.assistant.voice.profiles import resolve
from experiments.disc_assistant.assistant.voice.registry import Registry


class Handle:
    def __init__(self, runtime, name, spec, provider):
        self.runtime, self.name, self.spec, self.provider = runtime, name, spec, provider
        self.info, self.capabilities = provider.info, provider.capabilities
        self.lock = threading.Lock()
        self.calls = 0
        self.last_call = {}

    def available(self):
        return self.provider.available() is True

    @staticmethod
    def checked_evidence(evidence):
        if not isinstance(evidence, dict):
            raise InvalidSpeech('speech model evidence must be an object')
        # Evidence is public diagnostic metadata: adapters must not put secrets here.
        try:
            encoded = json.dumps(evidence, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise InvalidSpeech('speech model evidence must be JSON data') from exc
        if len(encoded) > 16384:
            raise InvalidSpeech('speech model evidence is too large')
        return evidence

    def evidence(self, locale=None):
        return {**self.checked_evidence(self.provider.evidence(locale)),
                'instance': self.name, 'adapter': self.spec.adapter}

    async def invoke(self, method, value, context):
        if self.runtime.closed:
            raise SpeechUnavailable('speech runtime is closed')
        if self.capabilities.locales is not None and context.locale not in self.capabilities.locales:
            raise SpeechUnavailable('speech provider does not support the selected locale')
        if context.vocabulary and not self.capabilities.vocabulary:
            raise InvalidSpeech('speech provider does not support vocabulary hints')
        if method == 'transcribe':
            from experiments.disc_assistant.assistant.voice.files import wav_audio
            wav_audio(value.data, max_seconds=min(self.capabilities.max_seconds, self.spec.settings.get('max_seconds', 120)))
        if not self.lock.acquire(blocking=False):
            raise SpeechUnavailable('speech provider is already processing a request')
        try:
            async def operation():
                start = time.monotonic()
                try:
                    await self.provider.prepare(context.locale)
                    prepared = time.monotonic()
                    result = (await self.provider.transcribe(value, context) if method == 'transcribe'
                              else await self.provider.synthesize(value))
                    self.last_call = {'cold': self.calls == 0,
                                      'model_evidence': self.checked_evidence(self.provider.result_evidence()),
                                      'prepare_ms': round((prepared-start)*1000, 3),
                                      'inference_ms': round((time.monotonic()-prepared)*1000, 3)}
                    self.calls += 1
                    return result
                except BaseException:
                    # Failed/cancelled work is never retried. Release owned resources;
                    # the next explicit request may prepare the same adapter anew.
                    await self.provider.aclose()
                    self.calls = 0
                    raise
            return await self.runtime.submit(operation, timeout=self.spec.settings.get('timeout', 120))
        finally:
            self.lock.release()

    async def transcribe(self, audio, context):
        return await self.invoke('transcribe', audio, context)

    async def synthesize(self, request):
        return await self.invoke('synthesize', request, request.context)


class SpeechRuntime:
    def __init__(self, config, *, registry=None):
        self.registry = registry or Registry(config.voice.get('plugins'))
        self.specs, self.selected, self.web_choices = resolve(config, registered=self.registry.factories)
        self.handles = {}
        self.loop = None
        self.thread = None
        self.closed = False
        self.guard = threading.Lock()

    def get(self, name):
        if self.closed:
            raise SpeechUnavailable('speech runtime is closed')
        if name not in self.specs:
            raise SpeechUnavailable('unknown speech provider')
        if name not in self.handles:
            spec = self.specs[name]
            self.handles[name] = Handle(self, name, spec, self.registry.create(spec))
        return self.handles[name]

    def describe(self):
        rows = []
        for name in self.web_choices:
            spec = self.specs[name]
            try:
                handle = self.get(name)
                rows.append({'id': name, 'label': spec.label, 'available': handle.available(),
                             'locales': handle.capabilities.locales,
                             'vocabulary': handle.capabilities.vocabulary, 'max_seconds': handle.capabilities.max_seconds, 'provider': asdict(handle.info)})
            except Exception:
                # A broken optional installation must not prevent text controls or
                # other explicitly selected engines. Do not expose exception bodies.
                rows.append({'id': name, 'label': spec.label, 'available': False})
        return rows

    def ensure_loop(self):
        with self.guard:
            if self.closed:
                raise SpeechUnavailable('speech runtime is closed')
            if self.loop is None:
                self.loop = asyncio.new_event_loop()
                self.thread = threading.Thread(target=self.loop.run_forever, name='disc-speech', daemon=True)
                self.thread.start()

    async def submit(self, factory, *, timeout):
        self.ensure_loop()
        async def run():
            return await asyncio.wait_for(factory(), timeout)
        work = run()
        future = asyncio.run_coroutine_threadsafe(work, self.loop)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            # Future.cancel() alone does not await the coroutine's cleanup.
            async def drain():
                tasks = [t for t in asyncio.all_tasks() if t.get_coro() is work]
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(drain(), self.loop))
            raise

    def close(self):
        with self.guard:
            if self.closed:
                return
            self.closed = True
        if self.loop is not None:
            async def shutdown():
                pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                results = await asyncio.gather(*(h.provider.aclose() for h in self.handles.values()), return_exceptions=True)
                await asyncio.get_running_loop().shutdown_asyncgens()
                await asyncio.get_running_loop().shutdown_default_executor()
                return results
            try:
                asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result()
            finally:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join()
                self.loop.close()
        self.handles.clear()

    async def aclose(self):
        await asyncio.to_thread(self.close)
