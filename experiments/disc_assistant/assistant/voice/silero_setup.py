"""Explicit optional Silero model/runtime setup. Never called by speech requests."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

from experiments.disc_assistant.assistant.voice.adapters.tts.silero import MODEL_SHA256
MODEL_URL = 'https://models.silero.ai/models/tts/ru/v5_5_ru.pt'


def verify(path):
    with path.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != MODEL_SHA256:
            raise ValueError('Silero model SHA-256 mismatch; existing files were not replaced')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('~/disc-speech/silero'))
    parser.add_argument('--model-only', action='store_true')
    args = parser.parse_args()
    root = args.root.expanduser().absolute()
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'v5_5_ru.pt'
    if target.exists():
        verify(target)
    else:
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            download = Path(temporary) / target.name
            subprocess.run(['curl', '-fL', '--retry', '2', '--max-time', '900', '-o', str(download), MODEL_URL], check=True)
            verify(download)
            download.rename(target)
    if not args.model_only:
        if sys.version_info[:2] != (3, 12):
            parser.error('use Python 3.12 for the reviewed optional environment')
        environment = root / '.venv'
        if not environment.exists():
            venv.create(environment, with_pip=True)
        python = environment / 'bin/python'
        subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                        str(Path(__file__).parent / 'requirements/silero.txt')], check=True)
    print(f'Installed v5_5_ru: {MODEL_SHA256}\nWeights: CC BY-NC-SA 4.0 (separate from project MIT license).')


if __name__ == '__main__':
    main()
