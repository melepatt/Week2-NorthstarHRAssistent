from __future__ import annotations

from pathlib import Path

import pymupdf


def write_ingestion_fixture(path: Path) -> Path:
    document = pymupdf.open()

    first = document.new_page()
    first.insert_text(
        (54, 36),
        "Northstar Labs\nFixture Policy | Version 2026.10-draft",
        fontsize=8,
    )
    first.insert_text(
        (54, 90),
        "1. Eligibility\nFull-time employees work at least 30 hours.\n"
        "4.1 Numbered clauses remain intact.",
        fontsize=11,
    )
    first.insert_text((270, 760), "Page 1 of 3", fontsize=8)

    second = document.new_page()
    second.insert_text(
        (54, 36),
        "Northstar Labs\nFixture Policy | Version 2026.10-draft",
        fontsize=8,
    )
    second.insert_text((270, 760), "Page 2 of 3", fontsize=8)

    third = document.new_page()
    third.insert_text(
        (54, 36),
        "Northstar Labs\nFixture Policy | Version 2026.10-draft",
        fontsize=8,
    )
    third.insert_text(
        (54, 90),
        "2. Leave\nEmployees receive twenty paid time off days.",
        fontsize=11,
    )
    third.insert_text((270, 760), "Page 3 of 3", fontsize=8)

    document.save(path)
    document.close()
    return path
