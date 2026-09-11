#!/usr/bin/env python3
"""Small, dependency-free FiiO Link client. Defaults to the local emulator only."""
import argparse
import json
import select
import socket
import time


def frame(tag, payload=b''):
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    if len(tag) != 4 or any(c not in '0123456789abcdefABCDEF' for c in tag):
        raise ValueError('tag must have four hex digits')
    if len(payload) > 65535 - 8:
        raise ValueError('frame too large')
    return tag.encode('ascii') + f'{8 + len(payload):04X}'.encode() + payload


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

    def request(self, tag, payload=b''):
        self.drain_notifications()
        self.socket.sendall(frame(tag, payload))
        expected = 'a' + tag[1:].lower()
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
        result = json.loads(self.request('0202'))
        if isinstance(result.get('song'), str):
            result['song'] = json.loads(result['song'])
        return result

    def play_pause(self):
        # 0201 -> FUN_004e477c -> FUN_00424b2c(0, action); action 0 toggles.
        self.socket.sendall(frame('0201', '0000'))

    def set_volume(self, value):
        if type(value) is not int or not 0 <= value <= 120:
            raise ValueError('volume outside 0..120')
        # 0502 -> 004e4744 -> callback 0088cc44 -> 004e0fdc (DAC + UI + DB).
        self.socket.sendall(frame('0502', f'{value:04X}'))

    def play_all(self):
        # 0101 -> 004e4cb4 -> comm_play_all(list_type=1), indexed local library.
        # Type 0 reuses the current queue and fails if LIST_SONG_0 is absent.
        self.socket.sendall(frame('0101', '0001'))

    def tracks(self, offset=0):
        if not 0 <= offset <= 65535:
            raise ValueError('offset outside 0..65535')
        reply = self.request('0401', f'{offset:04X}')
        return {'total': int(reply[:4], 16), 'items': json.loads(reply[4:])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=12100)
    parser.add_argument('--play-pause', action='store_true', help='toggle the selected track')
    parser.add_argument('--volume', type=int, choices=range(121), metavar='0..120')
    parser.add_argument('--play-all', action='store_true', help='start the indexed local library')
    args = parser.parse_args()
    with Client(args.host, args.port) as client:
        result = {'protocol': client.handshake()}
        if args.volume is not None:
            client.set_volume(args.volume)
            time.sleep(0.2)
        if args.play_all:
            client.play_all()
            time.sleep(0.2)
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
