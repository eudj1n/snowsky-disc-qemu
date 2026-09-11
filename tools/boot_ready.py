#!/usr/bin/env python3
"""Wait for the guest's input devices and first framebuffer flush, without TCP probes."""
import os
from pathlib import Path
import time

from keys import Device


def ready(device, proc=Path('/proc')):
    # 15_controls.sh resets this marker before each boot: old pixels cannot count.
    try:
        if (device.root / 'emu/fb-live').read_bytes() not in (b'\x00', b'\x01'):
            return False
    except OSError:
        return False
    expected = {b'/usr/bin/mq_ui': 'event1', b'/usr/bin/mq_player': 'event0'}
    found = set()
    for pid in device.processes():  # live processes in this exact chroot only
        entry = proc / str(pid)
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            for program, event in expected.items():
                if program in args and any(
                    fd.resolve() == device.root / 'dev/input' / event
                    for fd in (entry / 'fd').iterdir()
                ):
                    found.add(program)
        except OSError:
            continue  # process/fd disappeared during the snapshot
    return found == set(expected)


def wait_ready(device, timeout=60, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while not ready(device):
        if clock() >= deadline:
            raise TimeoutError('Guest input/framebuffer not ready; inspect mq_ui.log and mq_player.log')
        sleep(.2)


if __name__ == '__main__':
    wait_ready(Device(os.environ.get('ROOTFS', '/work/rootfs')))
    print('Guest input devices open and first framebuffer flush received', flush=True)
