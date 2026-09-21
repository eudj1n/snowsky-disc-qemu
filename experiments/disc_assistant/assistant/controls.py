"""Assistant control intent adapter; Stop is an explicit pause policy."""
from contextlib import nullcontext
import time
from uuid import uuid4
from controller.controls import control, observe, verify, UnknownPlayback
from controller.queue import previous_in_queue
from controller.operations import current_track, playback_control
from experiments.disc_assistant.assistant.controller_results import serialize
from controller.fiio_http import HTTPClient
from experiments.disc_assistant.assistant.device import PlaybackClient, device_lock


def execute(config, intent, *, shared=None):
    action = intent.action
    if action not in ('pause', 'resume', 'stop', 'next', 'previous', 'now_playing', 'like', 'dislike', 'volume'):
        raise ValueError('unsupported control action')
    client = None
    result = {'operation_id': uuid4().hex, 'status': 'not_sent', 'mutation_attempted': False}
    try:
        with (device_lock(config.data_dir) if shared is None else nullcontext()):
            with (PlaybackClient(config.host, config.tcp_port, config.timeout) if shared is None
                  else nullcontext(shared)) as client:
                if action in ('now_playing', 'like', 'dislike', 'volume'):
                    delta = None
                    if action == 'volume' and intent.direction is not None:
                        delta = config.volume_up_step if intent.direction == 'up' else -config.volume_down_step
                    result = serialize(current_track(client, action, value=intent.value if action == 'volume' else None,
                                     delta=delta, timeout=config.timeout))
                elif action == 'previous':
                    result = previous_in_queue(config, client,
                        HTTPClient(config.host, config.http_port, config.timeout))
                else:
                    result = serialize(playback_control(client, 'pause' if action == 'stop' else action, timeout=config.timeout))
    except (OSError, ValueError, RuntimeError) as exc:
        attempted = bool(client and client.mutation_attempted)
        result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted,
                      reason=str(exc), error_type=type(exc).__name__)
    result['action'] = action
    if action == 'stop':
        result.update(assistant_continuation='inactive', device_stop_semantics='pause_preserving_position_and_queue')
    return result
