"""Loads SYSTEM/USER text out of prompts/*.md without changing their wording.

Each prompt file in prompts/ follows the same shape: a `## SYSTEM` section,
a `## USER` section, then `## RESPONSE SCHEMA`. This just extracts the first
two verbatim so main.py/scoring.py/etc never hand-copy prompt wording.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import BASE_DIR

PROMPTS_DIR = BASE_DIR / "prompts"


@dataclass(frozen=True)
class PromptTemplate:
    system: str
    user_template: str


def _extract_section(text: str, start_marker: str, end_marker: str | None) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start) if end_marker else len(text)
    section = text[start:end]
    # Drop a trailing "---" divider line if present.
    section = re.sub(r"\n---\s*$", "", section.strip())
    return section.strip()


@lru_cache(maxsize=None)
def load_prompt(filename: str) -> PromptTemplate:
    text = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    system = _extract_section(text, "## SYSTEM", "## USER")
    user = _extract_section(text, "## USER", "## RESPONSE SCHEMA")
    return PromptTemplate(system=system, user_template=user)


def fill_template(template: str, values: dict[str, str]) -> str:
    """Whitelist substitution — only the given {{keys}} are replaced.

    Deliberately not a blanket `.format()`/regex-replace-all: draft_email.md
    requires `{{first_name}}` to reach the model literally in some calls, and
    CV text is fenced, untrusted data that must never be treated as a format
    string.
    """
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out
