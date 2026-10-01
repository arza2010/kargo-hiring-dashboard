"""FastAPI app. Binds to 127.0.0.1 only (see scripts/run.sh) — local tool, no auth.

Route map lives in PLAN.md section 6. The one non-negotiable to keep in view
while editing this file: POST /drafts/{id}/send is the ONLY route that may
import or call app.resend_client. tests/test_no_autosend.py enforces this
with a static check, not just a code review.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterator

import psycopg
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import pattern_gate
from app.audit_log import log_event
from app.auth import require_auth
from app.brief import write_brief
from app.config import BASE_DIR, settings
from app.db import connect, init_db
from app.email_draft import ROLE_TITLES, draft_email
from app.evidence import quote_found
from app.ingest import ingest_bytes, ingest_file
from app.pii import _post_check, _redact_name  # re-used for the needs_name follow-up
from app.rubric import load_rubric
from app.scoring import score_candidate
from app.send_logic import DraftAlreadySentError, DraftNotFoundError, DraftNotReviewedError, validate_draft_for_send

APPLICATIONS_DIR = BASE_DIR / "data" / "applications"
JD_FILES = {"PM": BASE_DIR / "data" / "jds" / "jd_product_manager.docx",
            "SPM": BASE_DIR / "data" / "jds" / "jd_senior_product_manager.docx"}

app = FastAPI(title="Kargo Hiring Dashboard", dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@app.exception_handler(RuntimeError)
def runtime_error_handler(request: Request, exc: RuntimeError):
    from fastapi.responses import HTMLResponse as _HTMLResponse

    return _HTMLResponse(
        f"<body style='font-family:sans-serif;padding:40px;max-width:560px'>"
        f"<h2>Configuration problem</h2><p>{exc}</p>"
        f"<p><a href='/setup'>Back to Setup</a></p></body>",
        status_code=500,
    )


def get_db() -> Iterator[psycopg.Connection]:
    with connect() as conn:
        try:
            init_db(conn)
        except Exception:
            pass
        yield conn


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def candidate_id_for(content_hash: str) -> str:
    return f"cv_{content_hash[:10]}"


# ---------------------------------------------------------------- setup ----

@app.get("/", response_class=HTMLResponse)
def index(conn: psycopg.Connection = Depends(get_db)):
    if pattern_gate.is_confirmed(conn):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/setup")


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, conn: psycopg.Connection = Depends(get_db)):
    rubric = load_rubric()
    setup_row = pattern_gate.get_setup_row(conn)
    missing = settings.missing()
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "rubric": rubric,
            "weights": {"C1": 30, "C2": 20, "C3": 15, "C4": 10, "C5": 25},
            "confirmed": pattern_gate.is_confirmed(conn),
            "setup_row": setup_row,
            "missing_env": missing,
        },
    )


@app.get("/setup/jd/{role}", response_class=HTMLResponse)
def view_jd(role: str):
    """Step 0.2: load the JDs for reference on the Setup screen."""
    if role not in JD_FILES:
        raise HTTPException(404, "unknown role")
    import html

    from app.parsing import parse_file

    parsed = parse_file(JD_FILES[role])
    body = html.escape("\n".join(parsed.paragraphs))
    return HTMLResponse(f"<pre style='white-space:pre-wrap;font-family:inherit;padding:24px'>{body}</pre>")


@app.post("/setup/confirm")
def confirm_pattern(conn: psycopg.Connection = Depends(get_db)):
    pattern_gate.confirm(conn)
    log_event(conn, "pattern_confirmed", None, {"rubric_sha256": load_rubric().sha256})
    return RedirectResponse("/setup", status_code=303)


@app.post("/setup/settings")
def update_settings(acknowledge_delay: bool = Form(False), conn: psycopg.Connection = Depends(get_db)):
    pattern_gate.set_acknowledge_delay(conn, acknowledge_delay)
    return RedirectResponse("/setup", status_code=303)


# ------------------------------------------------------------- ingest A1 ----

def _store_ingested_row(row: dict, conn: psycopg.Connection) -> dict:
    """Persists an already-ingested row dict (see app/ingest.py) — the file's
    bytes live in Postgres (`file_bytes`), never on local disk, so this works
    the same locally or deployed with no persistent filesystem."""
    existing = conn.execute(
        "SELECT id FROM candidates WHERE content_hash = %s", (row["content_hash"],)
    ).fetchone()
    if existing:
        return {"id": existing["id"], "duplicate": True}

    cid = candidate_id_for(row["content_hash"])
    ts = now_iso()
    conn.execute(
        """INSERT INTO candidates
           (id, source, file_bytes, content_type, content_hash, original_filename, applied_role,
            name, email, phone, cleaned_text, parse_status, parse_notes, status, created_at, updated_at)
           VALUES (%(id)s, %(source)s, %(file_bytes)s, %(content_type)s, %(content_hash)s, %(original_filename)s,
                   %(applied_role)s, %(name)s, %(email)s, %(phone)s, %(cleaned_text)s,
                   %(parse_status)s, %(parse_notes)s, 'new', %(created_at)s, %(updated_at)s)""",
        {**row, "id": cid, "created_at": ts, "updated_at": ts},
    )
    if row["parse_status"] == "pii_block":
        log_event(conn, "pii_block", cid, {"reason": row["parse_notes"]})
    return {"id": cid, "duplicate": False}


@app.post("/candidates/upload")
def upload_candidate(
    file: UploadFile,
    role: str = Form("role_unknown"),
    conn: psycopg.Connection = Depends(get_db),
):
    data = file.file.read()
    row = ingest_bytes(data, file.filename, source="application", role_hint=role if role != "role_unknown" else None)
    result = _store_ingested_row(row, conn)
    return RedirectResponse(f"/candidates/{result['id']}", status_code=303)


@app.post("/candidates/import-batch")
def import_batch(conn: psycopg.Connection = Depends(get_db)):
    """Local-dev convenience: walks data/applications/ on disk. Not available
    once deployed with no persistent filesystem — use /candidates/upload
    (one at a time, or scripted) there instead."""
    imported, duplicates, flagged = 0, 0, 0
    if not APPLICATIONS_DIR.is_dir():
        return {"imported": 0, "duplicates": 0, "flagged": 0, "note": "data/applications/ not present on this deployment"}
    for path in sorted(APPLICATIONS_DIR.rglob("*")):
        if not path.is_file() or path.name == "README.md":
            continue
        row = ingest_file(path, source="application")
        result = _store_ingested_row(row, conn)
        if result["duplicate"]:
            duplicates += 1
        else:
            imported += 1
            row_status = conn.execute("SELECT parse_status FROM candidates WHERE id = %s", (result["id"],)).fetchone()
            if row_status and row_status["parse_status"] != "ok":
                flagged += 1
    return {"imported": imported, "duplicates": duplicates, "flagged": flagged}


@app.post("/candidates/{candidate_id}/role")
def set_role(candidate_id: str, role: str = Form(...), conn: psycopg.Connection = Depends(get_db)):
    if role not in ("PM", "SPM"):
        raise HTTPException(400, "role must be PM or SPM")
    conn.execute(
        "UPDATE candidates SET applied_role = %s, updated_at = %s WHERE id = %s",
        (role, now_iso(), candidate_id),
    )
    return RedirectResponse(f"/candidates/{candidate_id}", status_code=303)


@app.post("/candidates/{candidate_id}/name")
def set_name(candidate_id: str, name: str = Form(...), conn: psycopg.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,)).fetchone()
    if not row:
        raise HTTPException(404, "candidate not found")
    if row["parse_status"] != "needs_name":
        raise HTTPException(400, "this candidate is not waiting on a name")

    tokens = [w.strip(".") for w in name.strip().split()]
    new_cleaned = _redact_name(row["cleaned_text"], tokens, name.strip())
    blocked, reason = _post_check(new_cleaned, tokens)

    if blocked:
        conn.execute(
            "UPDATE candidates SET parse_status = 'pii_block', parse_notes = %s, updated_at = %s WHERE id = %s",
            (f"post-check found leftover PII after name entry: {reason}", now_iso(), candidate_id),
        )
        log_event(conn, "pii_block", candidate_id, {"reason": reason})
        raise HTTPException(422, f"could not clean this CV safely ({reason}) — flagged for manual review")

    conn.execute(
        "UPDATE candidates SET name = %s, cleaned_text = %s, parse_status = 'ok', parse_notes = NULL, "
        "updated_at = %s WHERE id = %s",
        (name.strip(), new_cleaned, now_iso(), candidate_id),
    )
    return RedirectResponse(f"/candidates/{candidate_id}", status_code=303)


# --------------------------------------------------------- scoring A4-A6 ----

def _score_and_brief_one(conn: psycopg.Connection, row: dict) -> None:
    result = score_candidate(row["applied_role"], row["cleaned_text"])
    ts = now_iso()
    conn.execute(
        """INSERT INTO scores (candidate_id, criteria_json, pm_score, spm_score, pm_years_from_cv,
               years_flag, level_hint, probes_json, one_line_rationale, injection_detected, scored_at)
           VALUES (%(candidate_id)s, %(criteria_json)s, %(pm_score)s, %(spm_score)s, %(pm_years_from_cv)s,
               %(years_flag)s, %(level_hint)s, %(probes_json)s, %(one_line_rationale)s, %(injection_detected)s, %(scored_at)s)
           ON CONFLICT (candidate_id) DO UPDATE SET
               criteria_json = EXCLUDED.criteria_json, pm_score = EXCLUDED.pm_score,
               spm_score = EXCLUDED.spm_score, pm_years_from_cv = EXCLUDED.pm_years_from_cv,
               years_flag = EXCLUDED.years_flag, level_hint = EXCLUDED.level_hint,
               probes_json = EXCLUDED.probes_json, one_line_rationale = EXCLUDED.one_line_rationale,
               injection_detected = EXCLUDED.injection_detected, scored_at = EXCLUDED.scored_at""",
        {
            "candidate_id": row["id"],
            "criteria_json": _to_json(result["criteria"]),
            "pm_score": result["pm_score"],
            "spm_score": result["spm_score"],
            "pm_years_from_cv": result["pm_years_from_cv"],
            "years_flag": result["years_flag"],
            "level_hint": result["level_hint"],
            "probes_json": _to_json(result["probes"]),
            "one_line_rationale": result["one_line_rationale"],
            "injection_detected": result["injection_detected"],
            "scored_at": ts,
        },
    )
    if result["injection_detected"]:
        log_event(conn, "injection_flag", row["id"], {"probes": result["probes"]})

    brief = write_brief(
        applied_role=row["applied_role"],
        pm_score=result["pm_score"],
        spm_score=result["spm_score"],
        level_hint=result["level_hint"],
        years_flag=result["years_flag"],
        verified_scoring_result=result,
        cleaned_cv_text=row["cleaned_text"],
    )
    conn.execute(
        """INSERT INTO briefs (candidate_id, who_text, why_ranked_json, gaps_json, probes_json, level_note, created_at)
           VALUES (%(candidate_id)s, %(who_text)s, %(why_ranked_json)s, %(gaps_json)s, %(probes_json)s, %(level_note)s, %(created_at)s)
           ON CONFLICT (candidate_id) DO UPDATE SET
               who_text = EXCLUDED.who_text, why_ranked_json = EXCLUDED.why_ranked_json,
               gaps_json = EXCLUDED.gaps_json, probes_json = EXCLUDED.probes_json,
               level_note = EXCLUDED.level_note, created_at = EXCLUDED.created_at""",
        {
            "candidate_id": row["id"],
            "who_text": brief["who"],
            "why_ranked_json": _to_json(brief["why_ranked_here"]),
            "gaps_json": _to_json(brief["gaps"]),
            "probes_json": _to_json(brief["probes"]),
            "level_note": brief["level_note"],
            "created_at": ts,
        },
    )
    conn.execute("UPDATE candidates SET status = 'scored', updated_at = %s WHERE id = %s", (ts, row["id"]))


def _to_json(value) -> str:
    import json

    return json.dumps(value)


@app.post("/score/all")
def score_all(conn: psycopg.Connection = Depends(get_db)):
    pattern_gate.require_confirmed(conn)
    rows = conn.execute(
        "SELECT * FROM candidates WHERE parse_status = 'ok' AND applied_role IN ('PM','SPM') "
        "AND status = 'new'"
    ).fetchall()
    scored, failed = 0, 0
    for row in rows:
        try:
            _score_and_brief_one(conn, row)
            scored += 1
        except Exception as exc:  # noqa: BLE001 — surfaced in the response, not swallowed
            failed += 1
            log_event(conn, "score_error", row["id"], {"error": str(exc)})
    return {"scored": scored, "failed": failed, "eligible": len(rows)}


@app.post("/candidates/{candidate_id}/score")
def score_one(candidate_id: str, conn: psycopg.Connection = Depends(get_db)):
    pattern_gate.require_confirmed(conn)
    row = conn.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,)).fetchone()
    if not row:
        raise HTTPException(404, "candidate not found")
    if row["parse_status"] != "ok" or row["applied_role"] not in ("PM", "SPM"):
        raise HTTPException(400, "candidate is not eligible to score yet (role/name/parse must be resolved)")
    _score_and_brief_one(conn, row)
    return RedirectResponse(f"/candidates/{candidate_id}", status_code=303)


# ------------------------------------------------------------- dashboard ----

def _candidate_rows(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        """SELECT c.*, s.pm_score, s.spm_score, s.years_flag, s.level_hint, s.one_line_rationale, s.scored_at
           FROM candidates c LEFT JOIN scores s ON s.candidate_id = c.id
           WHERE c.source = 'application'
           ORDER BY COALESCE(s.pm_score, 0) + COALESCE(s.spm_score, 0) DESC, c.created_at ASC"""
    ).fetchall()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, conn: psycopg.Connection = Depends(get_db)):
    rows = _candidate_rows(conn)

    unsent = conn.execute(
        "SELECT COUNT(*) AS n FROM candidates WHERE source='application' AND status IN ('decided','drafted')"
    ).fetchone()["n"]

    seven_days_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    stale = conn.execute(
        "SELECT COUNT(*) AS n FROM candidates c JOIN scores s ON s.candidate_id = c.id "
        "WHERE c.source='application' AND c.status = 'scored' AND s.scored_at < %s",
        (seven_days_ago,),
    ).fetchone()["n"]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "pm_rows": [r for r in rows if r["applied_role"] == "PM"],
            "spm_rows": [r for r in rows if r["applied_role"] == "SPM"],
            "all_rows": rows,
            "unsent_count": unsent,
            "stale_count": stale,
        },
    )


@app.get("/candidates/{candidate_id}", response_class=HTMLResponse)
def candidate_detail(request: Request, candidate_id: str, conn: psycopg.Connection = Depends(get_db)):
    import json

    row = conn.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,)).fetchone()
    if not row:
        raise HTTPException(404, "candidate not found")
    score = conn.execute("SELECT * FROM scores WHERE candidate_id = %s", (candidate_id,)).fetchone()
    brief = conn.execute("SELECT * FROM briefs WHERE candidate_id = %s", (candidate_id,)).fetchone()
    decisions = conn.execute(
        "SELECT * FROM decisions WHERE candidate_id = %s ORDER BY decided_at DESC", (candidate_id,)
    ).fetchall()
    drafts = conn.execute(
        "SELECT * FROM drafts WHERE candidate_id = %s ORDER BY created_at DESC", (candidate_id,)
    ).fetchall()

    criteria = json.loads(score["criteria_json"]) if score else None
    probes = json.loads(score["probes_json"]) if score else []
    brief_why = json.loads(brief["why_ranked_json"]) if brief else []
    brief_gaps = json.loads(brief["gaps_json"]) if brief else []
    brief_probes = json.loads(brief["probes_json"]) if brief else []

    return templates.TemplateResponse(
        request,
        "candidate.html",
        {
            "c": row,
            "score": score,
            "criteria": criteria,
            "probes": probes,
            "brief": brief,
            "brief_why": brief_why,
            "brief_gaps": brief_gaps,
            "brief_probes": brief_probes,
            "decisions": decisions,
            "drafts": drafts,
            "role_titles": ROLE_TITLES,
        },
    )


@app.get("/files/{candidate_id}")
def get_file(candidate_id: str, conn: psycopg.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT file_bytes, content_type, original_filename FROM candidates WHERE id = %s", (candidate_id,)
    ).fetchone()
    if not row or row["file_bytes"] is None:
        raise HTTPException(404, "candidate file not found")
    return Response(
        content=bytes(row["file_bytes"]),
        media_type=row["content_type"],
        headers={"Content-Disposition": f'inline; filename="{row["original_filename"]}"'},
    )


# ------------------------------------------------------- decide / draft ----

def _pick_highlight(criteria: dict, interview_role: str | None) -> str | None:
    if not interview_role:
        return None
    preferred_key = "C5_PM" if interview_role == "PM" else "C5_SPM"
    for key in (preferred_key, "C1", "C2", "C3", "C4"):
        c = criteria.get(key)
        if c and c.get("status") == "evidenced" and c.get("level", 0) > 0 and c.get("evidence"):
            return c["evidence"]
    return None


@app.post("/candidates/{candidate_id}/decision")
def record_decision(
    candidate_id: str,
    decision: str = Form(...),
    note: str = Form(""),
    conn: psycopg.Connection = Depends(get_db),
):
    if decision not in ("interview_pm", "interview_spm", "pass"):
        raise HTTPException(400, "decision must be interview_pm, interview_spm or pass")

    row = conn.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,)).fetchone()
    if not row:
        raise HTTPException(404, "candidate not found")

    ts = now_iso()
    decision_id = conn.execute(
        "INSERT INTO decisions (candidate_id, decision, note, decided_at) VALUES (%s, %s, %s, %s) RETURNING id",
        (candidate_id, decision, note or None, ts),
    ).fetchone()["id"]
    conn.execute("UPDATE candidates SET status = 'decided', updated_at = %s WHERE id = %s", (ts, candidate_id))
    log_event(conn, "decision", candidate_id, {"decision": decision, "note": note})

    interview_role = {"interview_pm": "PM", "interview_spm": "SPM"}.get(decision)
    highlight = None
    if interview_role:
        import json

        score = conn.execute("SELECT criteria_json FROM scores WHERE candidate_id = %s", (candidate_id,)).fetchone()
        if score:
            highlight = _pick_highlight(json.loads(score["criteria_json"]), interview_role)

    setup_row = pattern_gate.get_setup_row(conn)
    acknowledge_delay = bool(setup_row["acknowledge_delay"]) if setup_row else True

    try:
        draft = draft_email(
            decision=decision,
            applied_role=row["applied_role"],
            interview_role=interview_role,
            acknowledge_delay=acknowledge_delay,
            highlight=highlight,
        )
    except Exception as exc:  # noqa: BLE001
        log_event(conn, "draft_error", candidate_id, {"error": str(exc)})
        return RedirectResponse(f"/candidates/{candidate_id}", status_code=303)

    if highlight:
        assert quote_found(highlight, row["cleaned_text"]), "highlight must be a verified quote"

    draft_id = conn.execute(
        """INSERT INTO drafts (candidate_id, decision_id, subject, body_text, reviewed, warning, created_at, updated_at)
           VALUES (%s, %s, %s, %s, FALSE, %s, %s, %s) RETURNING id""",
        (candidate_id, decision_id, draft["subject"], draft["body_text"], draft["warning"], ts, ts),
    ).fetchone()["id"]
    conn.execute("UPDATE candidates SET status = 'drafted', updated_at = %s WHERE id = %s", (ts, candidate_id))
    log_event(conn, "draft", candidate_id, {"draft_id": draft_id, "warning": draft["warning"]})

    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def review_draft(request: Request, draft_id: int, conn: psycopg.Connection = Depends(get_db)):
    draft = conn.execute("SELECT * FROM drafts WHERE id = %s", (draft_id,)).fetchone()
    if not draft:
        raise HTTPException(404, "draft not found")
    candidate = conn.execute("SELECT * FROM candidates WHERE id = %s", (draft["candidate_id"],)).fetchone()
    sent = conn.execute("SELECT * FROM sends WHERE draft_id = %s", (draft_id,)).fetchone()

    first_name = (candidate["name"] or "").split(" ")[0] if candidate["name"] else "[name]"
    preview_body = draft["body_text"].replace("{{first_name}}", first_name)

    return templates.TemplateResponse(
        request,
        "review_email.html",
        {
            "draft": draft,
            "candidate": candidate,
            "preview_body": preview_body,
            "first_name": first_name,
            "already_sent": sent is not None,
            "demo_mode": settings.demo_mode,
            "demo_recipient": settings.demo_recipient,
        },
    )


@app.post("/drafts/{draft_id}")
def save_draft(
    draft_id: int,
    subject: str = Form(...),
    body_text: str = Form(...),
    conn: psycopg.Connection = Depends(get_db),
):
    draft = conn.execute("SELECT * FROM drafts WHERE id = %s", (draft_id,)).fetchone()
    if not draft:
        raise HTTPException(404, "draft not found")
    ts = now_iso()
    conn.execute(
        "UPDATE drafts SET subject = %s, body_text = %s, reviewed = TRUE, updated_at = %s WHERE id = %s",
        (subject, body_text, ts, draft_id),
    )
    log_event(conn, "edit", draft["candidate_id"], {"draft_id": draft_id})
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@app.post("/drafts/{draft_id}/send")
def send_draft(draft_id: int, conn: psycopg.Connection = Depends(get_db)):
    """The ONLY route in this app that may call app.resend_client.send_email."""
    draft = conn.execute("SELECT * FROM drafts WHERE id = %s", (draft_id,)).fetchone()
    already_sent = conn.execute("SELECT id FROM sends WHERE draft_id = %s", (draft_id,)).fetchone() is not None

    try:
        validate_draft_for_send(draft, already_sent)
    except DraftNotFoundError:
        raise HTTPException(404, "draft not found")
    except DraftNotReviewedError as exc:
        raise HTTPException(409, str(exc))
    except DraftAlreadySentError as exc:
        raise HTTPException(409, str(exc))

    candidate = conn.execute("SELECT * FROM candidates WHERE id = %s", (draft["candidate_id"],)).fetchone()
    if not candidate["email"]:
        raise HTTPException(422, "candidate has no email on file — cannot send")

    first_name = (candidate["name"] or "there").split(" ")[0]
    body_text = draft["body_text"].replace("{{first_name}}", first_name)

    from app import resend_client  # imported only here, inside the one send route

    result = resend_client.send_email(to_address=candidate["email"], subject=draft["subject"], body_text=body_text)

    ts = now_iso()
    conn.execute(
        "INSERT INTO sends (draft_id, resend_message_id, to_address, subject_sent, sent_at) VALUES (%s, %s, %s, %s, %s)",
        (draft_id, result["resend_message_id"], result["to_address"], result["subject_sent"], ts),
    )
    conn.execute("UPDATE candidates SET status = 'sent', updated_at = %s WHERE id = %s", (ts, candidate["id"]))
    log_event(conn, "send", candidate["id"], {"draft_id": draft_id, "resend_message_id": result["resend_message_id"]})

    return RedirectResponse(f"/candidates/{candidate['id']}", status_code=303)
