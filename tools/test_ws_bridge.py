import asyncio
import unittest
from unittest.mock import patch

try:
    from aiohttp import ClientSession, WSServerHandshakeError, WSMsgType, web
    from aiohttp.test_utils import TestServer
    from ws_bridge import Bridge
    from fiio_ws import WSClient
except ImportError:
    ClientSession = None
from fiio_link import Frames, frame


@unittest.skipUnless(ClientSession, 'aiohttp required; run the full suite in the Docker image')
class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.writers, self.received = set(), []
        async def player(reader, writer):
            self.writers.add(writer)
            parser = Frames()
            try:
                while data := await reader.read(65536):
                    for tag, payload in parser.feed(data):
                        self.received.append((tag, payload))
                        reply = b'0306' if tag == '0599' else payload
                        writer.write(frame('a' + tag[1:], reply))
                        await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                self.writers.discard(writer)
        self.tcp = await asyncio.start_server(player, '127.0.0.1', 0)
        async def http(request):
            self.http_seen = (request.method, request.raw_path, await request.read(), dict(request.headers))
            return web.Response(status=201, body=self.http_seen[2] or b'stock',
                headers={'Connection': 'X-Remove', 'X-Remove': 'private', 'X-Stock': 'yes'})
        app = web.Application()
        app.router.add_route('*', '/{path:.*}', http)
        self.http = TestServer(app)
        await self.http.start_server()
        self.bridge = Bridge(tcp_port=self.tcp.sockets[0].getsockname()[1], http_port=self.http.port)
        self.server = TestServer(self.bridge.app())
        await self.server.start_server()
        self.url = str(self.server.make_url('/api/websocket'))
        self.client = ClientSession()

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        await self.http.close()
        for writer in list(self.writers):
            writer.close()
        self.tcp.close()
        await self.tcp.wait_closed()

    async def test_handshake_and_bridge_identity(self):
        async with self.client.ws_connect(self.url) as ws:
            self.assertEqual(ws._response.headers['X-FiiO-Transport'], 'emulator-ws-to-tcp')
            await ws.send_str('0599000C0000')
            self.assertEqual((await ws.receive()).data, 'a599000C0306')
        self.assertEqual(self.received, [('0599', b'0000')])

    async def test_split_coalesced_utf8_and_binary_records(self):
        async with self.client.ws_connect(self.url) as ws:
            packet = frame('0501', '音楽')
            await ws.send_bytes(packet[:9])
            await ws.send_bytes(packet[9:] + frame('0202', b'\xff'))
            self.assertEqual((await ws.receive()).data, frame('a501', '音楽').decode())
            reply = await ws.receive()
            self.assertEqual(reply.type, WSMsgType.BINARY)
            self.assertEqual(reply.data, frame('a202', b'\xff'))

    async def test_tcp_fragmentation_and_unsolicited_notifications(self):
        async with self.client.ws_connect(self.url) as ws:
            writer = next(iter(self.writers))
            writer.write(b'a20200')
            await writer.drain()
            writer.write(b'0C0001a599000C0306')
            await writer.drain()
            self.assertEqual((await ws.receive()).data, 'a202000C0001')
            self.assertEqual((await ws.receive()).data, 'a599000C0306')

    async def test_second_ws_client_is_rejected(self):
        async with self.client.ws_connect(self.url):
            with self.assertRaises(WSServerHandshakeError) as error:
                await self.client.ws_connect(self.url)
            self.assertEqual(error.exception.status, 409)

    async def test_origin_and_host_guards(self):
        for headers in ({'Origin': 'https://evil.example'}, {'Origin': 'null'},
                        {'Host': 'evil.example:12103'}):
            with self.assertRaises(WSServerHandshakeError) as error:
                await self.client.ws_connect(self.url, headers=headers)
            self.assertEqual(error.exception.status, 403)
        async with self.client.ws_connect(self.url, origin='http://localhost:8080') as ws:
            await ws.send_str('0599000C0000')
            self.assertEqual((await ws.receive()).data, 'a599000C0306')

    async def test_invalid_and_oversized_messages_close_without_forwarding(self):
        for packet, code in (('xxxxxxxx', 1007), ('x' * 65536, 1009)):
            async with self.client.ws_connect(self.url) as ws:
                await ws.send_str(packet)
                reply = await ws.receive()
                self.assertEqual(reply.type, WSMsgType.CLOSE)
                self.assertEqual(reply.data, code)
            await self.wait_released()
        self.assertEqual(self.received, [])

    async def wait_released(self):
        async with asyncio.timeout(3):
            while self.bridge.active:
                await asyncio.sleep(.01)

    async def test_disconnect_releases_channel_for_reconnect(self):
        async with self.client.ws_connect(self.url):
            pass
        await self.wait_released()
        async with WSClient(self.url) as client:
            self.assertEqual(await client.handshake(), '0306')

    async def test_upstream_close_reaches_client(self):
        async with self.client.ws_connect(self.url) as ws:
            next(iter(self.writers)).close()
            reply = await ws.receive()
            self.assertEqual(reply.type, WSMsgType.CLOSE)
            self.assertEqual(reply.data, 1011)

    async def test_unavailable_upstream_does_not_claim_upgrade(self):
        self.tcp.close()
        await self.tcp.wait_closed()
        with self.assertRaises(WSServerHandshakeError) as error:
            await self.client.ws_connect(self.url)
        self.assertEqual(error.exception.status, 503)
        self.assertFalse(self.bridge.active)

    async def test_non_upgrade_on_ws_path_is_bad_request(self):
        async with self.client.get(self.url) as reply:
            self.assertEqual(reply.status, 400)

    async def test_short_tcp_handover_refusal_is_retried(self):
        original = asyncio.open_connection
        attempts = 0
        async def connect(*args):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionRefusedError
            return await original(*args)
        with patch('ws_bridge.asyncio.open_connection', side_effect=connect):
            async with WSClient(self.url) as client:
                self.assertEqual(await client.handshake(), '0306')
        self.assertEqual(attempts, 3)

    async def test_health_and_inspector_do_not_open_tcp(self):
        async with self.client.get(self.server.make_url('/bridge/health')) as reply:
            self.assertEqual((await reply.json())['transport'], 'emulator-ws-to-tcp')
        async with self.client.get(self.server.make_url('/bridge/')) as reply:
            self.assertIn('NOT STOCK WEBSOCKET', await reply.text())
        self.assertFalse(self.writers)

    async def test_http_upstream_unavailable(self):
        await self.http.close()
        async with self.client.get(self.server.make_url('/api/hi')) as reply:
            self.assertEqual(reply.status, 502)

    async def test_compressed_http_request_is_not_silently_mangled(self):
        import gzip
        async with self.client.post(self.server.make_url('/audio/'), data=gzip.compress(b'audio'),
                                    headers={'Content-Encoding': 'gzip'}) as reply:
            self.assertEqual(reply.status, 415)

    async def test_http_proxy_preserves_path_body_and_end_to_end_headers(self):
        url = self.server.make_url('/dir/a%20b?start-pos=2')
        async with self.client.post(url, data=b'body\x00\xff',
                headers={'Connection': 'X-Remove', 'X-Remove': 'secret', 'X-Keep': 'yes'}) as reply:
            self.assertEqual(reply.status, 201)
            self.assertEqual(await reply.read(), b'body\x00\xff')
            self.assertEqual(reply.headers['X-Stock'], 'yes')
            self.assertNotIn('X-Remove', reply.headers)
        method, path, body, headers = self.http_seen
        self.assertEqual((method, path, body), ('POST', '/dir/a%20b?start-pos=2', b'body\x00\xff'))
        self.assertEqual(headers['X-Keep'], 'yes')
        self.assertNotIn('X-Remove', headers)

    async def test_client_discards_queued_old_replies(self):
        async with WSClient(self.url) as client:
            client.enqueue(('a599', b'OLD'))
            self.assertEqual(await client.handshake(), '0306')

    async def test_client_timeout_and_close_are_reported(self):
        async with WSClient(self.url, timeout=.05) as client:
            with self.assertRaises(TimeoutError):
                await client.event()
            next(iter(self.writers)).close()
            with self.assertRaises(ConnectionError):
                await client.event()

    async def test_rfc6455_masked_fragmentation_with_interleaved_ping(self):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.server.port)
        try:
            writer.write((f'GET /api/websocket HTTP/1.1\r\nHost: localhost:{self.server.port}\r\n'
                          'Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\n'
                          'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n').encode())
            await writer.drain()
            headers = await reader.readuntil(b'\r\n\r\n')
            self.assertIn(b'101 Switching Protocols', headers)
            self.assertIn(b's3pPLMBiTxaQ9kYGzzhZRbK+xOo=', headers)
            def masked(opcode, payload):
                mask = b'\x01\x02\x03\x04'
                return bytes([opcode, 128 | len(payload)]) + mask + bytes(
                    byte ^ mask[i % 4] for i, byte in enumerate(payload))
            writer.write(masked(1, b'059900') + masked(0x89, b'ping') + masked(0x80, b'0C0000'))
            await writer.drain()
            replies = {}
            async with asyncio.timeout(3):
                for _ in range(2):
                    opcode, size = await reader.readexactly(2)
                    self.assertLess(size, 126)
                    replies[opcode] = await reader.readexactly(size)
            self.assertEqual(replies, {0x8a: b'ping', 0x81: b'a599000C0306'})
        finally:
            writer.close()
            await writer.wait_closed()
