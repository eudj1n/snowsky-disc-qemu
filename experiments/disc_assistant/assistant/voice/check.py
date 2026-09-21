"""Opt-in, device-free fixed-audio adapter matrix; never executes recognized text."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.voice.backends import transcribe_audio, synthesize_text
from experiments.disc_assistant.assistant.voice.files import load_audio
from experiments.disc_assistant.assistant.voice.runtime import SpeechRuntime


class ProbeTrace:
    """No application storage, device session, catalog, or raw-audio persistence."""
    def __init__(self):
        self.id = uuid4().hex
    def event(self, phase, value):
        pass


async def check(config, names, *, audio=None, text=None, repeats=2):
    # Fixed-audio model comparisons exclude private catalog prompts explicitly.
    config = replace(config, speech={**config.speech, 'catalog_hints': False})
    runtime = SpeechRuntime(config)
    rows = []
    try:
        for name in names:
            if name not in runtime.specs:
                raise ValueError('unknown provider instance')
            kind = runtime.specs[name].kind
            if (kind == 'stt' and audio is None) or (kind == 'tts' and text is None):
                raise ValueError('STT needs --audio; TTS needs --text')
            for repetition in range(repeats):
                row = {'instance':name, 'kind':kind, 'repetition':repetition,
                       'locale':config.locale, 'catalog_hints':False}
                try:
                    handle = runtime.get(name)
                    if kind == 'stt':
                        row['result'] = await transcribe_audio(config,audio,ProbeTrace(),provider=handle)
                    else:
                        _, row['result'] = await synthesize_text(config,text,ProbeTrace(),provider=handle)
                    row['status'] = 'ok'
                except Exception as exc:
                    # Preserve a failed row; do not retry the same failing provider.
                    row.update(status='error', error_type=type(exc).__name__)
                    rows.append(row)
                    break
                rows.append(row)
    finally:
        await runtime.aclose()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='~/disc-assistant.toml')
    parser.add_argument('--provider', action='append', required=True, help='configured instance; repeat for a sequential matrix')
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--text')
    parser.add_argument('--locale', default='ru')
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error('repeats must be 1..20')
    config = replace(load(Path(args.config).expanduser()),locale=args.locale)
    audio = load_audio(args.audio.expanduser()) if args.audio else None
    rows = asyncio.run(check(config,args.provider,audio=audio,text=args.text,repeats=args.repeats))
    print(json.dumps({'contract_version':1,'scope':'adapter integration, not speech quality acceptance','rows':rows},ensure_ascii=False,indent=2))
    return int(any(r['status']!='ok' for r in rows))


if __name__ == '__main__':
    raise SystemExit(main())
