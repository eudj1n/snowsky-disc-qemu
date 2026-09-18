"""Bounded sequential device operations shared by selection and controls."""
from contextlib import contextmanager
import os
import time

from controller.fiio_link import Client, frame
from research.disc_assistant.assistant.session import check_events


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


def validate_scan_events(events):
    pending = iter(events)
    class Pending:
        def event(self, timeout):
            try:
                return next(pending)
            except StopIteration as exc:
                raise TimeoutError from exc
    check_events(Pending(), during_read=True)


class ObservedSocket:
    def __init__(self, socket, session):
        self.socket, self.session = socket, session

    def __getattr__(self, name):
        return getattr(self.socket, name)

    def sendall(self, data):
        if data[:4] in (b'0100', b'0101', b'0102', b'0201'):
            kind = 'mode' if data[:4] == b'0102' else 'selection'
            if self.session.mutation_phase != kind:
                raise RuntimeError('unexpected mutation in the current phase')
            if self.session.mutation_phase in self.session.attempted_phases:
                raise RuntimeError('playback mutation replay refused')
            self.session.attempted_phases.add(self.session.mutation_phase)
            self.session.mutation_attempted = True
        return self.socket.sendall(data)


class PlaybackClient(Client):
    """One synchronous reader; retain unrelated events across Controller queries."""
    def __init__(self, host='127.0.0.1', port=12100, timeout=8):
        # Stock temporarily closes its listener after a client disconnects.
        # Wait only for an INITIAL connection, before handshake or any mutation.
        # Established sessions are never reconnected/replayed.
        deadline = time.monotonic() + timeout
        while True:
            try:
                super().__init__(host, port, max(.01, deadline - time.monotonic()))
                break
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        self.timeout = timeout
        self.observed = []
        self.mutation_attempted = False
        self.mutation_phase = 'selection'
        self.attempted_phases = set()
        self.socket = ObservedSocket(self.socket, self)

    def begin_phase(self, name):
        if (name not in ('mode', 'selection') or name in self.attempted_phases
                or (name == 'mode' and self.attempted_phases)):
            raise RuntimeError('mutation phase cannot be replayed')
        self.mutation_phase = name

    def retain(self, event):
        if len(self.observed) >= 10000:
            raise ValueError('device event budget exhausted')
        self.observed.append(event)

    def collect(self):
        for _ in range(10000):
            try:
                self.retain(super().event(timeout=.01))
            except TimeoutError:
                return
        raise ValueError('device event budget exhausted')

    def request(self, tag, payload=b'', *, expected=None):
        self.collect()
        self.socket.sendall(frame(tag, payload))
        expected = expected or 'a' + tag[1:].lower()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            event = super().event(timeout=max(.001, deadline - time.monotonic()))
            if event[0] == expected:
                return event[1]
            self.retain(event)
        raise TimeoutError(f'no {expected} reply')

    def scan_guard(self):
        self.collect()
        events, self.observed = self.observed, []
        validate_scan_events(events)
