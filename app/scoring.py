"""Step A4 (scoring call) + A5 (evidence verification, score maths).

The AI returns levels only (CLAUDE.md rule 6: "the backend does the maths").
"""
from __future__ import annotations

from app.evidence import verify_all
from app.gemini_client import generate_json
from app.prompt_loader import fill_template, load_prompt
from app.rubric import WEIGHTS, load_rubric, years_flag_for

CRITERION_SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "integer", "minimum": 0, "maximum": 4},
        "evidence": {"type": ["string", "null"]},
        "status": {"type": "string", "enum": ["evidenced", "not_evidenced"]},
    },
    "required": ["level", "evidence", "status"],
}

SCORE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "object",
            "properties": {k: CRITERION_SCHEMA for k in ("C1", "C2", "C3", "C4", "C5_PM", "C5_SPM")},
            "required": ["C1", "C2", "C3", "C4", "C5_PM", "C5_SPM"],
        },
        "pm_years_from_cv": {"type": ["number", "null"]},
        "probes": {"type": "array", "items": {"type": "string"}},
        "one_line_rationale": {"type": "string"},
        "injection_detected": {"type": "boolean"},
    },
    "required": ["criteria", "pm_years_from_cv", "probes", "one_line_rationale", "injection_detected"],
}

CRITERIA_KEYS = ("C1", "C2", "C3", "C4", "C5_PM", "C5_SPM")


def build_score_prompt(applied_role: str, cleaned_cv_text: str) -> tuple[str, str]:
    template = load_prompt("score_candidate.md")
    rubric = load_rubric()
    user = fill_template(
        template.user_template,
        {
            "rubric_parts_A_B_E": rubric.ai_facing_text(),
            "applied_role": applied_role,
            "cleaned_cv_text": cleaned_cv_text,
        },
    )
    return template.system, user


def score_candidate(applied_role: str, cleaned_cv_text: str) -> dict:
    """Calls Gemini, verifies evidence, computes scores. Returns a dict ready
    to persist to the `scores` table (see app/db.py)."""
    system, user = build_score_prompt(applied_role, cleaned_cv_text)
    raw = generate_json(
        system_instruction=system,
        user_content=user,
        response_schema=SCORE_RESPONSE_SCHEMA,
        temperature=0,
    )
    return finalize_score(raw, cleaned_cv_text)


def finalize_score(raw: dict, cleaned_cv_text: str) -> dict:
    """The A5 half: verify quotes, then compute everything in code."""
    verified = verify_all(raw["criteria"], cleaned_cv_text)

    def level(key: str) -> int:
        return verified[key]["level"]

    pm_score = (
        WEIGHTS["C1"] * level("C1") / 4
        + WEIGHTS["C2"] * level("C2") / 4
        + WEIGHTS["C3"] * level("C3") / 4
        + WEIGHTS["C4"] * level("C4") / 4
        + WEIGHTS["C5"] * level("C5_PM") / 4
    )
    spm_score = (
        WEIGHTS["C1"] * level("C1") / 4
        + WEIGHTS["C2"] * level("C2") / 4
        + WEIGHTS["C3"] * level("C3") / 4
        + WEIGHTS["C4"] * level("C4") / 4
        + WEIGHTS["C5"] * level("C5_SPM") / 4
    )

    pm_years = raw.get("pm_years_from_cv")
    years_flag = years_flag_for(pm_years)
    level_hint = abs(pm_score - spm_score) >= 10

    return {
        "criteria": verified,
        "pm_score": round(pm_score, 2),
        "spm_score": round(spm_score, 2),
        "pm_years_from_cv": pm_years,
        "years_flag": years_flag,
        "level_hint": level_hint,
        "probes": raw.get("probes", []),
        "one_line_rationale": raw.get("one_line_rationale", ""),
        "injection_detected": bool(raw.get("injection_detected", False)),
    }
