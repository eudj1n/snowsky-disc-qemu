"""Exercise SD removal/reinsert and charging in a disposable integration guest."""
from tests.integration.profile import (version as firmware_version, capability, diagnostic)
import hashlib
from pathlib import Path
import sys
import time
from emulator.runtime.keys import Device
from emulator.runtime.peripherals import Peripherals


def main():
    root = Path('/work/rootfs')
    controls = Peripherals(Device(root))
    card = root / 'tmp/sdcard'
    def tracks():
        return {str(p.relative_to(card)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in card.rglob('*.wav')}
    before = tracks()
    assert before, 'Expected generated CI media'
    version = controls._profile()['version']
    if capability('sd_hotplug'):
        from tests.integration.storage_check import ui, starts, matches, wait_for, dismiss
        from research.diagnostics.player_memory import PlayerMemory
        initial_scans = starts()
    # A real open file prevents unmount. Refuse before stock cleanup and keep
    # both the nodes and data intact; never use forced/lazy unmount to fake success.
    with next(card.rglob('*.wav')).open('rb'):
        controls.set_sd(False)
        deadline = time.monotonic() + 10
        while controls.operation and time.monotonic() < deadline:
            time.sleep(.1)
        assert controls.error and 'busy' in controls.error, controls.snapshot()
        assert controls.snapshot()['sd_inserted'] and tracks() == before
    for inserted in (False, True, False, True):
        controls.set_sd(inserted)
        deadline = time.monotonic() + 40
        while controls.operation and time.monotonic() < deadline:
            time.sleep(.1)
        assert controls.operation is None and controls.error is None, controls.snapshot()
        assert controls.snapshot()['sd_inserted'] == inserted
        if capability('sd_hotplug'):
            deadline = time.monotonic() + 8
            while ui()['sd'] != int(inserted) and time.monotonic() < deadline:
                time.sleep(.1)
            assert ui()['sd'] == int(inserted), 'Stock UI did not receive SD event'
        assert controls._mounted(card) == inserted
        assert controls._mounted(Path('/tmp/sdcard')) == inserted
        if inserted:
            assert tracks() == before, f'SD filenames/content changed: {before!r} -> {tracks()!r}'
        else:
            assert not tracks(), 'Removed SD remains visible'
            # Tap and boot helpers must not reconnect an ejected card.
            controls._mount_sd()
            assert not controls._mounted(card)
    for connected in (True, False):
        controls.set_usb(connected)
        assert controls.snapshot()['usb_connected'] == connected
        expected = 'Charging' if connected else 'Discharging'
        assert (root / 'sys/class/power_supply/cw221X-bat/status').read_text().strip() == expected
        if capability('usb_power'):
            from research.diagnostics.player_memory import PlayerMemory
            with PlayerMemory(root, firmware_version()) as memory:
                deadline = time.monotonic() + 5
                while memory.word(diagnostic('power.usb_detected')[0], 1) != int(connected) and time.monotonic() < deadline:
                    time.sleep(.1)
                assert memory.word(diagnostic('power.usb_detected')[0], 1) == int(connected), 'Native USB detector did not follow cable'
    if capability('sd_hotplug'):
        # SD insertion queues a later stock UI auto-scan. A mounted card and a
        # finished USB toggle do not establish a stable catalog. The TCP/WS
        # comparison must not straddle that scan's drop/rebuild of SONG.
        wait_for(lambda: starts() > initial_scans, 'peripheral auto-scan started', 30)
        with PlayerMemory(root, version) as memory:
            scan_flag = memory.profile['diagnostics']['network']['scan_running']
            wait_for(lambda: memory.word(scan_flag) == 0 and ui()['modal'] == 1,
                     'peripheral auto-scan finished/result visible', 30)
        wait_for(matches, 'peripheral SD/SQLite/TCP catalog agreement', 30)
        dismiss()
        print('Viewer: insertion-triggered scan settled before TCP/WS comparison.')
    print(f'Viewer: SD media preserved; USB cable/sysfs and V{firmware_version()} native power detection verified.')


if __name__ == '__main__':
    main()
