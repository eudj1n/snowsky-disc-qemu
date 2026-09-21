"""Explicit installation of the optional offline RUNorm small pipeline."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

from experiments.disc_assistant.assistant.voice.text import directory_digest

MODELS = {
    'small': ('RUNorm-normalizer-small', '24fa466a3818f14c66b6392965e67b9644ed3136',
              ('added_tokens.json', 'generation_config.json', 'merges.txt', 'vocab.json')),
    'tagger': ('RUNorm-tagger', 'ce379228483424b9bf7cca3175c7777bd53b2945', ('vocab.txt',)),
    'kirillizator': ('RUNorm-kirillizator', 'b130ae67db4b209babec461767bcd2ace74fe88a', ('generation_config.json',)),
}
COMMON = ('README.md', 'config.json', 'pytorch_model.bin', 'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('~/disc-speech/runorm'))
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error('use Python 3.12 for the reviewed optional environment')
    root = args.root.expanduser().absolute()
    root.mkdir(parents=True, exist_ok=True)
    models, manifest = root / 'models', root / 'models.json'
    if models.exists():
        if not manifest.is_file() or directory_digest(models) != json.loads(manifest.read_text())['sha256']:
            raise ValueError('existing RUNorm models differ from manifest; no files replaced')
    else:
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            target = Path(temporary) / 'models'
            jobs = []
            for key, (repo, revision, extra) in MODELS.items():
                destination = target / key
                destination.mkdir(parents=True)
                jobs.extend((f'https://huggingface.co/RUNorm/{repo}/resolve/{revision}/{name}', destination / name)
                            for name in COMMON + extra)
            def download(job):
                url, path = job
                subprocess.run(['curl', '-fsSL', '--retry', '2', '--max-time', '1800', '-o', str(path), url], check=True)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(download, jobs))
            digest = directory_digest(target)
            target.rename(models)
            manifest.write_text(json.dumps({'sha256': digest, 'models': MODELS, 'license': 'Apache-2.0'}, indent=2) + '\n')
    environment = root / '.venv'
    if not environment.exists():
        venv.create(environment, with_pip=True)
    subprocess.run([str(environment / 'bin/python'), '-m', 'pip', 'install', '-r',
                    str(Path(__file__).parent / 'requirements/runorm.txt')], check=True)
    digest = json.loads(manifest.read_text())['sha256']
    print(f'RUNorm small installed; model_sha256 = "{digest}"')


if __name__ == '__main__':
    main()
