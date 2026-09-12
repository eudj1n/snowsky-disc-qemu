"""V2.57 SD/auto-scan acceptance; ONLY in a disposable integration volume.

Uses stock hotplug and UI events. Never changes firmware memory or library rows.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from firmware_profile import load_profile, validate
from player_memory import PlayerMemory, load_segments, parse_maps, guest_base, read_memory
from keys import Device, Buttons
from guest_check import ROOT, capture, tap
from fiio_link import Client

FIELDS = {'auto': (0x83a5d0, 4), 'sd': (0x83a720, 4),
          'modal': (0x8dee8e, 1), 'locked': (0x8e1735, 1)}


def ui():
    binary = ROOT / 'usr/bin/mq_ui'
    data = binary.read_bytes()
    assert hashlib.sha256(data).hexdigest() == load_profile('2.57')['binaries']['usr/bin/mq_ui']
    pids = [p for p in Device(ROOT).processes()
            if Path(f'/proc/{p}/comm').read_text().strip() == 'mq_ui']
    assert len(pids) == 1, pids
    proc = Path(f'/proc/{pids[0]}')
    maps = parse_maps((proc / 'maps').read_text())
    base = guest_base(maps, load_segments(data), binary.stat())
    with (proc / 'mem').open('rb', buffering=0) as memory:
        return {name: int.from_bytes(read_memory(memory, maps, base, address, size), 'little')
                for name, (address, size) in FIELDS.items()}


def wait_for(predicate, description, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.1)
    capture('storage-failure')
    raise AssertionError(f'Timed out: {description}; UI={ui()}')


def event(action):
    assert action in ('add', 'remove')
    with PlayerMemory(ROOT, '2.57') as player:
        # One chroot-scoped, fingerprinted PID; never multicast or kernel PID 0.
        assert any(row.split()[1:3] == ['15', str(player.pid)] for row in
                   Path('/proc/net/netlink').read_text().splitlines()[1:])
        payload = (f'{action}@/devices/platform/mmc/mmcblk0\0ACTION={action}\0'
                   'SUBSYSTEM=block\0DEVNAME=mmcblk0\0').encode()
        with socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15) as channel:
            channel.bind((0, 0))
            channel.sendto(payload, (player.pid, 0))
    wait_for(lambda: ui()['sd'] == int(action == 'add'), f'SD {action}')


def starts():
    return Path('/work/mq_player.log').read_text(errors='replace').count('scan_songs_thread start')


def db_paths():
    with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/song.db?mode=ro', uri=True) as db:
        try:
            return sorted(row[0] for row in db.execute('SELECT PATH FROM SONG'))
        except sqlite3.OperationalError as error:
            # Stock scan rebuilds SONG; absence/locking during that bounded
            # transition is not an empty finished index. Other errors still fail.
            if str(error) in ('no such table: SONG', 'database is locked'):
                return None
            raise


def matches():
    expected = sorted('/' + str(p.relative_to(ROOT)) for p in (ROOT / 'tmp/sdcard').rglob('*.wav'))
    if db_paths() != expected:
        return False
    try:
        with Client(timeout=2) as client:
            assert client.handshake() == '0306'
            page = client.tracks()
            total, items = page['total'], page['items']
            while len(items) < total:
                page = client.tracks(len(items))
                assert page['total'] == total and page['items'], page
                items.extend(page['items'])
            return total == len(expected) and sorted(i['title'] for i in items) == sorted(
                Path(p).name for p in expected)
    except OSError:
        return False  # Allow the stock single-client listener to reopen.


def dismiss():
    # Use the verified button-background target, after explicitly unlocking UI.
    assert ui()['locked'] == 0
    tap(130, 303)
    wait_for(lambda: ui()['modal'] == 0, 'result dismissed')


def scan(label, remove=True):
    assert ui()['modal'] == ui()['locked'] == 0
    before = starts()
    if remove:
        event('remove')
        time.sleep(1.2)  # Let the stock one-second removal popup finish.
    event('add')
    wait_for(lambda: starts() == before + 1, f'{label}: worker started')
    wait_for(matches, f'{label}: exact SD/SQLite/TCP match', 30)
    with PlayerMemory(ROOT, '2.57') as player:
        wait_for(lambda: player.word(player.profile['diagnostics']['network']['scan_running']) == 0,
                 'worker finished')
    time.sleep(1)  # Stock completion notification -> result button layout.
    capture(f'storage-{label}')
    print(label, db_paths(), flush=True)


def run():
    assert os.environ.get('FW_VERSION') == '2.57', 'UI addresses are V2.57-only'
    validate(ROOT, load_profile('2.57'))
    sd = ROOT / 'tmp/sdcard'
    relative = Path('Кириллица Ё й/CI Tone — Проверка.wav')
    original = sd / relative
    assert sorted(p.relative_to(sd) for p in sd.rglob('*') if p.is_file()) == [relative], \
        'Requires only the generated CI fixture; refusing to modify other media'
    assert original.read_bytes() == (Path('/sdcard') / relative).read_bytes()
    subprocess.run(['bash', '/repo/scripts/20_boot.sh'], check=True)

    # Recreate first enumeration: mmcblk0 and mmcblk0p1 alias one loop device.
    for name in ('blkid.tab', 'blkid.tab.old'):
        (ROOT / 'run/blkid' / name).unlink(missing_ok=True)
    command = ['bash', '-lc', 'source /repo/scripts/lib.sh; guest_run 10 /sbin/blkid']
    print('Cold blkid:', subprocess.check_output(command, text=True).strip(), flush=True)
    subprocess.run(['bash', '-lc', 'source /repo/scripts/lib.sh; sd_mount'], check=True)
    assert '/dev/mmcblk0p1:' in subprocess.check_output(command, text=True)
    scan('first', remove=False)

    before = starts()
    event('add')
    time.sleep(2)
    assert starts() == before and ui()['modal'] == 1, 'Open result must block another scan'
    dismiss()
    added, renamed = sd / 'Новый трек — Ё.wav', sd / 'Переименован — й.wav'
    shutil.copyfile(original, added)
    time.sleep(2)
    assert len(db_paths()) == 1, 'File edit alone unexpectedly changed index'
    scan('add'); dismiss()
    added.rename(renamed)
    scan('rename'); dismiss()
    original.unlink()
    scan('delete'); dismiss()

    # Same add can rescan after dismissal; a remove edge is not required.
    scan('repeat-add', remove=False); dismiss()
    device = Device(ROOT)
    keys = Buttons(ROOT, device)
    keys.gesture('power', 'single')
    wait_for(lambda: ui()['locked'] == 1 and not device.screen_on(), 'screen locked/off')
    before = starts()
    event('add'); time.sleep(2)
    assert starts() == before, 'Locked UI must not start auto scan'
    keys.gesture('power', 'single')
    wait_for(device.screen_on, 'backlight on')
    # Backlight-on can still display the stock clock lockscreen. Tap to unlock.
    tap(180, 180)
    wait_for(lambda: ui()['locked'] == 0, 'clock lockscreen dismissed')
    time.sleep(2)
    assert starts() == before, 'Earlier blocked insertion unexpectedly replayed'
    scan('after-unlock', remove=False); dismiss()
    print('V2.57: cold-cache remount, modal/lock gates, Unicode add/rename/delete and repeated scans passed.',
          flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable', action='store_true', required=True,
                        help='Confirm this is the disposable CI work volume')
    parser.parse_args()
    run()
