"""Device identity, not the emulator environment, selects the protocol contract."""
import os
import unittest
from unittest.mock import Mock, patch, AsyncMock

from controller.compatibility import CONTRACTS, require
from controller.fiio_link import Client
from controller.fiio_ws import WSClient


class CompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def test_unknown_and_malformed_versions_are_not_coerced(self):
        for version in (240, 258, 999, None, '257', 257.0, True):
            for feature in CONTRACTS[257] - {'network_check'}:
                with self.subTest(version=version, feature=feature), self.assertRaises(ValueError):
                    require(version, feature)
        with self.assertRaises(ValueError):
            require(257, 'unreviewed_feature')

    async def test_unverified_device_never_sends_selection_tcp_or_ws(self):
        with patch.dict(os.environ, {'FW_VERSION': '2.57'}):
            tcp = Client.__new__(Client)
            tcp.settings = Mock(return_value={'soc_version': 258})
            tcp.socket = Mock()
            ws = WSClient.__new__(WSClient)
            ws.settings = AsyncMock(return_value={'soc_version': 258})
            ws.send = AsyncMock()
            http = Mock()
            for method, args, kwargs in [
                ('play_index', (0, 6), {}),
                ('play_playlist', (0,), {'http': http, 'expected_name': 'Test'}),
                ('play_genre', ('Jazz',), {'http': http}),
                ('play_artist', ('Artist',), {'http': http}),
                ('play_folder', ('/tmp/sdcard',), {'http': http}),
            ]:
                with self.subTest(method=method):
                    with self.assertRaises(ValueError):
                        getattr(tcp, method)(*args, **kwargs)
                    with self.assertRaises(ValueError):
                        await getattr(ws, method)(*args, **kwargs)
            tcp.socket.sendall.assert_not_called()
            ws.send.assert_not_called()
            self.assertEqual(http.mock_calls, [])

    def test_local_firmware_does_not_disable_reviewed_physical_device(self):
        with patch.dict(os.environ, {'FW_VERSION': '9.99'}):
            tcp = Client.__new__(Client)
            tcp.settings = Mock(return_value={'soc_version': 257})
            tcp.socket = Mock()
            tcp.play_index(0, 6)
            tcp.socket.sendall.assert_called_once()
