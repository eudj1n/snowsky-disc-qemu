"""V2.57 artist/genre/folder selectors with fresh HTTP preflight, shared by TCP/WS.

HTTP and Link must target the same device. Positions have no revision token;
serialize browsing/edits and never retry a selection after an uncertain write.
"""
from controller.fiio_http import name_header, sd_path


def position(index):
    if index is not None and (type(index) is not int or not 0 <= index <= 65535):
        raise ValueError('track position outside 0..65535')
    return '' if index is None else f'{index:04X}'


def genre_command(genre, index=None, album=None):
    prefix = position(index)
    name_header(genre)
    if genre == 'unknown_style':
        raise ValueError('reserved unknown-genre token is not supported')
    if album is None and index is not None:
        payload = '000A' + genre
    else:
        if album is None:
            # FiiO Control's whole-genre selector. Do not use this empty-album
            # form for indexed playback: that takes a different stock path.
            album = ''
        else:
            name_header(album)
        # Stock uses sscanf, NOT a JSON parser: quoted/backslash names cannot
        # safely be escaped with json.dumps. Key order and colon spacing matter.
        if any(c in genre + album for c in ('"', '\\')) or album == 'unknown_album':
            raise ValueError('type-8 genre/album names cannot contain quotes/backslashes or reserved tokens')
        payload = '0008' + '{"style":"' + genre + '", "album":"' + album + '"}'
    return ('0101' if index is None else '0100', prefix + payload)


def verify_genre(http, genre, index=None, album=None):
    filters = {'style': genre}
    if album is not None:
        filters['album'] = album
    wanted = 0 if index is None else index
    page = http.catalog('style/song' if album is None else 'style/album/song',
                        offset=wanted, limit=1, **filters)
    checked_row(page, wanted)


def artist_command(artist, index=None, album=None):
    """Captured type-7 selectors; empty album is reviewed for Play all only."""
    prefix = position(index)
    name_header(artist)
    if album is None:
        if index is not None:
            raise ValueError('indexed type-7 playback requires an album')
        album = ''
    else:
        name_header(album)
    # Stock sscanf has the same strict syntax as type 8, not JSON unescaping.
    if (artist == 'unknown_artist' or album == 'unknown_album'
            or any(c in artist + album for c in ('"', '\\'))):
        raise ValueError('type-7 names cannot contain quotes/backslashes or reserved tokens')
    payload = '0007' + '{"artist":"' + artist + '", "album":"' + album + '"}'
    return ('0101' if index is None else '0100', prefix + payload)


def verify_artist(http, artist, index=None, album=None):
    filters = {'artist': artist}
    if album is not None:
        filters['album'] = album
    wanted = 0 if index is None else index
    page = http.catalog('artist/song' if album is None else 'artist/album/song',
                        offset=wanted, limit=1, **filters)
    checked_row(page, wanted)


def checked_row(page, wanted):
    total, rows = page['total'], page['items']
    if type(total) is not int or not 0 <= wanted < total or len(rows) != 1:
        raise ValueError('position outside the current source list')
    row = rows[0]
    if type(row.get('pos')) is not int or row['pos'] != wanted:
        raise ValueError('unexpected source position')
    return row


def folder_command(path, index=None, expected_name=None):
    prefix = position(index)
    path = sd_path(path)
    # Stock appends slash into 512 bytes and treats ANY .m3u substring as a file.
    if len(path.encode()) > 510 or '.m3u' in path.lower():
        raise ValueError('folder path too long or ambiguous with stock M3U handling')
    if index is not None:
        if (not isinstance(expected_name, str) or not expected_name
                or any(ord(c) < 32 for c in expected_name) or '/' in expected_name):
            raise ValueError('indexed folder selection requires the displayed filename')
    elif expected_name is not None:
        raise ValueError('expected filename applies only to indexed selection')
    return ('0101' if index is None else '0100', prefix + '0004' + path)


def verify_folder(http, path, index=None, expected_name=None):
    def playable(row):
        if (row.get('is_dir') is not False or
                any(row.get(flag) is not False for flag in ('is_cue', 'is_m3u', 'is_image'))):
            raise ValueError('select an ordinary audio file; folders/CUE/M3U/images are unsupported')
    if index is not None:
        row = checked_row(http.directory(path, offset=index, limit=1, local=True), index)
        playable(row)
        if row.get('name') != expected_name:
            raise ValueError('directory changed; refresh its position and filename')
        return
    # Stock Play all starts at the first non-directory, not at directory index 0.
    offset = 0
    while True:
        page = http.directory(path, offset=offset, local=True)
        total, rows = page['total'], page['items']
        if type(total) is not int or total <= offset or not rows:
            raise ValueError('folder has no playable entries')
        for i, row in enumerate(rows, offset):
            if type(row.get('pos')) is not int or row['pos'] != i or i >= total:
                raise ValueError('unexpected directory position')
            if row.get('is_dir') is True:
                continue
            playable(row)
            return
        offset += len(rows)


def album_command(album, index=None):
    """Ordinary named album (type 3), distinct from an artist-scoped album."""
    prefix = position(index)
    name_header(album)
    if album == 'unknown_album':
        raise ValueError('reserved unknown album is not supported')
    return ('0101' if index is None else '0100', prefix + '0003' + album)


def verify_album(http, album, index=None):
    wanted = 0 if index is None else index
    checked_row(http.catalog('album/song', offset=wanted, limit=1, album=album), wanted)
