"""Natural EOF acceptance on disposable media; never inject next/seek/EOF."""
import asyncio
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import time
import wave

from queue_check import connection, http_client
from remote_control import call, snapshot, flush, ROOT, NAMES
from fiio_link import playback_snapshot
from player_memory import PlayerMemory
from scan_cancel_check import scan
from probe_keys import snapshot as memory_snapshot
from track_end_trace import is_start, is_stop, validate

DURATION = 6
FOLDER = 'Natural EOF CI Ё'
SHORT_NAMES = ('End A — й.wav', 'End B — й.flac', 'End C — й.flac')
PLAYLIST = 'Natural EOF CI'


def sources():
    sd = ROOT / 'tmp/sdcard'
    originals = {sd / 'Кириллица Ё й' / name for name in NAMES}
    assert {p for p in sd.rglob('*') if p.is_file()} == originals
    for p in originals:
        assert p.read_bytes() == (Path('/sdcard') / p.relative_to(sd)).read_bytes()


def make_fixture():
    folder = ROOT / 'tmp/sdcard' / FOLDER
    folder.mkdir()
    wav = folder / SHORT_NAMES[0]
    period = b''.join(struct.pack('<hh', v, v) for v in [1024] * 50 + [-1024] * 50)
    with wav.open('xb') as output:
        with wave.open(output, 'wb') as target:
            target.setparams((2, 2, 44100, 0, 'NONE', 'NONE'))
            target.writeframes(period * (44100 * DURATION // 100))
    for name in SHORT_NAMES[1:]:
        subprocess.run(['sox', str(wav), '--add-comment', 'ARTIST=EOF CI',
                        '--add-comment', 'ALBUM=EOF CI', str(folder / name)], check=True)
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}


async def index(client, expected):
    with PlayerMemory(ROOT, '2.57') as memory:
        await scan(client, memory)
    assert (await call(client.tracks))['total'] == expected


async def observe(client, mode, seconds=35):
    started = time.monotonic()
    events = []
    starts = 0
    stopped_at = None
    while True:
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            # Do not accept a terminal event arriving just before the deadline
            # without also observing its complete quiet tail.
            raise TimeoutError(f'EOF observation deadline for mode {mode}: {events}')
        if stopped_at is not None and time.monotonic() - stopped_at >= 2:
            return events  # Observe a quiet tail, not just the first stop delta.
        try:
            tag, payload = await call(client.event, min(.5, remaining))
        except TimeoutError:
            continue
        elapsed = round(time.monotonic() - started, 3)
        if tag == 'a202':
            value = playback_snapshot(payload)
            song = value.get('song', {})
            events.append((elapsed, tag, value.get('state'), song.get('song_name'),
                           song.get('pos_id'), value.get('playing_num')))
            if is_start(events[-1]):
                starts += 1
            if mode in (0, 4) and is_stop(events[-1]):
                stopped_at = time.monotonic()
        elif tag == 'a103':
            events.append((elapsed, tag, int(payload, 16)))
            # Sample continuing playback away from its next EOF boundary. All
            # completed cycles are validated below, including progress restart.
            if mode not in (0, 4) and starts >= (4 if mode == 1 else 3) and int(payload, 16) > 0:
                return events


async def exercise(transport):
    async with connection(transport) as client:
        http = http_client(transport)
        original_mode = (await call(client.settings))['playMode']
        assert await call(client.device_setting, 'gapless') == 0
        assert await call(client.device_setting, 'folder_jump') == 0
        assert http.catalog('custom')['total'] == 0
        http.create_playlist(PLAYLIST)
        catalog = http.catalog()['items']
        for pos, item in enumerate(catalog):
            if item['name'] in SHORT_NAMES:
                http.add_to_playlist(0, [[pos, pos]])
        page = http.catalog('custom/song', src_list_id=0)
        assert page['total'] == 3
        order = [item['name'] for item in page['items']]
        assert set(order) == set(SHORT_NAMES)
        print(f'{transport}: EOF queue order={order}', flush=True)
        for mode, start in ((0, 1), (4, 1), (2, 1), (3, 2), (1, 1)):
            await call(client.set_play_mode, mode)
            assert await call(client.play_mode) == mode
            await asyncio.sleep(2.1)
            await flush(client)
            result = client.play_playlist(0, start, http=http, expected_name=PLAYLIST)
            if asyncio.iscoroutine(result):
                await result
            events = await observe(client, mode)
            print(f'{transport} mode={mode} start={start}: events={events}', flush=True)
            positions = validate(events, mode, start, order, DURATION)
            if mode in (0, 4):
                # A timeout is an observed stock limitation, not a generic
                # stopped-state detector. Independently require terminal events,
                # stopped runtime, intact queue and a responsive settings query.
                try:
                    await call(client.now_playing)
                except TimeoutError:
                    pass
                else:
                    raise AssertionError('expected silent 0202 after natural stop')
                current = None
            else:
                current = await call(client.now_playing)
                assert current['state'] == 0
                assert current['song']['song_name'] == order[positions[-1]]
            assert await call(client.play_mode) == mode
            queue = http.catalog('curlist/song')
            assert queue['total'] == 3
            assert [item['name'] for item in queue['items']] == order
            assert queue['mark'] == positions[-1]
            runtime = memory_snapshot(ROOT, '2.57')
            assert runtime['player_state'] == (3 if mode in (0, 4) else 1)
            print(f'{transport} mode={mode}: PASS positions={positions}, '
                  f'player_state={runtime["player_state"]}, queue mark={queue["mark"]}, '
                  f'0202={"silent" if current is None else "playing"}', flush=True)
            if current is not None:
                await call(client.play_pause)
                await snapshot(client, lambda s: s['state'] == 1)
        await asyncio.sleep(2.1)
        await call(client.play_all, 3, 'CI Album')
        await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
        await call(client.play_pause)
        await snapshot(client, lambda s: s['state'] == 1)
        http.delete_playlist(0)
        assert http.catalog('custom')['total'] == 0
        await call(client.set_play_mode, original_mode)
        assert await call(client.play_mode) == original_mode


async def main():
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('natural EOF acceptance requires disposable V2.57')
    with PlayerMemory(ROOT, '2.57'):
        pass
    sources()
    fixture = make_fixture()
    async with connection('tcp') as client:
        await index(client, 6)
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    for p, digest in fixture.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
        p.unlink()
    (ROOT / 'tmp/sdcard' / FOLDER).rmdir()
    async with connection('tcp') as client:
        await index(client, 3)
    sources()
    print('NATURAL EOF CHECK PASS V2.57 TCP/WS; source bytes and original catalog restored', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
