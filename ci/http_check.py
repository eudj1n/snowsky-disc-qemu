"""Stock HTTP acceptance, ONLY for ci/integration.sh's disposable scanned SD."""
import asyncio
import inspect
import os
from pathlib import Path
import sqlite3
import struct
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from fiio_http import HTTPClient
from fiio_link import Client
from fiio_ws import WSClient
from fixture import NAMES

ROOT = Path('/work/rootfs')


def png():
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\0' + b'\xff\0\0' * 2 + b'\0' + b'\0\xff\0' * 2)) +
            chunk(b'IEND', b''))


def db_rows(sql):
    with sqlite3.connect(f'file:{ROOT}/usr/data/fiio/db/song.db?mode=ro', uri=True) as db:
        return db.execute(sql).fetchall()


async def scan_events(client, total):
    async def call(fn, *args):
        value = fn(*args)
        return await value if inspect.isawaitable(value) else value
    await call(client.handshake)
    await call(client.scan_library)
    deadline = time.monotonic() + 45
    events = []
    while time.monotonic() < deadline:
        try:
            tag, data = await call(client.event, 1)
        except TimeoutError:
            continue
        if tag in ('a60a', 'a622'):
            events.append((tag, int(data, 16)))
        if tag == 'a60a' and int(data, 16) == 5:
            break
    assert ('a60a', 15) in events and ('a60a', 5) in events, events
    assert ('a622', total) in events, events


def scan(total, websocket=False):
    if websocket:
        async def run():
            async with WSClient('ws://wsbridge:12103/api/websocket', timeout=5,
                                host_header='127.0.0.1:12103') as client:
                await scan_events(client, total)
        asyncio.run(run())
        assert HTTPClient(port=12103).catalog()['total'] == total
        return
    deadline = time.monotonic() + 8
    while True:
        try:
            client = Client(timeout=3)
            break
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.2)
    with client:
        asyncio.run(scan_events(client, total))
    assert HTTPClient(port=12103).catalog()['total'] == total


def exercise(host, label):
    client = HTTPClient(host, 12103, host_header='127.0.0.1:12103')
    assert client.catalog('custom')['total'] == 0, 'requires disposable empty custom playlists'
    songs = client.catalog()['items']
    assert {x['name'] for x in songs} == set(NAMES), songs
    folder = f'/tmp/sdcard/HTTP CI + Ё {label}'
    target = folder + '/Upload — й.flac'
    image = folder + '/Image + Ё.png'
    source = Path('/sdcard/Кириллица Ё й') / NAMES[1]
    assert not Path(str(ROOT) + folder).exists()
    client.mkdir(folder)
    assert Path(str(ROOT) + folder).is_dir()
    assert client.mkdir(folder).headers['is-exist'] == '1'
    client.upload(source, target)
    assert Path(str(ROOT) + target).read_bytes() == source.read_bytes()
    progress = client.progress(target)
    assert progress['now_size'] == source.stat().st_size and progress['percentage'] == 1.0
    try:
        client.upload(source, target)
    except FileExistsError:
        pass
    else:
        raise AssertionError('upload must reject an observed existing destination')
    assert client.directory(folder)['items'][0]['name'] == 'Upload — й.flac'
    assert client.directory(folder, local=True)['total'] == 1
    # Upload completes without indexing. A later scanner operation must be explicit.
    assert client.catalog()['total'] == len(NAMES)
    scan(len(NAMES) + 1, websocket=label == 'proxy')
    assert any(x['name'] == 'Upload — й.flac' for x in client.catalog()['items'])
    client.delete_file(target)
    assert not Path(str(ROOT) + target).exists()
    scan(len(NAMES), websocket=label == 'proxy')
    first = client.catalog(offset=0, limit=1)
    rest = client.catalog(offset=1, limit=2)
    assert first['items'] + rest['items'] == songs
    assert client.catalog('album/song', album='CI Album')['total'] == 2
    if os.environ.get('FW_VERSION', '2.57') == '2.57':
        image_source = Path('/work/http-fixture.png')
        image_source.write_bytes(png())
        client.upload(image_source, image, image=True)
        assert Path(str(ROOT) + image).read_bytes() == png()
        assert client.progress(image)['now_size'] == len(png())
        client.delete_file(image)
        assert not Path(str(ROOT) + image).exists()

    # Force internal LIST_ID != list position, then operate by wire positions.
    client.create_playlist('HTTP First')
    client.create_playlist('HTTP Second')
    assert client.catalog('custom')['total'] == 2
    client.delete_playlist(0)
    assert client.catalog('custom')['items'][0]['name'] == 'HTTP Second'
    rows = db_rows('SELECT LIST_ID FROM CUSTOM_PLAYLIST_INDEX ORDER BY LIST_ID')
    assert len(rows) == 1 and rows[0][0] != 0, rows
    name = 'HTTP Список + Ё'
    client.rename_playlist(0, name)
    assert client.catalog('custom')['items'][0]['name'] == name
    client.add_to_playlist(0, [[1, 2]])
    expected = [x['name'] for x in songs[1:]]
    assert [x['name'] for x in client.catalog('custom/song', src_list_id=0)['items']] == expected
    assert client.catalog('custom')['items'][0]['count'] == 2
    assert len(db_rows('SELECT * FROM CUSTOM_PLAYLIST')) == 2
    client.remove_from_playlist(0, [[0, 0]])
    assert client.catalog('custom/song', src_list_id=0)['items'][0]['name'] == expected[1]
    assert len(db_rows('SELECT * FROM CUSTOM_PLAYLIST')) == 1
    client.delete_playlist(0)
    assert client.catalog('custom')['total'] == 0
    assert not db_rows('SELECT * FROM CUSTOM_PLAYLIST')
    assert client.catalog()['items'] == songs
    for filename in NAMES:
        relative = Path('Кириллица Ё й') / filename
        assert (ROOT / 'tmp/sdcard' / relative).read_bytes() == (Path('/sdcard') / relative).read_bytes()
    client.delete_file(folder)
    assert not Path(str(ROOT) + folder).exists()
    # Transfer cache survives deletion; progress is not a file-existence oracle.
    assert client.progress(target)['now_size'] == source.stat().st_size
    print(f'{label}: directory, binary upload/progress, pagination, playlist lifecycle and source preservation passed', flush=True)


if __name__ == '__main__':
    exercise('127.0.0.1', 'direct')
    exercise('wsbridge', 'proxy')
