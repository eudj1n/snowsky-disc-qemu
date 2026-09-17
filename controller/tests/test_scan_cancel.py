import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from controller.fiio_link import Client
from controller.fiio_ws import WSClient


class ScanCancelTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_write_preserves_pending_events_without_query(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.request = Mock(side_effect=AssertionError('must not drain/query during scan'))
        tcp.pending = [('a60a', b'000F'), ('a622', b'0008')]
        tcp.cancel_library_scan()
        tcp.socket.sendall.assert_called_once_with(b'0622000C0001')
        tcp.request.assert_not_called()
        self.assertEqual(tcp.pending, [('a60a', b'000F'), ('a622', b'0008')])

        ws = WSClient()
        ws.send = AsyncMock()
        ws.request = AsyncMock(side_effect=AssertionError('must not drain/query during scan'))
        ws.pending.put_nowait(('a60a', b'000F'))
        ws.pending.put_nowait(('a622', b'0008'))
        await ws.cancel_library_scan()
        ws.send.assert_awaited_once_with('0622', '0001')
        ws.request.assert_not_awaited()
        self.assertEqual(await ws.event(), ('a60a', b'000F'))
        self.assertEqual(await ws.event(), ('a622', b'0008'))

    async def test_uncertain_write_is_not_retried(self):
        tcp = Client.__new__(Client)
        tcp.socket = Mock()
        tcp.socket.sendall.side_effect = TimeoutError('uncertain send')
        with self.assertRaises(TimeoutError):
            tcp.cancel_library_scan()
        tcp.socket.sendall.assert_called_once()
        ws = WSClient()
        ws.send = AsyncMock(side_effect=TimeoutError('uncertain send'))
        with self.assertRaises(TimeoutError):
            await ws.cancel_library_scan()
        ws.send.assert_awaited_once()

    async def test_cancel_does_not_send_start_reset_or_wait_for_ack(self):
        ws = WSClient()
        ws.send = AsyncMock()
        ws.event = AsyncMock(side_effect=AssertionError('no distinct cancel ack'))
        await asyncio.wait_for(ws.cancel_library_scan(), .5)
        ws.send.assert_awaited_once_with('0622', '0001')
        ws.event.assert_not_awaited()
