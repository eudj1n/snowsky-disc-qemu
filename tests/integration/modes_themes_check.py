"""Stock mode/codec/theme acceptance, ONLY on a disposable integration guest."""
from tests.integration.profile import (capability)
import asyncio
import argparse
import os
from pathlib import Path
import sqlite3
import struct
import sys
import time
import zlib
from urllib.parse import quote, unquote_to_bytes

from controller.fiio_link import Client
from controller.fiio_ws import WSClient
from controller.fiio_http import HTTPClient
from controller.fiio_theme import read_lock_screen, upload_lock_screen, select_system_lock_screen, FIELDS, ROUTE, CUSTOM_STYLES, update_system_lock_screen
from tests.integration.settings_check import call, set_and_read, wait_db

ROOT = Path('/work/rootfs')


def theme_rows():
    with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/theme.db?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute('SELECT * FROM CUSTOM_THEME ORDER BY ID')]


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 360, 360, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress((b'\0' + b'\x20\x40\x60' * 360) * 360)) + chunk(b'IEND', b''))


def alias_boundaries(http, source, label):
    # The stock header reader copies at most 63 encoded bytes BEFORE decoding.
    # Raw over-limit requests are diagnostic probes only, on a disposable guest.
    upload_lock_screen(http, source, alias='Alias baseline')
    baseline = read_lock_screen(http)
    headers = {k: baseline.headers[k] for k in FIELDS}
    for alias in ('A' * 63, 'A' * 64, 'Ё' * 10 + 'ABC', 'Ё' * 11, 'Пользовательский'):
        encoded = quote(alias, safe='')
        try:
            if len(encoded) <= 63:
                upload_lock_screen(http, source, alias=alias)
            else:
                http.request('POST', ROUTE, body=source.read_bytes(),
                             headers=dict(headers, alias=encoded))
            with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/theme.db?mode=ro', uri=True) as db:
                db.text_factory = bytes
                saved = db.execute('SELECT ALIAS FROM CUSTOM_THEME WHERE IS_SYSTEM=0').fetchone()[0]
            assert saved == unquote_to_bytes(encoded[:63]), (encoded, saved)
            reply = read_lock_screen(http)
            assert reply.headers['alias'] == '' and reply.body == source.read_bytes()
            print(f'{label}: alias encoded={len(encoded)} stored-bytes={len(saved)} '
                  f'lossless={saved == alias.encode()}', flush=True)
        finally:
            # A chopped percent-encoded UTF-8 sequence can leave invalid text in
            # SQLite. Restore through stock HTTP before ordinary row decoding.
            upload_lock_screen(http, source, alias='Alias restored')


async def modes(client, label):
    await call(client.handshake)
    original_mode = await call(client.device_setting, 'work_mode')
    original_codec = await call(client.device_setting, 'bt_source_codec')
    volume = (await call(client.settings))['currentVolume']
    try:
        for mode, persisted in ((1, 1), (8, 0), (10, 5), (8, 0)):
            await set_and_read(client, 'work_mode', mode)
            await wait_db('SELECT WORK_MODE,INPUT_MODE FROM SYSCONFIG', [(persisted, mode)])
        for codec in range(5):
            await set_and_read(client, 'bt_source_codec', codec)
            await wait_db('SELECT BT_CODEC FROM SYSCONFIG', [(codec,)])
            assert await call(client.device_setting, 'work_mode') == 8
    finally:
        # Codec selection reopens LOCALPLAYER; restore the requested mode last.
        await set_and_read(client, 'work_mode', 8)
        await set_and_read(client, 'bt_source_codec', original_codec)
        await set_and_read(client, 'work_mode', original_mode)
    assert (await call(client.settings))['currentVolume'] == volume
    print(f'{label}: USB/local/AirPlay control transitions and all five source codecs persisted; restored', flush=True)


