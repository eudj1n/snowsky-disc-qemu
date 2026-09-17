"""V2.57 disposable CI display-time fixture; never patch guest memory."""
import argparse
import os
import sqlite3
import time

from storage_check import ROOT, Device, load_profile, validate, ui


def run(configure):
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('Requires the disposable V2.57 CI stack')
    validate(ROOT, load_profile('2.57'))
    database = ROOT / 'usr/data/fiio/db/sysconfig.db'
    if configure:
        if Device(ROOT).processes():
            raise RuntimeError('Stop the guest before preparing its CI settings')
        with sqlite3.connect(f'file:{database}?mode=rw', uri=True) as db:
            before = db.execute('SELECT ID, LIGTH_ON_TIME FROM SYSCONFIG').fetchall()
            if len(before) != 1 or before[0][0] != 1:
                raise RuntimeError('Unexpected SYSCONFIG fixture')
            db.execute('UPDATE SYSCONFIG SET LIGTH_ON_TIME=7 WHERE ID=1')
        print(f'CI-only display-time fixture: {before[0][1]} -> 7 (never)', flush=True)
    else:
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as db:
            assert db.execute('SELECT LIGTH_ON_TIME FROM SYSCONFIG WHERE ID=1').fetchone() == (7,)
        deadline = time.monotonic() + 10
        while True:
            values = ui({'display_index': (0x8e1721, 1), 'display_seconds': (0x83a650, 4)})
            if values == {'display_index': 7, 'display_seconds': 65535}:
                print(f'CI display-time readback: {values}', flush=True)
                return
            if time.monotonic() >= deadline:
                raise AssertionError(values)
            time.sleep(.1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true')
    run(parser.parse_args().configure)
