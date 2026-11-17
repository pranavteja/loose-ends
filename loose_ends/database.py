"""SQLite setup and connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS captures (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    input_type TEXT NOT NULL CHECK (input_type IN ('text', 'audio')),
    original_text TEXT,
    transcript TEXT,
    audio_path TEXT,
    captured_at TEXT NOT NULL,
    timezone TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL,
    attempt_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clarifications (
    id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    skipped INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('task', 'idea')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    source_excerpt TEXT NOT NULL,
    timing_phrase TEXT,
    due_date TEXT,
    work_start_at TEXT,
    timezone TEXT NOT NULL,
    needs_clarification INTEGER NOT NULL DEFAULT 0,
    missing_detail TEXT,
    proposed_steps_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('draft', 'approved', 'dismissed', 'superseded')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS proposals_active_idx ON proposals(capture_id, revision, state);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    proposal_id TEXT UNIQUE,
    source_capture_id TEXT,
    source_excerpt TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('task', 'idea')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    due_date TEXT,
    work_start_at TEXT,
    timezone TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'completed', 'cancelled')),
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(task_id, position)
);

CREATE TABLE IF NOT EXISTS request_receipts (
    owner_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, operation, request_key)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "UPDATE captures SET state = 'failed', error_message = 'Processing was interrupted; retry this capture.' "
                "WHERE state = 'processing'"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