def system_edits(http, label):
    before = theme_rows()
    active = next(r for r in before if r['USE'])
    slot = 1
    saved = read_lock_screen(http, slot, system=True)
    headers = saved.headers
    original_flags = dict(item.split('=') for item in headers['lock-screen'].split(';'))
    original_color = tuple(int(item.split('=')[1]) for item in headers['front-color'].split(';'))
    changes = ([{'alpha': value} for value in (49, 0, 100)] +
               [{'color': rgb} for rgb in ((253, 0, 255), (251, 255, 0),
                                          (255, 255, 255), (255, 169, 169))] +
               [{'style': style} for style in CUSTOM_STYLES] +
               [{f'show_{name}': value} for name in ('time', 'date', 'battery', 'id3')
                for value in (False, True)])
    try:
        for change in changes:
            reply = update_system_lock_screen(http, slot, **change)
            row = next(r for r in theme_rows() if r['IS_SYSTEM'] and r['POS_ID'] == slot)
            flags = dict(item.split('=') for item in reply.headers['lock-screen'].split(';'))
            rgb = tuple(int(item.split('=')[1]) for item in reply.headers['front-color'].split(';'))
            assert row['ALPHA'] == int(reply.headers['back-groud'].split('=')[1])
            assert row['FRONT_COLOR'] == (rgb[0] << 16 | rgb[1] << 8 | rgb[2])
            assert tuple(row['LOCK_' + name.upper()] for name in flags) == tuple(int(v) for v in flags.values())
            assert row['USE'] == 1
            assert reply.body == saved.body == (ROOT / row['PATH'].lstrip('/')).read_bytes()
            for other in theme_rows():
                if other['IS_SYSTEM'] and other['POS_ID'] == slot:
                    continue
                original = next(r for r in before if r['ID'] == other['ID'])
                assert other == dict(original, USE=0), (other, original)
        print(f'{label}: system opacity/RGB/four styles/independent overlays verified in HTTP and DB', flush=True)
    finally:
        update_system_lock_screen(http, slot,
            alpha=int(headers['back-groud'].split('=')[1]), color=original_color,
            style=headers['msg-style'],
            **{f'show_{name}': value == '1' for name, value in original_flags.items()})
        select_system_lock_screen(http, active['POS_ID'])
    assert theme_rows() == before, 'system editing did not restore original database state'
    assert read_lock_screen(http, slot, system=True).body == saved.body
    print(f'{label}: system metadata, original image and active selection restored', flush=True)


