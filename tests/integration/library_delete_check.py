"""Category DELETE scope on generated disposable V2.57 media ONLY.

Raw destructive requests deliberately stay here, outside the public client.
Never select a deletion target for playback while sending DELETE.
"""
import asyncio
import hashlib
import json
import os

from tests.integration.queue_check import connection, http_client
from tests.integration.remote_control import call, send, snapshot, ROOT
from tests.fixtures.library_fixture import generate, TRACKS, FOLDER
from tests.integration.track_end_check import sources
from tests.integration.scan_cancel_check import scan
from research.diagnostics.player_memory import PlayerMemory
from tests.integration.http_check import db_rows
from controller.fiio_http import range_body


def names(http, category='all/song', **filters):
    page = http.catalog(category, **filters)
    assert page['total'] == len(page['items']), page
    return [row['name'] for row in page['items']]


def observe(http):
    return {
        'catalog': names(http),
        'favorites': names(http, 'love/song'),
        'playlists': http.catalog('custom'),
        'members': [http.catalog('custom/song', src_list_id=row['pos'])
                    for row in http.catalog('custom')['items']],
        'db_song_paths': db_rows('SELECT PATH FROM SONG ORDER BY PATH'),
        'db_custom': db_rows('SELECT ID, PLAYLIST_ID, PATH FROM CUSTOM_PLAYLIST ORDER BY PLAYLIST_ID, ID'),
        'db_lists': db_rows('SELECT LIST_ID FROM CUSTOM_PLAYLIST_INDEX ORDER BY LIST_ID'),
        'db_favorite_paths': db_rows('SELECT PATH FROM MY_LOVE ORDER BY PATH'),
    }


def check_effects(before, after, category, delete_source, generated):
    """Assert independently observed membership loss/stale references, not HTTP 200."""
    chosen = {'Library Alpha', 'Library Gamma'}
    paths = {'/' + str(p.relative_to(ROOT))
             for p, (title, _) in generated.items() if title in chosen}
    # Every category uses a different table scope. Source deletion from a custom
    # list is path-based across ALL custom lists, but leaves SONG/MY_LOVE stale.
    catalog_removed = chosen if category == 'all/song' else set()
    assert after['catalog'] == [n for n in before['catalog'] if n not in catalog_removed]
    assert after['db_song_paths'] == [r for r in before['db_song_paths']
                                     if not (catalog_removed and r[0] in paths)]
    assert after['favorites'] == ([] if category in ('all/song', 'love/song')
                                  else before['favorites'])
    assert after['db_favorite_paths'] == ([] if category in ('all/song', 'love/song')
                                          else before['db_favorite_paths'])
    expected_members = {
        'custom/song': [['Library Beta'], ['Library Beta'] if delete_source
                        else ['Library Alpha', 'Library Beta', 'Library Gamma']],
        'all/song': [['Library Beta'], ['Library Beta']],
        'love/song': [['Library Alpha', 'Library Beta', 'Library Gamma']] * 2,
        'custom': [['Library Alpha', 'Library Beta', 'Library Gamma']],
    }[category]
    assert [[r['name'] for r in p['items']] for p in after['members']] == expected_members
    assert [p['total'] for p in after['members']] == [len(m) for m in expected_members]
    assert [r['count'] for r in after['playlists']['items']] == [len(m) for m in expected_members]
    assert [r['name'] for r in after['playlists']['items']] == (
        ['Delete witness Ё'] if category == 'custom' else ['Delete target Ё', 'Delete witness Ё'])
    target_id = before['db_lists'][0][0]
    assert after['db_lists'] == (before['db_lists'][1:] if category == 'custom' else before['db_lists'])
    expected_rows = []
    for row in before['db_custom']:
        _, list_id, path = row
        remove = ((category == 'custom' and list_id == target_id)
                  or (category == 'all/song' and path in paths)
                  or (category == 'custom/song' and path in paths
                      and (delete_source or list_id == target_id)))
        if not remove:
            expected_rows.append(row)
    assert after['db_custom'] == expected_rows


async def index(client, total):
    with PlayerMemory(ROOT, '2.57') as memory:
        await scan(client, memory)
    assert (await call(client.tracks))['total'] == total


async def prepare(client, http):
    assert http.catalog('custom')['total'] == 0
    for position, name in enumerate(('Delete target Ё', 'Delete witness Ё')):
        http.create_playlist(name)
        http.add_selection_to_playlist(position, [[0, 2]], expected_name=name,
                                       category='album/song', album='Shared Album')
        assert names(http, 'custom/song', src_list_id=position) == [
            'Library Alpha', 'Library Beta', 'Library Gamma']
    await asyncio.sleep(2.1)
    # After source recreation/rescan, album playback order need not match HTTP
    # display order. Select the known file from a fresh directory page instead.
    directory = '/tmp/sdcard/' + FOLDER + '/A'
    row = next(row for row in http.directory(directory, local=True)['items']
               if row['name'] == '01.flac')
    await call(lambda: client.play_folder(directory, row['pos'], http=http,
                                          expected_name='01.flac'))
    await snapshot(client, lambda s: s['state'] == 0
                   and s['song']['song_name'] == 'Library Alpha'
                   and s['song']['song_file_path'] == directory + '/01.flac')
    await send(client, '0104', '0001')
    await snapshot(client, lambda s: s.get('love') is True)
    await asyncio.sleep(2.1)
    await call(client.play_all, 3, 'CI Album')
    await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3
                   and s['song']['song_name'] not in {t[1] for t in TRACKS})
    await asyncio.sleep(2.1)
    await call(client.play_pause)
    await snapshot(client, lambda s: s['state'] == 1)
    assert names(http, 'love/song') == ['Library Alpha']


