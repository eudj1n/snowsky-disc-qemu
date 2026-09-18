"""Persistent foreground session: one socket reader, serialized operations, no replay."""
from collections import deque
from contextlib import contextmanager
from copy import deepcopy
import random
import socket
import threading
import time

from controller.fiio_link import Client, Frames, frame, playback_snapshot
from research.disc_assistant.assistant.device import PlaybackClient, ObservedSocket, device_lock, validate_scan_events
from research.disc_assistant.assistant.playback import merge_snapshot


class LiveSocket(ObservedSocket):
    def sendall(self, data):
        mutation = data[:4] in (b'0100', b'0101', b'0102', b'0201')
        if mutation:
            remaining = self.session.last_write + 2.1 - time.monotonic()
            if remaining > 0 and self.session.closed.wait(remaining):
                raise ConnectionError('session ended before dispatch')
        if self.session.closed.is_set():
            raise ConnectionError('session ended; request was not replayed')
        try:
            if mutation:
                self.session.last_write = time.monotonic()
            return super().sendall(data)
        except OSError:
            self.session.close()
            raise


class LiveClient(Client):
    """Only _receive touches recv; request callers wait on a condition variable."""
    begin_phase = PlaybackClient.begin_phase

    def __init__(self, host, port, timeout):
        raw = socket.create_connection((host, port), timeout)
        raw.settimeout(.25)
        self.timeout = timeout
        self.closed = threading.Event()
        self.condition = threading.Condition()
        self.requests = threading.Lock()
        self.frames = Frames()
        self.events = deque()
        self.waiting = None
        self.reply = None
        self.active = False
        self.mutation_attempted = False
        self.mutation_phase = 'selection'
        self.attempted_phases = set()
        self.last_write = 0
        self.handshake_value = None
        self.state, self.position, self.mode = {}, None, None
        self.playback = 'unknown'
        self.scan_active = False
        self.observed_at = None
        self.zero_progress = False
        self.socket = LiveSocket(raw, self)
        self.reader = threading.Thread(target=self._receive, daemon=True, name='disc-reader')
        self.reader.start()

    def close(self):
        self.closed.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
        with self.condition:
            self.state, self.position, self.playback = {}, None, 'unknown'
            self.condition.notify_all()

    def handshake(self):
        if self.handshake_value is None:
            self.handshake_value = super().handshake()
        return self.handshake_value

    def now_playing(self):
        update = playback_snapshot(self.request('0202'))
        if not update:
            return {}
        # a202 can be a state-only push even while a query is pending. The reader
        # has already reduced it with the latest metadata, including loading/EOF.
        with self.condition:
            return deepcopy(self.state)

    def _update(self, tag, payload):
        self.observed_at = time.time()
        if tag == 'a202':
            update = playback_snapshot(payload)
            if not update:
                return
            old_song = self.state.get('song')
            self.state = merge_snapshot(self.state, update)
            if self.state.get('song') != old_song:
                self.position = None
            if update.get('state') == 2:
                self.playback = 'stopped' if not update.get('song') and self.zero_progress else 'loading'
            elif self.state.get('song') and self.state.get('state') in (0, 1):
                self.playback = 'playing' if self.state['state'] == 0 else 'paused'
            else:
                self.playback = 'unknown'
            self.zero_progress = False
        elif tag == 'a103':
            self.position = int(payload, 16)
            self.zero_progress = self.position == 0
        elif tag == 'a102':
            self.mode = int(payload, 16)
        elif tag == 'a622':
            self.scan_active = True
        elif tag == 'a60a':
            value = int(payload, 16)
            if value == 15:
                self.scan_active = True
            elif value == 5:
                self.scan_active = False

    def _receive(self):
        try:
            while not self.closed.is_set():
                try:
                    data = self.socket.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    break
                for tag, payload in self.frames.feed(data):
                    with self.condition:
                        self._update(tag, payload)
                        if self.waiting == tag and self.reply is None:
                            self.reply = payload
                        elif self.active:
                            if len(self.events) >= 10000:
                                raise ValueError('operation event budget exhausted')
                            self.events.append((tag, payload))
                        self.condition.notify_all()
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            self.close()

    def request(self, tag, payload=b'', *, expected=None):
        expected = expected or 'a' + tag[1:].lower()
        with self.requests:
            with self.condition:
                if self.closed.is_set():
                    raise ConnectionError('device disconnected')
                self.waiting, self.reply = expected, None
                try:
                    self.socket.sendall(frame(tag, payload))
                    deadline = time.monotonic() + self.timeout
                    while self.reply is None and not self.closed.is_set():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            # a202 is also unsolicited and can be silent at final EOF.
                            # Other late replies cannot be safely reused: retire this
                            # connection, then let the owner reconnect for observation.
                            if expected != 'a202':
                                self.close()
                            raise TimeoutError(f'no {expected} reply')
                        self.condition.wait(remaining)
                    if self.closed.is_set():
                        raise ConnectionError('device disconnected during request')
                    return self.reply
                finally:
                    self.waiting, self.reply = None, None

    def begin_operation(self, timeout):
        with self.condition:
            if self.closed.is_set():
                raise ConnectionError('device disconnected before operation')
            self.timeout = timeout
            self.active = True
            self.events.clear()
            # A scan observed while idle must also block later selection/sync.
            if self.scan_active:
                self.events.append(('a60a', b'000F'))
            self.mutation_attempted = False
            self.mutation_phase = 'selection'
            self.attempted_phases = set()

    def end_operation(self):
        with self.condition:
            self.active = False
            self.events.clear()

    def event(self, timeout=None):
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        with self.condition:
            while not self.events and not self.closed.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('no event')
                self.condition.wait(remaining)
            if self.closed.is_set():
                raise ConnectionError('device disconnected')
            return self.events.popleft()

    def take_events(self):
        with self.condition:
            events = list(self.events)
            self.events.clear()
            return events

    def scan_guard(self):
        with self.condition:
            if self.closed.is_set():
                raise ConnectionError('device disconnected')
            validate_scan_events(self.take_events())
            if self.scan_active:
                raise ValueError('observed library scan activity; wait for completion')

    def view(self):
        with self.condition:
            return {'playback': self.playback, 'state': deepcopy(self.state),
                    'position_ms': self.position, 'mode': self.mode,
                    'scan_active': self.scan_active, 'observed_at': self.observed_at}


