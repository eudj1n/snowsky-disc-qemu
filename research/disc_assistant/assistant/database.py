"""Versioned private Assistant storage; catalog storage has an independent schema."""
import os
from pathlib import Path
import sqlite3


def connect(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / 'assistant.sqlite3'
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(descriptor)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        # Read the schema version under the migration lock, including concurrent startup.
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, 2):
            raise ValueError(f'unsupported assistant database version {version}')
        if version == 0:
            db.execute('''CREATE TABLE settings (
                key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))''')
        if version < 2:
            db.execute('''CREATE TABLE requests (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, source TEXT NOT NULL,
                device TEXT NOT NULL, command TEXT NOT NULL, input TEXT NOT NULL,
                normalized_input TEXT NOT NULL, input_truncated INTEGER NOT NULL,
                context_json TEXT NOT NULL, started_at TEXT NOT NULL,
                completed_at TEXT, status TEXT NOT NULL DEFAULT 'pending', outcome_json TEXT)''')
            db.execute('''CREATE TABLE request_events (
                id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
                phase TEXT NOT NULL, observed_at TEXT NOT NULL, elapsed_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL)''')
            db.execute('CREATE INDEX request_events_request ON request_events(request_id,id)')
            db.execute('CREATE INDEX requests_started ON requests(started_at)')
            db.execute('PRAGMA user_version=2')
        db.commit()
    except BaseException:
        db.close()
        raise
    return db