async def exercise(transport, generated, baseline):
    async with connection(transport) as client:
        http = http_client(transport)
        await index(client, 8)
        await call(client.set_play_mode, 4)
        cases = [('custom/song', 0), ('all/song', 0), ('love/song', 0),
                 ('custom', 0), ('custom/song', 1), ('all/song', 1), ('custom', 1)]
        for category, delete_source in cases:
            await prepare(client, http)
            filters = {'src_list_id': 0} if category == 'custom/song' else {}
            page = http.catalog(category, **filters)
            target_names = ({'Delete target Ё'} if category == 'custom' else
                            {'Library Alpha'} if category == 'love/song' else
                            {'Library Alpha', 'Library Gamma'})
            rows = [row for row in page['items'] if row['name'] in target_names]
            assert len(rows) == len(target_names)
            ranges = [[row['pos'], row['pos']] for row in rows]
            before = observe(http)
            state_before = await snapshot(client)
            headers = http._category(category, filters)
            headers.update({'delete_source': str(delete_source),
                            'Content-Type': 'application/json'})
            with PlayerMemory(ROOT, '2.57') as memory:
                assert memory.word('8989d4') == 0, 'no deletion during scan'
            reply = http.request('DELETE', '/song_category_tree/', range_body(ranges), headers)
            assert reply.status == 200
            after = observe(http)
            state_after = await snapshot(client)
            assert state_after['song'] == state_before['song'] and state_after['state'] == 1
            # Physical effects checked independently of HTTP/SQLite responses.
            removed_titles = ({'Library Alpha', 'Library Beta', 'Library Gamma'}
                              if category == 'custom' else target_names) if delete_source else set()
            removed = {p for p, (title, _) in generated.items() if title in removed_titles}
            sd = ROOT / 'tmp/sdcard'
            assert {p for p in sd.rglob('*') if p.is_file()} == (set(baseline) | set(generated)) - removed
            for path, digest in baseline.items():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            for path, (_, data) in generated.items():
                if path in removed:
                    assert not path.exists()
                else:
                    assert path.read_bytes() == data
            check_effects(before, after, category, delete_source, generated)
            print(json.dumps({'transport': transport, 'category': category,
                              'delete_source': delete_source, 'ranges': ranges,
                              'before': before, 'after': after,
                              'removed': sorted(removed_titles)}, ensure_ascii=False), flush=True)
            await index(client, 8 - len(removed))
            recovered = observe(http)
            assert set(recovered['catalog']) == set(before['catalog']) - removed_titles
            assert recovered['db_song_paths'] == [r for r in before['db_song_paths']
                                                  if ROOT / r[0].lstrip('/') not in removed]
            for key in ('db_favorite_paths', 'db_custom', 'db_lists'):
                assert recovered[key] == after[key], (key, recovered, after)
            # A folder-origin favorite retains its path, but loses joined SONG
            # metadata after the file disappears from the scanned index.
            expected_favorites = ['01.flac'] if (
                delete_source and category in ('custom', 'custom/song')) else after['favorites']
            assert recovered['favorites'] == expected_favorites, recovered
            assert recovered['playlists']['items'] == after['playlists']['items']
            assert [(p['total'], p['items']) for p in recovered['members']] == [
                (p['total'], p['items']) for p in after['members']]
            print(json.dumps({'transport': transport, 'category': category,
                              'delete_source': delete_source, 'after_scan': recovered},
                             ensure_ascii=False), flush=True)
            # Restore only exact generated files; no owner data exists in this stack.
            for path in removed:
                with path.open('xb') as output:
                    output.write(generated[path][1])
            if removed:
                await index(client, 8)
            while http.catalog('custom')['total']:
                http.delete_playlist(0)
        print(f'{transport}: category DELETE physical effects checked', flush=True)


async def main():
    assert os.environ.get('CI_DISPOSABLE') == '1' and os.environ.get('FW_VERSION') == '2.57'
    sources()  # Refuse any SD contents other than the three generated CI sources.
    sd = ROOT / 'tmp/sdcard'
    baseline = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sd.rglob('*') if p.is_file()}
    folder = generate(sd)
    generated = {folder / relative: (title, (folder / relative).read_bytes())
                 for relative, title, *_ in TRACKS}
    for transport in ('tcp', 'ws'):
        await exercise(transport, generated, baseline)
    for path, (_, data) in generated.items():
        assert path.read_bytes() == data
        path.unlink()
    for path in sorted((p for p in folder.rglob('*') if p.is_dir()),
                       key=lambda p: len(p.parts), reverse=True):
        path.rmdir()
    folder.rmdir()
    async with connection('tcp') as client:
        await index(client, 3)
    sources()
    print('LIBRARY DELETE PASSED V2.57: disposable files restored and cleaned', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
