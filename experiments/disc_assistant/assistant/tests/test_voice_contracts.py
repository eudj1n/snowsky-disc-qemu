"""Shared adapter v1 conformance, profile routing and lifecycle regression."""
import asyncio
import base64
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from controller.tests.session_fixture import Server
from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.voice.contracts import (
    Audio, Capabilities, SpeechAdapter, SpeechContext, SynthesisRequest,
    Transcription, SpeechUnavailable, InvalidSpeech,
)
from experiments.disc_assistant.assistant.voice.registry import Registry, AdapterSpec, validate_adapter
from experiments.disc_assistant.assistant.voice.runtime import SpeechRuntime
from experiments.disc_assistant.assistant.voice.backends import transcribe_audio, synthesize_text
from experiments.disc_assistant.assistant.voice.files import wav_audio
from experiments.disc_assistant.assistant.voice.replies import ReplySynthesizer
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.web.server import create_app


class ContractSTT(SpeechAdapter):
    info = ProviderInfo('contract_stt', '1', 'local')
    capabilities = Capabilities(locales=('ru',))

    def __init__(self, settings):
        self.settings = settings
        self.calls = 0
        self.closes = 0
        self.loops = []
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def evidence(self, locale=None):
        return {'model': 'synthetic-v1'}

    async def prepare(self, locale):
        self.loops.append(asyncio.get_running_loop())
        if self.settings.get('prepare_fail'):
            raise SpeechUnavailable('fixture unavailable')

    async def transcribe(self, audio, context):
        self.calls += 1
        self.started.set()
        if self.settings.get('slow'):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                await asyncio.sleep(.01)
                self.cancelled.set()
                raise
        return Transcription('пауза', self.settings.get('return_locale', context.locale))

    async def aclose(self):
        self.closes += 1
        self.loops.append(asyncio.get_running_loop())


class ContractTTS(ContractSTT):
    info = ProviderInfo('contract_tts', '1', 'local')

    async def synthesize(self, request):
        self.calls += 1
        return Audio(wav(), 'audio/wav', 16000, 1)


class Trace:
    id = 'contract-probe'
    def __init__(self):
        self.events = []
    def event(self, phase, payload):
        self.events.append((phase, payload))


def config_at(directory):
    path = Path(directory) / 'config.toml'
    path.write_text('[device]\nkey="fixture"\nhost="127.0.0.1"\n')
    return load(path)


