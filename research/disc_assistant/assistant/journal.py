"""Bounded request/decision journal. Evidence collection, never a replay queue."""
from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from research.disc_assistant.assistant.database import connect
from research.disc_assistant.assistant.languages import load_languages, normalized
from research.disc_assistant.library.store import StaleSnapshot
from research.disc_assistant.assistant.responses import Responses


class JournalWriteError(RuntimeError):
    pass


@contextmanager
def durable_write(db):
    try:
        with db:
            yield
    except sqlite3.Error as exc:
        raise JournalWriteError('journal write failed; an operation may already have completed; do not replay it') from exc


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def bounded(value, depth=0):
    """Bound trusted structured evidence; never pass raw SDK/HTTP error bodies here."""
    if depth > 8:
        return {'truncated': True}
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, dict):
        return {str(k)[:100]: bounded(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return [bounded(v, depth + 1) for v in value[:10]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return type(value).__name__


def candidate(row):
    return bounded({k: row[k] for k in ('kind', 'id', 'track_id', 'artist', 'album', 'title',
                                      'score', 'evidence', 'match', 'text_match', 'source') if k in row})


def search_evidence(result):
    rows = result.get('candidates', [])
    evidence = {k: result[k] for k in ('query', 'generation', 'device', 'observed_at',
                'intent', 'ranking_policy', 'retrieval', 'found', 'selection', 'identity', 'candidate_count') if k in result}
    evidence.update(candidates=[candidate(row) for row in rows[:10]],
                    returned_count=len(rows), retained_count=min(10, len(rows)),
                    truncated=(len(rows) > 10 or result.get('found', 0) > len(rows)
                               or result.get('candidates_truncated', False)
                               or result.get('retrieval', {}).get('truncated', False)))
    return evidence


def outcome(result):
    # Do not persist arbitrary exception reasons, server bodies, headers or full queues.
    result = result or {}
    safe = {k: result[k] for k in ('status', 'operation_id', 'mutation_attempted', 'action',
            'outcome', 'state', 'fresh_position', 'metadata_equivalent_rows', 'assistant_continuation',
            'device_stop_semantics', 'enabled', 'source', 'reused', 'generation', 'index_generation',
            'track_count', 'error_type', 'requested', 'previous', 'confirmation', 'response') if k in result}
    if result.get('status') in ('not_sent', 'uncertain'):
        safe['failure_category'] = result['status']
    if 'mode_change' in result:
        safe['mode_change'] = outcome(result['mode_change'])
    if 'queue' in result:
        safe['queue'] = {k: result['queue'][k] for k in ('total', 'mode', 'source', 'continuation')
                         if k in result['queue']}
    return bounded(safe)


class Journal:
    def __init__(self, config):
        self.config = config
        self.db = connect(config.data_dir)
        self.db.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def prune(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.config.journal_retention_days)).isoformat(timespec='milliseconds')
        with durable_write(self.db):
            before = self.db.execute('SELECT count(*) FROM requests').fetchone()[0]
            self.db.execute('DELETE FROM requests WHERE started_at < ?', (cutoff,))
            # Recent in-flight requests are never removed by the count limit.
            self.db.execute('''DELETE FROM requests WHERE id IN (
                SELECT id FROM requests WHERE completed_at IS NOT NULL
                ORDER BY started_at DESC,rowid DESC LIMIT -1 OFFSET ?)''', (self.config.journal_max_requests,))
            return before - self.db.execute('SELECT count(*) FROM requests').fetchone()[0]

    def detail(self, request_id):
        row = self.db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
        if row is None:
            raise ValueError('request not found (it may have expired)')
        result = dict(row)
        result['context'] = json.loads(result.pop('context_json'))
        result['outcome'] = json.loads(result.pop('outcome_json') or 'null')
        result['events'] = [dict(id=r['id'], phase=r['phase'], observed_at=r['observed_at'],
                                 elapsed_ms=r['elapsed_ms'], payload=json.loads(r['payload_json']))
                            for r in self.db.execute('SELECT * FROM request_events WHERE request_id=? ORDER BY id', (request_id,))]
        return result


def recallable(text):
    """Recall submitted single-line commands, excluding history maintenance/UI."""
    return (bool(text.strip()) and len(text) <= 4000
            and not any(ord(c) < 32 or ord(c) == 127 for c in text)
            and text.strip().split(maxsplit=1)[0] not in ('/history', '/clear', '/exit'))


def console_history(config):
    """Oldest first, device-scoped interactive input; persistence stays in Trace."""
    if not config.journal_enabled:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.journal_retention_days)).isoformat(timespec='milliseconds')
    with Journal(config) as journal:
        rows = journal.db.execute('''SELECT input FROM requests
            WHERE device=? AND source='interactive' AND input_truncated=0 AND started_at>=?
              AND command NOT IN ('history','clear','exit')
            ORDER BY started_at DESC,rowid DESC LIMIT ?''',
            (config.device_key, cutoff, min(1000, config.journal_max_requests))).fetchall()
    return [row['input'] for row in reversed(rows) if recallable(row['input'])]


