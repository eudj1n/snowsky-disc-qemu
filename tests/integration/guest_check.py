"""Fresh English UI -> stock library scan; assert real TCP index and PCM.

Only for ci/integration.sh's disposable guest, not an existing interactive session.
"""
from tests.integration.profile import (version as firmware_version)
import argparse
import os
from pathlib import Path
import sys
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from emulator.runtime.audio import capture_info
from controller.fiio_link import Client
from emulator.runtime.framebuffer import png, to_rgb, BUF
from emulator.runtime.touch import Touch
from research.diagnostics.player_memory import PlayerMemory
from tests.fixtures.fixture import NAMES

ROOT = Path('/work/rootfs')
touch = Touch(ROOT)
tap, swipe = touch.tap, touch.swipe


def capture(name):
    live = (ROOT / 'emu/fb-live').read_bytes()[0]
    assert live in (0, 1), 'No observed framebuffer flush'
    raw = (ROOT / 'dev/fb0').read_bytes()[live * BUF:(live + 1) * BUF]
    Path(f'/work/shots/ci-{name}.png').write_bytes(png(to_rgb(raw)))


def wait_library(total, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with Client(timeout=3) as client:
                assert client.handshake() == '0306'
                tracks = client.tracks()
                if tracks['total'] == total:
                    return tracks
        except OSError:
            pass  # Stock single-client TCP listener needs time to reopen.
        time.sleep(1)
    raise AssertionError(f'Stock library did not reach {total} tracks')


def scan():
    # Read the actual card by its original Unicode path before involving the UI.
    # This fails if image creation used a different charset from the guest mount.
    relative = Path('Кириллица Ё й') / 'CI Tone — Проверка.wav'
    assert (ROOT / 'tmp/sdcard' / relative).read_bytes() == (Path('/sdcard') / relative).read_bytes()
    wait_library(0)  # No copied index / pre-existing state is allowed.
    capture('main')
    # Slow carousel drag to Settings, avoiding a fast inertial fling.
    # Coordinates are version-specific, visible display pixels; normal touch path.
    swipe(80, 180, 280, 180, steps=20, hold=.1)
    time.sleep(2)
    capture('carousel')
    tap(180, 180)
    time.sleep(2)
    capture('settings')
    for _ in range(5):
        swipe(180, 300, 180, 110, steps=20, hold=.08)
        time.sleep(.5)
    time.sleep(2)
    capture('settings-scrolled')
    tap(180, 280)
    time.sleep(2)
    capture('library')
    # Sample the actual worker flag across the stock UI-triggered scan. A very
    # short scan may fit between samples; record observed values without making
    # scheduler timing a CI pass/fail condition.
    with PlayerMemory(ROOT, firmware_version()) as player:
        address = player.profile['diagnostics']['network']['scan_running']
        stop = Event()
        def sample_scan():
            values = {player.word(address)}
            while not stop.wait(.01):
                values.add(player.word(address))
            return values
        with ThreadPoolExecutor(max_workers=1) as pool:
            sample = pool.submit(sample_scan)
            try:
                tap(180, 85)
                time.sleep(2)
                capture('scan')
                tracks = wait_library(len(NAMES))
            finally:
                stop.set()
            observed = sample.result()
        assert observed <= {0, 1}, observed
        print('Diagnostic scan_running samples:', sorted(observed))
    assert 'CI Tone' in str(tracks), tracks
    assert {item['title'] for item in tracks['items']} == set(NAMES), tracks
    print(f'Fresh V{firmware_version()}: stock UI scanned {len(NAMES)} generated tracks; TCP index verified.')


def audio():
    info = capture_info(ROOT)
    assert (info['channels'], info['sample_bytes'], info['rate']) == (2, 4, 44100), info
    assert info['bytes'] >= 4096, info
    with (ROOT / 'audio.pcm').open('rb') as capture:
        data = capture.read(1024 * 1024)
    # The DAC path promotes signed 16-bit input to 32-bit. Ignore startup silence/
    # fade but require two complete byte-exact periods, not merely a nonzero file.
    period = b''.join(struct.pack('<ii', value << 16, value << 16)
                      for value in ([4096] * 50 + [-4096] * 50))
    assert period * 2 in data, 'PCM does not contain the generated source waveform'
    print('Decoded stereo / 44.1 kHz / 32-bit PCM matches generated 16-bit source exactly.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', action='store_true')
    args = parser.parse_args()
    audio() if args.audio else scan()
