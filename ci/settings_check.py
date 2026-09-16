"""Remote settings and PEQ readback, ONLY on disposable integration guests."""
import asyncio
import inspect
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from fiio_link import Client
from fiio_ws import WSClient


async def call(fn, *args):
    value = fn(*args)
    return await value if inspect.isawaitable(value) else value


def db(sql, file='sysconfig.db'):
    with sqlite3.connect(f'file:/work/rootfs/usr/data/fiio/db/{file}?mode=ro', uri=True) as connection:
        return connection.execute(sql).fetchall()


async def wait_db(sql, expected):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        actual = db(sql)
        if actual == expected:
            return
        await asyncio.sleep(.05)
    raise AssertionError(f'{sql}: {actual} != {expected}')


async def set_and_read(client, name, value):
    await call(client.set_device_setting, name, value)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        actual = await call(client.device_setting, name)
        if actual == value:
            return
        await asyncio.sleep(.1)
    raise AssertionError(f'{name}: {actual} != {value}')


def dac_attenuation():
    return tuple((Path('/work/rootfs/emu') / f'dac-{side}').read_bytes()[0]
                 for side in ('left', 'right'))


async def wait_dac(expected):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        actual = dac_attenuation()
        if actual == expected:
            return
        await asyncio.sleep(.05)
    raise AssertionError(f'DAC attenuation: {actual} != {expected}')


async def balance_check(client, label):
    original = await call(client.device_setting, 'balance')
    saved_db = db('SELECT BALANCE_VOL FROM SYSCONFIG')
    baseline = None
    try:
        await set_and_read(client, 'balance', 0)
        await wait_db('SELECT BALANCE_VOL FROM SYSCONFIG', [(0,)])
        baseline = dac_attenuation()
        assert baseline[0] == baseline[1] and baseline[0] < 235, baseline
        for value in (-20, -1, 0, 1, 20, 0):
            await set_and_read(client, 'balance', value)
            packed = 0x100 + value if value > 0 else -value
            await wait_db('SELECT BALANCE_VOL FROM SYSCONFIG', [(packed,)])
            expected = (baseline[0] + max(value, 0), baseline[1] + max(-value, 0))
            await wait_dac(expected)
            print(f'{label}: balance {value:+d}, SQLite {packed:04X}, DAC L/R {expected}', flush=True)
    finally:
        await set_and_read(client, 'balance', original)
        # Both 0000 and 0100 mean center; the helper writes canonical 0000.
        restored = 0x100 + original if original > 0 else -original
        await wait_db('SELECT BALANCE_VOL FROM SYSCONFIG', [(restored,)])
        assert saved_db == [(restored,)] or (original == 0 and saved_db == [(0x100,)])
        if baseline is not None:
            await wait_dac((baseline[0] + max(original, 0), baseline[1] + max(-original, 0)))


async def exercise(client, label):
    await call(client.handshake)
    before_volume = (await call(client.settings))['currentVolume']
    original = {name: await call(client.device_setting, name)
                for name in ('gain', 'dre', 'filter', 'spdif', 'eq_type')}
    saved_bands = None
    saved_master = None
    try:
        await balance_check(client, label)
        for name, value, column, persisted in (
            ('gain', 1 - original['gain'], 'VOL_MODE', 1 - original['gain']),
            ('dre', 1 - original['dre'], 'DRE_STATUS', 1 - original['dre']),
            ('filter', (original['filter'] + 1) % 6, 'FILTER_TYPE', (original['filter'] + 1) % 6),
            ('spdif', 1 - original['spdif'], 'SPDIF', 1 - original['spdif']),
        ):
            await set_and_read(client, name, value)
            await wait_db(f'SELECT {column} FROM SYSCONFIG', [(persisted,)])
            await set_and_read(client, name, original[name])
        await set_and_read(client, 'eq_type', 160)
        await wait_db('SELECT EQ_TYPE FROM SYSCONFIG', [(11,)])
        saved_bands = await call(client.peq)
        saved_master = await call(client.device_setting, 'eq_master_db')
        band = dict(position=0, frequency=1000, gain=-1.0, qValue=1.5, filterType=0)
        await call(client.set_peq, [band])
        await asyncio.sleep(.2)
        result = await call(client.peq)
        assert result[0] == band, result
        await set_and_read(client, 'eq_master_db', -1.0)
        master, params = db('SELECT MASTER_GAIN,PARAMS_JSON FROM PEQ WHERE STYLE_PRESET=11', 'song.db')[0]
        assert master == -1.0
        persisted = json.loads(params)[0]
        assert persisted['frequency'] == 1000 and float(persisted['gain']) == -1.0
        assert float(persisted['qValue']) == 1.5
    finally:
        if saved_bands is not None:
            await call(client.set_peq, saved_bands)
        if saved_master is not None:
            await set_and_read(client, 'eq_master_db', saved_master)
        for name, value in original.items():
            await set_and_read(client, name, value)
    assert (await call(client.settings))['currentVolume'] == before_volume
    print(f'{label}: balance/gain/DRE/filter/SPDIF and user PEQ readback + SQLite persistence; settings restored', flush=True)


async def main():
    deadline = time.monotonic() + 8
    while True:
        try:
            client = Client(timeout=3)
            break
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(.2)
    with client:
        await exercise(client, 'TCP')
    await asyncio.sleep(2)
    async with WSClient('ws://wsbridge:12103/api/websocket', timeout=5,
                        host_header='127.0.0.1:12103') as client:
        await exercise(client, 'WS')


if __name__ == '__main__':
    asyncio.run(main())
