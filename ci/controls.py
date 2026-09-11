"""Physical events with protocol/sysfs readback, only in a disposable scanned guest."""
from pathlib import Path
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from fiio_link import Client
from keys import Buttons, Device


def wait(read, predicate, label, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(.2)
    raise AssertionError(f'Physical control readback failed: {label}')


def main():
    root = Path('/work/rootfs')
    device = Device(root)
    buttons = Buttons(root, device)
    buttons.reset()
    deadline = time.monotonic() + 8
    while True:
        try:
            client = Client(timeout=3)
            break
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.2)
    with client:
        assert client.handshake() == '0306'
        settings = client.settings()
        assert settings['soc_version'] == int(os.environ.get('FW_VERSION', '2.40').replace('.', ''))
        initial = settings['currentVolume']
        assert initial > 0
        buttons.gesture('volume_down', 'single')
        wait(client.settings, lambda s: s['currentVolume'] == initial - 1, 'volume down')
        buttons.gesture('volume_up', 'single')
        wait(client.settings, lambda s: s['currentVolume'] == initial, 'volume up')
        try:
            buttons.gesture('volume_down', 'hold')
            wait(client.settings, lambda s: s['currentVolume'] < initial, 'volume hold', timeout=1.2)
        finally:
            buttons.gesture('volume_down', 'end')
        client.set_volume(initial)
        wait(client.settings, lambda s: s['currentVolume'] == initial, 'restore volume')
        # Prior WebSocket integration leaves the selected track paused.
        buttons.gesture('play_pause', 'single')
        wait(client.now_playing, lambda s: isinstance(s.get('song'), dict) and s.get('state') == 0,
             'physical play')
        buttons.gesture('play_pause', 'single')
        wait(client.now_playing, lambda s: isinstance(s.get('song'), dict) and s.get('state') == 1,
             'physical pause')
        assert device.screen_on()
        buttons.gesture('power', 'single')
        wait(device.screen_on, lambda value: not value, 'screen sleep')
        buttons.gesture('power', 'single')
        wait(device.screen_on, bool, 'screen wake')
    print('Physical volume single/hold, media play/pause and screen sleep/wake verified.')


if __name__ == '__main__':
    main()
