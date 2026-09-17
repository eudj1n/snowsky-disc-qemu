#!/usr/bin/env python3
"""Small, dependency-free FiiO Link client. Defaults to the local emulator only."""
import argparse
from controller.compatibility import require
import json
import select
import socket
import time
from controller.fiio_settings import setting_query, setting_command, setting_value, peq_payload, peq_value
from controller.fiio_playlist import playlist_command, verify_playlist
from controller.fiio_library import (genre_command, verify_genre, folder_command, verify_folder,
                          artist_command, verify_artist)


def frame(tag, payload=b''):
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    if len(tag) != 4 or any(c not in '0123456789abcdefABCDEF' for c in tag):
        raise ValueError('tag must have four hex digits')
    if len(payload) > 65535 - 8:
        raise ValueError('frame too large')
    return tag.encode('ascii') + f'{8 + len(payload):04X}'.encode() + payload


def hex_value(value, maximum=65535, width=4):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'value outside 0..{maximum}')
    return f'{value:0{width}X}'


def list_payload(list_type, name=None, *, indexed=False):
    allowed = (1, 2, 3, 6) if indexed else (1, 2, 3)
    if type(list_type) is not int or list_type not in allowed:
        raise ValueError('unsupported list type')
    if list_type in (2, 3):
        if not isinstance(name, str) or not name or '\0' in name or len(name.encode('utf-8')) > 255:
            raise ValueError('artist/album requires a name of 1..255 UTF-8 bytes without NUL')
    elif name is not None:
        raise ValueError('this list type takes no name')
    return hex_value(list_type) + (name or '')


def index_payload(index, list_type=1, name=None):
    # This is a zero-based position in the selected list, NOT a catalog song ID.
    return hex_value(index) + list_payload(list_type, name, indexed=True)


def library_request(category, offset=0, name=None):
    tags = {'tracks': '0401', 'artists': '0402', 'albums': '0403',
            'genres': '0404', 'queue': '0406',
            'artist_tracks': '0412', 'album_tracks': '0413', 'playlist_tracks': '0415'}
    if category not in tags:
        raise ValueError('unsupported library category')
    suffix = ''
    if category.endswith('_tracks'):
        if not isinstance(name, str) or not name or '\0' in name or len(name.encode()) > 255:
            raise ValueError('named list requires 1..255 UTF-8 bytes without NUL')
        suffix = name
    elif name is not None:
        raise ValueError('this category takes no name')
    return tags[category], hex_value(offset) + suffix


def library_page(reply):
    if len(reply) < 4 or any(b not in b'0123456789abcdefABCDEF' for b in reply[:4]):
        raise ValueError('missing library count')
    items = json.loads(reply[4:])
    if not isinstance(items, list):
        raise ValueError('library page must contain an array')
    return {'total': int(reply[:4], 16), 'items': items}


def playback_snapshot(reply):
    # V2.40 can reply with an empty a202 while a favorites selection loads.
    # Absence of a snapshot is not a known stopped/paused state.
    if not reply:
        return {}
    result = json.loads(reply)
    if not isinstance(result, dict):
        raise ValueError('now-playing payload must be an object')
    if isinstance(result.get('song'), str):
        result['song'] = json.loads(result['song'])
    return result


def play_mode_value(reply):
    if len(reply) != 4 or any(b not in b'0123456789abcdefABCDEF' for b in reply):
        raise ValueError('play mode must be four hex digits')
    value = int(reply, 16)
    if value > 4:
        raise ValueError('unsupported DISC play mode')
    return value


