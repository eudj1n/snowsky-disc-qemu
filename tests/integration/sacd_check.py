"""Opt-in SACD ISO investigation; approved private input, disposable V2.57 only.

No disc/track text is printed on success. Guest diagnostic logs remain private.
The approved source is copied to the temporary SD fixture and is never edited.
"""
import asyncio
from pathlib import Path
import time

from research.diagnostics.inspect_sacd import inspect, digest
from research.diagnostics.player_memory import PlayerMemory
from tests.integration.profile import require_acceptance, version
from tests.integration.queue_check import connection, http_client
from tests.integration.remote_control import call, send, snapshot, flush, ROOT, NAMES
from tests.integration.scan_cancel_check import scan
from tests.integration.http_check import db_rows
from tests.fixtures.sacd_replacement import title_edits


PATH = '/tmp/sdcard/SACD CI/source.iso'


async def queue_page(client):
    page = await call(client.library, 'queue')
    items = list(page['items'])
    while len(items) < page['total']:
        next_page = await call(client.library, 'queue', len(items))
        assert next_page['total'] == page['total'] and next_page['items']
        items.extend(next_page['items'])
    assert len(items) == page['total']
    return dict(total=page['total'], items=items)


async def select(client, title, position, *, source=1):
    await asyncio.sleep(2.1)
    await flush(client)
    if source == 0:
        await call(client.play_queue_index, position)
    else:
        await call(client.play_index, position, source)
    playing = await snapshot(client, lambda s: s['state'] == 0 and s['song']['song_name'] == title)
    # A full state-0 snapshot can precede decoder readiness, especially when
    # selecting the same long ISO track again. Observe actual advancing position
    # before the single pause; never retry that toggle after a missed response.
    deadline = time.monotonic() + 20
    first = None
    advanced = False
    while time.monotonic() < deadline:
        try:
            tag, payload = await call(client.event, deadline - time.monotonic())
        except TimeoutError:
            break
        if tag == 'a103':
            position_ms = int(payload, 16)
            if first is None:
                first = position_ms
            elif position_ms >= first + 1000:
                advanced = True
                break
    if not advanced:
        raise AssertionError('ISO decoder did not produce advancing position')
    await asyncio.sleep(2.1)
    await call(client.play_pause)
    paused = await snapshot(client, lambda s: s['state'] == 1 and s['song']['song_name'] == title)
    assert paused['song'] == playing['song']
    return paused


async def exercise(transport, area):
    async with connection(transport) as client:
        http = http_client(transport)
        page, tcp = http.catalog(), await call(client.tracks)
        assert page['total'] == tcp['total'] == area['tracks'] + 3
        order = [x['name'] for x in page['items']]
        assert order == [x['title'] for x in tcp['items']]
        records = db_rows("SELECT TITLE,TRACK,IS_CUE,IS_ISO,IS_DSD,OFFSET,DURATION,IS_M3U FROM SONG WHERE PATH='" + PATH + "' ORDER BY TRACK")
        assert len(records) == area['tracks']
        assert [r[1] for r in records] == list(range(1, area['tracks'] + 1))
        assert all(r[2:6] == (0, 1, 0, 0) and r[7] is None for r in records)
        # ISO track time fractions are 1/75 s; stock index interprets that
        # two-digit field as centiseconds. Preserve this observed distinction.
        assert [r[6] for r in records] == [f // 75 * 1000 + f % 75 * 10
                                         for f in area['duration_frames']]
        directory = http.directory('/tmp/sdcard/SACD CI')
        assert {x['name'] for x in directory['items']} == {'source.iso'}
        print(f'{transport}: directory rows={len(directory["items"])}, indexed ISO tracks={len(records)}', flush=True)
        print('ISO row structure (ordinal, flags, offset, duration, M3U):', [r[1:] for r in records], flush=True)
        assert (await call(client.library, 'playlist_tracks', 0, '我的最爱'))['total'] == 0
        mode = await call(client.play_mode)
        await call(client.set_play_mode, 4)
        chosen = (records[0], records[-1])
        for record in chosen:
            title, ordinal = record[:2]
            index = order.index(title)
            current = await select(client, title, index)
            song = current['song']
            assert song['is_sacd'] is True and song['is_cue'] is False
            assert song['song_file_path'] == PATH and song['song_channel'] == area['channels']
            assert song['song_sample_rate'] == area['sample_rate']
            assert song['song_track'] == ordinal
            assert song['song_encoding_rate'] == 1 and song['is_dsd'] is True
            assert song['song_duration_time'] == record[6] // 1000 * 1000
            queue = await queue_page(client)
            assert queue['total'] == page['total']
            print('Queue positions relative to catalog:', [order.index(x['itemName']) for x in queue['items']], flush=True)
            assert [x['itemName'] for x in queue['items']] == order
            http_queue = http.catalog('curlist/song')
            assert http_queue['total'] == page['total']
            assert [x['name'] for x in http_queue['items']] == order
            same = await select(client, title, index, source=0)
            assert same['song']['song_file_path'] == PATH
            assert same['song']['song_duration_time'] == song['song_duration_time']
            try:
                await call(client.play_queue_index, queue['total'])
            except ValueError:
                pass
            else:
                raise AssertionError('out-of-bounds queue selection was accepted')
            await send(client, '0104', '0001')
            await snapshot(client, lambda s: s['love'] is True)
            print(f'{transport}: ordinal={ordinal}, wire_track={song["song_track"]}, '
                  f'duration_ms={song["song_duration_time"]}, bits={song["song_encoding_rate"]}, '
                  f'is_dsd={song["is_dsd"]}, catalog/queue/favorite addition PASS', flush=True)
        loved = await call(client.library, 'playlist_tracks', 0, '我的最爱')
        assert loved['total'] == 2
        assert all(x['track'] == 0 and x['isSacd'] is False and x['songPath'] == ''
                   for x in loved['items'])
        print('ISO favorites identity (track, isSacd, path present):',
              [(x.get('track'), x.get('isSacd'), bool(x.get('songPath'))) for x in loved['items']], flush=True)
        assert set(db_rows('SELECT PATH,TRACK,IS_ISO FROM MY_LOVE')) == {(PATH, r[1], 1) for r in chosen}
        for index, item in enumerate(loved['items']):
            current = await select(client, item['songName'], index, source=6)
            assert current['song']['is_sacd'] is True and current['love'] is True
            expected = next(r for r in chosen if r[0] == item['songName'])
            assert current['song']['song_track'] == expected[1]
            assert current['song']['song_duration_time'] == expected[6] // 1000 * 1000
        for title, *_ in chosen:
            await select(client, title, order.index(title))
            await send(client, '0104', '0000')
            await snapshot(client, lambda s: s['love'] is False)
        assert (await call(client.library, 'playlist_tracks', 0, '我的最爱'))['total'] == 0
        # Release ISO decoder before source removal; leave an original track paused.
        await select(client, NAMES[0], order.index(NAMES[0]))
        await call(client.set_play_mode, mode)
        assert await call(client.play_mode) == mode
        print(f'{transport}: two distinct ISO favorites, bounds and state restoration PASS', flush=True)


