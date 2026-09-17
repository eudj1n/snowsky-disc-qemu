"""Dedicated DISC V2.57 library reset; disposable generated media ONLY."""
import asyncio
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from queue_check import connection, http_client, collect
from remote_control import call, send, snapshot, flush, ROOT, NAMES, memory_state
from http_check import db_rows
from scan_cancel_check import scan
from player_memory import PlayerMemory
from inspect_link_commands import commands


def tables():
    return {name for name, in db_rows("SELECT name FROM sqlite_master WHERE type='table'")}


def system_config():
    with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/sysconfig.db?mode=ro', uri=True) as db:
        return db.execute('SELECT * FROM SYSCONFIG').fetchall()


def source_bytes():
    sd = ROOT / 'tmp/sdcard'
    expected = {sd / 'Кириллица Ё й' / name for name in NAMES}
    assert {p for p in sd.rglob('*') if p.is_file()} == expected
    for path in expected:
        assert path.read_bytes() == (Path('/sdcard') / path.relative_to(sd)).read_bytes()


async def full_scan(client):
    with PlayerMemory(ROOT, '2.57') as memory:
        await scan(client, memory)
    assert (await call(client.tracks))['total'] == 3


def missing_favorites(http):
    reply = http.request('GET', '/song_category_tree/', headers={
        'type': 'love/song', 'start-pos': '0', 'num-max': '100'})
    assert reply.headers['total-num'] == '-1', reply.headers
    try:
        reply.page()
    except ValueError:
        pass
    else:
        raise AssertionError('missing table must not be silently presented as an empty page')


def same_membership(actual, expected):
    # mark follows playback position; it is not persistent playlist membership.
    assert actual['total'] == expected['total'] and actual['items'] == expected['items'], actual


async def exercise(transport):
    name = f'Reset survivor Ё {transport}'
    async with connection(transport) as client:
        http = http_client(transport)
        await full_scan(client)
        assert http.catalog('custom')['total'] == 0
        http.create_playlist(name)
        http.add_to_playlist(0, [[0, 1]])
        custom_before = http.catalog('custom/song', src_list_id=0)
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await send(client, '0104', '0001')
        await snapshot(client, lambda s: s.get('love') is True)
        await asyncio.sleep(2.1)  # Selection-to-pause guard, not a toggle retry.
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        await memory_state('2.57', 2)
        assert http.catalog('love/song')['total'] == 1
        before_queue = http.catalog('curlist/song')
        assert before_queue['total'] == 2
        before_config = system_config()
        before_custom = {table: db_rows(f'SELECT * FROM {table}') for table in
                         ('CUSTOM_PLAYLIST_INDEX', 'CUSTOM_PLAYLIST')}
        before_lists = db_rows('SELECT * FROM PLAY_LIST WHERE LIST_ID NOT IN (0,3)')
        protected = [ROOT / 'usr/data/wpa_supplicant.conf', ROOT / 'usr/data/fiio/db/theme.db']
        protected_bytes = {p: p.read_bytes() if p.exists() else None for p in protected}
        before_tables = tables()
        print(f'{transport}: tables before reset={sorted(before_tables)}', flush=True)
        with PlayerMemory(ROOT, '2.57') as memory:
            assert memory.word('8989d4') == 0, 'never reset during a scan'
            assert memory.word('83a56c') == 0x4f0814
        await flush(client)
        result = client.reset_library(confirm=True)
        if asyncio.iscoroutine(result):
            await result
        events = await collect(client, 1)
        deadline = time.monotonic() + 5
        while 'SONG' in tables() and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        after_tables = tables()
        assert not {'SONG', 'MY_LOVE', 'LIST_SONG_0', 'LIST_SONG_3'} & after_tables
        assert system_config() == before_config
        assert all(db_rows(f'SELECT * FROM {table}') == rows for table, rows in before_custom.items())
        assert db_rows('SELECT * FROM PLAY_LIST WHERE LIST_ID IN (0,3)') == []
        assert db_rows('SELECT * FROM PLAY_LIST WHERE LIST_ID NOT IN (0,3)') == before_lists
        assert {p: p.read_bytes() if p.exists() else None for p in protected} == protected_bytes
        assert not [e for e in events if e[0] in ('a621', 'a60a', 'a622')], events
        await memory_state('2.57', 2)  # Missing a202 metadata is NOT proof of stopped audio.
        source_bytes()
        print(f'{transport}: dropped={sorted(before_tables - after_tables)}; events={events}', flush=True)
        assert http.catalog('all/song')['total'] == 0
        assert http.catalog('curlist/song')['total'] == 0
        missing_favorites(http)
        assert http.catalog('custom')['items'][0]['name'] == name
        assert http.catalog('custom/song', src_list_id=0) == {'total': 2, 'items': [], 'mark': -1}
        assert (await call(client.tracks)) == {'total': 0, 'items': []}
        assert await call(client.now_playing) == {}
        print(f'{transport}: catalogs empty, favorites total=-1, custom count=2/items=[]; '
              'a202 empty while runtime remains paused; files/settings/custom rows unchanged', flush=True)
        if transport == 'tcp':
            # A scan is explicit recovery, never an implicit part of reset_library.
            await full_scan(client)
            print(f'{transport}: scan without reboot: favorites table={"MY_LOVE" in tables()}, '
                  f'custom={http.catalog("custom/song", src_list_id=0)}', flush=True)
            same_membership(http.catalog('custom/song', src_list_id=0), custom_before)
            assert 'MY_LOVE' not in tables()
            missing_favorites(http)

    # Verify persistent effect separately from live caches. Never reboot user guests.
    subprocess.run(['bash', '/repo/scripts/20_boot.sh'], check=True)
    async with connection(transport) as client:
        http = http_client(transport)
        print(f'{transport}: after reboot tracks={await call(client.tracks)}; '
              f'favorites={http.catalog("love/song")}; custom={http.catalog("custom/song", src_list_id=0)}', flush=True)
        assert (await call(client.tracks))['total'] == (3 if transport == 'tcp' else 0)
        assert http.catalog('love/song')['total'] == 0
        same_membership(http.catalog('custom/song', src_list_id=0), custom_before)
        await full_scan(client)
        assert http.catalog('love/song')['total'] == 0
        # A saved custom list remains usable after index recovery, with fresh preflight.
        await asyncio.sleep(2.1)
        result = client.play_playlist(0, 0, http=http, expected_name=name)
        if asyncio.iscoroutine(result):
            await result
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 5
                       and s['song']['song_name'] == custom_before['items'][0]['name'])
        await asyncio.sleep(2.1)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        # Leave the custom queue before removing only our fixture.
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await asyncio.sleep(2.1)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        http.delete_playlist(0)
        assert http.catalog('custom')['total'] == 0
        source_bytes()


async def main():
    assert os.environ.get('CI_DISPOSABLE') == '1' and os.environ.get('FW_VERSION') == '2.57'
    admitted = commands((ROOT / 'usr/bin/mq_player').read_bytes(), '2.57')['admitted']
    assert '0621' in admitted and '0800' not in admitted
    source_bytes()
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    print('LIBRARY RESET PASSED V2.57: dedicated command, scope, reboot and recovery', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