class Frames:
    """TCP is a byte stream: handle fragments, coalesced replies and UTF-8 bytes."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= 8:
            header = self.buffer[:8]
            if any(c not in b'0123456789abcdefABCDEF' for c in header):
                raise ValueError(f'invalid header: {bytes(header)!r}')
            size = int(header[4:], 16)
            if size < 8:
                raise ValueError('invalid frame length')
            if len(self.buffer) < size:
                break
            result.append((header[:4].decode().lower(), bytes(self.buffer[8:size])))
            del self.buffer[:size]
        return result


class Client:
    def __init__(self, host='127.0.0.1', port=12100, timeout=8):
        self.socket = socket.create_connection((host, port), timeout)
        self.timeout = timeout
        self.frames = Frames()
        self.pending = []

    def close(self):
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def drain_notifications(self):
        # a202 is both a query reply and an asynchronous state notification.
        # Discard complete events already waiting BEFORE issuing a fresh query.
        self.pending.clear()
        while select.select([self.socket], [], [], 0)[0]:
            data = self.socket.recv(65536)
            if not data:
                raise ConnectionError('player closed the connection')
            self.frames.feed(data)

    def event(self, timeout=None):
        """Read one frame without issuing a query or discarding notifications."""
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        previous_timeout = self.socket.gettimeout()
        try:
            while not self.pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('no FiiO Link event')
                self.socket.settimeout(remaining)
                data = self.socket.recv(65536)
                if not data:
                    raise ConnectionError('player closed the connection')
                self.pending.extend(self.frames.feed(data))
            return self.pending.pop(0)
        finally:
            self.socket.settimeout(previous_timeout)

    def request(self, tag, payload=b'', *, expected=None):
        self.drain_notifications()
        self.socket.sendall(frame(tag, payload))
        expected = expected or 'a' + tag[1:].lower()
        deadline = time.monotonic() + self.timeout
        while True:
            pending, self.pending = self.pending, []
            for i, (reply_tag, reply) in enumerate(pending):
                if reply_tag == expected:
                    self.pending = pending[i + 1:]
                    return reply
                # Unrelated asynchronous notifications are deliberately discarded.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'no {expected} reply')
            self.socket.settimeout(remaining)
            data = self.socket.recv(65536)
            if not data:
                raise ConnectionError('player closed the connection')
            self.pending.extend(self.frames.feed(data))

    def handshake(self):
        return self.request('0599', '0000').decode('ascii')

    def settings(self):
        return json.loads(self.request('0501'))

    def now_playing(self):
        return playback_snapshot(self.request('0202'))

    def play_pause(self):
        # 0201 -> FUN_004e477c -> FUN_00424b2c(0, action); action 0 toggles.
        self.socket.sendall(frame('0201', '0000'))

    def next_track(self):
        self.socket.sendall(frame('0201', '0001'))

    def previous_track(self):
        # At >10 seconds stock restarts this track instead of moving backwards.
        self.socket.sendall(frame('0201', '0002'))

    def seek(self, position_ms):
        self.socket.sendall(frame('0103', hex_value(position_ms, 0x7fffffff, 8)))

    def set_play_mode(self, mode):
        self.socket.sendall(frame('0102', hex_value(mode, 4)))

    def play_mode(self):
        # Stock 0105 reads the mode but replies with a102, not a105.
        return play_mode_value(self.request('0105', expected='a102'))

    def scan_library(self):
        """Start stock indexing; observe a60a status and a622 count events."""
        self.socket.sendall(frame('0622', '0000'))

    def cancel_library_scan(self):
        """Request cooperative cancellation (verified V2.57); no ack or rollback.

        Send once on the connection observing the scan. Do not query/drain here:
        queued a60a/a622 events must remain available to the scan observer.
        """
        self.socket.sendall(frame('0622', '0001'))

    def reset_library(self, *, confirm=False):
        """Destructively reset the V2.57 index/favorites, not files or settings.

        Caller must serialize against scans/edits and refresh stale catalogs and
        queue state. No acknowledgement, retry, rescan or factory-reset fallback.
        """
        if confirm is not True:
            raise ValueError('library reset discards index and favorites; confirm=True required')
        self.socket.sendall(frame('0621', '0000'))

    def device_setting(self, name):
        return setting_value(name, self.request(setting_query(name)))

    def set_device_setting(self, name, value):
        command = setting_command(name, value)
        if name == 'bt_source_codec' and self.device_setting('work_mode') != 8:
            raise ValueError('select local playback before changing Bluetooth source codec')
        self.socket.sendall(frame(*command))

    def peq(self):
        return peq_value(self.request('0628'))

    def set_peq(self, bands):
        payload = peq_payload(bands)
        if self.device_setting('eq_type') not in range(160, 170):
            raise ValueError('select a user EQ preset before editing PEQ')
        self.socket.sendall(frame('0678', payload))

    def play_index(self, index, list_type=1, name=None):
        payload = index_payload(index, list_type, name)
        if list_type == 6:
            version = self.settings()['soc_version']
            require(version, 'favorite_positions')
        self.socket.sendall(frame('0100', payload))

    def play_queue_index(self, index):
        """Select a zero-based position in the current queue, with a fresh bounds check.

        The queue can still change between query and selection; Link has no revision
        token. Never replay this command after reconnecting or reuse a cached count.
        """
        position = hex_value(index)
        if index >= self.library('queue')['total']:
            raise ValueError('position outside the current queue')
        self.socket.sendall(frame('0100', position + '0000'))

    def play_playlist(self, position, index=None, *, http, expected_name):
        """Play a custom list, or its zero-based track index, after fresh HTTP checks.

        Requires a reviewed playlist contract and HTTPClient for this device. expected_name is
        the displayed list name, not a persistent identity. No automatic retry.
        """
        command = playlist_command(position, index, expected_name)
        version = self.settings().get('soc_version')
        require(version, 'playlist_playback')
        verify_playlist(http, position, index, expected_name)
        self.socket.sendall(frame(*command))

    def set_volume(self, value):
        if type(value) is not int or not 0 <= value <= 120:
            raise ValueError('volume outside 0..120')
        # 0502 -> 004e4744 -> callback 0088cc44 -> 004e0fdc (DAC + UI + DB).
        self.socket.sendall(frame('0502', f'{value:04X}'))

    def play_genre(self, genre, index=None, *, album=None, http):
        """Play genre tracks, optionally scoped to an album, with a reviewed contract."""
        command = genre_command(genre, index, album)
        version = self.settings().get('soc_version')
        require(version, 'genre_playback')
        verify_genre(http, genre, index, album)
        self.socket.sendall(frame(*command))

    def play_artist(self, artist, index=None, *, album=None, http):
        """Play an artist, or an artist-scoped album/track, after fresh HTTP checks.

        Indexed type-7 selection requires an album. HTTP must target this device;
        serialize edits and never replay an uncertain selection.
        """
        command = artist_command(artist, index, album)
        version = self.settings().get('soc_version')
        require(version, 'artist_playback')
        verify_artist(http, artist, index, album)
        self.socket.sendall(frame(*command))

    def play_folder(self, path, index=None, *, http, expected_name=None):
        """Play a folder or its displayed position (including directory rows)."""
        command = folder_command(path, index, expected_name)
        version = self.settings().get('soc_version')
        require(version, 'folder_playback')
        verify_folder(http, path, index, expected_name)
        self.socket.sendall(frame(*command))

    def play_all(self, list_type=1, name=None):
        # 0101 -> 004e4cb4 -> comm_play_all(list_type=1), indexed local library.
        # Type 0 reuses the current queue and fails if LIST_SONG_0 is absent.
        self.socket.sendall(frame('0101', list_payload(list_type, name)))

    def library(self, category='tracks', offset=0, name=None):
        return library_page(self.request(*library_request(category, offset, name)))

    def tracks(self, offset=0):
        return self.library('tracks', offset)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=12100)
    parser.add_argument('--play-pause', action='store_true', help='toggle the selected track')
    parser.add_argument('--volume', type=int, choices=range(121), metavar='0..120')
    navigation = parser.add_mutually_exclusive_group()
    navigation.add_argument('--play-all', action='store_true', help='start the selected indexed list')
    navigation.add_argument('--next', action='store_true', help='next track')
    navigation.add_argument('--previous', action='store_true', help='previous track, or restart after 10 seconds')
    parser.add_argument('--seek-ms', type=int, help='seek in milliseconds (stock rounds down to seconds)')
    parser.add_argument('--play-mode', type=int, choices=range(5), help='0 list once, 1 random, 2 repeat one, 3 repeat list, 4 single once')
    navigation.add_argument('--play-index', type=int, help='zero-based list position, not song ID')
    parser.add_argument('--list-type', type=int, choices=(1, 2, 3, 6), default=1,
                        help='1 all tracks, 2 artist, 3 album, 6 favorites (index only)')
    parser.add_argument('--name', help='exact artist/album name for list types 2/3')
    args = parser.parse_args()
    try:
        if args.play_index is not None:
            index_payload(args.play_index, args.list_type, args.name)
        elif args.play_all:
            list_payload(args.list_type, args.name)
        elif args.name is not None or args.list_type != 1:
            parser.error('--list-type/--name require --play-index or --play-all')
        if args.seek_ms is not None:
            hex_value(args.seek_ms, 0x7fffffff, 8)
    except ValueError as error:
        parser.error(str(error))
    with Client(args.host, args.port) as client:
        result = {'protocol': client.handshake()}
        if args.volume is not None:
            client.set_volume(args.volume)
            time.sleep(0.2)
        if args.play_all:
            client.play_all(args.list_type, args.name)
            time.sleep(0.2)
        if args.play_index is not None:
            client.play_index(args.play_index, args.list_type, args.name)
            time.sleep(0.2)
        if args.next:
            client.next_track()
        if args.previous:
            client.previous_track()
        if args.seek_ms is not None:
            client.seek(args.seek_ms)
        if args.play_mode is not None:
            client.set_play_mode(args.play_mode)
        if args.play_pause:
            client.play_pause()
            time.sleep(0.5)
        result['settings'] = client.settings()
        result['tracks'] = client.tracks()
        try:
            result['now_playing'] = client.now_playing()
        except TimeoutError:
            # Stock V2.40 may send nothing before the first track is selected.
            result['now_playing'] = None
            result['now_playing_note'] = 'No reply (select a track in Browse files first).'
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
