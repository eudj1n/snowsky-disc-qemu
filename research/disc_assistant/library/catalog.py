"""Read-only V2.57 catalog observation. Positional rows are snapshot identities."""
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    title: str
    artist: str
    album: str
    position: int
    raw: dict


from controller.catalog import CatalogChanged, CatalogReader as PageReader


class CatalogReader(PageReader):
    def read_once(self):
        root = self.rows('all/song')
        groups = self.rows('album')
        names = [r['name'] for r in groups]
        if len(set(names)) != len(names):
            raise ValueError('duplicate album selectors cannot be resolved safely')
        tracks = []
        for album in names:
            for row in self.rows('album/song', album=album):
                tracks.append(Track(row['name'], row['author'], album, row['pos'], row))
                if len(tracks) > self.max_tracks:
                    raise ValueError('catalog exceeds track limit')
        # Compare multiplicities: same title/artist is NOT proof of one recording.
        if Counter((r['name'], r['author']) for r in root) != Counter((t.title, t.artist) for t in tracks):
            raise CatalogChanged('album membership does not match the complete root catalog')
        return root, groups, tracks

    def read_stable(self):
        first = self.read_once()
        if first != self.read_once():
            raise CatalogChanged('catalog changed between full reads; retry once the device is idle')
        return first[2]
