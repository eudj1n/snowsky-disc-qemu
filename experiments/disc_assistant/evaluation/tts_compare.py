"""Create a local listening page using configured TTS adapters, without a player."""
import argparse
import asyncio
from dataclasses import replace
import html
import json
from pathlib import Path
import tomllib

from experiments.disc_assistant.assistant.config import load
from experiments.disc_assistant.assistant.voice.backends import synthesize_text
from experiments.disc_assistant.assistant.voice.check import ProbeTrace
from experiments.disc_assistant.assistant.voice.runtime import SpeechRuntime

TEXTS = ('Пауза.', 'Громкость 25%.', 'Включаю Ваню Дмитриенко.',
         'Играет Linkin Park — Numb.', 'Найдено 21 совпадение. Уточните исполнителя.',
         'Это нужный альбом?')


def render(rows, texts, output):
    sections = []
    for index, text in enumerate(texts):
        players = []
        for row in rows:
            if row['text_index'] != index:
                continue
            label = html.escape(row.get('label', row['provider']))
            if row['status'] == 'ok':
                metrics = row['metrics']
                source = html.escape(row['audio'], quote=True)
                players.append(f'<div><b>{label}</b><small>{metrics["synthesis_ms"]:.0f} ms · {metrics["sample_rate"]} Hz</small>'
                               f'<audio aria-label="{label}" controls preload="none" src="{source}"></audio></div>')
            else:
                players.append(f'<div>{label}: {html.escape(row["error"])}</div>')
        sections.append(f'<section><h2>{html.escape(text)}</h2><div class="players">{"".join(players)}</div></section>')
    (output / 'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    (output / 'index.html').write_text('''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Сравнение TTS</title>
<style>body{font:16px system-ui;background:#101823;color:#e8edf5;max-width:1100px;margin:40px auto;padding:0 24px}
h1{font-size:32px}h2{font-size:20px}p,small{color:#a7b6c9}section{padding:18px 0;border-top:1px solid #324050}
.players{display:flex;gap:24px;flex-wrap:wrap}.players>div{flex:1;min-width:280px}small{display:block;margin:8px 0}audio{width:100%}</style>
<h1>Сравнение русской озвучки</h1><p>Одинаковые фразы, локальный синтез. Задержка включает нормализацию;
первый вызов также включает загрузку модели. Это проверка интеграции, не оценка качества речи.</p>
''' + ''.join(sections) + '</html>')


async def generate(config, names, texts, output):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    # Complete one provider's corpus and release its models before loading another.
    # Five Vosk voices must not keep five identical large model copies resident.
    for name in names:
        runtime = SpeechRuntime(config)
        try:
            for index, text in enumerate(texts):
                row = {'text': text, 'text_index': index, 'provider': name}
                try:
                    spec = runtime.specs[name]
                    row['label'] = spec.label
                    if spec.kind != 'tts':
                        raise ValueError('select a TTS provider')
                    audio, metrics = await synthesize_text(config, text, ProbeTrace(), provider=runtime.get(name))
                    filename = f'{index:02d}-{name}.wav'
                    (output / filename).write_bytes(audio.data)
                    row.update(status='ok', audio=filename, metrics=metrics)
                except Exception as exc:
                    row.update(status='error', error=type(exc).__name__)
                rows.append(row)
        finally:
            await runtime.aclose()
        render(rows, texts, output)  # Preserve completed providers if a later one is interrupted.
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('~/disc-assistant.toml'))
    parser.add_argument('--profile', action='append', type=Path, default=[], help='merge explicit provider definitions only')
    parser.add_argument('--provider', action='append', required=True)
    parser.add_argument('--text', action='append', help='otherwise use six synthetic RU reply examples')
    parser.add_argument('--output', type=Path, required=True, help='new output directory outside Git')
    args = parser.parse_args()
    config = replace(load(args.config.expanduser()), locale='ru')
    providers = dict(config.voice.get('providers', {}))
    for path in args.profile:
        with path.expanduser().open('rb') as source:
            providers.update(tomllib.load(source)['voice'].get('providers', {}))
    config = replace(config, voice={**config.voice, 'providers': providers})
    rows = asyncio.run(generate(config, args.provider, args.text or TEXTS, args.output.expanduser()))
    print(f'{sum(row["status"] == "ok" for row in rows)}/{len(rows)} samples generated: {args.output}/index.html')
    return int(any(row['status'] != 'ok' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
