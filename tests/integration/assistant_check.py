"""Opt-in full Assistant scenarios against an isolated stock guest; never a LAN player."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

from tests.fixtures.assistant_fixture import MANIFEST


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def load_suite():
    import re
    suite = json.loads(MANIFEST.read_text())
    tracks = {t['key']: t for t in suite['tracks']}
    if len(tracks) != len(suite['tracks']):
        raise ValueError('Duplicate fixture keys')
    ids = set()
    for case in suite['cases']:
        if not re.fullmatch(r'[a-z][a-z0-9-]+', case['id']) or case['id'] in ids:
            raise ValueError('Unsafe or duplicate case ID')
        ids.add(case['id'])
        setup, expected = case['setup'], case['expected']
        if (case['locale'] not in ('ru', 'en') or not case['command'].strip()
                or setup['track'] not in tracks or setup['state'] not in ('playing', 'paused')
                or type(setup['progress_seconds']) is not int or not 1 <= setup['progress_seconds'] <= 15
                or expected['effect'] not in ('track', 'artist', 'paused', 'playing', 'next', 'previous', 'unchanged')
                or expected['mutation'] not in ('required', 'none') or not expected['status']):
            raise ValueError('Invalid scenario: ' + case['id'])
        if expected['effect'] in ('track', 'artist'):
            if any(k not in tracks for k in expected.get('accepted_targets', [expected.get('target')])):
                raise ValueError('Unknown expected recording')
    return suite


def identity(state):
    song = state.get('song', {})
    return tuple(song.get(k) for k in ('song_file_path', 'song_name', 'song_artist_name', 'pos_id'))


def recording(state, track):
    song = state.get('song', {})
    return (song.get('song_name') == track['title'] and song.get('song_artist_name') == track['artist']
            and song.get('song_file_path', '').endswith('/' + track['key'] + '.flac'))


def judge(case, tracks, before, result, after, writes):
    """Gold comes from fixtures/pre-state, never the Assistant's selected candidate."""
    expected = case['expected']
    b, a = before['state'], after['state']
    effect = expected['effect']
    checks = {'response_status': result.get('status') in expected['status'],
              'response_locale': result.get('response', {}).get('language') == expected.get('response_locale', case['locale']),
              'same_connection': before['generation'] == after['generation'],
              'sequential_mode': before['queue']['mode'] == after['queue']['mode'] == 0}
    if 'response_codes' in expected:
        checks['response_code'] = result.get('response', {}).get('code') in expected['response_codes']
    checks['mutation_contract'] = bool(writes) if expected['mutation'] == 'required' else not writes
    if expected['mutation'] == 'none' and result.get('mutation_attempted') is True:
        checks['mutation_contract'] = False
    if effect in ('track', 'artist'):
        accepted = [tracks[k] for k in expected.get('accepted_targets', [expected['target']])]
        checks['target'] = any(recording(a, t) for t in accepted)
        checks['playing'] = a.get('state') == 0
        # Fixture membership, not the returned selection, determines valid queues.
        valid = []
        for target in accepted:
            valid.append(Counter((t['title'], t['artist']) for t in tracks.values()
                                 if t['artist'] == target['artist'] and
                                 (effect == 'artist' or t['album'] == target['album'])))
        checks['queue_membership'] = Counter((r['name'], r['author']) for r in after['queue']['items']) in valid
    elif effect in ('next', 'previous'):
        step = 1 if effect == 'next' else -1
        index = before['queue']['mark'] + step
        row = before['queue']['items'][index]
        song = a.get('song', {})
        checks['expected_neighbor'] = (song.get('song_name'), song.get('song_artist_name'), song.get('pos_id')) == (row['name'], row['author'], index + 1)
        checks['playing'] = a.get('state') == 0
    else:
        checks['same_recording'] = identity(b) == identity(a)
        checks['playback_state'] = a.get('state') == (b.get('state') if effect == 'unchanged' else 1 if effect == 'paused' else 0)
        bp, ap = before['position_ms'], after['position_ms']
        elapsed = (after['monotonic'] - before['monotonic']) * 1000
        checks['position_retained'] = (bp is not None and ap is not None and
                                      0 <= ap - bp <= elapsed + 2000)
        if b.get('state') == a.get('state') == 0:
            checks['playback_progress'] = bp is not None and ap is not None and ap > bp
    if effect not in ('track', 'artist'):
        checks['queue_preserved'] = before['queue']['items'] == after['queue']['items']
    checks['queue_state_agrees'] = after['queue']['mark'] + 1 == a.get('song', {}).get('pos_id')
    return checks


