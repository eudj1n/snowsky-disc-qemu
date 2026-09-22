"""Synthetic metadata only; no user catalog or firmware input."""
from collections import Counter
from library.catalog import Track


TRACKS = [
    Track('Numb', 'Linkin Park', 'Meteora', 0, {'pos': 0, 'name': 'Numb', 'author': 'Linkin Park'}),
    Track('Numb', 'Linkin Park', 'Live', 0, {'pos': 0, 'name': 'Numb', 'author': 'Linkin Park'}),
    Track('Numb', 'Other Artist', 'Other Album', 0, {'pos': 0, 'name': 'Numb', 'author': 'Other Artist'}),
    Track('In the End', 'Linkin Park', 'Hybrid Theory', 0, {'pos': 0, 'name': 'In the End', 'author': 'Linkin Park'}),
    Track('Тишина', 'Артист Ё', 'Альбом', 0, {'pos': 0, 'name': 'Тишина', 'author': 'Артист Ё'}),
    Track('Cue entry', 'Cue Artist', 'Cue Album', 0, {'pos': 0, 'name': 'Cue entry', 'author': 'Cue Artist', 'id': 7}),
    Track('Cue entry', 'Cue Artist', 'Cue Album', 1, {'pos': 1, 'name': 'Cue entry', 'author': 'Cue Artist', 'id': 7}),
]
ALIASES = {'artists': {'Linkin Park': ['линкин парк']}, 'titles': {'Numb': ['намб']}}


class Catalog:
    def __init__(self, tracks=TRACKS):
        self.tracks = tracks
        self.calls = []
        self.change = None

    def catalog(self, category, offset=0, limit=200, **filters):
        self.calls.append((category, offset, limit, filters))
        if category == 'all/song':
            rows = [dict(t.raw, pos=i) for i, t in enumerate(self.tracks)]
        elif category == 'album':
            counts = Counter(t.album for t in self.tracks)
            rows = [dict(pos=i, name=name, count=count) for i, (name, count) in enumerate(counts.items())]
        elif category in ('artist/song', 'artist/album/song'):
            selected = [t for t in self.tracks if t.artist == filters['artist'] and
                        ('album' not in filters or t.album == filters['album'])]
            rows = [dict(t.raw, pos=i) for i, t in enumerate(selected)]
        elif category == 'album/song':
            rows = [dict(t.raw) for t in self.tracks if t.album == filters['album']]
        else:
            raise AssertionError(category)
        page = {'total': len(rows), 'items': rows[offset:offset+limit]}
        if self.change:
            self.change(category, offset, page)
        return page
