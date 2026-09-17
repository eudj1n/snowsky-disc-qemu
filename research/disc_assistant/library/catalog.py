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


class CatalogChanged(ValueError):
    pass


class CatalogReader:
    def __init__(self, http, *, page_size=200, max_tracks=100000, max_requests=10000):
        self.http = http
        self.page_size = page_size
        self.max_tracks = max_tracks
        self.remaining = max_requests

    def rows(self, category, **filters):
        result, expected = [], None
        while True:
            if self.remaining <= 0:
                raise ValueError('catalog request budget exhausted; previous snapshot retained')
            self.remaining -= 1
            page = self.http.catalog(category, offset=len(result), limit=self.page_size, **filters)
            total, items = page.get('total'), page.get('items')
            if type(total) is not int or not 0 <= total <= self.max_tracks:
                raise ValueError('missing or invalid catalog total')
            if expected is not None and total != expected:
                raise CatalogChanged('catalog total changed during pagination')
            expected = total
            if not isinstance(items, list) or len(items) > self.page_size or len(result) + len(items) > total:
                raise ValueError('invalid catalog page size')
            for position, row in enumerate(items, len(result)):
                if (not isinstance(row, dict) or type(row.get('pos')) is not int
                        or row['pos'] != position or not isinstance(row.get('name'), str)
                        or not row['name']):
                    raise ValueError('invalid catalog row or non-contiguous positions')
                if category.endswith('/song') and not isinstance(row.get('author'), str):
                    raise ValueError('track row is missing its author')
            result.extend(items)
            if len(result) == total:
                return result
            if not items:
                raise CatalogChanged('catalog pagination stopped before its declared total')

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
