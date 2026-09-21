"""Fresh current-track information, favorites and absolute/relative volume."""
from __future__ import annotations

import time
from uuid import uuid4
from controller.compatibility import Capability, require_client
from controller.controls import observe, identity, UnknownPlayback
from typing import Any
from controller.contracts import ControlClient, CurrentAction


def current(client: ControlClient, action: CurrentAction, *,
            value: int | None = None, delta: int | None = None, timeout: float = 8) -> dict[str, Any]:
    """One serialized operation. Stock has no atomic track-identity setter."""
    if action not in ('now_playing', 'like', 'dislike', 'volume'):
        raise ValueError('unsupported current-state action')
    if action == 'volume' and not (
            (type(value) is int and 0 <= value <= 120 and delta is None) or
            (value is None and type(delta) is int and -120 <= delta <= 120 and delta != 0)):
        raise ValueError('volume needs one absolute value or nonzero delta')
    result: dict[str, Any] = dict(operation_id=uuid4().hex, action=action, status='not_sent', mutation_attempted=False)
    try:
        capability = {'now_playing': Capability.CURRENT_TRACK, 'like': Capability.CURRENT_FAVORITE,
                      'dislike': Capability.CURRENT_FAVORITE, 'volume': Capability.VOLUME}[action]
        require_client(client, capability)
        if action == 'now_playing':
            try:
                state, _ = observe(client)
            except (UnknownPlayback, TimeoutError):
                return dict(result, status='unavailable')
            return dict(result, status='observed', state=state)
        client.begin_phase('volume' if action == 'volume' else 'favorite')
        client.wait_for_mutation()
        if action == 'volume':
            previous = client.settings().get('currentVolume')
            if type(previous) is not int or not 0 <= previous <= 120:
                raise ValueError('current volume unavailable')
            requested = value if value is not None else max(0, min(120, previous + (delta if delta is not None else 0)))
            result.update(previous_volume=previous, volume=requested)
            if previous == requested:
                return dict(result, status='already_satisfied')
            client.scan_guard()
            client.set_volume(requested)
        else:
            before, _ = observe(client)
            wanted_favorite = action == 'like'
            if type(before.get('love')) is not bool:
                raise ValueError('current favorite state unavailable')
            result['state'] = before
            if before['love'] == wanted_favorite:
                return dict(result, status='already_satisfied')
            client.scan_guard()
            fresh, _ = observe(client)
            if identity(fresh) != identity(before) or fresh.get('love') != before['love']:
                raise ValueError('current track or favorite changed before dispatch')
            client.set_favorite(wanted_favorite)
        result.update(status='uncertain', mutation_attempted=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            client.timeout = max(.05, min(2, deadline - time.monotonic()))
            if action == 'volume':
                if client.settings().get('currentVolume') == requested:
                    client.scan_guard()
                    return dict(result, status='confirmed')
            else:
                state, _ = observe(client)
                result['state'] = state
                if identity(state) != identity(before):
                    raise ValueError('current track changed during favorite confirmation')
                if type(state.get('love')) is bool and state['love'] == wanted_favorite:
                    return dict(result, status='confirmed')
            time.sleep(.1)
        result['reason'] = 'current-state change not confirmed; no replay'
    except (OSError, ValueError, RuntimeError) as exc:
        attempted = bool(client.mutation_attempted)
        result.update(status='uncertain' if attempted else 'not_sent', mutation_attempted=attempted,
                      reason=str(exc), error_type=type(exc).__name__)
    return result
