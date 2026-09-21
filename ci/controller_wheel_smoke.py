"""Executed only by controller_wheel.py inside its empty installed environment."""
import importlib.util
from importlib.resources import files
from pathlib import Path
import sys
from unittest.mock import patch

from controller import DeviceConfig, DiscSession, OperationStatus, __version__
import controller
from controller.device import MutationPacer


def main():
    assert __version__ == '0.1.0'
    assert Path(sys.prefix) in Path(controller.__file__).parents
    assert importlib.util.find_spec('aiohttp') is None
    assert files('controller').joinpath('py.typed').is_file()
    assert '<html' in files('controller.bridge').joinpath('ws_console.html').read_text().lower()
    spec = importlib.util.spec_from_file_location('synthetic_peer', sys.argv[1])
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    server = fixture.Server()
    server.state['song']['song_file_path'] = '/synthetic.flac'
    try:
        with patch.object(MutationPacer, 'interval', 0), DiscSession(
                DeviceConfig('127.0.0.1', tcp_port=server.server_address[1], timeout=.5)) as player:
            player.connect()
            assert player.wait_ready(2)
            observed = player.current_track().playback.track
            assert observed.title == 'Track' and observed.path == '/synthetic.flac'
            assert player.pause().status is OperationStatus.CONFIRMED
            assert player.pause().status is OperationStatus.ALREADY_SATISFIED
            favorite = player.set_favorite(True)
            assert favorite.playback.favorite is True
            volume = player.set_volume(42)
            assert volume.status is OperationStatus.CONFIRMED
            assert volume.volume == 42 and volume.previous_volume is not None
            assert player.adjust_volume(120).volume == 120
            assert player.adjust_volume(1).status is OperationStatus.ALREADY_SATISFIED
            assert server.accepts == 1
    finally:
        server.close()


if __name__ == '__main__':
    main()
