from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE_BREAK = "<!-- pagebreak -->"
NORTHSTAR_NAVY = colors.HexColor("#17324D")
NORTHSTAR_BLUE = colors.HexColor("#2F6B9A")
NORTHSTAR_LIGHT_BLUE = colors.HexColor("#EAF2F8")


class PolicyBuildError(ValueError):
    """Raised when the source corpus cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PolicyManifestEntry:
    document_id: str
    title: str
    source_file: Path
    output_file: Path
    version: str


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self.setAuthor("Northstar Labs")
        self.setCreator("Northstar Labs Policy Publisher")
        self.setSubject("Internal HR policy")

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for page_number, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            self._draw_page_number(page_number, page_count)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_number: int, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#52606D"))
        self.drawCentredString(LETTER[0] / 2, 0.35 * inch, f"Page {page_number} of {page_count}")
        self.restoreState()


def _required_text(record: dict[str, Any], name: str, index: int) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise PolicyBuildError(f"manifest entry {index} requires nonblank {name}")
    return value.strip()


def load_manifest(path: Path) -> list[PolicyManifestEntry]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyBuildError(f"unable to read policy manifest: {path}") from error
    if not isinstance(raw, list) or not raw:
        raise PolicyBuildError("policy manifest must be a nonempty JSON list")

    entries: list[PolicyManifestEntry] = []
    document_ids: set[str] = set()
    output_names: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise PolicyBuildError(f"manifest entry {index} must be an object")
        document_id = _required_text(item, "document_id", index)
        if document_id in document_ids:
            raise PolicyBuildError(f"duplicate document_id: {document_id}")
        document_ids.add(document_id)

        source_name = _required_text(item, "source_file", index)
        source_path = (path.parent / source_name).resolve()
        if not source_path.is_file():
            raise PolicyBuildError(f"{document_id} source file is missing: {source_name}")

        output_name = _required_text(item, "output_file", index)
        output_file = Path(output_name)
        if output_file.suffix.lower() != ".pdf" or output_file.name != output_name:
            raise PolicyBuildError(f"{document_id} output_file must be a PDF filename")
        if output_name in output_names:
            raise PolicyBuildError(f"duplicate output_file: {output_name}")
        output_names.add(output_name)

        entries.append(
            PolicyManifestEntry(
                document_id=document_id,
                title=_required_text(item, "title", index),
                source_file=source_path,
                output_file=output_file,
                version=_required_text(item, "version", index),
            )
        )
    return entries


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PolicyTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=NORTHSTAR_NAVY,
            alignment=TA_CENTER,
            spaceAfter=16,
        ),
        "h2": ParagraphStyle(
            "PolicyHeading2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=NORTHSTAR_NAVY,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "PolicyHeading3",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=NORTHSTAR_BLUE,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "PolicyBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1F2933"),
            spaceAfter=7,
        ),
        "list": ParagraphStyle(
            "PolicyList",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1F2933"),
        ),
    }


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text.strip())
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _parse_table(rows: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    parsed: list[list[Paragraph]] = []
    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        parsed.append([Paragraph(_inline_markdown(cell), styles["body"]) for cell in cells])
    if not parsed:
        raise PolicyBuildError("Markdown table has no data rows")
    column_count = max(len(row) for row in parsed)
    if any(len(row) != column_count for row in parsed):
        raise PolicyBuildError("Markdown table rows must have the same number of columns")
    table = Table(parsed, colWidths=[6.9 * inch / column_count] * column_count, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NORTHSTAR_LIGHT_BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), NORTHSTAR_NAVY),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9FB3C8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _markdown_story(source: str) -> list[Any]:
    styles = _styles()
    story: list[Any] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    list_kind: str | None = None
    table_rows: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            story.append(Paragraph(_inline_markdown(" ".join(paragraph_lines)), styles["body"]))
            paragraph_lines.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if list_items:
            items = [
                ListItem(Paragraph(_inline_markdown(item), styles["list"]), leftIndent=8)
                for item in list_items
            ]
            story.append(
                ListFlowable(
                    items,
                    bulletType="1" if list_kind == "number" else "bullet",
                    leftIndent=20,
                    bulletFontName="Helvetica",
                    bulletFontSize=9,
                    spaceAfter=7,
                )
            )
            list_items.clear()
            list_kind = None

    def flush_table() -> None:
        if table_rows:
            story.append(_parse_table(table_rows, styles))
            story.append(Spacer(1, 8))
            table_rows.clear()

    def flush_blocks() -> None:
        flush_paragraph()
        flush_list()
        flush_table()

    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            flush_blocks()
            continue
        if line == PAGE_BREAK:
            flush_blocks()
            story.append(PageBreak())
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            flush_list()
            table_rows.append(line)
            continue
        flush_table()
        heading = re.fullmatch(r"(#{1,3})\s+(.+)", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            style = "title" if level == 1 else "h2" if level == 2 else "h3"
            story.append(Paragraph(_inline_markdown(heading.group(2)), styles[style]))
            continue
        bullet = re.fullmatch(r"[-*]\s+(.+)", line)
        numbered = re.fullmatch(r"\d+\.\s+(.+)", line)
        if bullet or numbered:
            flush_paragraph()
            kind = "number" if numbered else "bullet"
            if list_kind and list_kind != kind:
                flush_list()
            list_kind = kind
            list_items.append((numbered or bullet).group(1))
            continue
        flush_list()
        paragraph_lines.append(line)
    flush_blocks()
    return story


def _draw_header(
    page_canvas: canvas.Canvas,
    document: SimpleDocTemplate,
    entry: PolicyManifestEntry,
) -> None:
    del document
    page_canvas.saveState()
    page_canvas.setFillColor(NORTHSTAR_NAVY)
    page_canvas.setFont("Helvetica-Bold", 8)
    page_canvas.drawString(0.7 * inch, LETTER[1] - 0.42 * inch, "Northstar Labs")
    page_canvas.setFont("Helvetica", 8)
    page_canvas.drawRightString(
        LETTER[0] - 0.7 * inch,
        LETTER[1] - 0.42 * inch,
        f"{entry.title}  |  Version {entry.version}",
    )
    page_canvas.setStrokeColor(colors.HexColor("#9FB3C8"))
    page_canvas.setLineWidth(0.5)
    page_canvas.line(
        0.7 * inch,
        LETTER[1] - 0.5 * inch,
        LETTER[0] - 0.7 * inch,
        LETTER[1] - 0.5 * inch,
    )
    page_canvas.restoreState()


def build_policy_pdf(entry: PolicyManifestEntry, output_dir: Path) -> Path:
    try:
        source = entry.source_file.read_text(encoding="utf-8")
    except OSError as error:
        message = f"unable to read source for {entry.document_id}: {entry.source_file}"
        raise PolicyBuildError(message) from error
    if not source.strip():
        raise PolicyBuildError(f"source is empty for {entry.document_id}: {entry.source_file}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / entry.output_file.name
    temporary_path = output_path.with_suffix(".pdf.tmp")
    document = SimpleDocTemplate(
        str(temporary_path),
        pagesize=LETTER,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.65 * inch,
        title=entry.title,
        author="Northstar Labs",
        subject="Internal HR policy",
    )
    story = _markdown_story(source)
    if not story:
        raise PolicyBuildError(f"source produced no content for {entry.document_id}")

    def header(page_canvas: canvas.Canvas, doc: SimpleDocTemplate) -> None:
        _draw_header(page_canvas, doc, entry)

    document.build(
        story,
        onFirstPage=header,
        onLaterPages=header,
        canvasmaker=_NumberedCanvas,
    )
    temporary_path.replace(output_path)
    return output_path


def build_corpus(manifest_path: Path, output_dir: Path) -> list[Path]:
    return [build_policy_pdf(entry, output_dir) for entry in load_manifest(manifest_path)]
