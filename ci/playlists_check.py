"""Custom-playlist playback on disposable V2.57 generated media only."""
import asyncio
from pathlib import Path

from queue_check import connection, http_client
from remote_control import call, snapshot, NAMES
from http_check import db_rows


async def exercise(transport):
    async with connection(transport) as client:
        http = http_client(transport)
        assert http.catalog('custom')['total'] == 0, 'requires disposable empty playlists'
        songs = http.catalog()['items']
        assert len(songs) == 3
        original_mode = (await call(client.settings))['playMode']
        await call(client.set_play_mode, 0)
        async def select(position, index=None, expected_name=None):
            await asyncio.sleep(2.1)
            result = client.play_playlist(position, index, http=http,
                                          expected_name=expected_name or name)
            if asyncio.iscoroutine(result):
                await result

        async def rejected(position, index=None, expected_name=None):
            before = await snapshot(client)
            try:
                await select(position, index, expected_name)
            except ValueError:
                pass
            else:
                raise AssertionError('stale/empty/out-of-range playlist must be rejected')
            after = await snapshot(client)
            assert after['song'] == before['song'] and after['playerflag'] == before['playerflag']

        def names(position=0):
            return [x['name'] for x in http.catalog('custom/song', src_list_id=position)['items']]

        http.create_playlist('Discarded ID')
        name = f'Playlist Ё + {transport}'
        http.create_playlist(name)
        http.create_playlist('Other playlist')
        http.delete_playlist(0)
        rows = db_rows('SELECT LIST_ID FROM CUSTOM_PLAYLIST_INDEX ORDER BY LIST_ID')
        assert len(rows) == 2 and rows[0][0] != 0, rows
        assert http.catalog('custom')['items'][0]['name'] == name
        # Add in reverse order; use fresh stock catalog order, never insertion order.
        http.add_to_playlist(0, [[2, 2]])
        http.add_to_playlist(0, [[0, 0]])
        expected = names()
        assert len(expected) == 2 and set(expected) == {songs[2]['name'], songs[0]['name']}, expected
        print(f'{transport}: list position 0 maps to SQLite LIST_ID={rows[0][0]}; '
              f'catalog order={expected}', flush=True)

        async def check(index):
            state = await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 5
                                   and s['song']['song_name'] == expected[index])
            queue = http.catalog('curlist/song')
            assert [x['name'] for x in queue['items']] == expected, queue
            assert queue['mark'] == index, queue
            print(f'{transport}: custom playlist {name!r}; selected {index}; '
                  f'pos_id={state["song"]["pos_id"]}; queue={expected}', flush=True)

        await select(0, 1)
        await check(1)
        await select(0)
        await check(0)
        await rejected(0, 2)
        await rejected(1, expected_name='Other playlist')  # Empty list.
        old_name = name
        name += ' renamed'
        http.rename_playlist(0, name)
        await rejected(0, 1, old_name)
        await select(0, 1)
        await check(1)
        http.remove_from_playlist(0, [[0, 0]])
        expected = expected[1:]
        assert names() == expected
        await select(0, 0)
        await check(0)
        await rejected(0, 1)  # Previously valid index no longer exists.
        http.add_to_playlist(0, [[1, 1]])
        membership = set(expected) | {songs[1]['name']}
        expected = names()
        assert len(expected) == 2 and set(expected) == membership
        await select(0, 1)
        await check(1)
        # Leave the list before deletion; no stale queue selector is replayed.
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await asyncio.sleep(2.1)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        http.add_to_playlist(1, [[1, 1]])
        await select(1, 0, 'Other playlist')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 5
                       and s['song']['song_name'] == songs[1]['name'])
        assert [x['name'] for x in http.catalog('curlist/song')['items']] == [songs[1]['name']]
        http.delete_playlist(0)
        await rejected(0, expected_name=name)  # Other list now occupies position 0.
        await rejected(1, expected_name='Other playlist')  # Old position vanished.
        name = 'Other playlist'
        expected = [songs[1]['name']]
        await select(0)
        await check(0)
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await asyncio.sleep(2.1)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        http.delete_playlist(0)
        assert http.catalog('custom')['total'] == 0
        await call(client.set_play_mode, original_mode)
        assert (await call(client.settings))['playMode'] == original_mode
        for filename in NAMES:
            relative = Path('Кириллица Ё й') / filename
            assert (Path('/work/rootfs/tmp/sdcard') / relative).read_bytes() == (
                Path('/sdcard') / relative).read_bytes()


async def main():
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    print('CUSTOM PLAYLIST ACCEPTANCE PASSED V2.57', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
