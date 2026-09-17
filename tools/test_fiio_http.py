import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import unquote
from unittest.mock import patch, Mock, call

from fiio_http import HTTPClient, Reply, name_header, range_body, sd_path


class HTTPTests(unittest.TestCase):
    def test_physical_source_delete_uses_current_row_and_preserves_total_on_empty_page(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_source_delete.json').read_text())
        before, after = fixture['before'][2], fixture['after'][0]
        request = fixture['delete']
        self.assertEqual(request['headers']['delete_source'], '1')
        # Actual catalog order is A2, A1: filename/title suffix is not a position.
        self.assertEqual([r['name'] for r in before['items']], ['Probe A2', 'Probe A1'])
        position = next(r['pos'] for r in before['items'] if r['name'] == 'Probe A1')
        self.assertEqual(range_body([[position, position]]), request['decoded_body'].encode())
        self.assertEqual(request['chunked_body'], '7\r\n[[1,1]]\r\n0\r\n\r\n')
        client = HTTPClient()
        client.request = Mock(return_value=Reply(200, after['response_headers'],
                                                 json.dumps(after['items']).encode()))
        page = client.catalog('style/album/song', offset=1, limit=100,
                              style='DISC Delete Probe', album='DISC Delete Album A')
        self.assertEqual(page, {'total': 1, 'items': [], 'mark': -1})
        self.assertEqual(client.request.call_args.kwargs['headers'],
                         {k: v for k, v in after['headers'].items() if v})
        self.assertEqual(fixture['after'][1]['items'][0]['count'], 1)

    def test_physical_directory_confirms_source_delete_and_previous_index_only_survivor(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_source_delete.json').read_text())
        directory = fixture['directory_after']
        client = HTTPClient()
        client.request = Mock(return_value=Reply(200, directory['response_headers'],
                                                 json.dumps(directory['items']).encode()))
        page = client.directory('/tmp/sdcard/DISC Delete Probe', limit=50)
        self.assertEqual(page['total'], 2)
        self.assertEqual({r['name'] for r in page['items']},
                         {'02-Probe-A2.flac', '03-Probe-B1.flac'})
        self.assertTrue(all(not r['is_dir'] for r in page['items']))
        # App percent-encodes an internal slash; both forms name the same path.
        self.assertEqual(unquote(client.request.call_args.args[1]), unquote(directory['path']))
        self.assertEqual(client.request.call_args.kwargs['headers'], directory['headers'])
        earlier = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_track_delete.json').read_text())
        self.assertEqual(earlier['after'][0]['items'], [])  # B1 absent from index earlier.
        self.assertEqual(earlier['delete']['headers']['delete_source'], '0')

    def test_physical_scoped_track_delete_and_empty_catalog_readback(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_track_delete.json').read_text())
        request = fixture['delete']
        # The unchecked iOS source checkbox maps to flag zero. Retain both
        # genre and album; a generic album request would have a broader scope.
        self.assertFalse(fixture['dialog']['source_checked'])
        self.assertEqual(request['headers']['delete_source'], '0')
        client = HTTPClient()
        filters = dict(style='DISC Delete Probe', album='DISC Delete Album B')
        expected = client._category('style/album/song', filters)
        self.assertEqual({k: request['headers'][k] for k in expected}, expected)
        self.assertEqual(range_body([[0, 0]]), request['decoded_body'].encode())
        self.assertEqual(request['chunked_body'], '7\r\n[[0,0]]\r\n0\r\n\r\n')
        before, after = fixture['before'][2], fixture['after'][0]
        client.request = Mock(side_effect=[
            Reply(200, row['response_headers'], json.dumps(row['items']).encode())
            for row in (before, after)])
        self.assertEqual(client.catalog('style/album/song', limit=100, **filters)['items'][0]['name'],
                         'Probe B1')
        # A real empty JSON array + total-num:0 is a valid catalog, distinct
        # from the empty-body HTTP 200 returned by unsupported routes.
        self.assertEqual(client.catalog('style/album/song', limit=100, **filters),
                         {'total': 0, 'items': [], 'mark': -1})
        self.assertEqual(client.request.call_args_list, [call('GET', '/song_category_tree/',
            headers=dict(expected, **{'start-pos': '0', 'num-max': '100'}))] * 2)
        self.assertEqual(fixture['after'][1]['items'], [fixture['before'][1]['items'][0]])
        self.assertEqual(fixture['after'][1]['items'][0]['count'], 2)
        self.assertEqual([fixture['before'][0]['items'][0]['count'],
                          fixture['after'][2]['items'][0]['count']], [3, 2])

    def test_physical_genre_album_groups_create_add_rename(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_group_add_rename.json').read_text())
        client = HTTPClient()
        client.request = Mock(return_value=Reply(200, {}, b''))
        # Fresh preflight sees the created empty list and six genre-album rows.
        created = fixture['custom_readbacks'][2]
        def catalog(category, offset=0, limit=1, **filters):
            if category == 'custom':
                source = created
            else:
                self.assertEqual(category, 'style/album')
                self.assertEqual(filters, {'style': fixture['genre']})
                source = fixture['source_page']
            return dict(total=source['total'], items=source['items'][offset:offset + limit])
        client.catalog = Mock(side_effect=catalog)
        client.create_playlist(fixture['created_name'])
        ranges = json.loads(fixture['mutations'][1]['decoded_body'])
        client.add_selection_to_playlist(fixture['destination_position'], ranges,
                                          expected_name=fixture['created_name'],
                                          category='style/album', style=fixture['genre'])
        client.rename_playlist(fixture['destination_position'], fixture['renamed_name'])
        expected = []
        for item in fixture['mutations']:
            headers = {k: v for k, v in item['headers'].items()
                       if v and k not in ('transfer-encoding', 'content-type')}
            if 'content-type' in item['headers']:
                headers['Content-Type'] = item['headers']['content-type']
            expected.append(call(item['method'], item['path'], item['decoded_body'].encode(), headers))
        self.assertEqual(client.request.call_args_list, expected)
        self.assertEqual(client.catalog.call_args_list, [
            call('custom', offset=2, limit=1),
            call('style/album', offset=0, limit=1, style=fixture['genre']),
            call('style/album', offset=2, limit=1, style=fixture['genre']),
            call('custom', offset=2, limit=1)])

    def test_physical_group_rename_readback_and_partial_membership(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_group_add_rename.json').read_text())
        before, after = fixture['custom_readbacks'][-2:]
        page = Reply(200, {'total-num': str(after['total'])},
                     json.dumps(after['items']).encode()).page()
        self.assertEqual(page['items'][2]['name'], fixture['renamed_name'])
        self.assertEqual(page['items'][2]['pos'], 2)
        self.assertEqual(page['items'][:2], before['items'][:2])
        self.assertEqual((before['items'][2]['count'], page['items'][2]['count']), (105, 105))
        # The count agrees with selected groups; 100 rows is a partial page,
        # not the total playlist length and not full membership evidence.
        count = sum(fixture['source_page']['items'][i]['count'] for i in (0, 2))
        observed = fixture['membership_page']
        self.assertEqual(observed['total'], count)
        self.assertEqual(observed['returned'], 100)
        self.assertGreater(observed['total'], observed['returned'])
        client = HTTPClient()
        client.request = Mock(return_value=Reply(200, {'total-num': '105'}, b'[]'))
        client.catalog('custom/song', src_list_id=2, limit=100)
        client.request.assert_called_with('GET', '/song_category_tree/', headers=observed['headers'])

    def test_physical_album_batch_add_and_fresh_membership(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' /
                              'fiio_control_ios_album_batch_add.json').read_text())
        client = HTTPClient()
        # Preserve real preflight logic, replying with the recorded source and
        # destination rows. A position is not the selected track's ordinal/ID.
        def request(method, path, body=b'', headers=None):
            if method == 'POST':
                return Reply(200, fixture['add']['response_headers'], b'')
            category = headers['type']
            evidence = (fixture['destination_before'] if category == 'custom' else
                        fixture['source_page'] if category == 'album/song' else
                        fixture['membership_after'])
            start, limit = int(headers['start-pos']), int(headers['num-max'])
            items = evidence['items'][start:start + limit]
            return Reply(200, {'total-num': str(evidence['total'])}, json.dumps(items).encode())
        client.request = Mock(side_effect=request)
        client.add_selection_to_playlist(fixture['destination_position'], fixture['add']['ranges'],
                                          expected_name=fixture['destination_name'],
                                          category='album/song', album=fixture['album'])
        writes = [c for c in client.request.call_args_list if c.args[0] != 'GET']
        # App sends chunked HTTP and empty unused filters; helper uses a bytes
        # body (Content-Length) and omits empty filters. Compare decoded content.
        headers = {k: v for k, v in fixture['add']['headers'].items()
                   if v and k not in ('transfer-encoding', 'content-type')}
        headers['Content-Type'] = 'application/json'
        self.assertEqual(writes, [call('POST', fixture['add']['path'],
                                      fixture['add']['decoded_body'].encode(), headers)])
        before = fixture['destination_before']['items'][1]
        after = fixture['destination_after']['items'][1]
        self.assertEqual((before['count'], after['count']), (0, 2))
        membership = client.catalog('custom/song', src_list_id=fixture['destination_position'], limit=100)
        expected = [fixture['source_page']['items'][i]['name'] for i in (0, 2)]
        self.assertEqual([r['name'] for r in membership['items']], expected)
        self.assertEqual([r['pos'] for r in membership['items']], [0, 1])
        self.assertEqual(membership['total'], 2)
        client.request.assert_called_with('GET', '/song_category_tree/', headers={
            'type': 'custom/song', 'src_list_id': '1', 'start-pos': '0', 'num-max': '100'})

    def test_guarded_bulk_add_checks_destination_and_scoped_endpoints(self):
        client = HTTPClient()
        def catalog(category, offset=0, **filters):
            return dict(total=4, items=[dict(pos=offset, name='Target' if category == 'custom' else 'Song')])
        client.catalog = Mock(side_effect=catalog)
        client.add_to_playlist = Mock()
        client.add_selection_to_playlist(2, [[0, 1], [3, 3]], expected_name='Target',
                                          category='style/album', style='Genre Ё')
        self.assertEqual(client.catalog.call_args_list, [
            call('custom', offset=2, limit=1),
            call('style/album', offset=0, limit=1, style='Genre Ё'),
            call('style/album', offset=1, limit=1, style='Genre Ё'),
            call('style/album', offset=3, limit=1, style='Genre Ё'),
            call('custom', offset=2, limit=1)])
        client.add_to_playlist.assert_called_once_with(2, [[0, 1], [3, 3]],
                                                       'style/album', style='Genre Ё')

    def test_guarded_bulk_add_rejects_ambiguous_sources_before_io(self):
        client = HTTPClient()
        client.catalog = Mock()
        client.add_to_playlist = Mock()
        for category, filters in (('custom', {}), ('style/song', {}),
                                  ('style/album/song', {'style': 'x'}),
                                  ('style', {'album': 'unexpected'}), ('folder', {})):
            with self.assertRaises(ValueError):
                client.add_selection_to_playlist(0, [[0, 0]], expected_name='Target',
                                                  category=category, **filters)
        client.catalog.assert_not_called()
        client.add_to_playlist.assert_not_called()

    def test_guarded_bulk_add_rejects_stale_bounds_and_never_retries(self):
        good = dict(total=1, items=[dict(pos=0, name='Target')])
        bad = [dict(total=0, items=[]), dict(total=1, items=[]),
               dict(total=True, items=[dict(pos=0, name='Target')]),
               dict(total=1, items=[dict(pos=True, name='Target')]),
               dict(total=1, items=[dict(pos=0, name='Renamed')])]
        client = HTTPClient()
        client.add_to_playlist = Mock()
        for replies in ([b] for b in bad):
            client.catalog = Mock(side_effect=replies)
            with self.assertRaises(ValueError):
                client.add_selection_to_playlist(0, [[0, 0]], expected_name='Target')
        for replies in ([good, bad[0]], [good, good, bad[-1]]):
            client.catalog = Mock(side_effect=replies)
            with self.assertRaises(ValueError):
                client.add_selection_to_playlist(0, [[0, 0]], expected_name='Target')
        client.add_to_playlist.assert_not_called()
        client.catalog = Mock(return_value=good)
        client.add_to_playlist.side_effect = TimeoutError('uncertain write')
        with self.assertRaises(TimeoutError):
            client.add_selection_to_playlist(0, [[0, 0]], expected_name='Target')
        client.add_to_playlist.assert_called_once()

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
