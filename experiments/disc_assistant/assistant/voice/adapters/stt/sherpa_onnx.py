"""Optional resident Sherpa adapter; subprocess ownership survives per-request event loops."""
from experiments.disc_assistant.assistant.voice.contracts import SpeechAdapter, Capabilities
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import threading

from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.speech import SpeechUnavailable, InvalidSpeech, Transcription
from experiments.disc_assistant.assistant.voice.files import wav_audio
from experiments.disc_assistant.assistant.voice.sherpa_model import ENGINE_VERSION, MODEL_ID, REVISION, FILES

REPO = Path(__file__).resolve().parents[6]


class SherpaTranscriber(SpeechAdapter):
    capabilities = Capabilities(locales=('ru',))
    info = ProviderInfo('sherpa_onnx', ENGINE_VERSION, 'local')
    supports_vocabulary = False

    def __init__(self, settings):
        if type(settings.get('sherpa_threads', 2)) is not int or not 1 <= settings.get('sherpa_threads', 2) <= 16:
            raise ValueError('sherpa_threads must be 1..16')
        self.settings = dict(settings)
        self.root = Path(settings.get('sherpa_root', '~/disc-speech/sherpa-onnx')).expanduser().resolve()
        self.python = Path(settings.get('sherpa_python', self.root / '.venv/bin/python')).expanduser().absolute()
        self.process = None
        self.lock = threading.Lock()

    def available(self):
        return self.python.is_file() and all((self.root / MODEL_ID / name).is_file() for name in FILES)

    def evidence(self, locale=None):
        return {'model': MODEL_ID, 'revision': REVISION, 'sha256': FILES,
                'model_binding': 'worker verifies pinned files before loading; weights remain resident',
                'decoder': 'greedy_search', 'provider': 'cpu', 'tail_padding_ms': 300,
                'threads': self.settings.get('sherpa_threads', 2)}

    async def aclose(self):
        await asyncio.to_thread(self.close)

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()

    @staticmethod
    def read(process):
        line = process.stdout.readline(65537)
        if not line.endswith(b'\n') or len(line) > 65536:
            raise InvalidSpeech('invalid Sherpa worker response')
        return json.loads(line)

    def exchange(self, audio, cancelled):
        try:
            if cancelled.is_set():
                raise SpeechUnavailable('recognition cancelled')
            if self.process is None:
                if not self.available():
                    raise SpeechUnavailable('install the optional Sherpa environment before selecting it')
                self.process = subprocess.Popen([
                    str(self.python), '-m', 'experiments.disc_assistant.assistant.voice.sherpa_worker',
                    '--root', str(self.root), '--threads', str(self.settings.get('sherpa_threads', 2)),
                ], cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                if cancelled.is_set():
                    raise SpeechUnavailable('recognition cancelled')
                if self.read(self.process) != {'ready': True}:
                    raise SpeechUnavailable('Sherpa startup failed')
            if cancelled.is_set():
                raise SpeechUnavailable('recognition cancelled')
            if audio is None:
                return
            process = self.process
            process.stdin.write(json.dumps({'audio': base64.b64encode(audio.data).decode()}).encode() + b'\n')
            process.stdin.flush()
            result = self.read(process)
            if (not isinstance(result, dict) or set(result) != {'text', 'no_speech'}
                    or not isinstance(result['text'], str) or len(result['text']) > 1000
                    or any(ord(c) < 32 or ord(c) == 127 for c in result['text'])
                    or type(result['no_speech']) is not bool
                    or (result['no_speech'] and result['text'].strip())):
                raise InvalidSpeech('invalid Sherpa transcription')
            return Transcription(result['text'], 'ru', result['no_speech'])
        except BaseException:
            self.close()
            raise

    async def prepare(self, locale):
        from experiments.disc_assistant.assistant.speech import SpeechContext
        await self.transcribe(None, SpeechContext(locale, 'prepare'))

    async def transcribe(self, audio, context):
        if context.locale != 'ru':
            raise SpeechUnavailable('Sherpa RU supports Russian commands; select Whisper for this language')
        if context.vocabulary:
            raise InvalidSpeech('this Sherpa model does not support catalog hints')
        if audio is not None:
            wav_audio(audio.data, max_seconds=self.settings.get('max_seconds', 30))
        if not self.lock.acquire(blocking=False):
            raise SpeechUnavailable('Sherpa is already processing another request')
        cancelled = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(self.exchange, audio, cancelled))
        try:
            return await asyncio.wait_for(asyncio.shield(task), self.settings.get('timeout', 120))
        except (TimeoutError, asyncio.CancelledError):
            cancelled.set()
            # Kill the owned process to unblock reads/writes; never replay this input.
            process = self.process
            if process is not None and process.poll() is None:
                process.kill()
            await asyncio.gather(task, return_exceptions=True)
            self.close()
            raise
        except (InvalidSpeech, SpeechUnavailable):
            raise
        except Exception as exc:
            raise SpeechUnavailable('Sherpa recognition failed; request was not retried') from exc
        finally:
            self.lock.release()
