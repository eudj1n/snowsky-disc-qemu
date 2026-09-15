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


async def exercise(client, label):
    await call(client.handshake)
    before_volume = (await call(client.settings))['currentVolume']
    original = {name: await call(client.device_setting, name)
                for name in ('gain', 'dre', 'filter', 'spdif', 'eq_type')}
    saved_bands = None
    saved_master = None
    try:
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
    print(f'{label}: gain/DRE/filter/SPDIF and user PEQ readback + SQLite persistence; settings restored', flush=True)


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
