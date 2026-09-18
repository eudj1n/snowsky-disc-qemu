"""Assistant controls, native type-7 queue and natural EOF on disposable V2.57."""
import argparse
import asyncio
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import tempfile
import time

from controller.fiio_link import Client as BaseClient
from controller.fiio_http import HTTPClient
from research.disc_assistant.assistant.config import Config
from research.disc_assistant.assistant.controls import execute as control
from research.disc_assistant.assistant.intents import ControlIntent
from research.disc_assistant.assistant.playback import execute
from research.disc_assistant.assistant.queue import observe as queue_observe
from research.disc_assistant.assistant.session import sync
from research.disc_assistant.library.store import Store
from tests.fixtures.fixture import generate, NAMES
from tests.integration.scan_cancel_check import scan
from tests.integration.track_end_check import observe
from tests.integration.track_end_trace import validate
from tests.integration.remote_control import flush
from research.diagnostics.player_memory import PlayerMemory


class Client(BaseClient):
    """Test-only initial connection readiness; never retry an established session."""
    def __init__(self, *args, **kwargs):
        deadline = time.monotonic() + 10
        while True:
            try:
                super().__init__(*args, **kwargs)
                return
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.2)


def fixtures(directory):
    wav = generate(directory)
    for name in ('A', 'B', 'C'):
        subprocess.run(['sox', str(wav), '--add-comment', 'ARTIST=Assistant CI',
                        '--add-comment', 'ALBUM=Assistant EOF',
                        str(Path(directory) / (name + '.flac')), 'trim', '0', '6'], check=True)


async def eof():
    with Client(timeout=2) as client:
        assert client.handshake() == '0306'
        assert client.device_setting('gapless') == 0
        assert client.device_setting('folder_jump') == 0
        http = HTTPClient(port=12103)
        rows = http.catalog('artist/album/song', artist='Assistant CI', album='Assistant EOF')['items']
        order = [r['name'] for r in rows]
        assert len(order) == 3
        for mode in range(5):
            client.set_play_mode(mode)
            assert client.play_mode() == mode
            await asyncio.sleep(2.1)
            await flush(client)
            start = 2 if mode == 3 else 1
            client.play_artist('Assistant CI', start, album='Assistant EOF', http=http)
            events = await observe(client, mode)
            positions = validate(events, mode, start, order)
            print(f'PASS: type-7 native EOF mode={mode}, positions={positions}', flush=True)


def exercise():
    assert os.environ.get('CI_DISPOSABLE') == '1'
    assert os.environ.get('FW_VERSION') == '2.57'
    with Client() as client, PlayerMemory(Path('/work/rootfs'), '2.57') as memory:
        assert client.handshake() == '0306'
        asyncio.run(scan(client, memory))
    time.sleep(1)  # Stock listener reopens asynchronously after disconnect.
    with tempfile.TemporaryDirectory(prefix='assistant-check-') as tmp, Store(tmp) as store:
        config = Config('generated', '127.0.0.1', 12100, 12103, Path(tmp), 'localhost', 8108, 'http', 'UNUSED', {}, page_size=1)
        from unittest.mock import patch
        # Only test orchestration waits for the stock listener's readiness.
        with patch('research.disc_assistant.assistant.session.Client', Client):
            head = sync(config, store)
        time.sleep(1)
        documents = store.documents(head['generation'])
        assert len(documents) == 6
        target = next(d for d in documents if d['title'] == NAMES[2])
        ranking = {'generation': head['generation'], 'candidates': [dict(target, track_id=target['id'], kind='track')]}
        started = execute(replace(config, continuous_context=True), store, ranking)
        assert started['status'] == 'playing', started
        assert started['queue']['mode'] == 3 and started['queue']['total'] == 2, started
        time.sleep(1)
        for action, status in [('pause', 'confirmed'), ('pause', 'already_satisfied'),
                               ('resume', 'confirmed'), ('resume', 'already_satisfied'),
                               ('stop', 'confirmed'), ('stop', 'already_satisfied'),
                               ('resume', 'confirmed'), ('next', 'confirmed')]:
            time.sleep(1)
            result = control(config, ControlIntent(action))
            assert result['status'] == status, result
        print('PASS: Assistant selection/queue, pause/resume/stop and next on stock firmware', flush=True)
        # Exercise previous both below and above the stock ten-second threshold.
        time.sleep(1)
        started = execute(config, store, ranking)
        assert started['status'] == 'playing', started
        time.sleep(1)
        previous = control(config, ControlIntent('previous'))
        assert previous['status'] == 'confirmed' and previous['outcome'] == 'track_changed', previous
        time.sleep(1)
        with Client() as client:
            assert client.handshake() == '0306'
            client.seek(12000)
            time.sleep(1.2)
        time.sleep(1)
        previous = control(config, ControlIntent('previous'))
        assert previous['status'] == 'confirmed' and previous['outcome'] == 'restarted', previous
        print('PASS: previous changes track before ten seconds and confirms restart from progress afterward', flush=True)
        time.sleep(1)
        observed = queue_observe(config)
        assert observed['queue']['total'] == 2
        # Native playback continues after the Assistant's short-lived connection closes.
        short = next(d for d in documents if d['artist'] == 'Assistant CI')
        short_ranking = {'generation': head['generation'], 'candidates': [dict(short, track_id=short['id'], kind='track')]}
        time.sleep(1)
        initial = execute(replace(config, continuous_context=True), store, short_ranking)
        assert initial['status'] == 'playing', initial
        time.sleep(7)
        after = queue_observe(config)
        assert after['queue']['mode'] == 3
        assert after['queue']['state']['song']['song_name'] != initial['queue']['state']['song']['song_name'], after
        print('PASS: native queue advances while Assistant is disconnected', flush=True)
    time.sleep(1)
    asyncio.run(eof())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures')
    args = parser.parse_args()
    fixtures(args.fixtures) if args.fixtures else exercise()
