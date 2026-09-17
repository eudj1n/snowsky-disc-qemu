"""V2.57 stock multicast lifecycle; disposable namespace, no LAN exposure."""
import json
import os
import subprocess
import time

from tests.integration.remote_control import ROOT
from controller.fiio_discovery import listen, observe
from controller.fiio_link import Client
from research.diagnostics.player_memory import PlayerMemory


def receive(sock, address, seconds):
    return [(stamp, item) for stamp, item in observe(sock, seconds)
            if item['host'] == address]


def beacons(sock, address):
    packets = receive(sock, address, 8)
    assert len(packets) >= 3, packets
    assert all(item['name'] == 'SNOWSKY DISC' for _, item in packets)
    intervals = [round(b[0] - a[0], 3) for a, b in zip(packets, packets[1:])]
    assert all(.5 < interval < 4 for interval in intervals), intervals
    print(f'Discovery: {len(packets)} raw DISC beacons, intervals={intervals}', flush=True)


def main():
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('discovery acceptance requires disposable V2.57')
    interfaces = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'eth1']))
    address = next(info['local'] for info in interfaces[0]['addr_info'] if info['scope'] == 'global')
    with PlayerMemory(ROOT, '2.57') as memory, listen(address) as sock:
        assert memory.word('898950') == 0
        beacons(sock, address)
        # Accept alone suppresses discovery, before any Link handshake.
        with Client(address) as client:
            deadline = time.monotonic() + 3
            while not memory.word('898950') and time.monotonic() < deadline:
                time.sleep(.05)
            assert memory.word('898950') == 1
            receive(sock, address, 1)  # Drain the connection-boundary packet, if any.
            assert not receive(sock, address, 4), 'beacons continued during TCP connection'
            assert client.handshake() == '0306'
            assert client.settings()['soc_version'] == 257
            assert not receive(sock, address, 3)
            print('Discovery: suppressed before/after handshake, fresh TCP reads work', flush=True)
        deadline = time.monotonic() + 5
        while memory.word('898950') and time.monotonic() < deadline:
            time.sleep(.05)
        assert memory.word('898950') == 0
        beacons(sock, address)
    print('DISCOVERY CHECK PASS V2.57: idle beacons, connected silence, disconnect recovery', flush=True)


if __name__ == '__main__':
    main()
