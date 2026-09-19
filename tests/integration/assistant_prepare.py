"""Scan only the disposable Assistant fixture, before the persistent session starts."""
import json
import argparse
import os
from pathlib import Path
import time

from controller.fiio_link import Client
from controller.fiio_http import HTTPClient
from tests.fixtures.assistant_fixture import MANIFEST


def main(show_player=False):
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('Requires disposable V2.57 guest')
    tracks = json.loads(MANIFEST.read_text())['tracks']
    with Client(timeout=3) as client:
        if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
            raise RuntimeError('Unexpected guest firmware')
        if show_player:
            from emulator.runtime.touch import Touch
            client.play_artist('Test Atlas', 1, album='Test Album',
                               http=HTTPClient('127.0.0.1', 12103, 5))
            time.sleep(3)
            touch = Touch(Path('/work/rootfs'))
            # English startup carousel: Browse files -> Now playing. UI setup
            # only, before the Assistant owns the connection or cases are scored.
            touch.swipe(280, 180, 80, 180, steps=20, hold=.1)
            time.sleep(2)
            touch.tap(180, 180)
            time.sleep(1)
            print('Now-playing screen requested for visual evidence', flush=True)
            return
        client.scan_library()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                tag, payload = client.event(.5)
            except TimeoutError:
                continue
            if tag == 'a60a' and int(payload, 16) == 5:
                break
        else:
            raise TimeoutError('Fixture scan did not finish')
        page = HTTPClient('127.0.0.1', 12103, 5).catalog(limit=200)
        if page['total'] != len(tracks):
            raise RuntimeError(f'Fixture count mismatch: {page}')
        client.set_play_mode(0)
        if client.play_mode() != 0:
            raise RuntimeError('Sequential mode not established')
    print('Assistant fixture scan complete', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--show-player', action='store_true')
    main(parser.parse_args().show_player)
