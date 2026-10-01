"""Step A1-A3 orchestration: parse a file, strip PII, work out status.

Returns a plain dict shaped like a `candidates` row (minus id/timestamps),
so main.py can insert it directly. No AI calls happen here.

Bytes-first on purpose: the original file is stored in Postgres
(`candidates.file_bytes`), not on local disk, so ingest works the same way
whether a CV comes from `data/applications/` (batch import, local dev) or a
direct HTTP upload with no persistent disk at all (e.g. Vercel).
"""
from __future__ import annotations

from pathlib import Path

from app.parsing import detect_role, detect_role_from_filename, parse_bytes
from app.pii import strip_pii

CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


def _ingest(data: bytes, filename: str, applied_role: str, source: str) -> dict:
    parsed = parse_bytes(data, filename)
    row = {
        "source": source,
        "file_bytes": data,
        "content_type": CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream"),
        "content_hash": parsed.content_hash,
        "original_filename": filename,
        "applied_role": "role_unknown",
        "name": None,
        "email": None,
        "phone": None,
        "cleaned_text": None,
        "parse_status": parsed.parse_status,
        "parse_notes": parsed.parse_notes,
    }

    if parsed.parse_status != "ok":
        return row

    row["applied_role"] = applied_role

    pii = strip_pii(parsed.paragraphs, Path(filename).stem)
    row["email"] = pii.email
    row["phone"] = pii.phone

    if pii.blocked:
        row["parse_status"] = "pii_block"
        row["parse_notes"] = "; ".join(pii.notes) or "PII post-check failed"
        return row

    if pii.needs_name:
        row["parse_status"] = "needs_name"
        row["parse_notes"] = "; ".join(pii.notes)
        row["cleaned_text"] = pii.cleaned_text
        return row

    row["name"] = pii.name
    row["cleaned_text"] = pii.cleaned_text
    row["parse_status"] = "ok"
    row["parse_notes"] = "; ".join(pii.notes) if pii.notes else None
    return row


def ingest_bytes(data: bytes, filename: str, source: str = "application", role_hint: str | None = None) -> dict:
    """For uploads with no filesystem path — role can only come from the
    filename (or an explicit hint from a form field), never a pm/spm folder."""
    role = role_hint or detect_role_from_filename(filename)
    return _ingest(data, filename, role, source)


def ingest_file(path: Path, source: str = "application") -> dict:
    """For CVs already on local disk (batch import from data/applications/,
    tests, calibration) — role can also come from a pm/spm subfolder."""
    return _ingest(path.read_bytes(), path.name, detect_role(path), source)
