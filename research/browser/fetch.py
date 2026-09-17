"""Fetch and verify public prototype dependencies; does not fetch DISC firmware."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / 'work/browser-disc'


def fetch():
    downloads = WORK / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    sources = json.loads(Path(__file__).with_name('sources.json').read_text())
    for name, source in sources.items():
        target = downloads / name
        if not target.exists():
            temporary = target.with_suffix(target.suffix + '.tmp')
            with urllib.request.urlopen(source['url'], timeout=120) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            temporary.rename(target)
        with target.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != source['sha256']:
            raise ValueError(f'SHA-256 mismatch: {name}; refusing to use cached file')
        print(f'Verified {name}', flush=True)
        if name.endswith('.tar.gz'):
            with tarfile.open(target) as archive:
                root = archive.getmembers()[0].name.split('/')[0]
                if not (WORK / root).exists():
                    archive.extractall(WORK, filter='data')


if __name__ == '__main__':
    fetch()
