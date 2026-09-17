"""V2.57 preset/slot isolation through stock TCP/WS, disposable guests only."""
import asyncio
import json
import time

from tests.integration.profile import require_acceptance
from tests.integration.queue_check import connection
from tests.integration.settings_check import call, db, set_and_read, wait_db


# Independent oracle from V2.57 player_handle_link_set_eq_type (4ef174).
PRESETS = {255: 0, 0: 1, 1: 5, 2: 2, 3: 6, 4: 3, 5: 7, 6: 4,
           8: 8, 9: 9, 10: 10, **{160 + i: 11 + i for i in range(10)}}


def rows():
    return db('SELECT STYLE_PRESET,MASTER_GAIN,PARAMS_JSON FROM PEQ ORDER BY STYLE_PRESET', 'song.db')


async def bands_read(client, expected):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        actual = await call(client.peq)
        if actual == expected:
            return
        await asyncio.sleep(.1)
    raise AssertionError(f'PEQ readback mismatch: actual={actual}, expected={expected}; rows={rows()}')


async def persisted(slot, bands, master):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        matches = [r for r in rows() if r[0] == slot]
        if len(matches) == 1:
            _, gain, params = matches[0]
            values = json.loads(params)
            normalized = [dict(b, gain=float(b['gain']), qValue=float(b['qValue'])) for b in values]
            if gain == master and normalized == bands:
                return
        await asyncio.sleep(.1)
    raise AssertionError(f'PEQ slot {slot}: persisted parameters mismatch')


async def exercise(transport):
    async with connection(transport) as client:
        original = await call(client.device_setting, 'eq_type')
        volume = (await call(client.settings))['currentVolume']
        saved = {}
        try:
            for wire, stored in PRESETS.items():
                await set_and_read(client, 'eq_type', wire)
                await wait_db('SELECT EQ_TYPE FROM SYSCONFIG', [(stored,)])
                bands = await call(client.peq)
                assert [b['position'] for b in bands] == list(range(10))
                if wire >= 160 and wire != 255:
                    saved[wire] = (bands, await call(client.device_setting, 'eq_master_db'))
            baseline = rows()
            for wire in saved:
                await set_and_read(client, 'eq_type', wire)
                # First-use defaults can report Q=.71 while the new row already
                # stores .7. Back up the freshly reloaded persisted profile, not
                # that transient first-use response (documented stock rounding).
                bands = await call(client.peq)
                master = await call(client.device_setting, 'eq_master_db')
                await persisted(PRESETS[wire], bands, master)
                before = rows()
                # Non-adjacent bands distinguish position/count and verify a partial edit.
                edits = [dict(position=p, frequency=500 + 100 * (wire - 160) + p,
                              gain=-1.0 - p, qValue=1.5, filterType=0) for p in (0, 9)]
                expected = [dict(b) for b in bands]
                for b in edits:
                    expected[b['position']] = b
                await call(client.set_peq, edits)
                await bands_read(client, expected)
                await set_and_read(client, 'eq_master_db', -2.0)
                await persisted(PRESETS[wire], expected, -2.0)
                assert [r for r in rows() if r[0] != PRESETS[wire]] == [
                    r for r in before if r[0] != PRESETS[wire]], 'another slot changed'
                await set_and_read(client, 'eq_type', 255)
                await set_and_read(client, 'eq_type', wire)
                await bands_read(client, expected)
                assert await call(client.device_setting, 'eq_master_db') == -2.0
                await call(client.set_peq, bands)
                await set_and_read(client, 'eq_master_db', master)
                await bands_read(client, bands)
                await persisted(PRESETS[wire], bands, master)
                print(f'{transport}: User {wire - 159}, partial edit, slot isolation, reload/restoration PASS', flush=True)
            assert rows() == baseline, 'PEQ database not restored exactly'
        finally:
            # No automatic mutation retry. A failure is left for inspection in
            # this disposable stack; successful slots have already been restored.
            await set_and_read(client, 'eq_type', original)
        assert (await call(client.settings))['currentVolume'] == volume
        print(f'{transport}: all 21 supported preset codes and 10 user slots PASS', flush=True)


async def main():
    require_acceptance('peq')
    for transport in ('tcp', 'ws'):
        await exercise(transport)


if __name__ == '__main__':
    asyncio.run(main())
