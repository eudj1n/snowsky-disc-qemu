"""Explicit STT selection shared by file, console and browser adapters."""
from research.disc_assistant.assistant.voice.backends import WhisperCpp
from research.disc_assistant.assistant.voice.resident import WhisperServer
from research.disc_assistant.assistant.voice.gigaam import GigaAMServer


def transcriber(settings):
    provider = settings.get('provider', 'whisper')
    if provider == 'gigaam':
        if settings.get('backend') != 'server':
            raise ValueError('GigaAM requires backend=server')
        return GigaAMServer(settings)
    if provider != 'whisper':
        raise ValueError('unknown speech provider')
    return WhisperServer(settings) if settings.get('backend', 'cli') == 'server' else WhisperCpp(settings)
