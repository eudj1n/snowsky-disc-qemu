"""Assistant process ownership; transport behavior belongs to Controller."""
from contextlib import contextmanager
import os

from controller.device import PlaybackClient, ObservedSocket
from controller.events import validate_scan_events


@contextmanager
def device_lock(directory):
    # Local CLI invocations in this data directory share one device session.
    # Other controllers/data directories cannot participate in this local lock.
    import fcntl
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory / 'device.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another assistant device operation is active') from exc
        yield
    finally:
        os.close(descriptor)
