from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from northstar_rag.schemas import ChunkRecord, PolicyPage

SECTION_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S.+$")
TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class _Section:
    heading: str
    body: str


def _token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def stable_chunk_id(document_id: str, page: int, section: str, sequence: int) -> str:
    normalized_section = " ".join(section.split())
    provenance = f"{document_id.strip()}|{page}|{normalized_section}|{sequence}"
    return hashlib.sha256(provenance.encode("utf-8")).hexdigest()[:20]


def _sections_on_page(page: PolicyPage) -> list[_Section]:
    sections: list[_Section] = []
    heading = page.document_title
    body_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(body_lines).strip()
        if body:
            sections.append(_Section(heading=heading, body=body))
        body_lines.clear()

    for line in page.text.splitlines():
        stripped = line.strip()
        if SECTION_HEADING_PATTERN.fullmatch(stripped):
            flush()
            heading = stripped
            continue
        body_lines.append(stripped)
    flush()
    return sections


def _split_section(
    section: _Section,
    *,
    target_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    heading_tokens = _token_count(section.heading)
    content_target = target_tokens - heading_tokens
    if content_target < 1:
        raise ValueError("target_tokens is too small for the section heading")
    if _token_count(section.body) <= content_target:
        return [section.body]
    content_overlap = min(overlap_tokens, content_target - 1)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=content_target,
        chunk_overlap=content_overlap,
        length_function=_token_count,
        separators=["\n\n", "\n", " ", ""],
        keep_separator=False,
        strip_whitespace=True,
    )
    return splitter.split_text(section.body)


def chunk_pages(
    pages: Sequence[PolicyPage],
    target_tokens: int = 600,
    overlap_tokens: int = 90,
) -> list[ChunkRecord]:
    if target_tokens < 1:
        raise ValueError("target_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be nonnegative and smaller than target_tokens")

    chunks: list[ChunkRecord] = []
    for page in pages:
        sequence = 0
        for section in _sections_on_page(page):
            for body in _split_section(
                section,
                target_tokens=target_tokens,
                overlap_tokens=overlap_tokens,
            ):
                text = f"{section.heading}\n{body}".strip()
                chunks.append(
                    ChunkRecord(
                        chunk_id=stable_chunk_id(
                            page.document_id,
                            page.page,
                            section.heading,
                            sequence,
                        ),
                        document_id=page.document_id,
                        document_title=page.document_title,
                        section=section.heading,
                        page=page.page,
                        source_path=page.source_path,
                        text=text,
                    )
                )
                sequence += 1
    return chunks
