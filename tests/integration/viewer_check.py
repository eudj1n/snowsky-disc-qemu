"""Viewer resources, real guest frame/audio and HTTP power lifecycle in disposable CI."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from emulator.runtime.audio import capture_info
from tests.fixtures.framebuffer import decode_png

BASE = 'http://127.0.0.1:8080'
ROOT = Path('/work/rootfs')


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=3) as response:
        return response.headers.get_content_type(), response.read()


def wait(predicate, label, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads(get('/device.json')[1])
            if predicate(state):
                return state
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise AssertionError('Viewer did not reach ' + label)


def button(gesture):
    request = urllib.request.Request(BASE + '/button',
        json.dumps({'name': 'power', 'gesture': gesture}).encode(),
        {'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=3) as response:
        assert json.load(response) == {'ok': True}


def main():
    assert os.environ.get('CI_DISPOSABLE') == '1', 'Requires a disposable integration stack'
    with Path('/work/viewer-check.log').open('wb') as log:
        process = subprocess.Popen(['bash', '/repo/viewer/scripts/40_stream.sh'],
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            wait(lambda s: s['running'] and not s['transition'], 'running guest')
            kind, page = get('/')
            assert kind == 'text/html' and b'<title>Snowsky Disc</title>' in page
            assert b'id=screen-frame' in page and b'/skin' not in page
            for name in ('audio', 'keys', 'controls', 'frames'):
                kind, data = get('/' + name + '.js')
                assert kind == 'text/javascript'
                assert data == Path('/repo/viewer/static', name + '.js').read_bytes()
            kind, css = get('/device.css')
            assert kind == 'text/css'
            assert css == Path('/repo/viewer/static/device.css').read_bytes()
            state = wait(lambda s: s['running'], 'running')
            if not state['screen_on']:
                button('single')
            wait(lambda s: s['screen_on'], 'awake display')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                kind, png = get('/frame')
                if kind == 'image/png' and any(decode_png(png)):
                    break
                time.sleep(.2)
            else:
                raise AssertionError('Viewer frame stayed black')
            kind, data = get('/audio.json')
            info = json.loads(data)
            direct = capture_info(ROOT)
            assert kind == 'application/json' and info['running']
            assert info['generation'] == direct['generation'] and info['bytes'] > 0
            generation = info['generation']
            kind, pcm = get('/audio.pcm?generation=' + generation + '&offset=0')
            assert kind == 'application/octet-stream' and pcm
            with (ROOT / 'audio.pcm').open('rb') as capture:
                assert pcm == capture.read(len(pcm))
            button('single')
            wait(lambda s: not s['screen_on'] and s['running'], 'screen asleep')
            button('single')
            wait(lambda s: s['screen_on'] and s['running'], 'screen awake')
            button('hold')
            wait(lambda s: not s['running'] and not s['transition'], 'guest off')
            # Explicit local Power boots the same guest via the relocated script.
            button('single')
            wait(lambda s: s['running'] and s['screen_on'] and not s['transition'], 'guest rebooted')
            # Boot clears shots; retain the observed pre-reboot viewer frame afterwards.
            Path('/work/shots/ci-viewer-frame.png').write_bytes(png)
            print('Viewer CSS device/HTML/JS, live frame/PCM, sleep/wake, stop and Power boot verified.')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
