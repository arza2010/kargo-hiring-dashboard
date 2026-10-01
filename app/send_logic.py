"""Pure validation for POST /drafts/{id}/send — kept separate from main.py so
it can be unit-tested without a database or the Resend SDK.

The only side-effecting send call lives in resend_client.py, invoked from the
route in main.py after this validation passes. This module never imports
resend_client or app.db, on purpose.
"""
from __future__ import annotations


class DraftNotReviewedError(ValueError):
    pass


class DraftAlreadySentError(ValueError):
    pass


class DraftNotFoundError(ValueError):
    pass


def validate_draft_for_send(draft_row: dict | None, already_sent: bool) -> None:
    """Raises if this draft is not eligible to be sent. Called once, from the
    send route, right before (and only before) resend_client.send_email."""
    if draft_row is None:
        raise DraftNotFoundError("draft not found")
    if already_sent:
        raise DraftAlreadySentError("this draft has already been sent")
    if not draft_row.get("reviewed"):
        raise DraftNotReviewedError(
            "draft has not been opened on the review screen — cannot send an unreviewed draft"
        )
