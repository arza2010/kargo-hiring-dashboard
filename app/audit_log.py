"""Rule 8: log everything — decisions, drafts, edits, sends, PII blocks,
injection flags, each with a timestamp."""
from __future__ import annotations

import datetime as dt
import json

import psycopg


def log_event(conn: psycopg.Connection, event_type: str, candidate_id: str | None, detail: dict) -> None:
    conn.execute(
        "INSERT INTO event_log (ts, event_type, candidate_id, detail_json) VALUES (%s, %s, %s, %s)",
        (dt.datetime.now(dt.timezone.utc).isoformat(), event_type, candidate_id, json.dumps(detail)),
    )
