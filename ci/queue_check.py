"""Current-queue acceptance on disposable generated-media guests, TCP and WS.

--fresh additionally verifies the empty queue before any track has been selected.
Only the explicit raw invalid-index probe bypasses the new client's bounds guard.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import os
import time

from remote_control import Client, WSClient, call, send, snapshot, flush, NAMES
from fiio_http import HTTPClient


@asynccontextmanager
async def connection(transport):
    deadline = time.monotonic() + 8
    while True:
        try:
            if transport == 'tcp':
                client = Client(timeout=2)
            else:
                client = WSClient('ws://wsbridge:12103/api/websocket', timeout=2,
                                  host_header='127.0.0.1:12103')
                await client.__aenter__()
            break
        except (OSError, ConnectionError):
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(.2)
    try:
        assert await call(client.handshake) == '0306'
        yield client
    finally:
        if transport == 'tcp':
            client.close()
        else:
            await client.__aexit__(None, None, None)
    await asyncio.sleep(1)


def http_client(transport):
    return HTTPClient(port=12103) if transport == 'tcp' else HTTPClient(
        'wsbridge', 12103, host_header='127.0.0.1:12103')


async def collect(client, timeout=2):
    deadline = time.monotonic() + timeout
    result = []
    while time.monotonic() < deadline:
        try:
            tag, payload = await call(client.event, deadline - time.monotonic())
        except TimeoutError:
            break
        result.append((tag, payload.decode()))
    return result


async def rejected(client, index):
    try:
        await call(client.play_queue_index, index)
    except ValueError:
        return
    raise AssertionError(f'Client did not reject queue position {index}')


async def empty_queue(transport):
    async with connection(transport) as client:
        http = http_client(transport)
        assert http.catalog('curlist/song') == {'total': 0, 'items': [], 'mark': -1}
        assert await call(client.library, 'queue') == {'total': 0, 'items': []}
        await rejected(client, 0)
        await flush(client)
        await send(client, '0100', '00000000')
        replies = await collect(client)
        assert not any(t in ('a202', 'a103') for t, _ in replies), replies
        assert http.catalog('curlist/song')['total'] == 0
        assert (await call(client.settings))['soc_version'] == int(os.environ['FW_VERSION'].replace('.', ''))
        print(f'{transport}: fresh empty queue, guarded rejection and silent raw selector', flush=True)


async def exercise(transport):
    async with connection(transport) as client:
        assert {x['title'] for x in (await call(client.tracks))['items']} == set(NAMES)
        http = http_client(transport)
        original_mode = (await call(client.settings))['playMode']
        await call(client.set_play_mode, 0)

        async def start(list_type=3, name='CI Album'):
            await asyncio.sleep(2.1)
            await call(client.play_all, list_type, name)
            current = await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == list_type)
            queue = http.catalog('curlist/song')
            assert queue['total'] == (2 if list_type == 3 else 3), queue
            assert current['song']['song_name'] == queue['items'][0]['name']
            return queue

        async def check_selected(index, queue):
            current = await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 0
                                     and s['song']['song_name'] == queue['items'][index]['name'])
            assert current['song']['pos_id'] == index + 1
            assert current['playing_num'] == f"{index + 1}/{queue['total']}"
            refreshed = http.catalog('curlist/song')
            assert refreshed['items'] == queue['items']
            assert refreshed['mark'] == index, refreshed
            return current

        try:
            # Reset to the first album track before every variant, so a stale
            # snapshot of the target cannot satisfy the next selection check.
            for label in ('Список воспроизведения', '', 'Queue test'):
                queue = await start()
                await asyncio.sleep(2.1)
                await send(client, '0100', '00010000' + label)
                await check_selected(1, queue)
            print(f'{transport}: Russian, absent and arbitrary queue labels select the same position', flush=True)

            old_queue = await start(1, None)
            await asyncio.sleep(2.1)
            await call(client.play_queue_index, 2)
            await check_selected(2, old_queue)
            queue = await start()
            # Index 2 belonged to the old three-song queue; it is now invalid.
            await rejected(client, 2)
            current = await snapshot(client, lambda s: s['state'] == 0 and s['playerflag'] == 3)
            assert current['song']['song_name'] == queue['items'][0]['name']
            # Index 1 is still valid, but now denotes the second ALBUM track.
            assert old_queue['items'][1]['name'] != queue['items'][1]['name']
            await asyncio.sleep(2.1)
            await call(client.play_queue_index, 1)
            await check_selected(1, queue)
            print(f'{transport}: helper uses current queue, rejects stale bounds, updates mark/source/position', flush=True)

            queue = await start()
            await asyncio.sleep(2.1)
            await flush(client)
            await send(client, '0100', '00020000')  # Exactly one past this queue.
            replies = await collect(client)
            assert http.catalog('curlist/song')['items'] == queue['items']
            try:
                raw_result = await call(client.now_playing)
            except TimeoutError:
                raw_result = 'timeout'
            print(f'{transport}: raw out-of-range result {raw_result!r}; events {replies!r}', flush=True)
            assert raw_result == 'timeout', raw_result
            # Rebuild a valid selection; timeout did not kill the Link server.
            queue = await start()
            await asyncio.sleep(2.1)
            await call(client.play_queue_index, 1)
            await check_selected(1, queue)
            print(f'{transport}: valid album selection recovers after raw invalid queue index', flush=True)
        finally:
            await call(client.set_play_mode, original_mode)
            current = await snapshot(client)
            if current['state'] == 0:
                # Selection and pause share the stock navigation rate gate.
                await asyncio.sleep(2.1)
                await call(client.play_pause)
            await snapshot(client, lambda s: s['state'] == 1)


async def main(fresh):
    if fresh:
        for transport in ('tcp', 'ws'):
            await empty_queue(transport)
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    print(f'QUEUE ACCEPTANCE PASSED V{os.environ["FW_VERSION"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh', action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args.fresh))
