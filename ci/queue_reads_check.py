"""DISC 0105/0426 acceptance; disposable generated-media guest only."""
import asyncio
import argparse
import os
from pathlib import Path
import time

from queue_check import connection, http_client
from remote_control import call, snapshot, flush, NAMES


async def prepare():
    # The focused protocol scenario indexes through stock Link. Full integration
    # continues to test the UI scanner in guest_check.py.
    for name in NAMES:
        relative = Path('Кириллица Ё й') / name
        assert (Path('/work/rootfs/tmp/sdcard') / relative).read_bytes() == (
            Path('/sdcard') / relative).read_bytes()
    async with connection('tcp') as client:
        assert (await call(client.tracks))['total'] == 0
        await call(client.scan_library)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            tracks = await call(client.tracks)
            if tracks['total'] == len(NAMES):
                assert {item['title'] for item in tracks['items']} == set(NAMES)
                print('Stock network scan indexed all three generated tracks', flush=True)
                return
            await asyncio.sleep(.5)
        raise AssertionError(f'Stock network scan did not finish: {tracks}')


async def check_reads(client, http, label):
    before = http.catalog('curlist/song')
    mode = (await call(client.settings))['playMode']
    for _ in range(2):
        assert await call(client.play_mode) == mode
    # Test both the M21 empty request and DISC parser's four-digit argument.
    for payload in ('', '0000'):
        await flush(client)
        try:
            reply = await call(client.request, '0426', payload)
        except TimeoutError:
            pass
        else:
            raise AssertionError(f'Unexpected a426: {reply!r}')
        assert (await call(client.settings))['playMode'] == mode
        assert http.catalog('curlist/song') == before
    print(f'{label}: 0105 reads {mode}; both 0426 forms time out; queue and connection intact', flush=True)


async def exercise(transport):
    async with connection(transport) as client:
        http = http_client(transport)
        original_mode = (await call(client.settings))['playMode']
        try:
            await asyncio.sleep(2.1)
            await call(client.play_all, 3, 'CI Album')
            await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
            await check_reads(client, http, f'{transport}/playing')
            await call(client.play_pause)
            paused = await snapshot(client, lambda s: s['state'] == 1)
            for mode in range(5):
                await call(client.set_play_mode, mode)
                # Drain the setter's asynchronous a102 before testing the reader.
                assert (await call(client.settings))['playMode'] == mode
                await flush(client)
                for _ in range(2):
                    assert await call(client.play_mode) == mode
                current = await snapshot(client, lambda s: s['state'] == 1)
                assert current['song'] == paused['song']
                assert (await call(client.settings))['playMode'] == mode
            await check_reads(client, http, f'{transport}/paused')
            await call(client.set_play_mode, 0)
            await asyncio.sleep(2.1)
            await call(client.play_all, 1, None)
            await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 1)
            assert http.catalog('curlist/song')['total'] == 3
            # Stock track selection has a two-second guard, as in queue_check.
            await asyncio.sleep(2.1)
            await call(client.play_queue_index, 2)
            await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 0
                           and s['song']['pos_id'] == 3)
            await asyncio.sleep(2.1)
            await call(client.play_pause)
            await snapshot(client, lambda s: s['state'] == 1)
            await check_reads(client, http, f'{transport}/replaced-selected')
            print(f'{transport}: all five modes read twice without changing pause/track', flush=True)
        finally:
            await call(client.set_play_mode, original_mode)
            current = await snapshot(client)
            if current['state'] == 0:
                await asyncio.sleep(2.1)
                await call(client.play_pause)
            await snapshot(client, lambda s: s['state'] == 1)


async def main(fresh):
    if fresh:
        for transport in ('tcp', 'ws'):
            async with connection(transport) as client:
                http = http_client(transport)
                assert http.catalog('curlist/song')['total'] == 0
                await check_reads(client, http, f'{transport}/empty')
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    print(f'QUEUE READS PASSED V{os.environ["FW_VERSION"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    asyncio.run(prepare() if args.prepare else main(args.fresh))
