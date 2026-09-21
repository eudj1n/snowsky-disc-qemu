"""Typed guarded operations on an exclusively owned or borrowed client.

DiscSession handles ownership for normal callers. Adapters with an existing
operation can use these functions without opening another connection.
"""
from controller.contracts import ControlAction, ControlClient, CurrentAction
from controller.models import CommandResult


def current_track(client: ControlClient, action: CurrentAction = 'now_playing', *,
                  value: int | None = None, delta: int | None = None,
                  timeout: float = 8) -> CommandResult:
    from controller.current import current
    return CommandResult.from_result(current(client, action, value=value, delta=delta,
                                             timeout=timeout), action)


def playback_control(client: ControlClient, action: ControlAction, *,
                     timeout: float = 8) -> CommandResult:
    from controller.controls import control
    return CommandResult.from_result(control(client, action, timeout), action)
