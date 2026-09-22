"""Explicit lazy speech factories. Model settings are separate from adapter identity."""
from dataclasses import dataclass
from importlib import import_module
import inspect
import re

from experiments.disc_assistant.assistant.providers import ProviderInfo
from experiments.disc_assistant.assistant.voice.contracts import Capabilities, CONTRACT_VERSION, InvalidSpeech

BUILTINS = {
    'whisper_cpp': ('stt', 'stt.whisper_cpp:WhisperCpp'),
    'whisper_server': ('stt', 'stt.whisper_server:WhisperServer'),
    'sherpa_onnx': ('stt', 'stt.sherpa_onnx:SherpaTranscriber'),
    'gigaam_server': ('stt', 'stt.gigaam:GigaAMServer'),
    'piper': ('tts', 'tts.piper:PiperSynthesizer'),
    'silero': ('tts', 'tts.silero:SileroSynthesizer'),
    'vosk_tts': ('tts', 'tts.vosk:VoskSynthesizer'),
    'macos_say': ('tts', 'tts.macos_say:MacOSSay'),
}
NAME = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
FACTORY = re.compile(r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$')


@dataclass(frozen=True)
class AdapterSpec:
    kind: str
    adapter: str
    label: str
    settings: dict


def validate_adapter(provider, kind):
    if getattr(provider, 'contract_version', None) != CONTRACT_VERSION:
        raise InvalidSpeech('speech adapter contract version must be 1')
    if type(getattr(provider, 'info', None)) is not ProviderInfo:
        raise InvalidSpeech('speech adapter must declare ProviderInfo')
    info = provider.info
    if not info.name or not info.version or info.execution not in ('local', 'remote'):
        raise InvalidSpeech('invalid speech adapter identity')
    caps = getattr(provider, 'capabilities', None)
    if (type(caps) is not Capabilities or type(caps.vocabulary) is not bool
            or type(caps.max_seconds) is not int or not 1 <= caps.max_seconds <= 120
            or (caps.locales is not None and (type(caps.locales) is not tuple
                or any(not isinstance(s, str) or not s.strip() for s in caps.locales)))):
        raise InvalidSpeech('invalid speech adapter capabilities')
    for method in ('prepare', 'aclose', 'transcribe' if kind == 'stt' else 'synthesize'):
        if not inspect.iscoroutinefunction(getattr(provider, method, None)):
            raise InvalidSpeech(f'speech adapter must implement async {method}')
    for method in ('available', 'evidence', 'result_evidence'):
        if not callable(getattr(provider, method, None)):
            raise InvalidSpeech(f'speech adapter must implement {method}')
    return provider


class Registry:
    def __init__(self, plugins=None):
        self.factories = {}
        # Configuration is trusted local code configuration, never a web request.
        self.plugins = dict(plugins or {})
        for name, target in self.plugins.items():
            if name in BUILTINS or not NAME.fullmatch(name) or not isinstance(target, str) or not FACTORY.fullmatch(target):
                raise ValueError('invalid or reserved speech plugin registration')

    def register(self, name, kind, factory):
        if not NAME.fullmatch(name) or name in BUILTINS or name in self.plugins or name in self.factories:
            raise ValueError('duplicate or reserved speech adapter name')
        if kind not in ('stt', 'tts') or not callable(factory):
            raise ValueError('invalid speech factory')
        self.factories[name] = (kind, factory)

    def create(self, spec):
        if spec.adapter in self.factories:
            kind, factory = self.factories[spec.adapter]
        else:
            if spec.adapter in BUILTINS:
                kind, target = BUILTINS[spec.adapter]
                target = 'experiments.disc_assistant.assistant.voice.adapters.' + target
            elif spec.adapter in self.plugins:
                kind, target = spec.kind, self.plugins[spec.adapter]
            else:
                raise ValueError('unregistered speech adapter')
            module, member = target.split(':')
            factory = getattr(import_module(module), member)
        if kind != spec.kind:
            raise ValueError('speech adapter has the wrong role')
        settings = dict(spec.settings)
        if kind == 'tts':
            from experiments.disc_assistant.assistant.voice.text import Normalizer, NormalizedSynthesizer
            normalizer = Normalizer(settings.pop('normalization', {}))
            provider = validate_adapter(factory(settings), kind)
            return NormalizedSynthesizer(provider, normalizer)
        return validate_adapter(factory(settings), kind)