class Trace:
    def __init__(self, config, command, text, *, source='cli', session_id=None):
        self.config, self.command, self.text = config, command, text
        self.source, self.session_id = source, session_id or uuid4().hex
        self.id, self.stage = uuid4().hex, 'input'
        self.journal = None
        self.started = time.monotonic()
        self.responses = Responses(config.response_language, config.response_mode)

    def __enter__(self):
        if not self.config.journal_enabled:
            return self
        self.journal = Journal(self.config)
        try:
            self.journal.prune()
            rules = asdict(load_languages(self.config.languages))
            context = {'languages': list(self.config.languages), 'parser_version': 'literal-v1',
                       'language_rules_sha256': hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest(),
                       'selection_policy': 'automatic-best-match', 'continuous_context': self.config.continuous_context,
                       'response': self.responses.context()}
            with durable_write(self.journal.db):
                self.journal.db.execute('''INSERT INTO requests
                    (id,session_id,source,device,command,input,normalized_input,input_truncated,context_json,started_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''', (self.id, self.session_id, self.source, self.config.device_key,
                    self.command, self.text[:4000], normalized(self.text[:4000]), len(self.text) > 4000,
                    json.dumps(context), utcnow()))
        except BaseException:
            self.journal.__exit__()
            raise
        return self

    def event(self, phase, payload):
        self.stage = phase
        if self.journal is not None:
            with durable_write(self.journal.db):
                self.journal.db.execute('''INSERT INTO request_events(request_id,phase,observed_at,elapsed_ms,payload_json)
                    VALUES(?,?,?,?,?)''', (self.id, phase, utcnow(), round((time.monotonic() - self.started) * 1000),
                    json.dumps(bounded(payload), ensure_ascii=False)))

    def intent(self, intent):
        self.event('parsed', asdict(intent))

    def catalog(self, store):
        head = store.head(self.config.device_key)
        self.event('catalog', {k: head.get(k) for k in ('generation', 'index_generation', 'collection', 'index_signature')})

    def search(self, result, *, phase='ranking'):
        self.event(phase, search_evidence(result))

    def select(self, result):
        self.event('selection', {'method': 'automatic_best_match', 'rank': 1,
                                 'generation': result['generation'], 'candidate': candidate(result['candidates'][0])})

    def finish(self, result, *, failure=None):
        self.responses.attach(result, command=self.command, source=self.source, failure=failure)
        safe = outcome(result)
        status = result.get('status', 'completed') if result else 'completed'
        self.event('result', safe)
        if self.journal is not None:
            with durable_write(self.journal.db):
                self.journal.db.execute('UPDATE requests SET completed_at=?,status=?,outcome_json=? WHERE id=?',
                                       (utcnow(), status, json.dumps(safe, ensure_ascii=False), self.id))
            self.journal.prune()
            if result is not None:
                result['request_id'] = self.id
        return result

    def __exit__(self, kind=None, exc=None, tb=None):
        try:
            if exc is not None and self.journal is not None:
                exc.request_id = self.id
            if exc is not None and not isinstance(exc, JournalWriteError):
                if isinstance(exc, StaleSnapshot):
                    category = 'stale_index_or_catalog'
                elif isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    category = 'interrupted'
                elif self.stage in ('input', 'parse'):
                    category = 'unrecognized_or_invalid_command'
                elif self.stage == 'preference':
                    category = 'invalid_preference'
                elif self.stage in ('search', 'retrieval', 'catalog', 'ranking', 'search_query', 'intent_resolved'):
                    category = 'search_unavailable_or_invalid'
                else:
                    category = 'execution_error'
                # Class/category only: exception text may contain credentials or server bodies.
                self.event('error', {'stage': self.stage, 'category': category, 'type': type(exc).__name__})
                exc.assistant_result = self.finish(
                    {'status': 'interrupted' if category == 'interrupted' else 'error'}, failure=category)
        finally:
            if self.journal is not None:
                self.journal.__exit__()


def history_command(config, arguments=()):
    args = list(arguments)
    with Journal(config) as journal:
        if not args or (len(args) == 1 and args[0].isdigit()):
            limit = int(args[0]) if args else 20
            if not 1 <= limit <= 100:
                raise ValueError('history limit must be in 1..100')
            return {'requests': [dict(r) for r in journal.db.execute('''SELECT id,started_at,source,device,command,
                input,status FROM requests ORDER BY started_at DESC,rowid DESC LIMIT ?''', (limit,))]}
        if len(args) == 2 and args[0] == 'show':
            return journal.detail(args[1])
        if args == ['prune']:
            return {'removed': journal.prune()}
        if args == ['clear', '--yes']:
            with journal.db:
                count = journal.db.execute('SELECT count(*) FROM requests').fetchone()[0]
                journal.db.execute('DELETE FROM requests')
            return {'removed': count}
        if len(args) == 2 and args[0] == 'export':
            path = Path(args[1]).expanduser().resolve()
            repo = Path(__file__).resolve().parents[3]
            if path == repo or repo in path.parents:
                raise ValueError('export personal history outside the repository')
            # One consistent read transaction; exclusive/private output, never overwrite.
            journal.db.execute('BEGIN')
            try:
                with open(path, 'x', encoding='utf-8', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
                    count = 0
                    for row in journal.db.execute('SELECT id FROM requests ORDER BY started_at,rowid'):
                        output.write(json.dumps(journal.detail(row['id']), ensure_ascii=False) + '\n')
                        count += 1
            finally:
                journal.db.rollback()
            return {'exported': count, 'path': str(path)}
    raise ValueError('history: [1..100], show ID, export PATH, prune, or clear --yes')
