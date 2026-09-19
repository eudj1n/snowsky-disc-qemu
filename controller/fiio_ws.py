#!/usr/bin/env python3
"""Async FiiO Link client over the emulator WebSocket bridge (requires aiohttp)."""
import argparse
from controller.compatibility import require
import asyncio
import contextlib
import json
from controller.fiio_library import (genre_command, verify_genre, folder_command, verify_folder,
                          artist_command, verify_artist, album_command, verify_album)
from aiohttp import ClientSession, ClientTimeout, WSMsgType
from controller.fiio_link import (Frames, frame, hex_value, list_payload, index_payload,
                       library_request, library_page, playback_snapshot, play_mode_value)
from controller.fiio_settings import setting_query, setting_command, setting_value, peq_payload, peq_value
from controller.fiio_playlist import playlist_command, verify_playlist


class WSClient:
    def __init__(self, url='ws://127.0.0.1:12103/api/websocket', timeout=8, *, host_header=None):
        self.url, self.timeout = url, timeout
        # Disposable CI connects by Docker DNS while retaining the bridge's
        # localhost HTTP authority policy. This does not change server checks.
        self.host_header = host_header
        self.pending = asyncio.Queue(maxsize=256)
        self.error = None
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        self.session = ClientSession(timeout=ClientTimeout(total=self.timeout))
        try:
            headers = {'Host': self.host_header} if self.host_header is not None else None
            self.ws = await self.session.ws_connect(self.url, heartbeat=20, max_msg_size=65535,
                                                   headers=headers)
        except BaseException:
            await self.session.close()
            raise
        self.receiver = asyncio.create_task(self.receive_loop())
        return self

    async def __aexit__(self, *args):
        self.receiver.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.receiver
        await self.ws.close()
        await self.session.close()

    async def receive_loop(self):
        parser = Frames()
        try:
            async for message in self.ws:
                if message.type not in (WSMsgType.TEXT, WSMsgType.BINARY):
                    continue
                data = message.data.encode('utf-8') if message.type == WSMsgType.TEXT else message.data
                for item in parser.feed(data):
                    self.enqueue(item)
            self.error = ConnectionError(f'WebSocket closed: {self.ws.close_code}')
        except (ValueError, OSError) as exc:
            self.error = exc
        finally:
            self.enqueue(None)

    def enqueue(self, item):
        if self.pending.full():
            self.pending.get_nowait()  # bounded notifications; this is a sequential client
        self.pending.put_nowait(item)

    async def send(self, tag, payload=b''):
        async with asyncio.timeout(self.timeout):
            await self.ws.send_str(frame(tag, payload).decode('utf-8'))

    async def event(self, timeout=None):
        if self.error:
            raise self.error
        result = await asyncio.wait_for(self.pending.get(), self.timeout if timeout is None else timeout)
        if result is None:
            raise self.error or ConnectionError('WebSocket closed')
        return result

    async def request(self, tag, payload=b'', *, expected=None):
        async with self.lock:
            while not self.pending.empty():
                self.pending.get_nowait()
            if self.error:
                raise self.error
            async with asyncio.timeout(self.timeout):
                await self.send(tag, payload)
                while True:
                    reply_tag, reply = await self.event()
                    if reply_tag == (expected or 'a' + tag[1:].lower()):
                        return reply

    async def handshake(self):
        return (await self.request('0599', '0000')).decode('ascii')

    async def settings(self):
        return json.loads(await self.request('0501'))

    async def tracks(self, offset=0):
        return await self.library('tracks', offset)

    async def library(self, category='tracks', offset=0, name=None):
        return library_page(await self.request(*library_request(category, offset, name)))

    async def now_playing(self):
        return playback_snapshot(await self.request('0202'))

    async def set_volume(self, value):
        if type(value) is not int or not 0 <= value <= 120:
            raise ValueError('volume outside 0..120')
        await self.send('0502', f'{value:04X}')

    async def play_pause(self):
        await self.send('0201', '0000')

    async def next_track(self):
        await self.send('0201', '0001')

    async def previous_track(self):
        await self.send('0201', '0002')

    async def seek(self, position_ms):
        await self.send('0103', hex_value(position_ms, 0x7fffffff, 8))

    async def set_play_mode(self, mode):
        await self.send('0102', hex_value(mode, 4))

    async def play_mode(self):
        return play_mode_value(await self.request('0105', expected='a102'))

    async def scan_library(self):
        await self.send('0622', '0000')

    async def cancel_library_scan(self):
        """Request cancellation once; preserves queued scan events, no rollback."""
        await self.send('0622', '0001')

    async def reset_library(self, *, confirm=False):
        """V2.57 index/favorites reset; see Client.reset_library and LIBRARY_RESET.md."""
        if confirm is not True:
            raise ValueError('library reset discards index and favorites; confirm=True required')
        await self.send('0621', '0000')

    async def device_setting(self, name):
        return setting_value(name, await self.request(setting_query(name)))

    async def set_device_setting(self, name, value):
        command = setting_command(name, value)
        if name == 'bt_source_codec' and await self.device_setting('work_mode') != 8:
            raise ValueError('select local playback before changing Bluetooth source codec')
        await self.send(*command)

    async def peq(self):
        return peq_value(await self.request('0628'))

    async def set_peq(self, bands):
        payload = peq_payload(bands)
        if await self.device_setting('eq_type') not in range(160, 170):
            raise ValueError('select a user EQ preset before editing PEQ')
        await self.send('0678', payload)

    async def play_index(self, index, list_type=1, name=None):
        payload = index_payload(index, list_type, name)
        if list_type == 6:
            version = (await self.settings())['soc_version']
            require(version, 'favorite_positions')
        await self.send('0100', payload)

    async def play_queue_index(self, index):
        """Select the current queue after a fresh bounds check; no mutation retry."""
        position = hex_value(index)
        if index >= (await self.library('queue'))['total']:
            raise ValueError('position outside the current queue')
        await self.send('0100', position + '0000')

    async def play_all(self, list_type=1, name=None):
        await self.send('0101', list_payload(list_type, name))

    async def play_playlist(self, position, index=None, *, http, expected_name):
        """Custom list/track selection with fresh HTTP preflight; never replay."""
        command = playlist_command(position, index, expected_name)
        version = (await self.settings()).get('soc_version')
        require(version, 'playlist_playback')
        await asyncio.to_thread(verify_playlist, http, position, index, expected_name)
        await self.send(*command)

    async def play_genre(self, genre, index=None, *, album=None, http):
        command = genre_command(genre, index, album)
        version = (await self.settings()).get('soc_version')
        require(version, 'genre_playback')
        await asyncio.to_thread(verify_genre, http, genre, index, album)
        await self.send(*command)

    async def play_artist(self, artist, index=None, *, album=None, http):
        """Type-7 artist/scoped-album playback; same guards as the TCP client."""
        command = artist_command(artist, index, album)
        version = (await self.settings()).get('soc_version')
        require(version, 'artist_playback')
        await asyncio.to_thread(verify_artist, http, artist, index, album)
        await self.send(*command)

    async def play_album(self, album, index=None, *, http):
        """Play a complete named album after fresh source bounds verification."""
        command = album_command(album, index)
        version = (await self.settings()).get('soc_version')
        require(version, 'album_playback')
        await asyncio.to_thread(verify_album, http, album, index)
        await self.send(*command)

    async def play_folder(self, path, index=None, *, http, expected_name=None):
        command = folder_command(path, index, expected_name)
        version = (await self.settings()).get('soc_version')
        require(version, 'folder_playback')
        await asyncio.to_thread(verify_folder, http, path, index, expected_name)
        await self.send(*command)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='ws://127.0.0.1:12103/api/websocket')
    args = parser.parse_args()
    async with WSClient(args.url) as client:
        result = {'transport': 'emulator-ws-to-tcp', 'protocol': await client.handshake(),
                  'settings': await client.settings(), 'tracks': await client.tracks()}
        try:
            result['now_playing'] = await client.now_playing()
        except TimeoutError:
            result['now_playing'] = None
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
