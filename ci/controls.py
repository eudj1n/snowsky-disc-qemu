"""Physical events with protocol/sysfs readback, only in a disposable scanned guest."""
from pathlib import Path
import os
import socket
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from fiio_link import Client
from keys import Buttons, Device
from probe_keys import snapshot as key_snapshot
from probe_network import snapshot as network_snapshot
from inspect_http_routes import routes


def wait(read, predicate, label, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(.2)
    raise AssertionError(f'Physical control readback failed: {label}')


def check_idle_key_cpu(device):
    threads = []
    for pid in device.processes():
        try:
            if b'/usr/bin/mq_player' not in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0'):
                continue
            for task in Path(f'/proc/{pid}/task').iterdir():
                if (task / 'comm').read_text().strip() == 'echo_loop_key':
                    threads.append(task)
        except FileNotFoundError:
            continue
    assert len(threads) == 1, f'Expected one key reader, got {threads}'

    def ticks():
        fields = (threads[0] / 'stat').read_text().split(') ', 1)[1].split()
        return int(fields[11]) + int(fields[12])  # utime + stime, excluding pid/comm

    start, before = time.monotonic(), ticks()
    time.sleep(2)
    cpu = (ticks() - before) / os.sysconf('SC_CLK_TCK') / (time.monotonic() - start)
    print(f'Idle key-reader CPU: {cpu:.1%} of one core')
    # Generous margin for CI/QEMU overhead; an EOF busy loop consumes ~100%.
    assert cpu < .25, f'Key reader is busy-spinning at EOF: {cpu:.1%}'


def main():
    root = Path('/work/rootfs')
    device = Device(root)
    buttons = Buttons(root, device)
    buttons.reset()
    check_idle_key_cpu(device)
    version = os.environ.get('FW_VERSION', '2.57')
    network = network_snapshot(root, version)
    assert network['firmware'] == version and network['ready'] == 1, network
    assert network['storage_type'] == 1 and network['scan_running'] == 0, network
    assert network['dangerous_caps_dropped'] and network['capabilities']['NoNewPrivs'] == '1'
    expected_callbacks = {
        '2.40': {'0502': '0x4e4744', '0201': '0x4e477c', 'volume_device': '0x4e0fdc'},
        '2.57': {'0502': '0x4ed814', '0201': '0x4ed84c', 'volume_device': '0x4e9d24'},
    }
    assert network['callbacks'] == expected_callbacks[version], network
    assert network['ip'] == socket.gethostbyname(socket.gethostname()), network
    table = routes((root / 'usr/bin/mq_player').read_bytes(), version)
    assert len(table) == (17 if version == '2.57' else 16)
    assert any(r['method'] == 'GET' and r['path'] == '/log/' for r in table)
    assert any(r['method'] == 'POST' and r['path'] == '/image/' for r in table) == (version == '2.57')
    assert not any('websocket' in r['path'] for r in table)
    with sqlite3.connect(root / 'usr/data/fiio/db/sysconfig.db') as db:
        assignment = db.execute('SELECT KEY_SINGLE_CLICK_SLE, KEY_DOUBLE_CLICK_SLE, '
                                'KEY_LONG_PRESS_SLE FROM SYSCONFIG').fetchone()
    keys = key_snapshot(root, version)
    assert tuple(keys[k] for k in ('single', 'double', 'hold')) == assignment, keys
    print('Diagnostic network/HTTP snapshot:', network)
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
        assert settings['soc_version'] == int(os.environ.get('FW_VERSION', '2.57').replace('.', ''))
        initial = settings['currentVolume']
        assert initial > 0
        assert key_snapshot(root, version)['volume'] == initial
        buttons.gesture('volume_down', 'single')
        wait(client.settings, lambda s: s['currentVolume'] == initial - 1, 'volume down')
        assert key_snapshot(root, version)['volume'] == initial - 1
        buttons.gesture('volume_up', 'single')
        wait(client.settings, lambda s: s['currentVolume'] == initial, 'volume up')
        try:
            buttons.gesture('volume_down', 'hold')
            wait(client.settings, lambda s: s['currentVolume'] < initial, 'volume hold', timeout=1.2)
        finally:
            buttons.gesture('volume_down', 'end')
        client.set_volume(initial)
        wait(client.settings, lambda s: s['currentVolume'] == initial, 'restore volume')
        assert key_snapshot(root, version)['volume'] == initial
        # Prior WebSocket integration leaves the selected track paused.
        buttons.gesture('play_pause', 'single')
        wait(client.now_playing, lambda s: isinstance(s.get('song'), dict) and s.get('state') == 0,
             'physical play')
        wait(lambda: key_snapshot(root, version), lambda s: s['player_state'] == 1, 'memory playing')
        buttons.gesture('play_pause', 'single')
        wait(client.now_playing, lambda s: isinstance(s.get('song'), dict) and s.get('state') == 1,
             'physical pause')
        wait(lambda: key_snapshot(root, version), lambda s: s['player_state'] == 2, 'memory paused')
        assert device.screen_on()
        buttons.gesture('power', 'single')
        wait(device.screen_on, lambda value: not value, 'screen sleep')
        assert key_snapshot(root, version)['screen_on'] == 0
        buttons.gesture('power', 'single')
        wait(device.screen_on, bool, 'screen wake')
        assert key_snapshot(root, version)['screen_on'] == 1
    print('Physical volume single/hold, media play/pause and screen sleep/wake verified.')


if __name__ == '__main__':
    main()
