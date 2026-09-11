#!/usr/bin/env python3
"""Live checks against localhost emulator. --control changes playback temporarily."""
import argparse
import json
import time
import urllib.request
from fiio_link import Client
from probe_websocket import probe


def verify(control=False, start_library=False):
    result = {}
    with Client() as client:
        result['protocol'] = client.handshake()
        assert result['protocol'] == '0306', result
        result['settings'] = client.settings()
        assert result['settings']['soc_version'] == 240
        result['tracks'] = client.tracks()
        assert isinstance(result['tracks']['items'], list)
        if control:
            volume = result['settings']['currentVolume']
            target = volume - 1 if volume else 1
            try:
                client.set_volume(target)
                time.sleep(0.2)
                result['volume_test'] = client.settings()['currentVolume']
                assert result['volume_test'] == target
            finally:
                client.set_volume(volume)
                time.sleep(0.2)
                result['volume_restored'] = client.settings()['currentVolume']
                assert result['volume_restored'] == volume
            if start_library:
                assert result['tracks']['total'] > 0, 'Run Update media lib first'
                client.play_all()
                time.sleep(0.7)
            before = client.now_playing()
            assert before.get('song'), 'Open a test track in Browse files first'
            assert before['state'] in (0, 1), 'Track stopped; use --start-library'
            result['before'] = before
            client.play_pause()
            time.sleep(0.2)
            after = client.now_playing()
            result['after_toggle'] = after
            assert after['state'] == 1 - before['state'], result
            client.play_pause()
            time.sleep(0.2)
            result['after_second_toggle'] = client.now_playing()
            assert result['after_second_toggle']['state'] == before['state'], result
            assert all(item['song']['id'] == before['song']['id']
                       for item in (after, result['after_second_toggle'])), result
            if start_library and result['after_second_toggle']['state'] == 0:
                client.play_pause()  # leave the test track paused, not sounding
                time.sleep(0.2)
                result['final_state'] = client.now_playing()['state']
                assert result['final_state'] == 1, result
    with urllib.request.urlopen('http://127.0.0.1:12103/api/hi', timeout=5) as response:
        result['http_hi'] = {'status': response.status, 'body': response.read().decode()}
        assert response.status == 200
    result['websocket'] = probe()
    result['unknown_route'] = probe(path='/__unmapped_probe__')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', action='store_true')
    parser.add_argument('--start-library', action='store_true', help='start first indexed track, leave paused')
    args = parser.parse_args()
    if args.start_library and not args.control:
        parser.error('--start-library requires --control')
    print(json.dumps(verify(args.control, args.start_library), indent=2, ensure_ascii=False))
