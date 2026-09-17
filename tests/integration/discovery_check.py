"""V2.57 stock multicast lifecycle; disposable namespace, no LAN exposure."""
from tests.integration.profile import (version as firmware_version, main_os_version, require_acceptance, diagnostic)
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
    require_acceptance('discovery')
    interfaces = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'eth1']))
    address = next(info['local'] for info in interfaces[0]['addr_info'] if info['scope'] == 'global')
    with PlayerMemory(ROOT, firmware_version()) as memory, listen(address) as sock:
        assert memory.word(diagnostic('network.connected')) == 0
        beacons(sock, address)
        # Accept alone suppresses discovery, before any Link handshake.
        with Client(address) as client:
            deadline = time.monotonic() + 3
            while not memory.word(diagnostic('network.connected')) and time.monotonic() < deadline:
                time.sleep(.05)
            assert memory.word(diagnostic('network.connected')) == 1
            receive(sock, address, 1)  # Drain the connection-boundary packet, if any.
            assert not receive(sock, address, 4), 'beacons continued during TCP connection'
            assert client.handshake() == '0306'
            assert client.settings()['soc_version'] == main_os_version()
            assert not receive(sock, address, 3)
            print('Discovery: suppressed before/after handshake, fresh TCP reads work', flush=True)
        deadline = time.monotonic() + 5
        while memory.word(diagnostic('network.connected')) and time.monotonic() < deadline:
            time.sleep(.05)
        assert memory.word(diagnostic('network.connected')) == 0
        beacons(sock, address)
    print(f'DISCOVERY CHECK PASS V{firmware_version()}: idle beacons, connected silence, disconnect recovery', flush=True)


if __name__ == '__main__':
    main()
