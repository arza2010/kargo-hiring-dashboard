"""Step A3: PII stripper + post-check, per CLAUDE.md's PII stripper spec.

Fail closed: if the post-check finds anything left over, the CV is blocked
from ever reaching the AI, not "cleaned as best we can".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CITY_LIST = [
    "New Delhi", "Mumbai", "Bengaluru", "Bangalore", "Chennai", "Delhi",
    "Pune", "Hyderabad", "Kolkata", "Ahmedabad", "Jamshedpur",
]
# Longest names first so "New Delhi" is matched whole, not as "New" + "[CITY]".
_CITY_SORTED = sorted(set(CITY_LIST), key=len, reverse=True)
CITY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _CITY_SORTED) + r")\b", re.IGNORECASE)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Candidate digit runs (with separators); filtered by digit-count below so
# shipment counts, percentages and year ranges ("180+", "30-40", "2022") are
# never mistaken for phone numbers.
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\-.\s()]{7,}\d")

URL_RE = re.compile(
    r"(?:https?://\S+"
    r"|www\.\S+"
    r"|\b(?:[a-zA-Z0-9-]+\.)?(?:linkedin|github|leetcode)\.com(?:/\S*)?"
    r"|\b[a-zA-Z0-9][a-zA-Z0-9-]{2,}\.(?:dev|io|me|xyz|app|tech)\b(?:/\S*)?)",
    re.IGNORECASE,
)

_LABEL_LINE_RE = re.compile(
    r"\b(DOB|Date of Birth|Age|Gender|Marital Status|Nationality|Religion|"
    r"Photograph|Photo|Address)\b\s*[:\-]", re.IGNORECASE,
)

_EDUCATION_HEADER_RE = re.compile(r"^\s*education\s*$", re.IGNORECASE)
_BULLET_PREFIX = ("-", "–", "—", "•", "*")


def _is_probable_header(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith(_BULLET_PREFIX) or "|" in s or "·" in s:
        return False
    if s.endswith((".", ",")):
        return False
    words = s.split()
    if len(words) > 5:
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio > 0.9:
        return True
    cap_words = sum(1 for w in words if w[:1].isupper())
    return len(words) <= 4 and cap_words / len(words) >= 0.8


def _find_phones(text: str) -> list[str]:
    found = []
    for m in _PHONE_CANDIDATE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 9 <= len(digits) <= 13:
            found.append(m.group(0))
    return found


def _redact_phones(text: str) -> str:
    def repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[PHONE]" if 9 <= len(digits) <= 13 else m.group(0)

    return _PHONE_CANDIDATE_RE.sub(repl, text)


def _remove_education_section(paragraphs: list[str]) -> list[str]:
    out = []
    i = 0
    while i < len(paragraphs):
        line = paragraphs[i]
        if _EDUCATION_HEADER_RE.match(line.strip()):
            i += 1
            while i < len(paragraphs) and not _is_probable_header(paragraphs[i]):
                i += 1
            continue
        out.append(line)
        i += 1
    return out


def _remove_labelled_lines(paragraphs: list[str]) -> list[str]:
    return [p for p in paragraphs if not _LABEL_LINE_RE.search(p)]


@dataclass
class NameGuess:
    full_name: str | None
    confident: bool
    tokens: list[str] = field(default_factory=list)


def _looks_like_name(line: str) -> bool:
    s = line.strip()
    words = s.split()
    if not (1 <= len(words) <= 4):
        return False
    for w in words:
        core = w.strip(".")
        if not core.isalpha():
            return False
        if not core[0].isupper():
            return False
    return True


def _filename_tokens(filename_stem: str) -> set[str]:
    parts = re.split(r"[_\-\s]+", filename_stem.lower())
    stop = {"cv", "resume", "application", "app"}
    tokens = {p for p in parts if p and p not in stop and not p.isdigit()}
    return tokens


def guess_name(paragraphs: list[str], filename_stem: str) -> NameGuess:
    header = next((p for p in paragraphs[:3] if p.strip()), "")
    if not _looks_like_name(header):
        return NameGuess(full_name=None, confident=False, tokens=[])
    tokens = [w.strip(".") for w in header.strip().split()]
    file_tokens = _filename_tokens(filename_stem)
    if file_tokens:
        overlap = sum(1 for t in tokens if t.lower() in file_tokens)
        confident = overlap >= 1
    else:
        # No name-shaped filename to cross-check against: trust a clean,
        # name-shaped header line on its own.
        confident = True
    return NameGuess(full_name=header.strip(), confident=confident, tokens=tokens)


def _redact_name(text: str, tokens: list[str], full_name: str | None) -> str:
    if full_name:
        text = re.sub(re.escape(full_name), "[CANDIDATE]", text)
    for tok in tokens:
        if len(tok) >= 3:
            text = re.sub(r"\b" + re.escape(tok) + r"\b", "[CANDIDATE]", text, flags=re.IGNORECASE)
    return text


@dataclass
class PiiResult:
    cleaned_text: str | None
    name: str | None
    email: str | None
    phone: str | None
    needs_name: bool
    blocked: bool
    block_reason: str | None
    notes: list[str]


def strip_pii(paragraphs: list[str], filename_stem: str) -> PiiResult:
    notes: list[str] = []
    original_text = "\n".join(paragraphs)

    email_match = EMAIL_RE.search(original_text)
    email = email_match.group(0) if email_match else None
    phones = _find_phones(original_text)
    phone = phones[0] if phones else None

    name_guess = guess_name(paragraphs, filename_stem)
    needs_name = not (name_guess.full_name and name_guess.confident)
    if needs_name:
        notes.append("name not found with confidence — Arjun must type it in")

    working = list(paragraphs)
    working = _remove_education_section(working)
    working = _remove_labelled_lines(working)

    cleaned_lines = []
    for line in working:
        line = EMAIL_RE.sub("[EMAIL]", line)
        line = _redact_phones(line)
        line = URL_RE.sub("[URL]", line)
        line = CITY_RE.sub("[CITY]", line)
        cleaned_lines.append(line)
    cleaned_text = "\n".join(cleaned_lines)

    if not needs_name:
        cleaned_text = _redact_name(cleaned_text, name_guess.tokens, name_guess.full_name)

    blocked, block_reason = _post_check(cleaned_text, name_guess.tokens if not needs_name else [])
    if blocked:
        notes.append(f"post-check found leftover PII: {block_reason}")

    return PiiResult(
        cleaned_text=cleaned_text,
        name=name_guess.full_name if not needs_name else None,
        email=email,
        phone=phone,
        needs_name=needs_name,
        blocked=blocked,
        block_reason=block_reason,
        notes=notes,
    )


def _post_check(cleaned_text: str, name_tokens: list[str]) -> tuple[bool, str | None]:
    if EMAIL_RE.search(cleaned_text):
        return True, "email address"
    if _find_phones(cleaned_text):
        return True, "phone number"
    if URL_RE.search(cleaned_text):
        return True, "url"
    for tok in name_tokens:
        if len(tok) >= 3 and re.search(r"\b" + re.escape(tok) + r"\b", cleaned_text, re.IGNORECASE):
            return True, f"name token '{tok}'"
    return False, None
