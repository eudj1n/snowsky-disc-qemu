import base64
import hashlib
import unittest
from unittest.mock import Mock, patch
from probe_websocket import probe


class UpgradeTests(unittest.TestCase):
    def check(self, status=101, upgrade='websocket', connection='keep-alive, Upgrade', accept=True):
        sock = Mock()
        def response():
            key = sock.request.call_args.kwargs['headers']['Sec-WebSocket-Key']
            headers = {'Upgrade': upgrade, 'Connection': connection,
                       'Sec-WebSocket-Accept': base64.b64encode(hashlib.sha1(
                           (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                       if accept else 'wrong'}
            return Mock(status=status, getheader=lambda name, default=None: headers.get(name, default))
        sock.getresponse.side_effect = response
        with patch('probe_websocket.http.client.HTTPConnection', return_value=sock):
            result = probe()
        sock.close.assert_called_once()
        return result['websocket']

    def test_valid_upgrade(self):
        self.assertTrue(self.check())

    def test_empty_ok_is_not_websocket(self):
        self.assertFalse(self.check(status=200))

    def test_rejects_invalid_accept_or_headers(self):
        self.assertFalse(self.check(accept=False))
        self.assertFalse(self.check(upgrade='h2c'))
        self.assertFalse(self.check(connection='keep-alive'))

    def test_closes_on_network_error(self):
        sock = Mock()
        sock.request.side_effect = TimeoutError
        with patch('probe_websocket.http.client.HTTPConnection', return_value=sock):
            with self.assertRaises(TimeoutError):
                probe()
        sock.close.assert_called_once()
