"""Loads and splits the rubric file. Only Parts A, B and E ever go to the AI."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import BASE_DIR

RUBRIC_PATH = BASE_DIR / "rubric" / "kargo_pm_spm_rubric.txt"

PART_HEADER_RE = re.compile(r"PART\s+([A-F])\s*·", re.IGNORECASE)

WEIGHTS = {"C1": 30, "C2": 20, "C3": 15, "C4": 10, "C5": 25}
PM_YEARS_RANGE = (2, 4)
SPM_YEARS_RANGE = (5, 8)


@dataclass(frozen=True)
class Rubric:
    raw_text: str
    sha256: str
    parts: dict[str, str]  # "A".."F" -> text of that part (without the header line)
    pattern_name: str

    def ai_facing_text(self) -> str:
        """Parts A, B and E only — what score_candidate.md sends to the model."""
        return "\n\n".join(self.parts[p] for p in ("A", "B", "E") if p in self.parts)

    def part_d_text(self) -> str:
        return self.parts.get("D", "")


def _split_parts(raw_text: str) -> dict[str, str]:
    matches = list(PART_HEADER_RE.finditer(raw_text))
    parts: dict[str, str] = {}
    for i, m in enumerate(matches):
        letter = m.group(1).upper()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        parts[letter] = raw_text[start:end].strip()
    return parts


def _extract_pattern_name(raw_text: str) -> str:
    m = re.search(r'Pattern name \(proposed\):\s*"([^"]+)"', raw_text)
    return m.group(1) if m else "Unnamed pattern"


@lru_cache(maxsize=1)
def load_rubric() -> Rubric:
    raw_text = RUBRIC_PATH.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    parts = _split_parts(raw_text)
    pattern_name = _extract_pattern_name(raw_text)
    return Rubric(raw_text=raw_text, sha256=sha256, parts=parts, pattern_name=pattern_name)


def years_flag_for(pm_years_from_cv: float | None) -> str:
    """Info-only flag (rubric Part A.10) — years are never scored."""
    if pm_years_from_cv is None:
        return "unclear"
    if PM_YEARS_RANGE[0] <= pm_years_from_cv <= PM_YEARS_RANGE[1]:
        return "within PM range"
    if SPM_YEARS_RANGE[0] <= pm_years_from_cv <= SPM_YEARS_RANGE[1]:
        return "within SPM range"
    return "outside both"
