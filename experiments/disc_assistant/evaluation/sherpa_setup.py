"""Install the optional CPU speech experiment outside the checkout; no device access."""
import argparse
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import urllib.request
import venv

from experiments.disc_assistant.assistant.voice.sherpa_model import (
    MODEL_ID, REVISION, BASE_URL, FILES, digest, verify_models,
)

REPO = Path(__file__).resolve().parents[3]


def outside_repo(value):
    path = Path(value).expanduser().resolve()
    if path.is_relative_to(REPO):
        raise ValueError('environment, models and reports must remain outside the checkout')
    return path


def install_models(root):
    import certifi
    context = ssl.create_default_context()
    context.load_verify_locations(certifi.where())
    directory = root / MODEL_ID
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, expected in FILES.items():
        target = directory / name
        if target.exists():
            if digest(target) != expected:
                raise ValueError(f'checksum mismatch: {name}; existing files are not replaced')
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = target.with_suffix(target.suffix + '.partial')
        print(f'Downloading {name}', flush=True)
        created = False
        try:
            with urllib.request.urlopen(f'{BASE_URL}/{name}', context=context, timeout=60) as response:
                with partial.open('xb') as stream:
                    created = True
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
            if digest(partial) != expected:
                raise ValueError(f'download checksum mismatch: {name}')
            partial.rename(target)
        finally:
            # Only remove this invocation's partial on ordinary failure.
            # A pre-existing partial is deliberately not overwritten by open('xb').
            if created:
                partial.unlink(missing_ok=True)
    verify_models(directory)
    (root / 'model-provenance.json').write_text(json.dumps({
        'model': MODEL_ID, 'revision': REVISION, 'source': BASE_URL, 'sha256': FILES,
        'scope': 'RU streaming transducer; INT8 encoder/joiner, FP32 decoder; CPU',
    }, indent=2) + '\n')
    print(f'Ready: {root}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='~/disc-speech/sherpa-onnx')
    parser.add_argument('--models-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11+ required')
    root = outside_repo(args.root)
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.models_only:
        install_models(root)
        return
    env = root / '.venv'
    python = env / 'bin/python'
    if not env.exists():
        venv.create(env, with_pip=True)
    if not python.is_file():
        raise ValueError('existing environment is incomplete; choose a new root')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                    str(Path(__file__).with_name('requirements-sherpa.txt'))], check=True)
    freeze = subprocess.check_output([str(python), '-m', 'pip', 'freeze'], text=True)
    (root / 'installed-requirements.txt').write_text(freeze)
    subprocess.run([str(python), '-m', 'experiments.disc_assistant.evaluation.sherpa_setup',
                    '--root', str(root), '--models-only'], cwd=REPO, check=True)


if __name__ == '__main__':
    main()
