"""Generated, tagged 180-second FLACs for Assistant end-to-end scenarios."""
import json
from pathlib import Path
import subprocess
import sys

MANIFEST = Path(__file__).with_name('assistant_scenarios.json')


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for track in json.loads(MANIFEST.read_text())['tracks']:
        target = directory / (track['key'] + '.flac')
        if target.exists():
            raise FileExistsError(target)
        subprocess.run(['sox', '-n', '-r', '8000', '-c', '1', '-b', '16',
                        '--add-comment', 'TITLE=' + track['title'],
                        '--add-comment', 'ARTIST=' + track['artist'],
                        '--add-comment', 'ALBUM=' + track['album'],
                        '--add-comment', 'TRACKNUMBER=' + str(track['number']),
                        str(target), 'synth', '180', 'sine', '440', 'vol', '0.01'], check=True)


if __name__ == '__main__':
    generate(sys.argv[1])
