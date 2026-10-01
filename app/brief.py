"""Step A6: interview brief call. Runs after scoring + verification."""
from __future__ import annotations

import json

from app.gemini_client import generate_json
from app.prompt_loader import fill_template, load_prompt

BRIEF_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {"type": "string"},
        "why_ranked_here": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "probes": {"type": "array", "items": {"type": "string"}},
        "level_note": {"type": ["string", "null"]},
    },
    "required": ["who", "why_ranked_here", "gaps", "probes", "level_note"],
}


def build_brief_prompt(
    *,
    applied_role: str,
    pm_score: float,
    spm_score: float,
    level_hint: bool,
    years_flag: str,
    verified_scoring_result: dict,
    cleaned_cv_text: str,
) -> tuple[str, str]:
    template = load_prompt("interview_brief.md")
    user = fill_template(
        template.user_template,
        {
            "applied_role": applied_role,
            "pm_score": str(pm_score),
            "spm_score": str(spm_score),
            "level_hint": str(level_hint).lower(),
            "years_flag": years_flag,
            "scoring_json_after_verification": json.dumps(verified_scoring_result, indent=2),
            "cleaned_cv_text": cleaned_cv_text,
        },
    )
    return template.system, user


def write_brief(
    *,
    applied_role: str,
    pm_score: float,
    spm_score: float,
    level_hint: bool,
    years_flag: str,
    verified_scoring_result: dict,
    cleaned_cv_text: str,
) -> dict:
    system, user = build_brief_prompt(
        applied_role=applied_role,
        pm_score=pm_score,
        spm_score=spm_score,
        level_hint=level_hint,
        years_flag=years_flag,
        verified_scoring_result=verified_scoring_result,
        cleaned_cv_text=cleaned_cv_text,
    )
    return generate_json(
        system_instruction=system,
        user_content=user,
        response_schema=BRIEF_RESPONSE_SCHEMA,
        temperature=0.2,
    )
