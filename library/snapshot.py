"""Offline snapshot projections; names are never used to merge recordings."""
from collections import OrderedDict


class Snapshot:
    def __init__(self, generation, entries):
        self.generation = generation
        self.entries = entries

    def tracks(self, album=None, artist=None):
        return [row for row in self.entries
                if (album is None or row['album'] == album)
                and (artist is None or row['artist'] == artist)]

    def groups(self, field, *, artist=None):
        groups = OrderedDict()
        for row in self.tracks(artist=artist):
            group = groups.setdefault(row[field], {'name': row[field], 'count': 0, 'artists': []})
            group['count'] += 1
            if row['artist'] and row['artist'] not in group['artists']:
                group['artists'].append(row['artist'])
        return list(groups.values())

    def selection(self, ordinal, *, artist=None):
        if type(ordinal) is not int or not 0 <= ordinal < len(self.entries):
            raise ValueError('snapshot position outside bounds')
        selected = self.entries[ordinal]
        if artist is not None and selected['artist'] != artist:
            raise ValueError('snapshot artist scope changed')
        tracks = self.tracks(album=selected['album'], artist=artist)
        index = next(i for i, row in enumerate(tracks) if row['ordinal'] == ordinal)
        rows = [dict(pos=i, name=row['title'], author=row['artist']) for i, row in enumerate(tracks)]
        return selected['album'], rows, index
