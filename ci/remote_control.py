"""Remote-control acceptance on ci/fixture.py media, TCP and native WS bridge.

Run only inside a disposable emulator. Uses stock commands, never writes guest DB
or memory directly. Leaves playback paused, restores play mode/favorite state,
and does not change volume.
"""
import asyncio
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from fiio_link import Client, frame
from fiio_ws import WSClient
from probe_keys import snapshot as key_snapshot
from keys import Buttons, Device
from fixture import NAMES

ROOT = Path('/work/rootfs')


async def call(fn, *args):
    result = fn(*args)
    return await result if inspect.isawaitable(result) else result


async def snapshot(client, predicate=lambda value: True, timeout=12):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = await call(client.now_playing)
        except TimeoutError:
            continue
        except json.JSONDecodeError as error:
            print('Invalid now-playing payload:', repr(error.doc), flush=True)
            raise
        if isinstance(last.get('song'), dict) and predicate(last):
            return last
        await asyncio.sleep(.15)
    raise AssertionError(f'No matching full playback snapshot: {last}')


async def memory_state(version, expected):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = key_snapshot(ROOT, version)['player_state']
        if value == expected:
            return
        await asyncio.sleep(.1)
    raise AssertionError(f'Guest state {value}, expected {expected}')


async def flush(client):
    # Bounded drain BEFORE an action, not after it; don't discard its evidence.
    deadline = time.monotonic() + .3
    while time.monotonic() < deadline:
        try:
            await call(client.event, .03)
        except TimeoutError:
            return


async def observe(client, predicate, label, timeout=10):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        try:
            tag, payload = await call(client.event, deadline - time.monotonic())
        except TimeoutError:
            break
        value = json.loads(payload) if tag == 'a202' else payload
        seen.append((tag, value))
        if predicate(tag, value):
            return value
    raise AssertionError(f'No event for {label}: {seen}')


async def send(client, tag, payload):
    if isinstance(client, Client):
        client.socket.sendall(frame(tag, payload))
    else:
        await client.send(tag, payload)


