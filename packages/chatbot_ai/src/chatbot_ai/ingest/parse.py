from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter
    from docling_core.types.doc.document import DoclingDocument

FileType = Literal["pdf", "txt", "docx"]
NO_TEXT_MESSAGE = "No extractable text (scanned PDFs are not supported)"
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")


class NoExtractableText(ValueError):
    def __init__(self) -> None:
        super().__init__(NO_TEXT_MESSAGE)


@dataclass(frozen=True)
class TextBlock:
    text: str
    headings: tuple[str, ...]


@dataclass(frozen=True)
class TableBlock:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    headings: tuple[str, ...]


Block = TextBlock | TableBlock


@dataclass
class _HeadingStack:
    entries: list[tuple[int, str]] = field(default_factory=list)

    def push(self, level: int, text: str) -> None:
        while self.entries and self.entries[-1][0] >= level:
            self.entries.pop()
        self.entries.append((level, text))

    def breadcrumb(self) -> tuple[str, ...]:
        return tuple(text for _, text in self.entries)


@cache
def _converter() -> DocumentConverter:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_options = PdfPipelineOptions(do_ocr=False)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)})


def heading_level(text: str, reported_level: int) -> int:
    numbered = NUMBERED_HEADING.match(text)
    if numbered:
        return numbered.group(1).count(".") + 1
    return reported_level


def _cell(value: object) -> str:
    return " ".join(str(value).split())


def blocks_from_docling(document: DoclingDocument) -> list[Block]:
    from docling_core.types.doc.items.table.table import TableItem
    from docling_core.types.doc.items.text import (
        ListItem,
        SectionHeaderItem,
        TextItem,
        TitleItem,
    )

    blocks: list[Block] = []
    stack = _HeadingStack()
    for item, _ in document.iterate_items():
        if isinstance(item, TitleItem):
            continue
        if isinstance(item, SectionHeaderItem):
            text = _cell(item.text)
            if text:
                stack.push(heading_level(text, item.level), text)
        elif isinstance(item, TableItem):
            frame = item.export_to_dataframe(document)
            header = tuple(_cell(c) for c in frame.columns)
            rows = tuple(tuple(_cell(v) for v in row) for row in frame.itertuples(index=False, name=None))
            if header or rows:
                blocks.append(TableBlock(header=header, rows=rows, headings=stack.breadcrumb()))
        elif isinstance(item, TextItem | ListItem):
            text = _cell(item.text)
            if text:
                blocks.append(TextBlock(text=text, headings=stack.breadcrumb()))
    return blocks


def blocks_from_text(raw: str) -> list[Block]:
    paragraphs = re.split(r"\n\s*\n", raw)
    return [TextBlock(text=_cell(p), headings=()) for p in paragraphs if _cell(p)]


def parse_document(path: Path, file_type: FileType) -> list[Block]:
    if file_type == "txt":
        blocks = blocks_from_text(path.read_text(encoding="utf-8", errors="replace"))
    else:
        blocks = blocks_from_docling(_converter().convert(path).document)
    if not blocks:
        raise NoExtractableText()
    return blocks
