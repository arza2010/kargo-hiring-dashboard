"""Step A2: parse a CV file to text, hash it for dedup, and work out the
applied role from its path/filename. No AI, no PII handling here — see pii.py."""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

SUPPORTED_TEXT_EXTS = {".docx"}
SUPPORTED_PDF_EXTS = {".pdf"}
UNSUPPORTED_EXTS = {".doc"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}

ROLE_WORD_RE = {
    "SPM": re.compile(r"(?i)(^|[^a-z])(spm|senior[_\- ]?product[_\- ]?manager|senior)([^a-z]|$)"),
    "PM": re.compile(r"(?i)(^|[^a-z])(pm|product[_\- ]?manager)([^a-z]|$)"),
}


@dataclass
class ParsedFile:
    text: str | None
    paragraphs: list[str]
    content_hash: str
    parse_status: str  # "ok" | "needs_manual_review"
    parse_notes: str | None


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iter_block_items(document):
    """Walk the document body in reading order, paragraphs and tables alike.

    Some CVs put the name/contact block in a table (two-column header), which
    document.paragraphs alone would skip entirely.
    """
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _extract_docx(fileobj) -> list[str]:
    document = docx.Document(fileobj)
    lines: list[str] = []
    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            if block.text.strip():
                lines.append(block.text)
        else:  # Table: flatten row by row, cell by cell, in reading order
            for row in block.rows:
                for cell in row.cells:
                    for line in cell.text.split("\n"):
                        if line.strip():
                            lines.append(line.strip())
    return lines


def _extract_pdf(fileobj) -> list[str]:
    reader = PdfReader(fileobj)
    lines: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        for line in page_text.splitlines():
            if line.strip():
                lines.append(line.strip())
    return lines


def parse_bytes(data: bytes, filename: str) -> ParsedFile:
    """The real parsing entrypoint — works from raw bytes, no filesystem
    needed. This is what makes ingest work the same way whether a CV comes
    from local disk (batch import) or an HTTP upload with no disk at all
    (e.g. a serverless deployment)."""
    chash = content_hash(data)
    ext = Path(filename).suffix.lower()

    if ext in SUPPORTED_TEXT_EXTS:
        try:
            paragraphs = _extract_docx(io.BytesIO(data))
        except Exception as exc:  # corrupt/unreadable docx
            return ParsedFile(None, [], chash, "needs_manual_review", f"docx parse error: {exc}")
        if not paragraphs:
            return ParsedFile(None, [], chash, "needs_manual_review", "docx has no extractable text")
        return ParsedFile("\n".join(paragraphs), paragraphs, chash, "ok", None)

    if ext in SUPPORTED_PDF_EXTS:
        try:
            paragraphs = _extract_pdf(io.BytesIO(data))
        except Exception as exc:
            return ParsedFile(None, [], chash, "needs_manual_review", f"pdf parse error: {exc}")
        if not paragraphs:
            return ParsedFile(
                None, [], chash, "needs_manual_review",
                "pdf has no text layer (likely scanned) — no OCR in v1",
            )
        return ParsedFile("\n".join(paragraphs), paragraphs, chash, "ok", None)

    if ext in UNSUPPORTED_EXTS:
        return ParsedFile(None, [], chash, "needs_manual_review", "legacy .doc format — no parser in v1")

    if ext in IMAGE_EXTS:
        return ParsedFile(None, [], chash, "needs_manual_review", "image file — no OCR in v1")

    return ParsedFile(None, [], chash, "needs_manual_review", f"unsupported file type: {ext}")


def parse_file(path: Path) -> ParsedFile:
    """Convenience wrapper for local-disk CVs (batch import, tests, calibration)."""
    return parse_bytes(path.read_bytes(), path.name)


def detect_role_from_filename(filename: str) -> str:
    """Applied role from the filename alone — the only signal available for
    a direct upload, which has no enclosing folder."""
    stem = Path(filename).stem
    if ROLE_WORD_RE["SPM"].search(stem):
        return "SPM"
    if ROLE_WORD_RE["PM"].search(stem):
        return "PM"
    return "role_unknown"


def detect_role(path: Path) -> str:
    """Applied role from a pm/spm subfolder name, else the filename, else role_unknown."""
    for parent in path.parents:
        name = parent.name.lower()
        if name == "spm":
            return "SPM"
        if name == "pm":
            return "PM"
    return detect_role_from_filename(path.name)