def custom_voice(settings=None):
    return {'stt': 'custom', 'web_stt': 'custom', 'web_choices': ['custom'], 'tts': 'custom_voice',
            'plugins': {'fixture_stt': __name__ + ':ContractSTT', 'fixture_tts': __name__ + ':ContractTTS'},
            'providers': {'custom': {'kind': 'stt', 'adapter': 'fixture_stt', 'label': 'Custom STT', 'settings': settings or {}},
                          'custom_voice': {'kind': 'tts', 'adapter': 'fixture_tts'}}}


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = replace(config_at(self.directory.name), voice=custom_voice())
        self.runtime = SpeechRuntime(self.config)
        self.addCleanup(self.runtime.close)
        self.context = SpeechContext('ru', 'fixture')
        self.audio = wav_audio(wav())

    def test_lazy_registration_identity_and_event_loop_survive_requests(self):
        self.assertIsNone(self.runtime.loop)
        h = self.runtime.get('custom')
        for _ in range(2):
            result = asyncio.run(transcribe_audio(self.config, self.audio, Trace(), provider=h))
            self.assertEqual(result['provider']['name'], 'contract_stt')
            self.assertEqual(result['model']['model'], 'synthetic-v1')
        self.assertEqual(h.provider.calls, 2)
        self.assertFalse(result['runtime']['cold'])
        self.assertEqual(len(set(h.provider.loops)), 1)
        owner_loop = h.provider.loops[0]
        self.runtime.close()
        self.assertTrue(owner_loop.is_closed())
        self.assertEqual(h.provider.closes, 1)
        with self.assertRaises(SpeechUnavailable):
            asyncio.run(h.transcribe(self.audio, self.context))

    def test_unsupported_locale_hints_and_missing_id_do_not_infer(self):
        h = self.runtime.get('custom')
        for context in (SpeechContext('en', 'fixture'), SpeechContext('ru', 'fixture', ('name',))):
            with self.assertRaises((SpeechUnavailable, InvalidSpeech)):
                asyncio.run(h.transcribe(self.audio, context))
        self.assertEqual(h.provider.calls, 0)
        with self.assertRaises(SpeechUnavailable):
            self.runtime.get('missing')

    def test_timeout_cancel_cleanup_and_no_parallel_queue(self):
        async def scenario(cancel):
            runtime = SpeechRuntime(replace(self.config, voice=custom_voice({'slow': True, 'timeout': .15})))
            h = runtime.get('custom')
            try:
                task = asyncio.create_task(h.transcribe(self.audio, self.context))
                await asyncio.to_thread(h.provider.started.wait, 2)
                with self.assertRaises(SpeechUnavailable):
                    await h.transcribe(self.audio, self.context)
                if cancel:
                    task.cancel()
                with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError):
                    await task
                self.assertTrue(h.provider.cancelled.is_set())
                self.assertEqual(h.provider.calls, 1)
                self.assertEqual(h.provider.closes, 1)
            finally:
                await runtime.aclose()
        for cancel in (False, True):
            asyncio.run(scenario(cancel))

    def test_prepare_error_never_infers_or_falls_back(self):
        runtime = SpeechRuntime(replace(self.config, voice=custom_voice({'prepare_fail': True})))
        self.addCleanup(runtime.close)
        h = runtime.get('custom')
        with self.assertRaises(SpeechUnavailable):
            asyncio.run(h.transcribe(self.audio, self.context))
        self.assertEqual(h.provider.calls, 0)
        self.assertEqual(h.provider.closes, 1)

    def test_common_boundary_rejects_wrong_locale_and_records_no_hints(self):
        runtime = SpeechRuntime(replace(self.config, voice=custom_voice({'return_locale': 'en'})))
        self.addCleanup(runtime.close)
        trace = Trace()
        with patch('experiments.disc_assistant.assistant.voice.backends.catalog_vocabulary', side_effect=AssertionError('no catalog read')):
            with self.assertRaises(InvalidSpeech):
                asyncio.run(transcribe_audio(self.config, self.audio, trace, provider=runtime.get('custom')))
        self.assertIn(('speech_vocabulary', {'enabled': False, 'reason': 'unsupported_by_provider'}), trace.events)

    def test_tts_profile_is_used_in_file_and_reply_flows_with_cache(self):
        async def scenario():
            audio, metadata = await synthesize_text(self.config, 'Пауза', Trace())
            self.assertEqual(metadata['provider']['name'], 'contract_tts')
            self.assertEqual(audio.sample_rate, 16000)
            replies = ReplySynthesizer()
            try:
                result = {'request_id':'fixture', 'response':{'speak':True, 'text':'Пауза', 'language':'ru'}}
                _, first = await replies.synthesize(self.config, result)
                _, second = await replies.synthesize(self.config, result)
                self.assertEqual(first['provider']['name'], 'contract_tts')
                self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit'])
                self.assertEqual(replies.runtime.get('custom_voice').provider.provider.calls, 1)
            finally:
                await replies.aclose()
        asyncio.run(scenario())

    def test_contract_validation_and_explicit_factory_registration(self):
        registry = Registry()
        registry.register('local_test', 'stt', ContractSTT)
        adapter = registry.create(AdapterSpec('stt', 'local_test', 'Test', {}))
        self.assertIsInstance(adapter, ContractSTT)
        with self.assertRaises(ValueError): registry.register('local_test', 'stt', ContractSTT)
        with self.assertRaises(ValueError): registry.create(AdapterSpec('tts', 'local_test', 'Test', {}))
        adapter.contract_version = 99
        with self.assertRaises(InvalidSpeech): validate_adapter(adapter, 'stt')
        adapter.contract_version = 1
        adapter.capabilities = {'locales':['ru']}
        with self.assertRaises(InvalidSpeech): validate_adapter(adapter, 'stt')

    def test_embedded_registry_and_explicit_disabled_tts(self):
        registry = Registry()
        registry.register('fixture_stt', 'stt', ContractSTT)
        registry.register('fixture_tts', 'tts', ContractTTS)
        voice = custom_voice()
        voice.pop('plugins')
        runtime = SpeechRuntime(replace(self.config, voice=voice), registry=registry)
        self.addCleanup(runtime.close)
        self.assertEqual(asyncio.run(runtime.get('custom').transcribe(self.audio, self.context)).text, 'пауза')
        disabled = replace(self.config, voice={**custom_voice(), 'tts': 'none'})
        with self.assertRaises(SpeechUnavailable):
            asyncio.run(synthesize_text(disabled, 'Пауза', Trace()))

    def test_matrix_preserves_failure_without_retry_and_continues_explicit_instances(self):
        from experiments.disc_assistant.assistant.voice.check import check
        config = replace(self.config, voice=custom_voice({'return_locale':'en'}))
        rows = asyncio.run(check(config, ['custom','custom_voice'], audio=self.audio, text='Пауза', repeats=2))
        self.assertEqual([(row['instance'],row['status']) for row in rows],
                         [('custom','error'),('custom_voice','ok'),('custom_voice','ok')])
        self.assertEqual(rows[0]['error_type'],'InvalidSpeech')

    def test_legacy_defaults_do_not_select_optional_models(self):
        from experiments.disc_assistant.assistant.voice.profiles import resolve
        for speech, tts, expected_stt, expected_tts in (
            ({}, {}, 'whisper_cli', 'none'),
            ({'backend': 'cli'}, {'backend': 'none'}, 'whisper_cli', 'none'),
            ({'backend': 'server'}, {'backend': 'piper'}, 'whisper', 'piper'),
        ):
            with self.subTest(speech=speech, tts=tts):
                specs, selected, _ = resolve(replace(self.config, voice={}, speech=speech, tts=tts))
                self.assertEqual(selected, {'stt': expected_stt, 'web_stt': 'whisper', 'tts': expected_tts})
                self.assertNotIn('normalization', specs['piper'].settings)

    def test_profile_loading_precedence_and_validation_without_plugin_import(self):
        root = Path(self.directory.name)
        profile = root/'speech.toml'
        profile.write_text('[voice]\nstt="sherpa"\nweb_stt="sherpa"\ntts="none"\n')
        config = root/'profile-config.toml'
        config.write_text(f'[device]\nkey="fixture"\nhost="127.0.0.1"\n[voice]\nprofile="{profile}"\nweb_stt="whisper"\n')
        c = load(config)
        runtime = SpeechRuntime(c)
        self.assertEqual(runtime.selected, {'stt':'sherpa','web_stt':'whisper','tts':'none'})
        runtime.close()
        for bad in ('stt="unknown"', 'stt="piper"', 'plugins.whisper_cpp="bad:factory"', 'providers.test.kind="bad"'):
            config.write_text('[device]\nkey="fixture"\nhost="127.0.0.1"\n[voice]\n'+bad+'\n')
            with self.assertRaises(ValueError): load(config)
        config.write_text('[device]\nkey="fixture"\nhost="127.0.0.1"\n[voice.plugins]\nabsent="not_installed:Factory"\n')
        self.assertIn('absent', load(config).voice['plugins'])


class PluginHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_example_has_persistent_session_and_valid_stt_tts(self):
        seen = []
        async def stt(request):
            data = await request.json(); seen.append(data['locale'])
            self.assertEqual(base64.b64decode(data['audio']), wav())
            return web.json_response({'text':'пауза','locale':data['locale'],'no_speech':False})
        async def tts(request):
            data = await request.json(); seen.append(data['locale'])
            return web.json_response({'audio':base64.b64encode(wav()).decode()})
        app = web.Application(); app.router.add_post('/transcribe',stt); app.router.add_post('/synthesize',tts)
        async with TestServer(app) as server:
            with tempfile.TemporaryDirectory() as directory:
                voice = custom_voice()
                prefix = 'experiments.disc_assistant.assistant.voice.examples.http_speech:'
                voice['plugins'] = {'fixture_stt':prefix+'JSONTranscriber','fixture_tts':prefix+'JSONSynthesizer'}
                for name, route in [('custom','/transcribe'),('custom_voice','/synthesize')]:
                    voice['providers'][name]['settings'] = {'model':'synthetic', 'locales':['ru'], 'server_url':str(server.make_url(route))}
                config = replace(config_at(directory), voice=voice)
                runtime = SpeechRuntime(config)
                try:
                    h=runtime.get('custom')
                    await transcribe_audio(config,wav_audio(wav()),Trace(),provider=h)
                    session=h.provider.session
                    await transcribe_audio(config,wav_audio(wav()),Trace(),provider=h)
                    self.assertIs(session,h.provider.session)
                    await synthesize_text(config,'Пауза',Trace(),provider=runtime.get('custom_voice'))
                finally:
                    await runtime.aclose()
                self.assertTrue(session.closed)
        self.assertEqual(seen,['ru','ru','ru'])

    async def test_web_uses_profile_choices_and_custom_stt_without_core_changes(self):
        peer = Server()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config = replace(config_at(directory), data_dir=Path(directory)/'data',
                                 tcp_port=peer.server_address[1], http_port=1, search_port=1,
                                 timeout=.15, voice=custom_voice())
                async with TestClient(TestServer(create_app(config))) as client:
                    headers={'Host':'127.0.0.1:8090'}
                    state=await (await client.get('/api/state',headers=headers)).json()
                    self.assertEqual(state['speech']['default_engine'],'custom')
                    self.assertEqual([r['id'] for r in state['speech']['engines']],['custom'])
                    headers.update({'X-Disc-Token':state['token'],'Content-Type':'audio/wav'})
                    response=await client.post('/api/audio?mode=preview&engine=custom',data=wav(),headers=headers)
                    result=(await response.json())['result']
                    self.assertEqual(result['status'],'planned')
                    self.assertEqual(result['transcription']['provider']['name'],'contract_stt')
                    self.assertEqual(result['transcription']['model']['instance'],'custom')
                    self.assertEqual(peer.writes,0)
                    response=await client.post('/api/audio?engine=whisper',data=wav(),headers=headers)
                    self.assertEqual(response.status,400)
        finally:
            await asyncio.to_thread(peer.close)
