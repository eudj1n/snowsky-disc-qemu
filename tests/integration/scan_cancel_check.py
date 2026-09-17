"""V2.57 scan cancellation on disposable generated media, never user libraries."""
from tests.integration.profile import (version as firmware_version, require_acceptance, diagnostic)
import asyncio
import hashlib
import io
import os
from pathlib import Path
import time
import wave

from tests.integration.queue_check import connection, http_client, collect
from tests.integration.remote_control import call, flush, ROOT, NAMES
from tests.integration.http_check import db_rows
from research.diagnostics.player_memory import PlayerMemory

COUNT = 1024
FOLDER = 'Cancel scan CI Ё'


def sample():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 8000, 0, 'NONE', 'NONE'))
        audio.writeframes(b'\0\0' * 8000)
    return output.getvalue()


def paths():
    return {p for p, in db_rows('SELECT PATH FROM SONG')}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def scan(client, memory, *, cancel=False):
    assert memory.word(diagnostic('network.scan_running')) == 0
    await flush(client)
    await call(client.scan_library)
    deadline = time.monotonic() + 60
    events = []
    requested = None
    while time.monotonic() < deadline:
        try:
            tag, data = await call(client.event, .5)
        except TimeoutError:
            continue
        if tag not in ('a60a', 'a622'):
            continue
        value = int(data, 16)
        events.append((tag, value))
        if cancel and requested is None and tag == 'a622' and value >= 1:
            assert ('a60a', 15) in events, events
            assert memory.word(diagnostic('network.scan_running')) == 1, 'scan finished before cancellation'
            await call(client.cancel_library_scan)
            requested = value
        if tag == 'a60a' and value == 5:
            break
    else:
        raise AssertionError(f'Scan did not finish: {events}')
    assert ('a60a', 15) in events, events
    if cancel:
        assert requested is not None, 'did not cancel an active scan'
    deadline = time.monotonic() + 5
    while memory.word(diagnostic('network.scan_running')) and time.monotonic() < deadline:
        await asyncio.sleep(.05)
    assert memory.word(diagnostic('network.scan_running')) == 0
    assert memory.word(diagnostic('network.scan_stop')) == 0, 'finished scan must clear stop flag'
    print(f'Scan cancel={cancel}, request at count={requested}; events={events}', flush=True)
    return events


async def catalog(client, http):
    expected_paths = paths()
    names = {Path(p).name for p in expected_paths}
    for read in (lambda offset: client.tracks(offset),
                 lambda offset: http.catalog(offset=offset, limit=100)):
        items = []
        while True:
            page = await call(read, len(items))
            assert page['total'] == len(expected_paths), page
            items.extend(page['items'])
            if len(items) >= page['total']:
                break
            assert page['items'], page
        assert len(items) == len(names)
        assert {item.get('title', item.get('name')) for item in items} == names
    return expected_paths


async def exercise(transport):
    async with connection(transport) as client:
        http = http_client(transport)
        with PlayerMemory(ROOT, firmware_version()) as memory:
            before = await catalog(client, http)
            await flush(client)
            await call(client.cancel_library_scan)  # Idle cancellation: no library reset.
            idle = await collect(client, .3)
            assert not [e for e in idle if e[0] in ('a60a', 'a622')], idle
            assert memory.word(diagnostic('network.scan_stop')) == 1
            assert memory.word(diagnostic('network.scan_running')) == 0
            assert await catalog(client, http) == before

            events = await scan(client, memory, cancel=True)
            partial = await catalog(client, http)
            assert 0 < len(partial) < COUNT + len(NAMES), len(partial)
            assert [n for tag, n in events if tag == 'a622'][-1] == len(partial)
            assert len(partial) < len(before), 'cancelled rescan must not restore old full index'
            print(f'{transport}: partial index {len(partial)}/{len(before)}; '
                  'TCP/HTTP/SQLite agree; finish is still a60a/0005', flush=True)
            await scan(client, memory)
            assert await catalog(client, http) == before, 'fresh scan must rebuild complete index'


async def run():
    require_acceptance('scan-cancel')
    # Resolve and fingerprint the running guest before making the fixture.
    with PlayerMemory(ROOT, firmware_version()) as memory:
        assert memory.word(diagnostic('network.scan_running')) == 0
    sd = ROOT / 'tmp/sdcard'
    originals = {sd / 'Кириллица Ё й' / name for name in NAMES}
    assert {p for p in sd.rglob('*') if p.is_file()} == originals
    baseline = {p: digest(p) for p in originals}
    for path in originals:
        assert digest(path) == digest(Path('/sdcard') / path.relative_to(sd))
    folder = sd / FOLDER
    folder.mkdir()  # No exist_ok: never reuse or delete an unknown directory.
    audio = sample()
    generated = [folder / f'Track {i:04d} — й.wav' for i in range(COUNT)]
    for path in generated:
        with path.open('xb') as target:
            target.write(audio)
    # Establish a complete baseline first; cancellation must be tested as rescan,
    # not just an empty first scan. No direct database or memory writes.
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, firmware_version()) as memory:
            await scan(client, memory)
        assert len(await catalog(client, http_client('tcp'))) == COUNT + len(NAMES)
    for transport in ('tcp', 'ws'):
        await exercise(transport)
    assert all(digest(p) == value for p, value in baseline.items())
    assert all(p.read_bytes() == audio for p in generated)
    for path in generated:
        path.unlink()
    folder.rmdir()
    async with connection('tcp') as client:
        with PlayerMemory(ROOT, firmware_version()) as memory:
            await scan(client, memory)
        expected = {'/' + str(p.relative_to(ROOT)) for p in originals}
        assert await catalog(client, http_client('tcp')) == expected
    print(f'SCAN CANCELLATION PASSED V{firmware_version()}: idle, partial rescan, recovery, source preservation', flush=True)


if __name__ == '__main__':
    asyncio.run(run())
