"""Assistant queue adapter and explicit continuous-context policy."""
from contextlib import nullcontext
from controller.fiio_http import HTTPClient
from controller.controls import set_mode
from controller.models import PlayMode
from controller.queue import MODES, read_queue, continuation, snapshot
from research.disc_assistant.assistant.device import PlaybackClient, device_lock


def observe(config, *, shared=None):
    with (device_lock(config.data_dir) if shared is None else nullcontext()), \
            (PlaybackClient(config.host, config.tcp_port, config.timeout) if shared is None else nullcontext(shared)) as client:
        if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
            raise ValueError('queue observation requires reviewed DISC V2.57')
        result = snapshot(config, client, HTTPClient(config.host, config.http_port, config.timeout))
    return {'status': 'observed', 'queue': result}


def ensure_continuous(client):
    """Assistant opt-in policy; Controller owns enum encoding and verification."""
    return set_mode(client, PlayMode.REPEAT_LIST)
