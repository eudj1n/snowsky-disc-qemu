"""Opt-in RUNorm host. All three models must already be installed locally."""
import importlib.metadata
import json
from pathlib import Path
import sys

from experiments.disc_assistant.assistant.voice.json_worker import read_message
from experiments.disc_assistant.assistant.voice.text import checked_text, directory_digest


def main():
    output = sys.stdout
    sys.stdout = sys.stderr
    def send(value):
        print(json.dumps(value, ensure_ascii=False), file=output, flush=True)
    settings = read_message(sys.stdin.buffer)
    root = Path(settings['models'])
    if directory_digest(root) != settings['model_sha256']:
        raise ValueError('RUNorm model digest mismatch')
    if importlib.metadata.version('runorm') != '1.1':
        raise ValueError('install the reviewed RUNorm version')
    import torch
    from runorm import RUNorm
    torch.set_num_threads(settings.get('threads', 2))
    torch.set_grad_enabled(False)
    normalizer = RUNorm()
    normalizer.paths.update({key: str(root / key) for key in ('small', 'tagger', 'kirillizator')})
    normalizer.load(model_size='small', device='cpu')
    send({'ready': True})
    while (request := read_message(sys.stdin.buffer)) is not None:
        text = checked_text(request['text'], 1000)
        with torch.inference_mode():
            normalized = normalizer.norm(text)
        send({'text': checked_text(normalized)})


if __name__ == '__main__':
    main()
