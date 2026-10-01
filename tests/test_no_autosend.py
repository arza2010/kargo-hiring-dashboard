"""Check 07 / "The Cut": nothing reaches a candidate without a human click.

Static checks here (grep/AST) rather than a live DB, so this test runs fully
offline and can't be defeated by a fixture that happens to look reviewed.
"""
import ast
from pathlib import Path

import pytest

from app.send_logic import (
    DraftAlreadySentError,
    DraftNotFoundError,
    DraftNotReviewedError,
    validate_draft_for_send,
)

APP_DIR = Path(__file__).resolve().parent.parent / "app"
MAIN_PY = APP_DIR / "main.py"


def _real_code_references(path: Path, identifier: str) -> bool:
    """AST-level check: does actual code (not a comment or docstring) name
    this identifier? A plain substring search would also flag comments like
    'this module never imports resend_client', which is the point being made,
    not a violation of it."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == identifier:
            return True
        if isinstance(node, ast.alias) and (node.name == identifier or node.name.endswith("." + identifier)):
            return True
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(identifier):
            return True
    return False


def _functions_referencing(path: Path, identifier: str) -> list[str]:
    tree = ast.parse(path.read_text())
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and inner.id == identifier:
                    hits.append(node.name)
                    break
    return hits


def test_resend_client_referenced_only_in_main():
    """Every app/*.py file except resend_client.py itself: the identifier
    `resend_client` may only appear as real code inside main.py."""
    offenders = [
        path.name
        for path in APP_DIR.glob("*.py")
        if path.name not in ("resend_client.py", "main.py") and _real_code_references(path, "resend_client")
    ]
    assert offenders == [], f"resend_client referenced outside main.py in: {offenders}"


def test_resend_client_referenced_only_in_the_send_endpoint():
    names = set(_functions_referencing(MAIN_PY, "resend_client"))
    assert names == {"send_draft"}, f"resend_client referenced in unexpected functions: {names}"


def test_send_draft_is_the_post_drafts_send_route():
    tree = ast.parse(MAIN_PY.read_text())
    send_draft = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "send_draft")
    decorator_srcs = [ast.unparse(d) for d in send_draft.decorator_list]
    assert any("/drafts/{draft_id}/send" in d and ".post(" in d for d in decorator_srcs), decorator_srcs


def test_no_batch_endpoint_references_resend_client():
    referencing_fns = set(_functions_referencing(MAIN_PY, "resend_client"))
    for fn_name in ("score_all", "score_one", "import_batch", "record_decision"):
        assert fn_name not in referencing_fns


def test_send_rejects_unreviewed_draft():
    with pytest.raises(DraftNotReviewedError):
        validate_draft_for_send({"reviewed": False}, already_sent=False)


def test_send_accepts_reviewed_unsent_draft():
    validate_draft_for_send({"reviewed": True}, already_sent=False)  # should not raise


def test_send_rejects_missing_draft():
    with pytest.raises(DraftNotFoundError):
        validate_draft_for_send(None, already_sent=False)


def test_send_rejects_already_sent_draft():
    with pytest.raises(DraftAlreadySentError):
        validate_draft_for_send({"reviewed": True}, already_sent=True)


def test_no_scheduler_or_background_job_files_exist():
    suspicious_names = {"scheduler.py", "cron.py", "jobs.py", "tasks.py", "worker.py"}
    present = {p.name for p in APP_DIR.glob("*.py")} & suspicious_names
    assert not present, f"found scheduler-shaped module(s): {present}"
