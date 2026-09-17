import socket
import unittest
from unittest.mock import Mock, patch

from controller.fiio_discovery import announcement, interface_address, listen, observe, PAYLOAD, GROUP, PORT


class DiscoveryTests(unittest.TestCase):
    def test_plain_name_not_a_link_frame(self):
        value = announcement(PAYLOAD, ('192.0.2.12', 45678))
        self.assertEqual(value, dict(name='SNOWSKY DISC', host='192.0.2.12',
                                     source_port=45678, tcp_port=12100, http_port=12103))

    def test_unknown_and_malformed_payloads_ignored(self):
        for data in (b'', b'SNOWSKY DISC\0', b'SNOWSKY DISC\n', b'snowsky disc',
                     b'0599000C0000', b'SNOWSKY DISC' + b'x' * 4096, b'\xff'):
            self.assertIsNone(announcement(data, ('192.0.2.1', 1)))

    def test_specific_interface_required(self):
        for value in ('0.0.0.0', GROUP, '255.255.255.255', 'en0', '::1'):
            with self.assertRaises(ValueError):
                interface_address(value)
        self.assertEqual(interface_address('127.0.0.1'), '127.0.0.1')

    def test_membership_on_explicit_interface_and_no_send(self):
        with patch('controller.fiio_discovery.socket.socket') as factory:
            sock = listen('192.0.2.1')
            sock.bind.assert_called_once_with(('', PORT))
            sock.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(GROUP) + socket.inet_aton('192.0.2.1'))
            sock.sendto.assert_not_called()
            sock.connect.assert_not_called()

    def test_setup_failure_closes_socket(self):
        with patch('controller.fiio_discovery.socket.socket') as factory:
            factory.return_value.bind.side_effect = OSError('busy')
            with self.assertRaises(OSError):
                listen('192.0.2.1')
            factory.return_value.close.assert_called_once()

    def test_observer_ignores_unknown_and_times_out(self):
        sock = Mock()
        sock.recvfrom.side_effect = [(b'other', ('192.0.2.1', 1)),
                                    (PAYLOAD, ('192.0.2.2', 2)), socket.timeout()]
        values = list(observe(sock, 1))
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0][1]['host'], '192.0.2.2')
        sock.connect.assert_not_called()

    def test_deadline_is_bounded(self):
        for seconds in (0, -1, 301, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                list(observe(Mock(), seconds))
