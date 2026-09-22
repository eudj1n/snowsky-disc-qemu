"""Resident STT ownership, cancellation and request boundaries without model dependencies."""
import asyncio
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments.disc_assistant.assistant.speech import SpeechContext, SpeechUnavailable, InvalidSpeech
from experiments.disc_assistant.assistant.tests.test_voice_files import wav
from experiments.disc_assistant.assistant.voice.files import wav_audio
from experiments.disc_assistant.assistant.voice.sherpa import SherpaTranscriber
from experiments.disc_assistant.assistant.config import load

SUCCESS = '''import json,sys
print('{"ready": true}', flush=True)
for line in sys.stdin:
    json.loads(line)
    print(json.dumps({'text':'пауза', 'no_speech':False}),flush=True)
'''


class SherpaTests(unittest.TestCase):
    def setUp(self):
        self.provider = SherpaTranscriber({'timeout': 2})
        self.addCleanup(self.provider.close)
        self.audio = wav_audio(wav())
        self.context = SpeechContext('ru', 'test')

    def worker(self, source):
        real = subprocess.Popen
        def start(*args, **kwargs):
            return real([sys.executable, '-u', '-c', source], **kwargs)
        return patch('experiments.disc_assistant.assistant.voice.adapters.stt.sherpa_onnx.subprocess.Popen', side_effect=start)

    def test_resident_worker_survives_new_event_loops_and_closes(self):
        with patch.object(self.provider, 'available', return_value=True), self.worker(SUCCESS):
            first = asyncio.run(self.provider.transcribe(self.audio, self.context))
            process = self.provider.process
            second = asyncio.run(self.provider.transcribe(self.audio, self.context))
            self.assertIs(self.provider.process, process)
            self.assertEqual(first.text, second.text)
            self.provider.close()
            self.assertIsNotNone(process.poll())

    def test_locale_and_hints_reject_before_start(self):
        with patch('experiments.disc_assistant.assistant.voice.adapters.stt.sherpa_onnx.subprocess.Popen') as start:
            with self.assertRaises(SpeechUnavailable):
                asyncio.run(self.provider.transcribe(self.audio, SpeechContext('en', 'test')))
            with self.assertRaises(InvalidSpeech):
                asyncio.run(self.provider.transcribe(self.audio, SpeechContext('ru', 'test', ('private name',))))
            start.assert_not_called()

    def test_timeout_and_cancellation_reap_worker_without_retry(self):
        async def run(cancel):
            task = asyncio.create_task(self.provider.transcribe(self.audio, self.context))
            for _ in range(200):
                if self.provider.process is not None:
                    break
                await asyncio.sleep(.005)
            process = self.provider.process
            self.assertIsNotNone(process)
            if cancel:
                task.cancel()
            with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError):
                await task
            self.assertIsNotNone(process.poll())
            self.assertIsNone(self.provider.process)
        for cancel in (False, True):
            self.provider.settings['timeout'] = .2
            with patch.object(self.provider, 'available', return_value=True), self.worker('import time; time.sleep(30)') as start:
                asyncio.run(run(cancel))
                self.assertEqual(start.call_count, 1)

    def test_invalid_response_reaps_worker(self):
        source = SUCCESS.replace("'text':'пауза'", "'text':['invalid']")
        with patch.object(self.provider, 'available', return_value=True), self.worker(source):
            with self.assertRaises(InvalidSpeech):
                asyncio.run(self.provider.transcribe(self.audio, self.context))
            self.assertIsNone(self.provider.process)

    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.toml'
            for value in ('web_backend="unknown"', 'sherpa_threads=0', 'sherpa_python="relative"'):
                path.write_text('[device]\nkey="test"\nhost="127.0.0.1"\n[speech]\n' + value)
                with self.assertRaises(ValueError):
                    load(path)
            path.write_text('[device]\nkey="test"\nhost="127.0.0.1"\n[speech]\nweb_backend="sherpa"\nsherpa_threads=2')
            self.assertEqual(load(path).speech['web_backend'], 'sherpa')
