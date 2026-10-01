"""Step B5: draft email call. Runs only after Arjun records a decision.

Never sends anything — see resend_client.py / the /drafts/{id}/send route for
the only code path that does. This module only produces subject/body text and
runs the backend checks from prompts/draft_email.md.
"""
from __future__ import annotations

import re

from app.gemini_client import generate_json
from app.prompt_loader import fill_template, load_prompt

ROLE_TITLES = {"PM": "Product Manager", "SPM": "Senior Product Manager"}
WORD_LIMITS = {"interview_pm": 150, "interview_spm": 150, "pass": 110}

_FORBIDDEN_IN_PASS = ("score", "rubric", "criteria", "ai", "experience in", "looking for")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*[a-zA-Z_]+\s*\}\}")

DRAFT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body_text": {"type": "string"},
    },
    "required": ["subject", "body_text"],
}


def build_draft_prompt(
    *,
    decision: str,
    applied_role: str,
    interview_role: str | None,
    acknowledge_delay: bool,
    highlight: str | None,
) -> tuple[str, str]:
    template = load_prompt("draft_email.md")
    interview_role_title = ROLE_TITLES[interview_role] if interview_role else "null"
    user = fill_template(
        template.user_template,
        {
            "decision": decision,
            "applied_role_title": ROLE_TITLES[applied_role],
            "interview_role_title_or_null": interview_role_title,
            "acknowledge_delay": str(acknowledge_delay).lower(),
        },
    )
    # <highlight> is fenced, untrusted data — never merged with the whitelist
    # substitution above, which only touches the app's own control fields.
    user = user.replace(
        "{{one_verified_evidence_quote_or_null}}",
        highlight if highlight else "null",
    )
    return template.system, user


def run_backend_checks(decision: str, body_text: str) -> list[str]:
    problems = []

    first_name_count = body_text.count("{{first_name}}")
    if first_name_count != 1:
        problems.append(f"body_text must contain {{{{first_name}}}} exactly once, found {first_name_count}")

    other_placeholders = [m for m in _PLACEHOLDER_RE.findall(body_text) if m.replace(" ", "") != "{{first_name}}"]
    if other_placeholders:
        problems.append(f"body_text contains unexpected placeholders: {other_placeholders}")

    word_count = len(body_text.split())
    limit = WORD_LIMITS[decision]
    if word_count > limit:
        problems.append(f"body_text is {word_count} words, over the {limit}-word limit for {decision}")

    if decision == "pass":
        lowered = body_text.lower()
        for term in _FORBIDDEN_IN_PASS:
            if re.search(r"\b" + re.escape(term) + r"\b", lowered):
                problems.append(f"pass email contains forbidden term: {term!r}")

    return problems


def draft_email(
    *,
    decision: str,
    applied_role: str,
    interview_role: str | None,
    acknowledge_delay: bool,
    highlight: str | None,
) -> dict:
    """Calls Gemini, runs the backend checks, regenerates once on failure.

    Returns {"subject", "body_text", "warning"} — warning is None unless the
    checks still fail after one regeneration attempt.
    """
    system, user = build_draft_prompt(
        decision=decision,
        applied_role=applied_role,
        interview_role=interview_role,
        acknowledge_delay=acknowledge_delay,
        highlight=highlight,
    )

    for attempt in (1, 2):
        raw = generate_json(
            system_instruction=system,
            user_content=user,
            response_schema=DRAFT_RESPONSE_SCHEMA,
            temperature=0.4,
        )
        problems = run_backend_checks(decision, raw.get("body_text", ""))
        if not problems:
            return {"subject": raw["subject"], "body_text": raw["body_text"], "warning": None}
        if attempt == 1:
            continue

    warning = "Backend checks failed after regeneration: " + "; ".join(problems)
    return {"subject": raw["subject"], "body_text": raw["body_text"], "warning": warning}