def screenshot(root, output):
    """Read only the last-flushed sub-buffer; this is evidence, not a visual assertion."""
    from emulator.runtime.framebuffer import Framebuffer, BUF, to_rgb, png
    from emulator.runtime.keys import Device
    framebuffer = Framebuffer(root)
    if framebuffer.active_buffer() is None:
        raise RuntimeError('No reviewed active framebuffer marker')
    sample = framebuffer.read()
    if sample is None or sample[1] is None or len(sample[0]) != BUF * 2:
        raise RuntimeError('Framebuffer changed or is incomplete')
    raw, active = sample
    with output.open('xb') as stream:
        stream.write(png(to_rgb(raw[active * BUF:(active + 1) * BUF])))
    return {'file': output.name, 'buffer': active, 'visually_reviewed': False,
            'screen_on': Device(root).screen_on(), 'consistency': 'stable_marker_not_atomic'}


def observed_session(config):
    from controller.session import LiveClient
    from research.disc_assistant.assistant.live import DeviceSession

    class SocketLog:
        def __init__(self, socket, owner):
            self.socket, self.owner = socket, owner

        def __getattr__(self, key):
            return getattr(self.socket, key)

        def sendall(self, data):
            entry = {'tag': data[:4].decode('ascii'), 'monotonic': time.monotonic(), 'sent': False}
            self.owner.sends.append(entry)
            self.socket.sendall(data)
            entry['sent'] = True

    class EvidenceClient(LiveClient):
        def __init__(self, *args):
            self.sends = []
            self.progress_seq = 0
            self.progress_at = None
            super().__init__(*args)
            self.socket = SocketLog(self.socket, self)

        def _update(self, tag, payload):
            super()._update(tag, payload)
            if tag == 'a103':
                self.progress_seq += 1
                self.progress_at = time.monotonic()

    return DeviceSession(config, client_factory=EvidenceClient)


def observe(app):
    from controller.fiio_http import HTTPClient
    from controller.queue import snapshot
    started = time.monotonic()
    with app.session.operation() as client:
        state = client.now_playing()
        with client.condition:
            seq = client.progress_seq
        # Require new progress while playing. Paused firmware may stop a103;
        # retain its last position explicitly, backed by fresh paused state reads
        # and the separate write log, rather than claiming a fresh position query.
        deadline = time.monotonic() + 5
        with client.condition:
            while state.get('state') == 0 and client.progress_seq <= seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('No fresh progress event')
                client.condition.wait(remaining)
        queue = snapshot(app.config, client, HTTPClient(app.config.host, app.config.http_port, 5))
        view = client.view()
        if queue['state'] != view['state']:
            raise RuntimeError('State changed during readback')
        return {'state': queue['state'], 'position_ms': view['position_ms'], 'queue': queue,
                'monotonic': time.monotonic(), 'read_started': started,
                'position_source': 'fresh_event' if client.progress_seq > seq else 'retained_event_while_paused',
                'position_event_at': client.progress_at, 'position_event_sequence': client.progress_seq,
                'generation': app.session.status()['generation']}


def request(app, text):
    try:
        return app.request(text)
    except Exception as exc:
        if hasattr(exc, 'assistant_result'):
            return exc.assistant_result
        raise


def prepare(app, case, tracks):
    from controller.fiio_http import HTTPClient
    track = tracks[case['setup']['track']]
    app.request('/language ' + case['locale'], source='startup')
    http = HTTPClient(app.config.host, app.config.http_port, 5)
    rows = http.catalog('artist/album/song', artist=track['artist'], album=track['album'])['items']
    index = next(r['pos'] for r in rows if r['name'] == track['title'])
    result = app.session.play_artist(track['artist'], album=track['album'], index=index).to_dict()
    # Check the actual effect even when the setup response could not confirm it.
    evidence = observe(app)
    if not recording(evidence['state'], track) or evidence['state'].get('state') != 0:
        raise RuntimeError('Setup did not select the declared fixture')
    deadline = time.monotonic() + 20
    while (evidence['position_ms'] or 0) < case['setup']['progress_seconds'] * 1000:
        if time.monotonic() >= deadline:
            raise TimeoutError('Setup progress did not advance')
        evidence = observe(app)
    paused = None
    if case['setup']['state'] == 'paused':
        paused = app.session.pause().to_dict()
    evidence = observe(app)
    if evidence['state'].get('state') != (1 if case['setup']['state'] == 'paused' else 0):
        raise RuntimeError('Setup playback state not established')
    if evidence['queue']['mode'] != 0 or not recording(evidence['state'], track):
        raise RuntimeError('Setup queue changed')
    if evidence['position_ms'] is None or evidence['position_ms'] > 30000:
        raise RuntimeError('Setup must be early in the recording')
    return {'selection': result, 'pause': paused}, evidence


