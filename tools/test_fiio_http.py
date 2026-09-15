import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from fiio_http import HTTPClient, Reply, name_header, range_body, sd_path


class HTTPTests(unittest.TestCase):
    def test_unicode_and_path_boundaries(self):
        self.assertEqual(name_header('Ё +'), '%D0%81%20%2B')
        self.assertEqual(sd_path('/tmp/sdcard/Ё +.flac'), '/tmp/sdcard/Ё +.flac')
        for value in ('/tmp', '/tmp/sdcard2/a', '/tmp/sdcard/../a', '/tmp/sdcard//a',
                      '/tmp/sdcard/a\\b', '/tmp/sdcard/a\n', '/tmp/sdcard/./a'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sd_path(value)
        for value in ('', ' x', 'x ', 'x\r\ny', 'Я' * 43):
            with self.subTest(value=value), self.assertRaises(ValueError):
                name_header(value)

    def test_invalid_mutations_do_not_connect(self):
        client = HTTPClient()
        calls = [lambda: client.delete_file('/tmp/sdcard'),
                 lambda: client.mkdir('/usr/data/test'),
                 lambda: client.create_playlist('x\r\ntype: delete'),
                 lambda: client.rename_playlist(True, 'name'),
                 lambda: client.delete_playlist(-1),
                 lambda: client.add_to_playlist(0, [[2, 1]]),
                 lambda: client.remove_from_playlist(0, [[1, 2], [2, 3]]),
                 lambda: client.catalog('invented'),
                 lambda: client.catalog(limit=0),
                 lambda: client.catalog('custom/song', src_list_id=-1)]
        with patch('fiio_http.http.client.HTTPConnection') as connection:
            for call in calls:
                with self.assertRaises(ValueError):
                    call()
            connection.assert_not_called()

    def test_position_ranges(self):
        self.assertEqual(range_body([[0, 0], [2, 4]]), b'[[0,0],[2,4]]')
        for value in ([], [[0]], [[0, 1000000]], [[False, 1]], [[2, 3], [0, 1]]):
            with self.assertRaises(ValueError):
                range_body(value)

    def test_unknown_empty_reply_is_not_empty_catalog(self):
        reply = Reply(200, {}, b'')
        self.assertIsNone(reply.page()['total'])
        with patch.object(HTTPClient, 'request', return_value=reply):
            with self.assertRaises(ValueError):
                HTTPClient().catalog()
        self.assertEqual(Reply(200, {'total-num': '0'}, b'[]').page()['total'], 0)
        for body, total in ((b'{}', '0'), (b'[1]', '1'), (b'[{}]', '0'), (b'[]', '-1'), (b'bad', '0')):
            with self.assertRaises(ValueError):
                Reply(200, {'total-num': total}, body).page()

    def test_real_http_wire_and_binary_stream(self):
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def do_DELETE(self):
                self.handle_request()

            def handle_request(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                seen.append((self.command, self.path, dict(self.headers), body))
                self.send_response(200)
                payload = b'[]' if self.path.startswith('/song_category_tree/') and self.command == 'GET' else b''
                if payload:
                    self.send_header('total-num', '0')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = HTTPClient('127.0.0.1', server.server_port)
            client.catalog('album/song', album='Ё +')
            self.assertEqual(seen[-1][2]['album'], '%D0%81%20%2B')
            client.create_playlist('Test Ё')
            self.assertEqual(seen[-1][:2], ('POST', '/custom_list_cmd/'))
            self.assertEqual(seen[-1][2]['list_name'], 'Test%20%D0%81')
            client.add_to_playlist(2, [[0, 1]], 'album/song', album='Test')
            self.assertEqual(seen[-1][2]['dst_list_id'], '2')
            self.assertEqual(seen[-1][3], b'[[0,1]]')
            client.remove_from_playlist(2, [[0, 0]])
            self.assertEqual(seen[-1][2]['delete_source'], '0')
            self.assertEqual(seen[-1][2]['src_list_id'], '2')
            client.delete_file('/tmp/sdcard/Ё +.flac')
            self.assertEqual(seen[-1][1], '/file/tmp/sdcard/%D0%81%20%2B.flac')
            self.assertEqual(seen[-1][3], b'')
            self.assertNotIn('all-select', seen[-1][2])
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'sample.flac'
                data = bytes(range(256)) * 400
                source.write_bytes(data)
                client.upload(source, '/tmp/sdcard/Ё.flac')
                method, path, headers, body = seen[-1]
                self.assertEqual((method, path), ('POST', '/audio/tmp/sdcard/%D0%81.flac'))
                self.assertEqual(body, data)
                self.assertEqual(headers['Content-Length'], str(len(data)))
                self.assertNotIn('Transfer-Encoding', headers)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_no_automatic_retry_on_uncertain_write(self):
        with patch('fiio_http.http.client.HTTPConnection') as constructor:
            connection = constructor.return_value
            connection.getresponse.side_effect = TimeoutError('reply lost after write')
            with self.assertRaises(TimeoutError):
                HTTPClient().create_playlist('Test')
            self.assertEqual(connection.request.call_count, 1)
            connection.close.assert_called_once()

    def test_existing_upload_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sample.flac'
            source.write_bytes(b'fixture')
            # Includes a conservative rejection for a stale transfer record.
            with patch.object(HTTPClient, 'progress', return_value={'now_size': 7}), \
                 patch.object(HTTPClient, 'request') as request:
                with self.assertRaises(FileExistsError):
                    HTTPClient().upload(source, '/tmp/sdcard/sample.flac')
                request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
