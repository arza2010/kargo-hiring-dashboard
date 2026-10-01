"""Gate 0.5: scoring is disabled until Arjun confirms the rubric on Setup.

The confirmation is stored against the rubric file's SHA-256. If the file
changes, the hash no longer matches and the confirmation is treated as gone.
"""
from __future__ import annotations

import datetime as dt

import psycopg

from app.rubric import load_rubric


def get_setup_row(conn: psycopg.Connection) -> dict:
    return conn.execute("SELECT * FROM setup WHERE id = 1").fetchone()


def is_confirmed(conn: psycopg.Connection) -> bool:
    row = get_setup_row(conn)
    if not row or not row["rubric_hash"] or not row["confirmed_at"]:
        return False
    return row["rubric_hash"] == load_rubric().sha256


def confirm(conn: psycopg.Connection) -> None:
    rubric = load_rubric()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    conn.execute(
        "UPDATE setup SET rubric_hash = %s, confirmed_at = %s WHERE id = 1",
        (rubric.sha256, now),
    )


def set_acknowledge_delay(conn: psycopg.Connection, value: bool) -> None:
    conn.execute("UPDATE setup SET acknowledge_delay = %s WHERE id = 1", (value,))


class PatternNotConfirmedError(RuntimeError):
    pass


def require_confirmed(conn: psycopg.Connection) -> None:
    if not is_confirmed(conn):
        raise PatternNotConfirmedError(
            "Scoring is disabled until the rubric pattern is confirmed on the Setup screen."
        )
