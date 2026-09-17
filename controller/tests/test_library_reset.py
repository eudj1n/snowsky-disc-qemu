import unittest
from unittest.mock import AsyncMock, Mock

from controller.fiio_link import Client
from controller.fiio_ws import WSClient


class LibraryResetTests(unittest.IsolatedAsyncioTestCase):
    def clients(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.request = Mock(side_effect=AssertionError('reset must not query'))
        ws = WSClient()
        ws.send = AsyncMock()
        ws.request = AsyncMock(side_effect=AssertionError('reset must not query'))
        return tcp, ws

    async def test_missing_confirmation_rejected_before_io(self):
        tcp, ws = self.clients()
        with self.assertRaises(ValueError):
            tcp.reset_library()
        with self.assertRaises(ValueError):
            await ws.reset_library()
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_awaited()

    async def test_only_literal_true_confirms(self):
        tcp, ws = self.clients()
        for value in (False, None, 0, 1, 'true', 'yes', [], {}, object()):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    tcp.reset_library(confirm=value)
                with self.assertRaises(ValueError):
                    await ws.reset_library(confirm=value)
        tcp.socket.sendall.assert_not_called()
        ws.send.assert_not_awaited()

    async def test_one_dedicated_frame_no_ack_query_or_fallback(self):
        tcp, ws = self.clients()
        tcp.pending = [('a202', b'{}')]
        ws.pending.put_nowait(('a202', b'{}'))
        tcp.reset_library(confirm=True)
        await ws.reset_library(confirm=True)
        tcp.socket.sendall.assert_called_once_with(b'0621000C0000')
        ws.send.assert_awaited_once_with('0621', '0000')
        tcp.request.assert_not_called()
        ws.request.assert_not_awaited()
        self.assertEqual(tcp.pending, [('a202', b'{}')])
        self.assertEqual(await ws.event(), ('a202', b'{}'))

    async def test_uncertain_write_not_retried(self):
        tcp, ws = self.clients()
        tcp.socket.sendall.side_effect = TimeoutError('uncertain send')
        ws.send.side_effect = TimeoutError('uncertain send')
        with self.assertRaises(TimeoutError):
            tcp.reset_library(confirm=True)
        with self.assertRaises(TimeoutError):
            await ws.reset_library(confirm=True)
        tcp.socket.sendall.assert_called_once()
        ws.send.assert_awaited_once()