def run(args):
    from research.disc_assistant.assistant.config import Config
    from research.disc_assistant.assistant.console import Application
    if os.environ.get('CI_DISPOSABLE') != '1' or os.environ.get('FW_VERSION') != '2.57':
        raise RuntimeError('Run only through ci/assistant.sh on disposable V2.57')
    suite = load_suite()
    ids = {c['id'] for c in suite['cases']}
    if set(args.case) - ids:
        raise ValueError('Unknown case IDs: ' + ', '.join(sorted(set(args.case) - ids)))
    output = Path('/reports/results')
    output.mkdir(mode=0o700)
    tracks = {t['key']: t for t in suite['tracks']}
    selected = [c for c in suite['cases'] if not args.case or c['id'] in args.case]
    write_json(output / 'manifest.json', suite)
    sources = {}
    for folder in ('controller', 'research/disc_assistant', 'tests/integration', 'tests/fixtures', 'firmware/profiles', 'ci'):
        for directory, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for name in files:
                f = Path(directory) / name
                if not name.startswith('.') and f.suffix in ('.py', '.toml', '.json', '.sh', '.yml', '.yaml', '.Dockerfile'):
                    sources[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    from importlib.metadata import version
    write_json(output / 'provenance.json', {'revision': os.environ.get('ASSISTANT_SOURCE_REVISION'),
               'dependencies': {name: version(name) for name in ('typesense', 'aiohttp', 'prompt_toolkit')},
               'files': sources, 'firmware': '2.57', 'selected_cases': [c['id'] for c in selected],
               'cohort': 'emulator-regression', 'manifest_sha256': hashlib.sha256(MANIFEST.read_bytes()).hexdigest()})
    config = Config('disposable-assistant', 'emu', 12100, 12103, Path('/reports/runtime'),
                    'typesense', 8108, 'http', 'ASSISTANT_TEST_KEY', {}, timeout=8)
    deadline = time.monotonic() + 60
    while True:
        try:
            with urllib.request.urlopen('http://typesense:8108/health', timeout=2) as reply:
                if json.load(reply).get('ok'):
                    break
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError('Typesense unavailable')
        time.sleep(.5)
    records = []
    with Application(config, session_factory=observed_session, source='emulator-acceptance') as app:
        if not app.session.wait_ready(30):
            raise RuntimeError('Guest connection unavailable')
        imported = app.request('/sync', source='startup')
        if imported.get('track_count') != len(tracks):
            raise RuntimeError(f'Unexpected fixture catalog: {imported}')
        indexed = app.request('/index', source='startup')
        write_json(output / 'bootstrap.json', {'sync': imported, 'index': indexed})
        for case in selected:
            record = {'id': case['id'], 'command': case['command'], 'expected': case['expected'], 'outcome': 'blocked'}
            try:
                record['setup'], record['before'] = prepare(app, case, tracks)
                client = app.session.client
                start = len(client.sends)
                record['submitted'] = True
                try:
                    record['result'] = request(app, case['command'])
                finally:
                    # Record only the measured command's sends, never setup/readback.
                    record['sends'] = list(client.sends[start:])
                    record['writes'] = [w for w in record['sends'] if w['tag'] not in ('0599', '0501', '0105', '0202')]
                record['after'] = observe(app)
                record['checks'] = judge(case, tracks, record['before'], record['result'], record['after'], record['writes'])
                record['outcome'] = 'passed' if all(record['checks'].values()) else 'failed'
            except Exception as exc:
                record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
                if record.get('submitted'):
                    record['outcome'] = 'verification_error'
            if args.screenshots == 'all' or record['outcome'] != 'passed':
                try:
                    record['screen'] = screenshot(Path('/guest/rootfs'), output / (case['id'] + '.png'))
                except Exception as exc:
                    record['screen_error'] = str(exc)
            write_json(output / (case['id'] + '.json'), record)
            records.append(record)
            print(case['id'], record['outcome'], record.get('checks', record.get('error')), flush=True)
    counts = dict(Counter(r['outcome'] for r in records))
    write_json(output / 'report.json', {'cohort': 'emulator-regression', 'counts': counts, 'cases': records})
    with (output / 'report.md').open('x') as report:
        report.write('# Assistant emulator results\n\nNo physical audio or visual acceptance is claimed.\n\n')
        report.write('| Case | Outcome | Command latency (ms) | Failed checks / error |\n| --- | --- | --- | --- |\n')
        for r in records:
            report.write(f"| {r['id']} | {r['outcome']} | {r.get('result', {}).get('timing', {}).get('total_ms', '')} | " +
                         (', '.join(k for k,v in r.get('checks', {}).items() if not v) or
                          r.get('error', {}).get('type', '')) + ' |\n')
    return 0 if counts.get('passed') == len(selected) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--screenshots', choices=('failures', 'all'), default='failures')
    parser.add_argument('--list', action='store_true', help='list case IDs without starting services')
    args = parser.parse_args()
    if args.list:
        for case in load_suite()['cases']:
            print(case['id'], case['command'])
    else:
        raise SystemExit(run(args))
