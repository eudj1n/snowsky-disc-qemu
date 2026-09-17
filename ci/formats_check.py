"""V2.57 CUE/DSF/DFF metadata and positional selection on disposable media."""
import asyncio
import hashlib
import os

from queue_check import connection, http_client
from remote_control import call, snapshot, send, ROOT, NAMES
from track_end_check import sources
from formats_fixture import generate, FOLDER
from scan_cancel_check import scan
from player_memory import PlayerMemory
from http_check import db_rows

TITLES = ('DFF Pattern', 'DSF Title Ё', 'Cue First Ё', 'Cue Second й')
BASE = '/tmp/sdcard/' + FOLDER + '/'


async def favorites(client):
    return await call(client.library, 'playlist_tracks', 0, '我的最爱')


async def select(client, name, index, source=1, *, queue=False):
    await asyncio.sleep(2.1)
    if queue:
        await call(client.play_queue_index, index)
    else:
        await call(client.play_index, index, source)
    value = await snapshot(client, lambda s: s['state'] == 0 and s['song']['song_name'] == name)
    # Toggle is also subject to the stock navigation interval. No retry.
    await asyncio.sleep(2.1)
    await call(client.play_pause)
    paused = await snapshot(client, lambda s: s['state'] == 1 and s['song']['song_name'] == name)
    assert paused['song'] == value['song']
    return paused


def check_song(value, title):
    song = value['song']
    cue = title.startswith('Cue ')
    assert song['song_name'] == title
    assert song['is_cue'] is cue and song['is_dsd'] is (not cue)
    assert song['is_sacd'] is False and song['is_m3u'] is False
    assert song['song_duration_time'] == (6000 if cue else 8000)
    assert song['song_sample_rate'] == (44100 if cue else 2822400)
    assert song['song_encoding_rate'] == (16 if cue else 1)
    assert song['song_channel'] == 2
    file = 'Image.wav' if cue else ('Pattern.dsf' if title == TITLES[1] else 'Pattern.dff')
    assert song['song_file_path'] == BASE + file
    assert song['song_track'] == (7 if title == TITLES[1] else 0)
    if cue:
        assert song['song_album_name'] == 'Cue Album Ё'
        assert song['song_artist_name'] == 'Cue Artist'
    elif title == TITLES[1]:
        assert song['song_album_name'] == 'DSF Album'
        assert song['song_artist_name'] == 'Formats Artist'


def check_database():
    rows = db_rows('SELECT PATH, TITLE, TRACK, IS_CUE, IS_ISO, IS_DSD, OFFSET, DURATION FROM SONG')
    rows = [r for r in rows if r[0].startswith(BASE)]
    assert set(rows) == {
        (BASE + 'Image.wav', TITLES[2], 1, 1, 0, 0, 0, 6000),
        (BASE + 'Image.wav', TITLES[3], 2, 1, 0, 0, 6000, 6000),
        (BASE + 'Pattern.dsf', TITLES[1], 7, 0, 0, 1, 0, 0),
        (BASE + 'Pattern.dff', TITLES[0], 0, 0, 0, 1, 0, 0),
    }
    cue_flags = db_rows('SELECT PATH, IS_M3U FROM SONG WHERE IS_CUE=1')
    assert cue_flags == [(BASE + 'Image.wav', None)] * 2
    print('Format source rows:', rows, flush=True)


async def exercise(transport):
    async with connection(transport) as client:
        http = http_client(transport)
        assert (await favorites(client))['total'] == 0
        mode = await call(client.play_mode)
        await call(client.set_play_mode, 4)
        page = http.catalog()
        tcp_page = await call(client.tracks)
        order = [item['name'] for item in page['items']]
        assert page['total'] == tcp_page['total'] == 7
        assert set(order) == set(NAMES) | set(TITLES)
        assert [item['title'] for item in tcp_page['items']] == order
        directory = http.directory(BASE.rstrip('/'))
        assert {item['name'] for item in directory['items']} == {'Image.wav', 'Pattern.dsf', 'Pattern.dff'}
        check_database()
        for title in TITLES:
            index = order.index(title)
            current = await select(client, title, index)
            check_song(current, title)
            assert current['song']['pos_id'] == index + 1
            assert current['playing_num'] == f'{index + 1}/7'
            queue = await call(client.library, 'queue')
            assert queue['total'] == 7
            assert [item['itemName'] for item in queue['items']] == order
            queue_page = http.catalog('curlist/song')
            assert [item['name'] for item in queue_page['items']] == order
            same_id = [i for i, item in enumerate(queue['items'])
                       if item['songId'] == current['song']['id']]
            assert index in same_id
            # Stock can mark the wrong row when mixed CUE/normal IDs collide.
            # Do not hide the ambiguity by deduplicating entries or replacing IDs.
            assert queue_page['mark'] in same_id
            print(f'{transport}: {title!r}: pos={index}, id={current["song"]["id"]}, '
                  f'same-ID positions={same_id}, HTTP mark={queue_page["mark"]}', flush=True)
            if title.startswith('Cue '):
                assert current['song']['id'] == index + 1
                chosen = await select(client, title, index, queue=True)
                check_song(chosen, title)
                await send(client, '0104', '0001')
                await snapshot(client, lambda s: s['love'] is True)

        loved = await favorites(client)
        assert loved['total'] == 2
        assert [item['songName'] for item in loved['items']] == list(TITLES[2:])
        assert all(item['isCue'] is False and item['track'] == 0 and item['songPath'] == ''
                   for item in loved['items'])
        assert set(db_rows('SELECT PATH, TRACK, IS_CUE FROM MY_LOVE')) == {
            (BASE + 'Image.wav', 1, 1), (BASE + 'Image.wav', 2, 1)}
        print(f'{transport}: lossy favorites response={loved}', flush=True)
        for index, title in enumerate(TITLES[2:]):
            current = await select(client, title, index, 6)
            check_song(current, title)
            assert current['love'] is True
        # Leave favorites context before removal; remove only our two entries.
        for title in TITLES[2:]:
            await select(client, title, order.index(title))
            await send(client, '0104', '0000')
            await snapshot(client, lambda s: s['love'] is False)
        assert (await favorites(client))['total'] == 0
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await asyncio.sleep(2.1)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        await call(client.set_play_mode, mode)
        assert await call(client.play_mode) == mode
        print(f'{transport}: format metadata, catalog/queue/favorite positions and restoration PASS', flush=True)


async def main():
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('format acceptance requires disposable V2.57')
    with PlayerMemory(ROOT, '2.57'):
        pass
    sources()
    folder = generate(ROOT / 'tmp/sdcard')
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, '2.57') as memory:
            await scan(client, memory)
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    for p, digest in hashes.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
        p.unlink()
    folder.rmdir()
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, '2.57') as memory:
            await scan(client, memory)
        assert (await call(client.tracks))['total'] == 3
    sources()
    print('FORMAT CHECK PASS V2.57 TCP/WS: CUE/DSF/DFF metadata and identity; sources restored', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
