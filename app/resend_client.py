"""The only module in this app that calls Resend.

CLAUDE.md non-negotiable #1 ("The Cut"): the only code path that reaches this
module is POST /drafts/{id}/send, triggered by an explicit click on one
reviewed draft. No scheduler, batch route, or retry loop may import this.
test_no_autosend.py asserts that with a grep/AST check.
"""
from __future__ import annotations

import resend

from app.config import settings


def send_email(*, to_address: str, subject: str, body_text: str) -> dict:
    """Sends one email via Resend. In DEMO_MODE, redirects to DEMO_RECIPIENT
    and prefixes the subject so nothing goes to a real applicant during a
    demo/dry run."""
    resend.api_key = settings.resend_api_key

    actual_to = to_address
    actual_subject = subject
    if settings.demo_mode:
        if not settings.demo_recipient:
            raise RuntimeError("DEMO_MODE is on but DEMO_RECIPIENT is not set")
        actual_to = settings.demo_recipient
        actual_subject = f"[DEMO → {to_address}] {subject}"

    params: resend.Emails.SendParams = {
        "from": settings.email_from,
        "to": [actual_to],
        "subject": actual_subject,
        "text": body_text,
    }
    response = resend.Emails.send(params)
    return {"resend_message_id": response.get("id"), "to_address": actual_to, "subject_sent": actual_subject}
