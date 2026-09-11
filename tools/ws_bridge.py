#!/usr/bin/env python3
"""Local FiiO Link WebSocket/TCP adapter, NOT a stock firmware WebSocket service."""
import argparse
import asyncio
import contextlib
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, DummyCookieJar, WSMsgType, web
from multidict import CIMultiDict
from yarl import URL
from fiio_link import Frames, frame

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade', 'host'}
ORIGINS = {f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (8080, 12103)}


def end_to_end(headers):
    blocked = HOP_HEADERS | {s.strip().lower() for s in headers.get('Connection', '').split(',')}
    return CIMultiDict((k, v) for k, v in headers.items() if k.lower() not in blocked)


class Bridge:
    def __init__(self, upstream='127.0.0.1', tcp_port=12100, http_port=12103):
        self.upstream, self.tcp_port = upstream, tcp_port
        self.http_url = f'http://{upstream}:{http_port}'
        self.active = False
        self.websockets = set()

    async def lifecycle(self, app):
        # Never persist cookies between independent HTTP clients or decompress proxy bodies.
        async with ClientSession(cookie_jar=DummyCookieJar(), auto_decompress=False,
                                 timeout=ClientTimeout(total=None, sock_connect=3, sock_read=30)) as session:
            self.session = session
            yield

    async def shutdown(self, app):
        await asyncio.gather(*(ws.close(code=1001, message=b'bridge stopping')
                               for ws in list(self.websockets)))

    async def connect_tcp(self):
        # Stock closes its listening socket while serving a client, then recreates it.
        # A short handover can therefore refuse connect even after the old peer closed.
        # Retry only the connection, never replay a command or hide a mid-session drop.
        while True:
            try:
                return await asyncio.open_connection(self.upstream, self.tcp_port)
            except ConnectionRefusedError:
                await asyncio.sleep(.1)

    async def handle(self, request):
        # Localhost publication alone doesn't stop a hostile web page from opening WS.
        if urlsplit('//'+request.host).hostname not in ('localhost', '127.0.0.1'):
            raise web.HTTPForbidden(text='Local Host required\n')
        origin = request.headers.get('Origin')
        if origin is not None and origin not in ORIGINS:
            raise web.HTTPForbidden(text='Origin not allowed\n')
        if request.path == '/bridge/health':
            return web.json_response({'transport': 'emulator-ws-to-tcp', 'active': self.active,
                                      'upstream': f'{self.upstream}:{self.tcp_port}'})
        if request.path == '/bridge/':
            return web.Response(text=Path(__file__).with_name('ws_console.html').read_text(),
                                content_type='text/html')
        if request.path == '/api/websocket':
            return await self.websocket(request)
        if request.headers.get('Upgrade'):
            raise web.HTTPNotFound(text='WebSocket path is /api/websocket\n')
        return await self.http(request)

    async def websocket(self, request):
        ws = web.WebSocketResponse(heartbeat=20, timeout=2, compress=False, max_msg_size=65535)
        if request.method != 'GET' or request.can_read_body or not ws.can_prepare(request).ok:
            raise web.HTTPBadRequest(text='A bodyless RFC6455 GET upgrade is required\n')
        if self.active:
            raise web.HTTPConflict(text='FiiO Link bridge already has a client\n')
        self.active = True  # no await before reserving the single-client firmware channel
        writer = None
        pumps = []
        try:
            try:
                reader, writer = await asyncio.wait_for(
                    self.connect_tcp(), 3)
            except (OSError, asyncio.TimeoutError):
                raise web.HTTPServiceUnavailable(text='Player TCP unavailable; boot the guest\n')
            ws.headers['X-FiiO-Transport'] = 'emulator-ws-to-tcp'
            await ws.prepare(request)
            self.websockets.add(ws)
            pumps = [asyncio.create_task(self.from_ws(ws, writer)),
                     asyncio.create_task(self.from_tcp(ws, reader))]
            done, _ = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ValueError, UnicodeError):
            await ws.close(code=1007, message=b'invalid FiiO Link frame')
        except (OSError, ClientError, asyncio.TimeoutError):
            if ws.prepared:
                await ws.close(code=1011, message=b'upstream disconnected')
            else:
                raise
        finally:
            for task in pumps:
                task.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            if writer:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()
            if ws.prepared:
                await ws.close()
            self.websockets.discard(ws)
            self.active = False
        return ws

    async def from_ws(self, ws, writer):
        frames = Frames()
        async for message in ws:
            if message.type not in (WSMsgType.TEXT, WSMsgType.BINARY):
                continue
            data = message.data.encode('utf-8') if message.type == WSMsgType.TEXT else message.data
            # Accept split/coalesced application records, but never pass invalid headers to firmware.
            for tag, payload in frames.feed(data):
                writer.write(frame(tag, payload))
                await asyncio.wait_for(writer.drain(), 10)

    async def from_tcp(self, ws, reader):
        frames = Frames()
        while True:
            data = await reader.read(65536)
            if not data:
                await ws.close(code=1011, message=b'player TCP closed')
                return
            for tag, payload in frames.feed(data):
                packet = frame(tag, payload)
                try:
                    text = packet.decode('utf-8')
                except UnicodeError:
                    await asyncio.wait_for(ws.send_bytes(packet), 10)
                else:
                    await asyncio.wait_for(ws.send_str(text), 10)

    async def http(self, request):
        # Keep the stock HTTP API on host 12103 too. No arbitrary upstream or redirects.
        target = URL(self.http_url + request.raw_path, encoded=True)
        if request.headers.get('Content-Encoding', 'identity') != 'identity':
            # aiohttp decodes incoming compressed bodies: don't forward stale lengths/encoding.
            raise web.HTTPUnsupportedMediaType(text='Compressed HTTP request bodies are not proxied\n')
        response = None
        try:
            async with self.session.request(request.method, target, headers=end_to_end(request.headers),
                    data=request.content.iter_chunked(65536) if request.can_read_body else None,
                    allow_redirects=False) as reply:
                headers = end_to_end(reply.headers)
                headers['X-FiiO-Transport'] = 'stock-http-via-bridge'
                response = web.StreamResponse(status=reply.status, headers=headers)
                await response.prepare(request)
                async for chunk in reply.content.iter_chunked(65536):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except (ClientError, OSError, asyncio.TimeoutError):
            if response is not None and response.prepared:
                # Headers already went out: terminate the truncated response, not a second HTTP reply.
                if request.transport:
                    request.transport.close()
                return response
            raise web.HTTPBadGateway(text='Stock HTTP unavailable\n')

    def app(self):
        app = web.Application()
        app.cleanup_ctx.append(self.lifecycle)
        app.on_shutdown.append(self.shutdown)
        app.router.add_route('*', '/{path:.*}', self.handle)
        return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=12103)
    parser.add_argument('--upstream', default='127.0.0.1')
    parser.add_argument('--tcp-port', type=int, default=12100)
    parser.add_argument('--http-port', type=int, default=12113)
    args = parser.parse_args()
    web.run_app(Bridge(args.upstream, args.tcp_port, args.http_port).app(),
                host=args.listen, port=args.port, shutdown_timeout=3)
