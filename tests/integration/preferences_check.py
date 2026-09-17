"""V2.57 preference reads and rejected local-only writes; disposable guests only.

No firmware patches, DB writes or guest-memory writes. The rejected commands
are individually identified stock UI settings, never a sweep of unknown tags.
"""
import asyncio
from pathlib import Path

from tests.integration.settings_check import call, db
from controller.fiio_link import Client, frame
from controller.fiio_ws import WSClient
from controller.fiio_settings import SETTING_FIELDS
from research.diagnostics.inspect_link_commands import commands
from research.diagnostics.player_memory import PlayerMemory


# name: (local-only tag, SQLite column, config byte, runtime word or None,
#        callback slot, callback). All addresses are V2.57-only.
FIELDS = {
    'gapless': ('0647', 'PLAY_GAP', 0x83a796, 0x898a60, 0x83a684, 0x4f1e2c),
    'folder_jump': ('0687', 'FOLDER_JUMP', 0x83a795, 0x898a04, 0x83a62c, 0x4f1c58),
    'replay_gain': ('0718', 'SYS_REPLAY_GAIN', 0x83a79a, 0x898a6c, 0x83a690, 0x4f1f74),
    'artist_class_type': ('0648', 'ARTIST_CLASS_TYPE', 0x83a798, 0x898d30, 0x83a688, 0x4f1ed0),
    'track_display': ('064d', 'TRACK_DISPLAY', 0x83a79d, 0x898a78, 0x83a634, 0x4f1cf8),
    'list_oper_mode': ('064e', 'LIST_OPER_MODE', 0x83a7a4, None, 0x83a638, 0x4f1d98),
}


def saved():
    return {name: db(f'SELECT {field[1]} FROM SYSCONFIG')[0][0]
            for name, field in FIELDS.items()}


async def verify(client, expected):
    assert saved() == expected
    with PlayerMemory(version='2.57') as player:
        for name, value in expected.items():
            _, _, config, runtime, slot, callback = FIELDS[name]
            assert player.word(hex(slot)) == callback, name
            assert player.word(hex(config), 1) == value, name
            if runtime is not None:
                assert player.word(hex(runtime)) == value, name
    for name in SETTING_FIELDS:
        assert await call(client.device_setting, name) == expected[name], name
    # This is a fixed capability advertisement, NOT artist_class_type readback.
    assert (await call(client.settings))['artist_sub_album'] == 1


async def exercise(client, label):
    assert await call(client.handshake) == '0306'
    original = saved()
    before_volume = (await call(client.settings))['currentVolume']
    await verify(client, original)
    for name, (tag, *_) in FIELDS.items():
        # Always request a DIFFERENT valid value: matching a default proves nothing.
        assert original[name] in ((0, 1, 2) if name == 'replay_gain' else (0, 1))
        value = (original[name] + 1) % (3 if name == 'replay_gain' else 2)
        if isinstance(client, Client):
            client.socket.sendall(frame(tag, f'{value:04X}'))
        else:
            await client.send(tag, f'{value:04X}')
        # The parser drops invalid input (including any coalesced later frames).
        # Give it time to consume this deliberate negative probe before a read.
        await asyncio.sleep(.3)
        await verify(client, original)
        print(f'{label}: local-only {tag} ({name}) rejected; SQLite/config/runtime unchanged; '
              'fresh a501 reads still work', flush=True)
    assert (await call(client.settings))['currentVolume'] == before_volume


async def main():
    admitted = commands(Path('/work/rootfs/usr/bin/mq_player').read_bytes(), '2.57')['admitted']
    assert '0501' in admitted
    assert all(field[0] not in admitted for field in FIELDS.values())
    with Client(timeout=5) as client:
        await exercise(client, 'TCP')
    await asyncio.sleep(2)
    async with WSClient('ws://wsbridge:12103/api/websocket', timeout=5,
                        host_header='127.0.0.1:12103') as client:
        await exercise(client, 'WS')
    print('Preferences: three read-only helpers; six local-only setters rejected by stock TCP', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