async def main():
    require_acceptance('sacd')
    source = ROOT / PATH.lstrip('/')
    facts = inspect(source)
    fingerprint = digest(source)
    assert digest('/sdcard/SACD CI/source.iso') == fingerprint, 'SD copy differs from approved input'
    assert len(facts['areas']) == 1 and facts['areas'][0]['channels'] == 2
    area = facts['areas'][0]
    assert area['tracks'] >= 2
    print('SACD input:', fingerprint, facts, flush=True)
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, version()) as memory:
            await scan(client, memory)
    for transport in ('tcp', 'ws'):
        await exercise(transport, area)
    assert digest(source) == fingerprint
    # Replace metadata at the same path only after selecting an ordinary file.
    # The owner-provided original and the /sdcard input copy remain untouched.
    with source.open('rb') as handle:
        new_title, edits = title_edits(handle)
    old_title = db_rows("SELECT TITLE FROM SONG WHERE PATH='" + PATH + "' AND TRACK=1")[0][0]
    with source.open('r+b') as handle:
        for offset, before, after in edits:
            handle.seek(offset)
            assert handle.read(len(before)) == before
            handle.seek(offset)
            handle.write(after)
    assert digest(source) != fingerprint and inspect(source) == facts
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, version()) as memory:
            await scan(client, memory)
    for transport in ('tcp', 'ws'):
        async with connection(transport) as client:
            page = http_client(transport).catalog()
            order = [x['name'] for x in page['items']]
            assert new_title in order and old_title not in order
            assert page['total'] == area['tracks'] + 3
            selected = await select(client, new_title, order.index(new_title))
            assert selected['song']['song_track'] == 1 and selected['song']['is_sacd'] is True
            await select(client, NAMES[0], order.index(NAMES[0]))
            print(f'{transport}: changed ISO title at same path, fresh scan and selection PASS', flush=True)
    with source.open('r+b') as handle:
        for offset, before, after in edits:
            handle.seek(offset)
            assert handle.read(len(after)) == after
            handle.seek(offset)
            handle.write(before)
    assert digest(source) == fingerprint
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, version()) as memory:
            await scan(client, memory)
        order = [x['name'] for x in http_client('tcp').catalog()['items']]
        assert old_title in order and new_title not in order
    source.unlink()
    source.parent.rmdir()
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, version()) as memory:
            await scan(client, memory)
        assert (await call(client.tracks))['total'] == 3
        assert {Path(r[0]).name for r in db_rows('SELECT PATH FROM SONG')} == set(NAMES)
        assert {r['title'] for r in (await call(client.tracks))['items']} == set(NAMES)
    assert digest('/sdcard/SACD CI/source.iso') == fingerprint
    print('SACD CHECK PASS: metadata/positional selection; original media intact, generated catalog restored', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
