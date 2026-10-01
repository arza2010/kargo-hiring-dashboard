"""Postgres (Neon) connection and schema.

Raw SQL, no ORM — kept simple on purpose (CLAUDE.md: "simple enough that I
can explain every file in class"). A single schema is used; tests point
DATABASE_URL at a disposable branch/schema, never the real data.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from app.config import settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candidates (
    id               TEXT PRIMARY KEY,
    source           TEXT NOT NULL,
    file_path        TEXT,
    file_bytes       BYTEA,
    content_type     TEXT NOT NULL DEFAULT 'application/octet-stream',
    content_hash     TEXT UNIQUE NOT NULL,
    original_filename TEXT NOT NULL,
    applied_role     TEXT NOT NULL DEFAULT 'role_unknown',
    name             TEXT,
    email            TEXT,
    phone            TEXT,
    cleaned_text     TEXT,
    parse_status     TEXT NOT NULL,
    parse_notes      TEXT,
    status           TEXT NOT NULL DEFAULT 'new',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
    criteria_json        TEXT NOT NULL,
    pm_score              DOUBLE PRECISION,
    spm_score              DOUBLE PRECISION,
    pm_years_from_cv        DOUBLE PRECISION,
    years_flag                TEXT,
    level_hint                  BOOLEAN NOT NULL DEFAULT FALSE,
    probes_json                    TEXT,
    one_line_rationale                TEXT,
    injection_detected                  BOOLEAN NOT NULL DEFAULT FALSE,
    scored_at                              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefs (
    candidate_id     TEXT PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
    who_text          TEXT,
    why_ranked_json     TEXT,
    gaps_json             TEXT,
    probes_json              TEXT,
    level_note                  TEXT,
    created_at                     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id  TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    decision      TEXT NOT NULL,
    note          TEXT,
    decided_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_id   TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    decision_id    BIGINT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    subject        TEXT NOT NULL,
    body_text      TEXT NOT NULL,
    reviewed       BOOLEAN NOT NULL DEFAULT FALSE,
    warning        TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sends (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    draft_id           BIGINT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    resend_message_id  TEXT,
    to_address         TEXT NOT NULL,
    subject_sent       TEXT NOT NULL,
    sent_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS setup (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    rubric_hash         TEXT,
    confirmed_at        TEXT,
    acknowledge_delay   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS event_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts            TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    candidate_id  TEXT,
    detail_json   TEXT
);
"""


def get_connection(database_url: str | None = None) -> psycopg.Connection:
    url = database_url or settings.database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. This app stores candidate data in Neon "
            "(Postgres) — add your Neon connection string to .env as "
            "DATABASE_URL before starting the app."
        )
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)
    return conn


# Migration for a `candidates` table created before file storage moved from
# local disk into Postgres (bytes-in-DB, needed once the app has no
# persistent disk — e.g. deployed serverless). Safe to run every startup.
_MIGRATE_FILE_STORAGE_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS file_bytes BYTEA;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'application/octet-stream';
ALTER TABLE candidates ALTER COLUMN file_path DROP NOT NULL;
"""


def init_db(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL)
    conn.execute(_MIGRATE_FILE_STORAGE_SQL)
    conn.execute(
        "INSERT INTO setup (id, acknowledge_delay) VALUES (1, TRUE) "
        "ON CONFLICT (id) DO NOTHING"
    )


@contextlib.contextmanager
def connect(database_url: str | None = None) -> Iterator[psycopg.Connection]:
    conn = get_connection(database_url)
    try:
        yield conn
    finally:
        conn.close()
