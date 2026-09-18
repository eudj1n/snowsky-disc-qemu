"""Assistant control intent adapter; Stop is an explicit pause policy."""
from contextlib import nullcontext
import time
from uuid import uuid4
from controller.controls import control, observe, verify, UnknownPlayback
from research.disc_assistant.assistant.device import PlaybackClient, device_lock


def execute(config, intent, *, shared=None):
    action = intent.action
    if action not in ('pause', 'resume', 'stop', 'next', 'previous'):
        raise ValueError('unsupported control action')
    client = None
    result = {'operation_id': uuid4().hex, 'status': 'not_sent', 'mutation_attempted': False}
    try:
        with (device_lock(config.data_dir) if shared is None else nullcontext()):
            with (PlaybackClient(config.host, config.tcp_port, config.timeout) if shared is None
                  else nullcontext(shared)) as client:
                result = control(client, 'pause' if action == 'stop' else action, config.timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        attempted = bool(client and client.mutation_attempted)
        result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted,
                      reason=str(exc), error_type=type(exc).__name__)
    result['action'] = action
    if action == 'stop':
        result.update(assistant_continuation='inactive', device_stop_semantics='pause_preserving_position_and_queue')
    return result
