from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from northstar_rag.schemas import Citation, SearchHit

CITATION_PATTERN = re.compile(r"\[(?P<title>[^\[\]\n]+?),\s+p\.\s+(?P<page>[1-9]\d*)\]")
BRACKET_PATTERN = re.compile(r"\[[^\]\n]*\]")
CITATION_MARKER_PATTERN = re.compile(r"\bp\.", re.IGNORECASE)
DANGLING_CLOSE_PATTERN = re.compile(r"[^\[\]\n]+?,\s+p\.\s+[^\n]*\]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CitationValidation:
    valid: bool
    citations: tuple[Citation, ...]
    reason: str | None = None


def parse_citations(answer: str) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[tuple[str, int]] = set()
    for match in CITATION_PATTERN.finditer(answer):
        title = match.group("title").strip()
        page = int(match.group("page"))
        key = (title, page)
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(document_title=title, page=page))
    return citations


def _has_malformed_citation(answer: str) -> bool:
    bracket_depth = 0
    for character in answer:
        if character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth -= 1
        if bracket_depth < 0:
            return True
    if bracket_depth != 0:
        return True

    valid_spans = {match.span() for match in CITATION_PATTERN.finditer(answer)}
    for bracket in BRACKET_PATTERN.finditer(answer):
        if CITATION_MARKER_PATTERN.search(bracket.group()) and bracket.span() not in valid_spans:
            return True

    without_valid = CITATION_PATTERN.sub("", answer)
    unmatched_open = without_valid.rsplit("[", maxsplit=1)
    if len(unmatched_open) == 2 and CITATION_MARKER_PATTERN.search(unmatched_open[1]):
        return True
    return bool(DANGLING_CLOSE_PATTERN.search(without_valid))


def validate_grounded_answer(
    answer: str,
    evidence: Sequence[SearchHit],
) -> CitationValidation:
    if _has_malformed_citation(answer):
        return CitationValidation(
            valid=False,
            citations=(),
            reason="The answer contains a malformed policy citation.",
        )

    parsed = parse_citations(answer)
    if not parsed:
        return CitationValidation(
            valid=False,
            citations=(),
            reason="A grounded answer requires at least one policy citation.",
        )

    evidence_by_location: dict[tuple[str, int], str] = {}
    for hit in evidence:
        location = (hit.chunk.document_title, hit.chunk.page)
        evidence_by_location.setdefault(location, hit.chunk.chunk_id)

    validated: list[Citation] = []
    for citation in parsed:
        location = (citation.document_title, citation.page)
        chunk_id = evidence_by_location.get(location)
        if chunk_id is None:
            return CitationValidation(
                valid=False,
                citations=(),
                reason=(
                    "The answer cites a document title or page that was not retrieved: "
                    f"{citation.document_title}, p. {citation.page}."
                ),
            )
        validated.append(
            Citation(
                document_title=citation.document_title,
                page=citation.page,
                chunk_id=chunk_id,
            )
        )
    return CitationValidation(valid=True, citations=tuple(validated))
