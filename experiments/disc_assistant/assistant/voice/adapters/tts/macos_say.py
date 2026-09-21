"""macOS speech synthesis to a file; never plays through speakers."""
import platform
import sys
import tempfile
from pathlib import Path
from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.speech import SpeechUnavailable
from experiments.disc_assistant.assistant.voice.process import run_process
from experiments.disc_assistant.assistant.voice.files import load_audio
from experiments.disc_assistant.assistant.voice.contracts import SpeechAdapter, Capabilities

class MacOSSay(SpeechAdapter):
    info = ProviderInfo('macos_say', platform.mac_ver()[0] or 'unavailable', 'local')

    def __init__(self, settings):
        self.settings = settings

    @property
    def capabilities(self):
        return Capabilities(locales=tuple(self.settings.get('voices', {'ru': 'Milena', 'en': 'Samantha'})))

    def available(self):
        return sys.platform == 'darwin'

    def evidence(self, locale=None):
        return {'model': 'macOS system voice', 'voice': self.voice(locale), 'rate': self.settings.get('rate', 175)}

    def voice(self, locale):
        voice = self.settings.get('voices', {'ru': 'Milena', 'en': 'Samantha'}).get(locale)
        if not voice:
            raise SpeechUnavailable('configure a TTS voice for the active locale in speech.voices')
        return voice

    async def synthesize(self, request):
        if sys.platform != 'darwin':
            raise SpeechUnavailable('macos_say requires macOS; inject another SpeechSynthesizer on this platform')
        voice = request.voice or self.voice(request.context.locale)
        with tempfile.TemporaryDirectory(prefix='disc-tts-') as temporary:
            root = Path(temporary)
            source, output = root / 'input.txt', root / 'output.wav'
            source.write_text(request.text, encoding='utf-8')
            await run_process(['/usr/bin/say', '-v', voice, '-r', str(self.settings.get('rate', 175)),
                               '-f', str(source), '-o', str(output), '--file-format=WAVE',
                               '--data-format=LEI16@16000', '--channels=1'],
                              timeout=self.settings.get('timeout', 120))
            return load_audio(output, max_seconds=self.settings.get('max_seconds', 30))
