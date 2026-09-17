import unittest
import socket
import threading
from unittest.mock import Mock
from controller.fiio_link import Client, Frames, frame


class FramingTests(unittest.TestCase):
    def test_disc_length_is_not_android_utf16_length(self):
        # Android BLinker declares 0x10 UTF-16 units for this same favorite key.
        # DISC needs 0x18 UTF-8 bytes; do not share the Android framing rule.
        self.assertEqual(frame('0415', '0000我的最爱'),
                         b'04150018' + '0000我的最爱'.encode())
        # Supplementary characters also distinguish UTF-8, UTF-16 and code points.
        self.assertEqual(frame('0413', '0000A😀'),
                         b'04130011' + '0000A😀'.encode())

    def test_handshake(self):
        self.assertEqual(frame('0599', '0000'), b'0599000C0000')

    def test_each_byte_fragmented(self):
        parser = Frames()
        result = []
        for byte in frame('a501', '{"name":"音楽"}'):
            result.extend(parser.feed(bytes([byte])))
        self.assertEqual(result, [('a501', '{"name":"音楽"}'.encode())])

    def test_coalesced_and_partial(self):
        parser = Frames()
        self.assertEqual(parser.feed(b'a599000C0306a103000C0001a2'),
                         [('a599', b'0306'), ('a103', b'0001')])
        self.assertEqual(parser.feed(b'020008'), [('a202', b'')])

    def test_invalid_header_and_length(self):
        for data in (b'xxxx0008', b'a5010007', b'a501zzzz'):
            with self.assertRaises(ValueError):
                Frames().feed(data)

    def test_request_validation(self):
        for tag, payload in [('xyz1', ''), ('05010', ''), ('0501', b'x' * 65528)]:
            with self.assertRaises(ValueError):
                frame(tag, payload)

    def test_safe_control_frames(self):
        client = Client.__new__(Client)
        client.socket = Mock()
        client.set_volume(118)
        client.socket.sendall.assert_called_with(b'0502000C0076')
        client.play_pause()
        client.socket.sendall.assert_called_with(b'0201000C0000')
        client.play_all()
        client.socket.sendall.assert_called_with(b'0101000C0001')
        for value in (-1, 121, True, 1.5):
            with self.assertRaises(ValueError):
                client.set_volume(value)

    def test_request_skips_notifications_and_reads_fragments(self):
        client = Client.__new__(Client)
        client.socket = Mock()
        client.timeout, client.frames, client.pending = 1, Frames(), []
        client.drain_notifications = Mock()
        client.socket.recv.side_effect = [b'a103000C0001a59900', b'0C0306']
        self.assertEqual(client.handshake(), '0306')

    def test_peer_close(self):
        client = Client.__new__(Client)
        client.socket = Mock()
        client.timeout, client.frames, client.pending = 1, Frames(), []
        client.drain_notifications = Mock()
        client.socket.recv.return_value = b''
        with self.assertRaises(ConnectionError):
            client.handshake()

    def test_play_mode_uses_a102_and_ignores_a105(self):
        client = Client.__new__(Client)
        client.socket = Mock()
        client.timeout, client.frames, client.pending = 1, Frames(), []
        client.drain_notifications = Mock()
        client.socket.recv.side_effect = [b'a105000C0004a103000C0001a10200', b'0C0003']
        self.assertEqual(client.play_mode(), 3)
        client.socket.sendall.assert_called_once_with(b'01050008')

    def test_old_state_notification_is_not_a_new_query_reply(self):
        client = Client.__new__(Client)
        client.socket, peer = socket.socketpair()
        client.timeout, client.frames = 1, Frames()
        client.pending = [('a202', b'{"state":2}')]
        peer.sendall(frame('a202', '{"state":0}'))
        def respond():
            peer.recv(8)
            peer.sendall(frame('a202', '{"state":1}'))
        worker = threading.Thread(target=respond, daemon=True)
        worker.start()
        try:
            self.assertEqual(client.now_playing(), {'state': 1})
        finally:
            client.close()
            peer.close()
            worker.join(timeout=1)


if __name__ == '__main__':
    unittest.main()
