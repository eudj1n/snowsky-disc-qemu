#!/usr/bin/env python3
"""Async FiiO Link client over the emulator WebSocket bridge (requires aiohttp)."""
import argparse
import asyncio
import contextlib
import json
from aiohttp import ClientSession, ClientTimeout, WSMsgType
from fiio_link import Frames, frame


class WSClient:
    def __init__(self, url='ws://127.0.0.1:12103/api/websocket', timeout=8):
        self.url, self.timeout = url, timeout
        self.pending = asyncio.Queue(maxsize=256)
        self.error = None
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        self.session = ClientSession(timeout=ClientTimeout(total=self.timeout))
        try:
            self.ws = await self.session.ws_connect(self.url, heartbeat=20, max_msg_size=65535)
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

    async def event(self):
        if self.error:
            raise self.error
        result = await asyncio.wait_for(self.pending.get(), self.timeout)
        if result is None:
            raise self.error or ConnectionError('WebSocket closed')
        return result

    async def request(self, tag, payload=b''):
        async with self.lock:
            while not self.pending.empty():
                self.pending.get_nowait()
            if self.error:
                raise self.error
            async with asyncio.timeout(self.timeout):
                await self.send(tag, payload)
                while True:
                    reply_tag, reply = await self.event()
                    if reply_tag == 'a' + tag[1:].lower():
                        return reply

    async def handshake(self):
        return (await self.request('0599', '0000')).decode('ascii')

    async def settings(self):
        return json.loads(await self.request('0501'))

    async def tracks(self, offset=0):
        if type(offset) is not int or not 0 <= offset <= 65535:
            raise ValueError('offset outside 0..65535')
        reply = await self.request('0401', f'{offset:04X}')
        return {'total': int(reply[:4], 16), 'items': json.loads(reply[4:])}

    async def now_playing(self):
        result = json.loads(await self.request('0202'))
        if isinstance(result.get('song'), str):
            result['song'] = json.loads(result['song'])
        return result

    async def set_volume(self, value):
        if type(value) is not int or not 0 <= value <= 120:
            raise ValueError('volume outside 0..120')
        await self.send('0502', f'{value:04X}')

    async def play_pause(self):
        await self.send('0201', '0000')

    async def play_all(self):
        await self.send('0101', '0001')


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