async def exercise(client, transport):
    assert await call(client.handshake) == '0306'
    settings = await call(client.settings)
    version = os.environ['FW_VERSION']
    assert settings['soc_version'] == int(version.replace('.', ''))
    tracks = await call(client.tracks)
    assert tracks['total'] == 3 and {x['title'] for x in tracks['items']} == set(NAMES), tracks
    ordered = tracks['items']
    album = await call(client.library, 'album_tracks', 0, 'CI Album')
    assert album['total'] == 2, album
    assert {x['title'] for x in album['items']} == set(NAMES[1:]), album
    report = {'firmware': version, 'transport': transport, 'checks': []}

    def passed(name):
        report['checks'].append(name)
        print(f'{transport} V{version}: {name}', flush=True)

    async def selected(index, list_type=1, name=None, expected=None):
        await asyncio.sleep(2.1)
        await call(client.play_index, index, list_type, name)
        expected = ordered[index]['title'] if expected is None else expected
        value = await snapshot(client, lambda s: s['state'] == 0 and s.get('playerflag') == list_type and s['song']['song_name'] == expected)
        await memory_state(version, 1)
        return value

    favorite_added = False
    try:
        # Sequential mode, so next/previous have deterministic destinations.
        await call(client.set_play_mode, 0)
        current = await selected(1)
        song = current['song']
        assert song['song_duration_time'] == 30000 and song['song_sample_rate'] == 44100, song
        assert song['song_encoding_rate'] == 16 and song['song_channel'] == 2, song
        assert song['song_file_path'].endswith(NAMES[1]), song
        assert song['song_album_name'] == 'CI Album' and song['song_artist_name'] == 'CI Artist'
        report['metadata_fields'] = sorted(song)
        passed('zero-based track selection and metadata')

        await asyncio.sleep(2.1)  # Stock comm_play_ctrl drops rapid navigation.
        await call(client.next_track)
        await snapshot(client, lambda s: s['state'] == 0 and s['song']['song_name'] == ordered[2]['title'])
        passed('next track')
        await asyncio.sleep(2.1)
        await call(client.previous_track)
        await snapshot(client, lambda s: s['state'] == 0 and s['song']['song_name'] == ordered[1]['title'])
        passed('previous before 10 seconds')

        await flush(client)
        await call(client.seek, 15000)
        tick = await observe(client, lambda t, p: t == 'a103' and 15000 <= int(p, 16) <= 19000,
                             'seek to 15 seconds')
        report['seek_tick_ms'] = int(tick, 16)
        await flush(client)
        await asyncio.sleep(2.1)
        await call(client.previous_track)
        await observe(client, lambda t, p: t == 'a103' and int(p, 16) <= 3000, 'previous restarts')
        await snapshot(client, lambda s: s['song']['song_name'] == ordered[1]['title'])
        passed('seek and previous after 10 seconds restarts same track')

        await flush(client)
        await call(client.play_pause)
        delta = await observe(client, lambda t, p: t == 'a202' and p.get('state') == 1,
                              'pause notification')
        assert 'song' not in delta, delta
        current = await snapshot(client, lambda s: s['state'] == 1)
        await memory_state(version, 2)
        await call(client.seek, 15000)
        await snapshot(client, lambda s: s['state'] == 1)
        await flush(client)
        await call(client.play_pause)
        await observe(client, lambda t, p: t == 'a103' and 15000 <= int(p, 16) <= 19000,
                      'seek while paused takes effect on resume')
        passed('partial pause notification, paused seek and resume')

        for mode in range(5):
            await flush(client)
            await call(client.set_play_mode, mode)
            await observe(client, lambda t, p: t == 'a102' and int(p, 16) == mode, f'play mode {mode}')
            assert (await call(client.settings))['playMode'] == mode
            with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/sysconfig.db?mode=ro', uri=True) as db:
                assert db.execute('SELECT PLAY_MODE FROM SYSCONFIG').fetchone()[0] == mode
        await call(client.set_play_mode, 0)
        passed('all five play modes: event + query + persisted DB')

        await selected(1, 3, 'CI Album', album['items'][1]['title'])
        queue = await call(client.library, 'queue')
        assert {s['itemName'] for s in queue['items']} == set(NAMES[1:]), queue
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['song']['song_name'] == album['items'][0]['title'])
        passed('album selection, album play-all and queue contents')
        await selected(1, 2, 'CI Artist', album['items'][1]['title'])
        await asyncio.sleep(2.1)
        await call(client.play_all, 2, 'CI Artist')
        await snapshot(client, lambda s: s['state'] == 0 and s.get('playerflag') == 2
                       and s['song']['song_name'] == album['items'][0]['title'])
        passed('artist selection and play-all')

        # Only the built-in favorite playlist is seeded; no custom playlist API claim.
        current = await selected(2)
        assert not current['love'], 'Requires fresh disposable favorites'
        await send(client, '0104', '0001')
        await snapshot(client, lambda s: s.get('love') is True)
        favorite_added = True
        favorites = await call(client.library, 'playlist_tracks', 0, '我的最爱')
        assert favorites['total'] == 1 and favorites['items'][0].get('songName') == ordered[2]['title'], favorites
        if version == '2.57':
            await selected(0, 6, expected=ordered[2]['title'])
        else:
            try:
                await call(client.play_index, 0, 6)
            except ValueError:
                pass  # V2.40 internal favorite ID is not the ID in the wire list.
            else:
                raise AssertionError('V2.40 favorite position must fail before a selector is sent')
        # Remove the fixture from the catalog context, not from a one-item
        # active favorites queue. Queue deletion behavior is a separate contract.
        await selected(2)
        await send(client, '0104', '0000')
        await snapshot(client, lambda s: s.get('love') is False)
        favorite_added = False
        passed('built-in favorites read and ' + ('selection' if version == '2.57' else 'unsupported selection guard'))

        # Notifications from physical controls, with no intervening state query.
        await selected(0)
        await flush(client)
        buttons = Buttons(ROOT, Device(ROOT))
        buttons.gesture('play_pause', 'single')
        await observe(client, lambda t, p: t == 'a202' and p.get('state') == 1, 'physical pause')
        await snapshot(client, lambda s: s['state'] == 1)
        await memory_state(version, 2)
        passed('physical play/pause pushes state to remote')
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            if favorite_added:
                await send(client, '0104', '0000')
            await call(client.set_play_mode, settings['playMode'])
            current = await snapshot(client)
            if current['state'] == 0:
                await call(client.play_pause)
            await snapshot(client, lambda s: s['state'] == 1)
        except Exception as error:
            if not failed:
                raise
            print(f'Cleanup also failed: {error!r}; disposable stack teardown will stop the guest.', flush=True)
    return report


async def main():
    # This script requires access to the fingerprinted local guest and CI media.
    # Stock closes/reopens its listener between clients. Only retry connection
    # refusal here; commands and established-session failures are never replayed.
    deadline = time.monotonic() + 8
    while True:
        try:
            client = Client()
            break
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(.2)
    with client:
        tcp = await exercise(client, 'tcp')
    await asyncio.sleep(1)
    async with WSClient('ws://wsbridge:12103/api/websocket', host_header='127.0.0.1:12103') as client:
        ws = await exercise(client, 'ws')
    assert tcp['checks'] == ws['checks']
    print(json.dumps([tcp, ws], indent=2), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
