"""Exercise SD removal/reinsert and charging in a disposable integration guest."""
import hashlib
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from keys import Device
from viewer_controls import ViewerControls


def main():
    root = Path('/work/rootfs')
    controls = ViewerControls(Device(root))
    card = root / 'tmp/sdcard'
    def tracks():
        return {str(p.relative_to(card)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in card.rglob('*.wav')}
    before = tracks()
    assert before, 'Expected generated CI media'
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
        if controls._profile()['version'] == '2.57':
            from storage_check import ui
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
    print('Viewer: repeated SD eject/insert preserves media; USB charging stub verified.')


if __name__ == '__main__':
    main()
