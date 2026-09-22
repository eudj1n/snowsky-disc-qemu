"""Web boundary and shared application checks using a synthetic DISC peer only."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer

from controller.tests.session_fixture import Server
from experiments.disc_assistant.assistant.application import Application
from experiments.disc_assistant.assistant.config import Config
from experiments.disc_assistant.assistant.journal import history_command
from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.speech import Transcription
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.web.server import create_app, RUNTIME


class WebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.peer = Server()
        self.config = Config('web-fixture', '127.0.0.1', self.peer.server_address[1], 1,
                             Path(self.directory.name), '127.0.0.1', 1, 'http', 'UNSET_KEY', {},
                             timeout=.15, locale='en')
        self.provider = Mock(info=ProviderInfo('fixture-stt', '1', 'local'))
        self.provider.transcribe = AsyncMock(return_value=Transcription('Pause.', 'en'))
        def factory(config, **kwargs):
            return Application(config, transcriber=self.provider, **kwargs)
        self.app = create_app(self.config, factory=factory)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.headers = {'Host': '127.0.0.1:8090'}
        response = await self.client.get('/api/state', headers=self.headers)
        self.token = (await response.json())['token']
        self.headers['X-Disc-Token'] = self.token
        for _ in range(100):
            if self.app[RUNTIME].service.session.status()['connection'] == 'ready':
                break
            await asyncio.sleep(.01)

    async def asyncTearDown(self):
        await self.client.close()
        await asyncio.to_thread(self.peer.close)
        self.directory.cleanup()

    async def command(self, **payload):
        response = await self.client.post('/api/command', json=payload, headers=self.headers)
        self.assertEqual(response.status, 200, await response.text())
        return (await response.json())['result']

    async def test_preview_execute_and_observation_share_one_session(self):
        result = await self.command(text='Pause', mode='preview')
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(self.peer.writes, 0)
        result = await self.command(text='Pause', mode='execute')
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(self.peer.writes, 1)
        self.assertEqual((await self.command(text='Pause', mode='execute'))['status'], 'already_satisfied')
        self.assertEqual(self.peer.writes, 1)
        self.assertEqual(self.peer.accepts, 1)
        state = await (await self.client.get('/api/state', headers=self.headers)).json()
        self.assertEqual(state['session']['observation']['playback'], 'paused')
        self.assertEqual(state['device']['key'], 'web-fixture')

    async def test_audio_preview_and_execute_use_existing_journal(self):
        for mode in ('transcribe', 'preview', 'execute'):
            response = await self.client.post('/api/audio?mode=' + mode, data=wav(),
                                             headers={**self.headers, 'Content-Type': 'audio/wav'})
            result = (await response.json())['result']
            self.assertEqual(result['transcription']['command_text'], 'Pause')
            self.assertEqual(self.peer.writes, int(mode == 'execute'))
            record = history_command(self.config, ['show', result['request_id']])
            self.assertEqual(record['source'], 'web')
            self.assertEqual(record['input'], '[audio]')
        self.assertEqual(self.peer.accepts, 1)

    async def test_invalid_audio_and_natural_slash_cannot_dispatch_admin(self):
        for data in (b'invalid', wav(silent=True), wav(rate=48000), wav(frames=31 * 16000)):
            response = await self.client.post('/api/audio?mode=execute', data=data,
                                             headers={**self.headers, 'Content-Type': 'audio/wav'})
            self.assertEqual((await response.json())['result']['status'], 'error')
        result = await self.command(text='/history export /tmp/unwanted', mode='execute')
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.peer.writes, 0)
        self.provider.transcribe.assert_not_called()

    async def test_origin_token_host_and_command_surface_are_restricted(self):
        for headers in ({'Host': '127.0.0.1:8090'},
                        {**self.headers, 'Origin': 'https://other.invalid'},
                        {**self.headers, 'Host': 'other.invalid:8090'},
                        {**self.headers, 'Sec-Fetch-Site': 'cross-site'}):
            response = await self.client.post('/api/command', json={'text': 'Pause', 'mode': 'execute'}, headers=headers)
            self.assertEqual(response.status, 403)
        for payload in ({'action': 'history'}, {'action': 'transcribe', 'path': '/etc/passwd'}, [], {'text': 'a' * 9000}):
            response = await self.client.post('/api/command', json=payload, headers=self.headers)
            self.assertIn(response.status, (400, 413))
        response = await self.client.get('/static/unknown', headers=self.headers)
        self.assertEqual(response.status, 404)
        self.assertEqual(self.peer.writes, 0)

    async def test_language_is_saved_and_preview_never_changes_it(self):
        result = await self.command(text='Switch language to Russian', mode='preview')
        self.assertEqual(self.app[RUNTIME].service.config.locale, 'en')
        result = await self.command(action='language', locale='ru')
        self.assertEqual(result['locale'], 'ru')
        self.assertEqual(Application(self.config).config.locale, 'ru')
        response = await self.client.post('/api/command', json={'action': 'language', 'locale': 'ru /sync'}, headers=self.headers)
        self.assertEqual(response.status, 400)
        self.assertEqual(self.peer.writes, 0)

    async def test_busy_rejected_and_disconnected_caller_does_not_cancel_or_replay(self):
        async def slow(audio, context):
            await asyncio.sleep(.2)
            return Transcription('Pause', context.locale)
        self.provider.transcribe.side_effect = slow
        runtime = self.app[RUNTIME]
        request = asyncio.create_task(runtime.perform({'mode': 'execute'}, wav()))
        await asyncio.sleep(.05)
        response = await self.client.post('/api/command', json={'text': 'Resume', 'mode': 'execute'}, headers=self.headers)
        self.assertEqual(response.status, 409)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        await runtime.active
        self.assertEqual(runtime.last_result['result']['status'], 'confirmed')
        self.assertEqual(self.peer.writes, 1)
        self.assertFalse(runtime.busy)

    async def test_device_change_during_transcription_prevents_execution(self):
        async def changed(audio, context):
            self.app[RUNTIME].service.session.disconnect()
            return Transcription('Pause', context.locale)
        self.provider.transcribe.side_effect = changed
        response = await self.client.post('/api/audio?mode=execute', data=wav(),
                                         headers={**self.headers, 'Content-Type': 'audio/wav'})
        result = (await response.json())['result']
        self.assertEqual(result['status'], 'not_sent')
        self.assertFalse(result['mutation_attempted'])
        self.assertEqual(self.peer.writes, 0)

    async def test_events_emit_state_and_trace_without_a_second_device_session(self):
        response = await self.client.get('/api/events', headers=self.headers)
        first = await response.content.readline()
        event = json.loads(first.decode().removeprefix('data: '))
        self.assertEqual(event['type'], 'state')
        await self.command(text='Pause', mode='preview')
        found = False
        for _ in range(40):
            line = await asyncio.wait_for(response.content.readline(), 2)
            if line.startswith(b'data: ') and json.loads(line[6:])['type'] == 'trace':
                found = True
                break
        self.assertTrue(found)
        response.close()
        self.assertEqual(self.peer.writes, 0)
        self.assertEqual(self.peer.accepts, 1)

    async def test_web_forces_server_and_persists_reply_policy(self):
        self.assertEqual(self.app[RUNTIME].config.speech['backend'], 'server')
        self.assertEqual(self.config.speech.get('backend', 'cli'), 'cli')
        await self.command(action='response', mode='all')
        self.assertEqual(Application(self.config).config.response_mode, 'all')
        response = await self.client.post('/api/command', json={'action': 'response', 'mode': 'invalid'}, headers=self.headers)
        self.assertEqual(response.status, 400)

    async def test_sherpa_selection_preview_execute_and_journal(self):
        await self.command(action='language', locale='ru')
        provider = self.app[RUNTIME].voice.get('sherpa')
        with patch.object(provider, 'transcribe', AsyncMock(return_value=Transcription('Пауза', 'ru'))) as transcribe:
            for mode in ('transcribe', 'preview', 'execute'):
                response = await self.client.post('/api/audio?engine=sherpa&mode=' + mode, data=wav(),
                                                 headers={**self.headers, 'Content-Type': 'audio/wav'})
                result = (await response.json())['result']
                self.assertEqual(result['transcription']['provider']['name'], 'sherpa_onnx')
                self.assertEqual(self.peer.writes, int(mode == 'execute'))
                self.assertEqual(result['status'], {'transcribe': 'transcribed', 'preview': 'planned', 'execute': 'confirmed'}[mode])
                record = history_command(self.config, ['show', result['request_id']])
                self.assertIn('speech_model', [event['phase'] for event in record['events']])
            self.assertEqual(transcribe.await_count, 3)
        self.provider.transcribe.assert_not_called()
        self.assertEqual(self.peer.accepts, 1)

    async def test_sherpa_failure_unknown_engine_and_locale_never_fallback_or_write(self):
        response = await self.client.post('/api/audio?engine=sherpa&mode=execute', data=wav(),
                                         headers={**self.headers, 'Content-Type': 'audio/wav'})
        self.assertEqual((await response.json())['result']['status'], 'error')
        await self.command(action='language', locale='ru')
        with patch.object(self.app[RUNTIME].voice.get('sherpa').provider, 'available', return_value=False):
            response = await self.client.post('/api/audio?engine=sherpa&mode=execute', data=wav(),
                                             headers={**self.headers, 'Content-Type': 'audio/wav'})
            self.assertEqual((await response.json())['result']['status'], 'error')
        response = await self.client.post('/api/audio?engine=unknown&mode=execute', data=wav(),
                                         headers={**self.headers, 'Content-Type': 'audio/wav'})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.peer.writes, 0)
        self.provider.transcribe.assert_not_called()

    async def test_sherpa_reconnect_during_recognition_prevents_write(self):
        await self.command(action='language', locale='ru')
        async def changed(audio, context):
            self.app[RUNTIME].service.session.disconnect()
            return Transcription('Пауза', 'ru')
        with patch.object(self.app[RUNTIME].voice.get('sherpa'), 'transcribe', changed):
            response = await self.client.post('/api/audio?engine=sherpa&mode=execute', data=wav(),
                                             headers={**self.headers, 'Content-Type': 'audio/wav'})
        self.assertEqual((await response.json())['result']['status'], 'not_sent')
        self.assertEqual(self.peer.writes, 0)

    async def test_reply_failure_does_not_change_or_replay_completed_command(self):
        runtime = self.app[RUNTIME]
        runtime.synthesizer = Mock(synthesize=AsyncMock(side_effect=RuntimeError('fixture outage')))
        await self.command(action='response', mode='all')
        result = await self.command(text='Pause', mode='execute')
        self.assertTrue(result['response']['speak'])
        response = await self.client.post('/api/reply?request_id=' + result['request_id'], headers=self.headers)
        self.assertEqual(response.status, 503)
        self.assertEqual(runtime.last_result['result'], result)
        self.assertEqual(self.peer.writes, 1)
        record = history_command(self.config, ['show', result['request_id']])
        self.assertEqual(record['status'], 'confirmed')
        self.assertIn('reply_synthesis_failed', [event['phase'] for event in record['events']])
        self.assertNotIn('fixture outage', json.dumps(record))

    async def test_reply_requires_current_eligible_id_and_tracks_playback_separately(self):
        from experiments.disc_assistant.assistant.speech import Audio
        runtime = self.app[RUNTIME]
        runtime.synthesizer = Mock(synthesize=AsyncMock(return_value=(Audio(wav(), 'audio/wav', 16000, 1), {'fixture': True})))
        silent = await self.command(text='Pause', mode='execute')
        response = await self.client.post('/api/reply?request_id=' + silent['request_id'], headers=self.headers)
        self.assertEqual(response.status, 409)
        runtime.synthesizer.synthesize.assert_not_called()
        await self.command(action='response', mode='all')
        result = await self.command(text='Resume', mode='execute')
        response = await self.client.post('/api/reply?request_id=' + silent['request_id'], headers=self.headers)
        self.assertEqual(response.status, 410)
        response = await self.client.post('/api/reply?request_id=' + result['request_id'], headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.read(), wav())
        response = await self.client.post('/api/reply-status?request_id=' + result['request_id'] + '&outcome=played', headers=self.headers)
        self.assertEqual(response.status, 200)
        record = history_command(self.config, ['show', result['request_id']])
        event = next(e for e in record['events'] if e['phase'] == 'reply_playback')
        self.assertEqual(event['payload']['evidence'], 'browser_reported')
        self.assertEqual(self.peer.writes, 2)

    async def test_new_command_supersedes_inflight_speech(self):
        from experiments.disc_assistant.assistant.speech import Audio
        runtime = self.app[RUNTIME]
        started, release = asyncio.Event(), asyncio.Event()
        async def synthesize(config, result):
            started.set()
            await release.wait()
            return Audio(wav(), 'audio/wav', 16000, 1), {}
        runtime.synthesizer = Mock(synthesize=synthesize)
        await self.command(action='response', mode='all')
        first = await self.command(text='Pause', mode='execute')
        reply = asyncio.create_task(runtime.reply(first['request_id']))
        await started.wait()
        await self.command(text='Resume', mode='execute')
        release.set()
        from aiohttp.web import HTTPGone
        with self.assertRaises(HTTPGone):
            await reply
        self.assertEqual(self.peer.writes, 2)
