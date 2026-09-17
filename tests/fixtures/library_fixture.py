"""Generated genre/album/folder overlaps for disposable library acceptance."""
from pathlib import Path
import subprocess

from tests.fixtures.fixture import NAMES

FOLDER = 'Library CI Ё'
# Same album across artists/genres; same artist/genre across albums; nested folders.
# Filename differs from TITLE so tests cannot confuse directory and catalog rows.
TRACKS = (
    ('A/01.flac', 'Library Alpha', 'Shared Album', 'Genre Ё', 'Artist Ё'),
    ('A/02.flac', 'Library Beta', 'Shared Album', 'Genre Ё', 'Artist Ё'),
    ('B/03.flac', 'Library Gamma', 'Shared Album', 'Genre Other', 'Other Artist'),
    ('A/Nested/04.flac', 'Library Delta', 'Second Album', 'Genre Ё', 'Artist Ё'),
    ('B/05.flac', 'Library Epsilon', 'Third Album', 'Genre Other', 'Other Artist'),
)


def generate(sd):
    sd = Path(sd)
    folder = sd / FOLDER
    folder.mkdir()  # Refuse to overwrite an earlier/user fixture.
    for relative, title, album, genre, artist in TRACKS:
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['sox', str(sd / 'Кириллица Ё й' / NAMES[0]),
                        '--add-comment', 'ARTIST=' + artist,
                        '--add-comment', 'TITLE=' + title,
                        '--add-comment', 'ALBUM=' + album,
                        '--add-comment', 'GENRE=' + genre, str(target)], check=True)
    (folder / 'Empty').mkdir()
    return folder
