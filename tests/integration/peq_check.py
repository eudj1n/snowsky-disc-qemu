"""V2.57 preset/slot isolation through stock TCP/WS, disposable guests only."""
import asyncio
import json
from pathlib import Path
import time

from tests.integration.profile import require_acceptance
from tests.integration.queue_check import connection
from tests.integration.settings_check import call, db, set_and_read, wait_db
from tests.integration.remote_control import send
from controller.fiio_link import Frames


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


async def app_workflow(transport):
    """Captured iOS compact edit / Save / Reset, only on disposable USER10."""
    fixture = json.loads((Path(__file__).resolve().parents[2] / 'controller/tests/fixtures/' /
                          'fiio_control_ios_peq_save_reset.json').read_text())
    capture = fixture['captures'][0]['frames']

    async def captured(client, tag):
        observed = next(f for f in capture if f['direction'] == 'app' and f['tag'] == tag)
        [(actual_tag, body)] = Frames().feed(observed['wire'].encode())
        await send(client, actual_tag, body)

    async def edited(client):
        await bands_read(client, expected)
        assert await call(client.device_setting, 'eq_master_db') == -6.1
        await persisted(20, expected, -6.1)

    async with connection(transport) as client:
        original = await call(client.device_setting, 'eq_type')
        await set_and_read(client, 'eq_type', 169)
        saved_bands = await call(client.peq)
        saved_master = await call(client.device_setting, 'eq_master_db')
        await persisted(20, saved_bands, saved_master)
        before = rows()
        expected = [dict(b) for b in saved_bands]
        expected[0] = dict(position=0, frequency=32, gain=-3.4, qValue=.7, filterType=0)
        await captured(client, '0678')
        await bands_read(client, expected)
        await captured(client, '0630')
        await edited(client)
        assert [r for r in rows() if r[0] != 20] == [r for r in before if r[0] != 20]
        print(f'{transport}: captured compact band/master edits persist BEFORE Save PASS', flush=True)

    async with connection(transport) as client:
        assert await call(client.device_setting, 'eq_type') == 169
        await edited(client)
        before_save = rows()
        await captured(client, '0626')
        await edited(client)
        assert rows() == before_save, 'Save unexpectedly changed a profile'
        print(f'{transport}: reconnect retains edits; captured Save leaves profile unchanged PASS', flush=True)
        # Distinguish Reset from simply clearing the first gain/master: change
        # the last band's frequency and Q through the supported JSON path too.
        expected[9] = dict(position=9, frequency=12345, gain=-2.0, qValue=1.5, filterType=0)
        await call(client.set_peq, [expected[9]])
        await edited(client)
        await captured(client, '0675')
        defaults = [dict(position=p, frequency=f, gain=0.0, qValue=.71, filterType=0)
                    for p, f in enumerate((32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000))]
        await bands_read(client, defaults)
        assert await call(client.device_setting, 'eq_master_db') == 0.0
        reloaded = [dict(b, qValue=.7) for b in defaults]
        await persisted(20, reloaded, 0.0)
        assert [r for r in rows() if r[0] != 20] == [r for r in before if r[0] != 20]
        await set_and_read(client, 'eq_type', 255)
        await set_and_read(client, 'eq_type', 169)
        await bands_read(client, reloaded)

    async with connection(transport) as client:
        assert await call(client.device_setting, 'eq_type') == 169
        await bands_read(client, reloaded)
        assert await call(client.device_setting, 'eq_master_db') == 0.0
        await call(client.set_peq, saved_bands)
        await set_and_read(client, 'eq_master_db', saved_master)
        await bands_read(client, saved_bands)
        await persisted(20, saved_bands, saved_master)
        assert rows() == before, 'captured-workflow baseline not restored'
        await set_and_read(client, 'eq_type', original)
    print(f'{transport}: Reset restores ten bands/master, persists without Save, '
          'survives reselection/reconnect; baseline restored PASS', flush=True)


async def local_apply_workflow(transport):
    """Reproduce the captured app/firmware format mismatch, never on hardware."""
    fixture = json.loads((Path(__file__).resolve().parents[2] / 'controller/tests/fixtures/' /
                          'fiio_control_ios_peq_local_apply.json').read_text())
    from controller.fiio_settings import peq_value
    defaults = peq_value(Frames().feed(fixture['baseline']['bands']['wire'].encode())[0][1])
    # Fingerprinted decoder treats 72 bytes as nine 8-byte records, not
    # [range + ten 7-byte bands]. Malformed position-0 values persist first;
    # selecting the profile again normalizes that band to defaults (Q=.71
    # immediately, .7 serialized). Pin each phase, not a tolerant union.
    malformed = [dict(b) for b in defaults]
    malformed[0] = dict(position=0, filterType=0, frequency=32768, gain=6.2, qValue=179.2)
    malformed[9] = dict(position=9, filterType=0, frequency=32, gain=-3.5, qValue=.7)
    reselected = [dict(b) for b in malformed]
    reselected[0] = dict(defaults[0], qValue=.71)
    persisted_reselected = [dict(b) for b in reselected]
    persisted_reselected[0]['qValue'] = .7
    async with connection(transport) as client:
        original = await call(client.device_setting, 'eq_type')
        await set_and_read(client, 'eq_type', 169)
        saved = await call(client.peq)
        master = await call(client.device_setting, 'eq_master_db')
        before = rows()
        await call(client.set_peq, defaults)
        await set_and_read(client, 'eq_master_db', 0.0)
        for record in fixture['apply']:
            [(tag, body)] = Frames().feed(record['wire'].encode())
            await send(client, tag, body)
        await bands_read(client, malformed)
        assert await call(client.device_setting, 'eq_master_db') == -6.5
        await persisted(20, malformed, -6.5)
        assert [r for r in rows() if r[0] != 20] == [r for r in before if r[0] != 20]
        await set_and_read(client, 'eq_type', 255)
        await set_and_read(client, 'eq_type', 169)
        await bands_read(client, reselected)
        await persisted(20, persisted_reselected, -6.5)
        [(tag, body)] = Frames().feed(fixture['reset']['request']['wire'].encode())
        await send(client, tag, body)
        await persisted(20, defaults, 0.0)
        await set_and_read(client, 'eq_type', 255)
        await set_and_read(client, 'eq_type', 169)
        await bands_read(client, defaults)
        assert await call(client.device_setting, 'eq_master_db') == 0.0
        # The existing JSON helper applies the intended ten-band profile
        # correctly; do not copy the app's malformed bulk hex request.
        [(tag, body)] = Frames().feed(fixture['apply'][1]['wire'].encode())
        intended = peq_value(body)
        await call(client.set_peq, intended)
        await set_and_read(client, 'eq_master_db', -6.5)
        await bands_read(client, intended)
        await persisted(20, intended, -6.5)
        await set_and_read(client, 'eq_type', 255)
        await set_and_read(client, 'eq_type', 169)
        await bands_read(client, intended)
        assert [r for r in rows() if r[0] != 20] == [r for r in before if r[0] != 20]
        await call(client.set_peq, saved)
        await set_and_read(client, 'eq_master_db', master)
        await persisted(20, saved, master)
        assert rows() == before
        await set_and_read(client, 'eq_type', original)
    print(f'{transport}: captured Local Apply format mismatch reproduced in readback/SQLite; '
          'Reset recovery, correct JSON application, other-slot isolation and baseline restoration PASS', flush=True)


async def main():
    require_acceptance('peq')
    for transport in ('tcp', 'ws'):
        await exercise(transport)
        await app_workflow(transport)
        await local_apply_workflow(transport)


if __name__ == '__main__':
    asyncio.run(main())
