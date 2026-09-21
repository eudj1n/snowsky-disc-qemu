import asyncio
import contextlib
import socket
import unittest
from unittest.mock import AsyncMock, Mock, patch

from controller.bridge.lan_bridge import Proxy, http_ready, sender, announce, run
from controller.fiio_discovery import PAYLOAD, GROUP, PORT


class LanBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.servers = []
        self.proxy = None
        self.writers = []

    async def asyncTearDown(self):
        for server in self.servers:
            server.close()
        if self.proxy:
            await self.proxy.close()
        for writer in self.writers:
            writer.close()
            await writer.wait_closed()
        # Recent asyncio versions wait for accepted connections too. Close the
        # owned clients/proxy before awaiting listener shutdown, not afterward.
        for server in self.servers:
            await server.wait_closed()

    async def server(self, handler):
        server = await asyncio.start_server(handler, '127.0.0.1', 0)
        self.servers.append(server)
        return server.sockets[0].getsockname()[1]

    async def connect(self, port):
        reader, writer = await asyncio.open_connection('127.0.0.1', port)
        self.writers.append(writer)
        return reader, writer

    async def test_exact_bidirectional_bytes_and_half_close(self):
        received = []
        async def upstream(reader, writer):
            received.append(await reader.read())
            writer.write(b'\xff\x00response')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        upstream_port = await self.server(upstream)
        self.proxy = Proxy('127.0.0.1', http_port=upstream_port)
        port = await self.server(lambda r, w: self.proxy.handle(r, w, 'http'))
        reader, writer = await self.connect(port)
        writer.write(b'\0\xffrequest')
        await writer.drain()
        writer.write_eof()
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b'\xff\x00response')
        self.assertEqual(received, [b'\0\xffrequest'])

    async def test_non_allowed_peer_never_reaches_upstream(self):
        self.proxy = Proxy('192.0.2.1')
        port = await self.server(lambda r, w: self.proxy.handle(r, w, 'control'))
        reader, _ = await self.connect(port)
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b'')
        self.assertEqual(self.proxy.count['control'], 0)

    async def test_second_control_connection_rejected(self):
        connected = asyncio.Event()
        async def upstream(reader, writer):
            connected.set()
            await reader.read()
            writer.close()
            await writer.wait_closed()
        upstream_port = await self.server(upstream)
        self.proxy = Proxy('127.0.0.1', control_port=upstream_port)
        port = await self.server(lambda r, w: self.proxy.handle(r, w, 'control'))
        await self.connect(port)
        await asyncio.wait_for(connected.wait(), 2)
        second, _ = await self.connect(port)
        self.assertEqual(await asyncio.wait_for(second.read(), 2), b'')
        self.assertEqual(self.proxy.count['control'], 1)

    async def test_readiness_uses_only_stock_http_root(self):
        requests = []
        async def upstream(reader, writer):
            requests.append(await reader.readuntil(b'\r\n\r\n'))
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        port = await self.server(upstream)
        self.assertTrue(await http_ready(port))
        self.assertEqual(requests, [b'GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n'])

    async def test_readiness_rejects_non_http(self):
        async def upstream(reader, writer):
            await reader.readuntil(b'\r\n\r\n')
            writer.write(b'not stock HTTP\r\n\r\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        self.assertFalse(await http_ready(await self.server(upstream)))

    async def test_failed_upstream_releases_control_slot(self):
        self.proxy = Proxy('127.0.0.1')
        reader, writer = Mock(), Mock()
        writer.get_extra_info.return_value = ('127.0.0.1', 1)
        writer.wait_closed = AsyncMock()
        with patch('controller.bridge.lan_bridge.asyncio.open_connection', AsyncMock(side_effect=OSError('offline'))):
            await self.proxy.handle(reader, writer, 'control')
        self.assertEqual(self.proxy.count['control'], 0)
        self.assertFalse(self.proxy.tasks)
        writer.close.assert_called_once()

    async def test_quiet_client_times_out_even_with_server_notifications_then_reconnects(self):
        closed = asyncio.Queue()
        async def upstream(reader, writer):
            try:
                # Active upstream does not reset the OTHER pump's read deadline.
                while not reader.at_eof():
                    writer.write(b'tick')
                    await writer.drain()
                    await asyncio.sleep(.005)
            except OSError:
                pass
            finally:
                writer.close()
                # The proxy timeout can reset this still-writing peer. Report
                # closure even if wait_closed re-raises that expected reset.
                with contextlib.suppress(ConnectionError):
                    await writer.wait_closed()
                closed.put_nowait(True)
        port_upstream = await self.server(upstream)
        self.proxy = Proxy('127.0.0.1', control_port=port_upstream)
        port = await self.server(lambda r, w: self.proxy.handle(r, w, 'control'))
        with patch('controller.bridge.lan_bridge.READ_IDLE_TIMEOUT', .08):
            for _ in range(2):
                reader, _ = await self.connect(port)
                received = await asyncio.wait_for(reader.read(), 2)
                self.assertTrue(received and received.replace(b'tick', b'') == b'')
                await asyncio.wait_for(closed.get(), 2)
                # finally can finish just after the peer sees EOF.
                for _ in range(100):
                    if self.proxy.count['control'] == 0:
                        break
                    await asyncio.sleep(.005)
                self.assertEqual(self.proxy.count['control'], 0)
                self.assertFalse(self.proxy.tasks)

    async def test_connection_during_readiness_suppresses_announcement(self):
        proxy = Proxy('127.0.0.1')
        async def ready(port):
            proxy.count['control'] = 1
            return True
        loop = Mock(sock_sendto=AsyncMock())
        with patch('controller.bridge.lan_bridge.http_ready', ready), \
             patch('controller.bridge.lan_bridge.asyncio.get_running_loop', return_value=loop), \
             patch('controller.bridge.lan_bridge.asyncio.sleep', AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await announce(Mock(), proxy)
        loop.sock_sendto.assert_not_called()

    async def test_run_shutdown_closes_proxy_before_waiting_for_accepted_connections(self):
        connections_closed = asyncio.Event()
        proxy = Mock()
        proxy.close = AsyncMock(side_effect=connections_closed.set)
        servers = [Mock(), Mock()]
        for server in servers:
            server.wait_closed = AsyncMock(side_effect=connections_closed.wait)
        # Model asyncio's listener shutdown contract without publishing LAN ports
        # or announcements. An accepted connection survives until proxy.close().
        with patch('controller.bridge.lan_bridge.Proxy', return_value=proxy), \
             patch('controller.bridge.lan_bridge.asyncio.start_server', AsyncMock(side_effect=servers)), \
             patch('controller.bridge.lan_bridge.sender'), \
             patch('controller.bridge.lan_bridge.announce', AsyncMock()):
            async with asyncio.timeout(1):
                await run('127.0.0.1', '127.0.0.1', .01)
        proxy.close.assert_awaited_once()
        for server in servers:
            server.close.assert_called_once()
            server.wait_closed.assert_awaited_once()

    async def test_announcement_gates_and_payload(self):
        for count, ready, expected in ((0, True, True), (1, True, False), (0, False, False)):
            proxy = Proxy('127.0.0.1')
            proxy.count['control'] = count
            sock = Mock()
            loop = Mock(sock_sendto=AsyncMock())
            with patch('controller.bridge.lan_bridge.http_ready', AsyncMock(return_value=ready)), \
                 patch('controller.bridge.lan_bridge.asyncio.get_running_loop', return_value=loop), \
                 patch('controller.bridge.lan_bridge.asyncio.sleep', AsyncMock(side_effect=asyncio.CancelledError)):
                with self.assertRaises(asyncio.CancelledError):
                    await announce(sock, proxy)
            self.assertEqual(loop.sock_sendto.called, expected)
            if expected:
                loop.sock_sendto.assert_awaited_once_with(sock, PAYLOAD, (GROUP, PORT))

    def test_sender_uses_selected_interface_and_ttl_one(self):
        with patch('controller.bridge.lan_bridge.socket.socket'):
            sock = sender('192.0.2.1')
            sock.bind.assert_called_once_with(('192.0.2.1', 0))
            sock.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                           socket.inet_aton('192.0.2.1'))
