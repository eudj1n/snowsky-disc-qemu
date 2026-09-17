#!/usr/bin/env python3
"""Read-only WebSocket upgrade probe; never treats HTTP 200 as a successful upgrade."""
import argparse
import base64
import hashlib
import http.client
import json
import os


def probe(host='127.0.0.1', port=12103, path='/api/websocket'):
    key = base64.b64encode(os.urandom(16)).decode()
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.request('GET', path, headers={
            'Connection': 'Upgrade', 'Upgrade': 'websocket',
            'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': key})
        reply = connection.getresponse()
        expected = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        valid = (reply.status == 101 and reply.getheader('Upgrade', '').lower() == 'websocket'
                 and 'upgrade' in [s.strip().lower() for s in reply.getheader('Connection', '').split(',')]
                 and reply.getheader('Sec-WebSocket-Accept') == expected)
        return dict(path=path, status=reply.status, websocket=valid,
                    content_length=reply.getheader('Content-Length'))
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=12103)
    parser.add_argument('--path', default='/api/websocket')
    parser.add_argument('--require-upgrade', action='store_true', help='exit 1 if upgrade is unavailable')
    args = parser.parse_args()
    result = probe(args.host, args.port, args.path)
    print(json.dumps(result, indent=2))
    if args.require_upgrade and not result['websocket']:
        raise SystemExit(1)
