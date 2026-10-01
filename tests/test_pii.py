"""A3: run the PII stripper on the 8 hire CVs and check nothing personal survives."""
from pathlib import Path

import pytest

from app.ingest import ingest_file
from app.parsing import parse_file
from app.pii import EMAIL_RE, URL_RE, _find_phones

HIRES_DIR = Path(__file__).resolve().parent.parent / "data" / "hires"
HIRE_FILES = sorted(HIRES_DIR.glob("*.docx"))


@pytest.mark.parametrize("path", HIRE_FILES, ids=lambda p: p.name)
def test_no_email_phone_url_survives(path):
    row = ingest_file(path, source="hire")
    assert row["parse_status"] == "ok", row["parse_notes"]
    text = row["cleaned_text"]
    assert EMAIL_RE.search(text) is None
    assert not _find_phones(text)
    assert URL_RE.search(text) is None


@pytest.mark.parametrize("path", HIRE_FILES, ids=lambda p: p.name)
def test_no_name_token_survives(path):
    parsed = parse_file(path)
    header = next(p for p in parsed.paragraphs if p.strip())
    row = ingest_file(path, source="hire")
    assert row["parse_status"] == "ok", row["parse_notes"]
    for tok in header.split():
        tok = tok.strip(".")
        if len(tok) >= 3 and tok.isalpha():
            assert tok.lower() not in row["cleaned_text"].lower(), f"{tok!r} leaked in {path.name}"


@pytest.mark.parametrize("path", HIRE_FILES, ids=lambda p: p.name)
def test_education_section_removed(path):
    row = ingest_file(path, source="hire")
    assert row["parse_status"] == "ok", row["parse_notes"]
    assert "education" not in row["cleaned_text"].lower()
    # degree markers that only appear inside the Education section in these CVs
    for marker in ("CGPA", "B.Com", "B.Sc.", "B.E.,", "NIT ", "College"):
        assert marker.lower() not in row["cleaned_text"].lower(), f"{marker!r} leaked in {path.name}"


def test_port_and_terminal_names_preserved():
    found_any = False
    for path in HIRE_FILES:
        row = ingest_file(path, source="hire")
        text = row["cleaned_text"] or ""
        for term in ("JNPT", "Nhava Sheva", "ICD"):
            if term.lower() in text.lower():
                found_any = True
    assert found_any, "expected at least one operational port/terminal term to survive across the 8 hire CVs"


def test_post_check_blocks_when_pii_remains():
    from app.pii import PiiResult, _post_check

    blocked, reason = _post_check("Contact me at someone@example.com", [])
    assert blocked
    assert reason == "email address"
