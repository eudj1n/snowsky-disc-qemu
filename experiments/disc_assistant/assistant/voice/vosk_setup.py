"""Explicit optional Vosk TTS installation, outside Git and outside request handling."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import venv
import zipfile

from experiments.disc_assistant.assistant.voice.vosk_model import MODEL, ARCHIVE_SHA256, verify


def extract(archive, destination):
    """Reject traversal, links, duplicate entries and unexpectedly large archives."""
    with zipfile.ZipFile(archive) as bundle:
        names = set()
        if sum(item.file_size for item in bundle.infolist()) > 3 * 1024**3:
            raise ValueError('oversized Vosk archive')
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != MODEL
                    or '\\' in item.filename or item.filename in names or stat.S_ISLNK(mode)):
                raise ValueError('unsafe Vosk archive entry')
            names.add(item.filename)
        bundle.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('~/disc-speech/vosk-tts'))
    parser.add_argument('--archive', type=Path, help='reuse an already downloaded pinned archive')
    parser.add_argument('--model-only', action='store_true')
    args = parser.parse_args()
    if not args.model_only and sys.version_info[:2] != (3, 12):
        parser.error('use Python 3.12 for the reviewed optional environment')
    root = args.root.expanduser().absolute()
    root.mkdir(parents=True, exist_ok=True)
    target = root / MODEL
    if target.exists():
        verify(target)
    else:
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            work = Path(temporary)
            archive = args.archive.expanduser().absolute() if args.archive else work / 'model.zip'
            if not args.archive:
                subprocess.run(['curl', '-fL', '--retry', '2', '--max-time', '1800', '-o', str(archive),
                                f'https://alphacephei.com/vosk/models/{MODEL}.zip'], check=True)
            with archive.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != ARCHIVE_SHA256:
                    raise ValueError('Vosk archive digest mismatch; existing files were not replaced')
            extract(archive, work / 'extracted')
            candidate = work / 'extracted' / MODEL
            verify(candidate)
            candidate.rename(target)
    if not args.model_only:
        environment = root / '.venv'
        if not environment.exists():
            venv.create(environment, with_pip=True)
        subprocess.run([str(environment / 'bin/python'), '-m', 'pip', 'install', '-r',
                        str(Path(__file__).parent / 'requirements/vosk-tts.txt')], check=True)
    print(f'Installed {MODEL}: {ARCHIVE_SHA256}')


if __name__ == '__main__':
    main()