def themes(host, label):
    http = HTTPClient(host, 12103, host_header='127.0.0.1:12103')
    initial = theme_rows()
    active = [r for r in initial if r['USE'] == 1]
    assert len(active) == 1 and active[0]['IS_SYSTEM'] == 1, 'requires disposable stock theme'
    originals = {r['POS_ID']: r for r in initial if r['IS_SYSTEM'] == 1}
    # Exercise the five advertised system slots, with byte-exact HTTP readback.
    for slot, row in originals.items():
        select_system_lock_screen(http, slot)
        reply = read_lock_screen(http, slot, system=True)
        assert reply.headers['flag-in-use'] == '1'
        assert reply.body == (ROOT / row['PATH'].lstrip('/')).read_bytes()
        assert [r['POS_ID'] for r in theme_rows() if r['IS_SYSTEM'] and r['USE']] == [slot]
    if capability('theme_styles'):
        system_edits(http, label)
    source = Path('/work/theme-ci.png')
    source.write_bytes(png())
    upload_lock_screen(http, source, alias='Theme + Ё', alpha=70, color=(12, 34, 56))
    reply = read_lock_screen(http)
    assert reply.body == source.read_bytes()
    assert reply.headers['back-groud'] == 'alpha=70'
    assert reply.headers['lock-screen'] == 'time=1;date=1;battery=1;id3=0'
    assert reply.headers['front-color'] == 'r=12;g=34;b=56'
    row = next(r for r in theme_rows() if not r['IS_SYSTEM'])
    assert row['ALIAS'] == 'Theme + Ё'  # custom GET returns blank alias on V2.57
    assert (row['ALPHA'], row['LOCK_TIME'], row['LOCK_DATE'], row['LOCK_BATTERY'],
            row['LOCK_ID3'], row['FRONT_COLOR'], row['USE']) == (70, 1, 1, 1, 0, 0x0c2238, 1)
    assert (ROOT / row['PATH'].lstrip('/')).read_bytes() == source.read_bytes()
    if capability('theme_styles'):
        # Explicitly probe time both off/on, including analog clock, rather than
        # inferring firmware coupling from the app's observed clock time=1 POST.
        for style in CUSTOM_STYLES:
            for show_time in (False, True):
                upload_lock_screen(http, source, style=style, show_time=show_time,
                                   show_date=False, show_battery=False, show_id3=False,
                                   alias='Styles', alpha=70, color=(12, 34, 56))
                reply = read_lock_screen(http)
                assert reply.body == source.read_bytes()
                assert reply.headers['msg-style'] == style
                assert reply.headers['subclass'] == 'lock_screen/custom/default'
                assert reply.headers['lock-screen'] == f'time={int(show_time)};date=0;battery=0;id3=0'
                assert reply.headers['back-groud'] == 'alpha=70'
                assert reply.headers['front-color'] == 'r=12;g=34;b=56'
                assert reply.headers['flag-in-use'] == '1'
                row = next(r for r in theme_rows() if not r['IS_SYSTEM'])
                assert (row['LOCK_TIME'], row['LOCK_DATE'], row['LOCK_BATTERY'],
                        row['LOCK_ID3'], row['USE']) == (int(show_time), 0, 0, 0, 1)
                assert (ROOT / row['PATH'].lstrip('/')).read_bytes() == source.read_bytes()
        print(f'{label}: four custom styles with time off/on, image and metadata preserved', flush=True)
        alias_boundaries(http, source, label)
        reply = read_lock_screen(http)
    # Pin the unsafe stock semantics so callers do not introduce metadata-only updates.
    select_system_lock_screen(http, active[0]['POS_ID'])
    headers = {k: reply.headers[k] for k in FIELDS}
    headers['flag-in-use'] = '0'
    http.request('POST', ROUTE, body=source.read_bytes(), headers=headers)
    assert not any(r['USE'] for r in theme_rows()), 'flag=0 stock behavior changed'
    http.request('POST', ROUTE, body=b'', headers=headers)
    empty = read_lock_screen(http)
    assert empty.body == b'' and empty.headers['content-type'] == 'image/none'
    assert next(r for r in theme_rows() if not r['IS_SYSTEM'])['PATH'] == ''
    # Restore the active system selection; all changes live in a disposable volume.
    select_system_lock_screen(http, active[0]['POS_ID'])
    for row in theme_rows():
        if row['IS_SYSTEM']:
            assert row == originals[row['POS_ID']], (row, originals[row['POS_ID']])
    print(f'{label}: five system themes, exact custom PNG, overlay metadata and stock empty-body/activation quirks', flush=True)


async def main():
    # Stock closes/reopens the listener after the preceding WS client exits.
    # Retry only connection establishment, never a sent command.
    deadline = time.monotonic() + 8
    while True:
        try:
            client = Client(timeout=8)
            break
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(.2)
    with client:
        await modes(client, 'TCP')
    await asyncio.sleep(2)
    async with WSClient('ws://wsbridge:12103/api/websocket', timeout=8,
                        host_header='127.0.0.1:12103') as client:
        await modes(client, 'WS')
    themes('127.0.0.1', 'direct')
    themes('wsbridge', 'proxy')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--themes-only', action='store_true')
    args = parser.parse_args()
    if os.environ.get('CI_DISPOSABLE') != '1':
        raise SystemExit('requires CI_DISPOSABLE=1; never run against interactive state')
    if args.themes_only:
        themes('127.0.0.1', 'direct')
        themes('wsbridge', 'proxy')
    else:
        asyncio.run(main())