class DeviceSession:
    """Own a connection until explicit disconnect/exit; commands never wait for recovery."""
    def __init__(self, config, *, client_factory=LiveClient, backoff=.5, health_interval=30):
        self.config, self.client_factory = config, client_factory
        self.backoff, self.health_interval = backoff, health_interval
        self.guard = threading.Condition()
        self.operations = threading.Lock()
        self.shutdown = threading.Event()
        self.enabled = False
        self.client = None
        self.generation = 0
        self.connection = 'disconnected'
        self.last_error = None

    def __enter__(self):
        self.owner = device_lock(self.config.data_dir)
        self.owner.__enter__()
        self.worker = threading.Thread(target=self._run, daemon=True, name='disc-session')
        self.worker.start()
        return self

    def __exit__(self, *args):
        self.shutdown.set()
        self.disconnect()
        self.worker.join(self.config.timeout * 4 + 2)
        self.owner.__exit__(*args)

    def connect(self):
        with self.guard:
            self.enabled = True
            self.guard.notify_all()

    def disconnect(self):
        with self.guard:
            self.enabled = False
            self.generation += 1
            if self.client:
                self.client.close()
            self.client = None
            self.connection = 'disconnected'
            self.guard.notify_all()

    def wait_ready(self, timeout):
        deadline = time.monotonic() + timeout
        with self.guard:
            while self.connection != 'ready' and self.enabled:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.guard.wait(remaining)
            return self.connection == 'ready'

    def status(self):
        with self.guard:
            ready = self.client is not None and not self.client.closed.is_set() and self.connection == 'ready'
            return {'connection': self.connection if ready or self.connection != 'ready' else 'reconnecting',
                    'enabled': self.enabled, 'generation': self.generation, 'last_error': self.last_error,
                    'observation': self.client.view() if ready else {'playback': 'unknown', 'state': {}}}

    @contextmanager
    def operation(self):
        with self.guard:
            requested_generation = self.generation
            if self.connection != 'ready' or self.client is None or self.client.closed.is_set():
                raise ConnectionError('device is not ready; command was not queued or replayed')
        with self.operations:
            with self.guard:
                client = self.client
                if (self.connection != 'ready' or client is None or client.closed.is_set()
                        or requested_generation != self.generation):
                    raise ConnectionError('device is not ready; command was not queued or replayed')
                client.begin_operation(self.config.timeout)
            try:
                yield client
            finally:
                client.end_operation()

    def _run(self):
        delay = self.backoff
        while not self.shutdown.is_set():
            with self.guard:
                while not self.enabled and not self.shutdown.is_set():
                    self.guard.wait(.5)
                if self.shutdown.is_set():
                    return
                generation = self.generation = self.generation + 1
                self.connection = 'connecting' if delay == self.backoff else 'reconnecting'
                self.guard.notify_all()
            client = None
            ready_at = None
            try:
                # Don't swap in a fresh connection while an old operation unwinds.
                with self.operations:
                    client = self.client_factory(self.config.host, self.config.tcp_port, self.config.timeout)
                    with self.guard:
                        if not self.enabled or generation != self.generation:
                            client.close()
                            continue
                        self.client = client
                    if client.handshake() != '0306' or client.settings().get('soc_version') != 257:
                        raise ValueError('persistent session requires reviewed DISC V2.57')
                    client.play_mode()
                    try:
                        client.now_playing()
                    except TimeoutError:
                        pass  # Healthy transport may have no now-playing at final EOF.
                    with self.guard:
                        if not self.enabled or generation != self.generation or client.closed.is_set():
                            continue
                        self.connection, self.last_error = 'ready', None
                        ready_at = time.monotonic()
                        self.guard.notify_all()
                health_at = time.monotonic()
                while not self.shutdown.wait(.1) and not client.closed.is_set():
                    with self.guard:
                        if not self.enabled or generation != self.generation:
                            break
                    if time.monotonic() - health_at >= self.health_interval and self.operations.acquire(False):
                        try:
                            client.timeout = self.config.timeout
                            client.play_mode()
                            health_at = time.monotonic()
                        finally:
                            self.operations.release()
            except (OSError, ValueError, RuntimeError) as exc:
                with self.guard:
                    self.last_error = type(exc).__name__ + ': ' + str(exc)
            finally:
                if client:
                    client.close()
                    client.reader.join(1)
                with self.guard:
                    if generation == self.generation:
                        self.client = None
                        self.connection = 'reconnecting' if self.enabled else 'disconnected'
                    self.guard.notify_all()
            if ready_at is not None and time.monotonic() - ready_at >= 30:
                delay = self.backoff
            with self.guard:
                if self.enabled and not self.shutdown.is_set():
                    self.guard.wait(delay * random.uniform(.8, 1.2))
            delay = min(15, delay * 2)
