"""TTS-only normalization. Original responses and catalog selectors stay exact."""
from dataclasses import replace
import hashlib
from pathlib import Path
import re
import time
from typing import Protocol

from experiments.disc_assistant.assistant.voice.contracts import InvalidSpeech, SpeechAdapter
from experiments.disc_assistant.assistant.voice.json_worker import JsonWorker

REVISION = 'identity-v1'
REVISIONS = {'identity': REVISION, 'ru_numbers': 'ru-numbers-v1', 'runorm': 'runorm-local-v1'}


def prepare(text: str, locale: str) -> str:
    """Compatibility hook. Configured preparation uses NormalizedSynthesizer."""
    return text


class TextNormalizer(Protocol):
    def evidence(self, locale: str | None = None) -> dict: ...
    def available(self) -> bool: ...
    async def normalize(self, text: str, locale: str) -> str: ...
    async def aclose(self) -> None: ...


def checked_text(text, maximum=4000):
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in text)):
        raise InvalidSpeech('invalid normalized speech text')
    return text


def plural(n, forms):
    return forms[2] if 11 <= n % 100 <= 14 else forms[0] if n % 10 == 1 else forms[1] if 2 <= n % 10 <= 4 else forms[2]


def russian_integer(n, *, feminine=False):
    if n == 0:
        return 'ноль'
    if n >= 1000:
        thousands, remainder = divmod(n, 1000)
        return (russian_integer(thousands, feminine=True) + ' ' + plural(thousands, ('тысяча', 'тысячи', 'тысяч'))
                + (' ' + russian_integer(remainder) if remainder else ''))
    units = ('', 'одна' if feminine else 'один', 'две' if feminine else 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять')
    teens = ('десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать')
    tens = ('', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто')
    hundreds = ('', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот')
    return ' '.join(x for x in (hundreds[n // 100], teens[n % 100 - 10] if 10 <= n % 100 < 20 else tens[n % 100 // 10],
                               '' if 10 <= n % 100 < 20 else units[n % 10]) if x)


# Preserve embedded names, signed values, decimals, times, fractions, dates,
# leading-zero identifiers, and tokens adjacent to their separators.
NUMBER = re.compile(r'(?<![\w+\-/.:,])(?:0|[1-9][0-9]{0,5})(?:\s*%)?(?![\w%]|[.,:/\-][0-9])')


def ru_numbers(text):
    def expand(match):
        token = match.group()
        percent = token.endswith('%')
        n = int(token.rstrip('%').strip())
        return russian_integer(n) + (' ' + plural(n, ('процент', 'процента', 'процентов')) if percent else '')
    return NUMBER.sub(expand, text)


def validate(settings):
    if not isinstance(settings, dict) or set(settings) - {'mode', 'python', 'models', 'model_sha256', 'threads', 'timeout'}:
        raise ValueError('invalid TTS normalization settings')
    mode = settings.get('mode', 'identity')
    if not isinstance(mode, str) or mode not in REVISIONS:
        raise ValueError('normalization.mode must be identity, ru_numbers or runorm')
    if mode != 'runorm' and set(settings) - {'mode'}:
        raise ValueError('model settings require normalization.mode=runorm')
    if mode == 'runorm':
        for key in ('python', 'models'):
            if not isinstance(settings.get(key), str) or not Path(settings[key]).expanduser().is_absolute():
                raise ValueError('RUNorm requires absolute python and models paths')
        if not isinstance(settings.get('model_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', settings['model_sha256']):
            raise ValueError('RUNorm requires a model directory digest')
        if type(settings.get('threads', 2)) is not int or not 1 <= settings.get('threads', 2) <= 16:
            raise ValueError('RUNorm threads must be 1..16')
        if type(settings.get('timeout', 120)) not in (int, float) or not 0 < settings.get('timeout', 120) <= 600:
            raise ValueError('RUNorm timeout must be in (0, 600]')
    return settings


def directory_digest(root):
    """Bind offline models including tokenizers/configs, independent of location."""
    root = Path(root)
    digest = hashlib.sha256()
    paths = sorted(p for p in root.rglob('*') if p.is_file() and '.cache' not in p.relative_to(root).parts)
    if not paths:
        raise ValueError('empty RUNorm model directory')
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        with path.open('rb') as stream:
            digest.update(hashlib.file_digest(stream, 'sha256').digest())
    return digest.hexdigest()


class Normalizer:
    def __init__(self, settings):
        self.settings = dict(validate(settings))
        self.mode = settings.get('mode', 'identity')
        self.worker = None
        if self.mode == 'runorm':
            self.worker = JsonWorker(settings['python'],
                'experiments.disc_assistant.assistant.voice.normalizer_worker',
                {**settings, 'models': str(Path(settings['models']).expanduser().absolute())},
                timeout=settings.get('timeout', 120))

    def evidence(self, locale=None):
        value = {'mode': self.mode, 'revision': REVISIONS[self.mode],
                 'applied': self.mode != 'identity' and locale == 'ru'}
        if self.worker is not None:
            value.update(model_sha256=self.settings['model_sha256'], package='runorm==1.1',
                         threads=self.settings.get('threads', 2), latin_policy='upstream transliteration')
        return value

    def available(self):
        return self.worker is None or (self.worker.available() and Path(self.settings['models']).expanduser().is_dir())

    async def normalize(self, text, locale):
        checked_text(text, 1000)
        if locale != 'ru' or self.mode == 'identity':
            return text
        if self.worker is not None:
            result = await self.worker.exchange({'text': text})
            if set(result) != {'text'}:
                raise InvalidSpeech('invalid normalizer response')
            return checked_text(result['text'])
        return checked_text(ru_numbers(text))

    async def aclose(self):
        if self.worker is not None:
            await self.worker.aclose()


class NormalizedSynthesizer(SpeechAdapter):
    """Compose normalization with any v1 TTS factory, including external plugins."""
    def __init__(self, provider, normalizer: TextNormalizer):
        self.provider, self.normalizer = provider, normalizer
        self.info, self.capabilities = provider.info, provider.capabilities
        self.last_normalization = {}

    def available(self):
        return self.provider.available() and self.normalizer.available()

    def evidence(self, locale=None):
        normalization = self.normalizer.evidence(locale)
        return {**self.provider.evidence(locale), 'normalization': normalization,
                'text_preparation': normalization['revision']}

    def result_evidence(self):
        return {**self.provider.result_evidence(), 'normalization_result': self.last_normalization}

    async def prepare(self, locale):
        await self.provider.prepare(locale)

    async def synthesize(self, request):
        started = time.monotonic()
        normalized = checked_text(await self.normalizer.normalize(request.text, request.context.locale))
        self.last_normalization = {**self.normalizer.evidence(request.context.locale),
            'changed': normalized != request.text, 'characters': len(normalized),
            'text_sha256': hashlib.sha256(normalized.encode()).hexdigest(),
            'elapsed_ms': round((time.monotonic() - started) * 1000, 3)}
        return await self.provider.synthesize(replace(request, text=normalized))

    async def aclose(self):
        try:
            await self.normalizer.aclose()
        finally:
            await self.provider.aclose()
