from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf

from northstar_rag.schemas import PolicyPage

PAGE_FOOTER_PATTERN = re.compile(r"Page\s+\d+\s+of\s+\d+")
SECTION_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S.+$")


class IngestionError(ValueError):
    """Raised when a policy PDF cannot be loaded completely and safely."""


def _normalize_line(line: str) -> str:
    normalized = unicodedata.normalize("NFKC", line)
    return re.sub(r"[\s\u2000-\u200B\u202F\u205F\u3000]+", " ", normalized).strip()


def normalize_page_text(
    text: str,
    header: str,
    footer_pattern: re.Pattern[str],
) -> str:
    normalized_header = _normalize_line(header)
    kept_lines: list[str] = []
    pending_blank = False
    for raw_line in text.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            pending_blank = bool(kept_lines)
            continue
        if line == normalized_header or footer_pattern.fullmatch(line):
            continue
        if pending_blank and kept_lines and kept_lines[-1] != "":
            kept_lines.append("")
        pending_blank = False
        kept_lines.append(line)
    while kept_lines and kept_lines[-1] == "":
        kept_lines.pop()
    return "\n".join(kept_lines)


def _remove_document_header(text: str, document_title: str) -> str:
    header_pattern = re.compile(
        rf"^{re.escape(document_title)}\s*\|\s*Version\s+\S+$",
        re.IGNORECASE,
    )
    return "\n".join(
        raw_line
        for raw_line in text.splitlines()
        if not header_pattern.fullmatch(_normalize_line(raw_line))
    )


def _first_section(text: str) -> str:
    for line in text.splitlines():
        if SECTION_HEADING_PATTERN.fullmatch(line):
            return line
    return ""


def load_policy_pages(
    pdf_path: Path,
    document_id: str,
    document_title: str,
) -> list[PolicyPage]:
    try:
        with pymupdf.open(pdf_path) as document:
            if len(document) == 0:
                raise IngestionError(f"{pdf_path} contains zero pages")
            pages: list[PolicyPage] = []
            for page_index, page in enumerate(document):
                raw_text = page.get_text("text")
                without_document_header = _remove_document_header(raw_text, document_title)
                cleaned = normalize_page_text(
                    without_document_header,
                    header="Northstar Labs",
                    footer_pattern=PAGE_FOOTER_PATTERN,
                )
                if not cleaned:
                    continue
                pages.append(
                    PolicyPage(
                        document_id=document_id,
                        document_title=document_title,
                        page=page_index + 1,
                        source_path=str(pdf_path),
                        text=cleaned,
                        section=_first_section(cleaned),
                    )
                )
            return pages
    except IngestionError:
        raise
    except Exception as error:
        raise IngestionError(f"unable to read policy PDF: {pdf_path}") from error
