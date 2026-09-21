"""Response synthesis and delivery evidence, separate from command execution."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
import json
import time

from experiments.disc_assistant.assistant.journal import Journal, utcnow, durable_write
from experiments.disc_assistant.assistant.speech import SynthesisRequest, SpeechContext, SpeechUnavailable, InvalidSpeech
from experiments.disc_assistant.assistant.voice.files import pcm_wav, audio_details
from experiments.disc_assistant.assistant.voice.piper import PiperSynthesizer


def delivery_event(config, request_id, phase, payload):
    if not config.journal_enabled:
        return
    with Journal(config) as journal:
        row = journal.db.execute('SELECT started_at FROM requests WHERE id=? AND device=?',
                                 (request_id, config.device_key)).fetchone()
        if row is None:
            return
        elapsed = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(row['started_at'])).total_seconds() * 1000)
        with durable_write(journal.db):
            journal.db.execute('''INSERT INTO request_events(request_id,phase,observed_at,elapsed_ms,payload_json)
                VALUES(?,?,?,?,?)''', (request_id, phase, utcnow(), round(elapsed, 3), json.dumps(payload)))


class ReplySynthesizer:
    def __init__(self, provider_factory=PiperSynthesizer):
        self.provider_factory = provider_factory
        self.cache = OrderedDict()

    async def synthesize(self, config, result):
        response = result.get('response', {})
        if not response.get('speak') or not response.get('text'):
            raise InvalidSpeech('this response is silent')
        if config.tts.get('backend') != 'piper':
            raise SpeechUnavailable('Piper is not configured; run setup --all')
        text, locale = response['text'], response['language']
        if not isinstance(text, str) or not 1 <= len(text) <= 1000:
            raise InvalidSpeech('invalid response text')
        provider = self.provider_factory(config.tts)
        evidence = await asyncio.to_thread(provider.evidence, locale)
        key = hashlib.sha256(json.dumps([text, locale, asdict(provider.info), evidence], sort_keys=True).encode()).hexdigest()
        started = time.monotonic()
        cached = key in self.cache
        if cached:
            audio = self.cache.pop(key)
        else:
            audio = await provider.synthesize(SynthesisRequest(text, SpeechContext(locale, result['request_id'])))
            checked = pcm_wav(audio.data, max_seconds=60)
            if (audio.media_type, audio.sample_rate, audio.channels) != ('audio/wav', checked.sample_rate, 1):
                raise InvalidSpeech('invalid synthesized audio metadata')
            if audio_details(audio)['digital_silence']:
                raise InvalidSpeech('Piper returned digital silence')
        self.cache[key] = audio
        while len(self.cache) > 8 or sum(len(a.data) for a in self.cache.values()) > 16 * 1024 * 1024:
            self.cache.popitem(last=False)
        metadata = {'provider': asdict(provider.info), 'locale': locale, **evidence,
                    'cache_hit': cached, 'synthesis_ms': round((time.monotonic() - started) * 1000, 3),
                    **audio_details(audio)}
        return audio, metadata
