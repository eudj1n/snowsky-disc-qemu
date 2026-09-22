import http.client
import json
import threading
import unittest
from uuid import uuid4

from experiments.disc_web.backend.demo import Demo
from experiments.disc_web.backend.server import Server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.demo = Demo()
        self.server = Server(('127.0.0.1', 0), self.demo)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        base = {'Content-Type': 'application/json', 'X-Disc-Token': self.server.token}
        base.update(headers or {})
        connection.request(method, path, json.dumps(body) if body is not None else None, base)
        response = connection.getresponse()
        status, content, response_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return status, content, response_headers

    def test_page_assets_and_synthetic_catalog(self):
        status, body, headers = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('frame-ancestors', headers['Content-Security-Policy'])
        self.assertIn('Плеер'.encode(), body)
        status, body, _ = self.request('GET', '/api/library?kind=albums')
        self.assertEqual(len(json.loads(body)['items']), 8)
        status, _, headers = self.request('GET', '/art/cover-4.svg')
        self.assertEqual((status, headers['Content-Type']), (200, 'image/svg+xml'))

    def test_no_token_cross_origin_and_rebinding_are_rejected(self):
        command = {'action': 'resume', 'request_id': uuid4().hex}
        for headers in ({'X-Disc-Token': ''}, {'Origin': 'https://untrusted.example'},
                        {'Sec-Fetch-Site': 'cross-site'}, {'Host': 'untrusted.example'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('POST', '/api/action', command, headers)[0], 403)
        self.assertFalse(self.demo.playing)
        self.assertEqual(self.request('GET', '/api/state', headers={'Host': 'evil.example'})[0], 403)

    def test_duplicate_request_never_changes_state_twice(self):
        command = {'action': 'next', 'request_id': uuid4().hex}
        self.assertEqual(self.request('POST', '/api/action', command)[0], 200)
        selected = self.demo.selected
        self.assertEqual(self.request('POST', '/api/action', command)[0], 409)
        self.assertEqual(self.demo.selected, selected)

    def test_mutations_are_not_get_routes_and_unknown_commands_fail(self):
        self.assertEqual(self.request('GET', '/api/action?action=resume')[0], 404)
        self.assertEqual(self.request('POST', '/api/action', {'action': 'raw', 'request_id': uuid4().hex})[0], 422)
        self.assertEqual(self.request('GET', '/../../AGENTS.md')[0], 404)
        self.assertFalse(self.demo.playing)

    def test_demo_isolation_and_current_favorite(self):
        self.assertEqual(self.request('POST', '/api/action', {'action': 'connect', 'request_id': uuid4().hex})[0], 422)
        command = {'action': 'favorite', 'value': False, 'request_id': uuid4().hex}
        self.assertEqual(self.request('POST', '/api/action', command)[0], 200)
        favorites = json.loads(self.request('GET', '/api/library?kind=favorites')[1])['items']
        self.assertNotIn('0-1', [t['id'] for t in favorites])
        self.assertFalse(self.demo.state()['playback']['favorite'])

    def test_invalid_json_shape_and_scalar_types(self):
        self.assertEqual(self.request('POST', '/api/action', [1, 2])[0], 422)
        self.assertEqual(self.request('POST', '/api/action', {'action': 'volume', 'value': True, 'request_id': uuid4().hex})[0], 422)
        self.assertEqual(self.request('POST', '/api/action', {'action': 'queue', 'index': -1, 'request_id': uuid4().hex})[0], 422)


if __name__ == '__main__':
    unittest.main()
