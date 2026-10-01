"""Evidence-or-nothing (CLAUDE.md rule 5): every quote is checked against the
cleaned CV text, normalising whitespace/punctuation before matching. A quote
that can't be found becomes level 0, status "unverified"."""
from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_PUNCT_TABLE = str.maketrans("", "", "\"'`‘’“”.,;:!?()[]{}-–—")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().translate(_PUNCT_TABLE)
    text = _WS_RE.sub(" ", text).strip()
    return text


def quote_found(quote: str | None, cleaned_text: str) -> bool:
    if not quote or not quote.strip():
        return False
    return normalise(quote) in normalise(cleaned_text)


def verify_criterion(criterion: dict, cleaned_text: str) -> dict:
    """Returns a copy of the criterion dict, demoted to level 0/unverified if
    its evidence quote isn't a verbatim (normalised) match in the CV."""
    level = criterion.get("level", 0)
    evidence = criterion.get("evidence")
    status = criterion.get("status", "not_evidenced")

    if level <= 0:
        return {"level": 0, "evidence": evidence, "status": status or "not_evidenced"}

    if quote_found(evidence, cleaned_text):
        return {"level": level, "evidence": evidence, "status": "evidenced"}

    return {"level": 0, "evidence": evidence, "status": "unverified"}


def verify_all(criteria: dict, cleaned_text: str) -> dict:
    return {key: verify_criterion(value, cleaned_text) for key, value in criteria.items()}
