"""Versioned public Controller API; importing it requires only the standard library."""
from controller.models import (
    CommandResult, ConnectionState, DeviceConfig, DeviceSnapshot, OperationStatus,
    PlaybackSnapshot, PlaybackSource, PlaybackState, PlayMode, QueueItem, QueueSnapshot, Track,
)
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from controller.session import DiscSession as DiscSession


def __getattr__(name: str) -> Any:
    # Keep `python -m controller.fiio_link` independent of facade imports.
    if name == 'DiscSession':
        from controller.session import DiscSession
        return DiscSession
    raise AttributeError(name)

__version__ = '0.1.0'
__all__ = [
    'CommandResult', 'ConnectionState', 'DeviceConfig', 'DeviceSnapshot',
    'DiscSession', 'OperationStatus', 'PlaybackSnapshot', 'PlaybackSource', 'PlaybackState',
    'PlayMode', 'QueueItem', 'QueueSnapshot', 'Track', '__version__',
]
