from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from chatbot_ai.ingest.parse import Block, TableBlock

ChunkKind = Literal["text", "table"]
CHARS_PER_TOKEN = 4
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    headings: tuple[str, ...]
    kind: ChunkKind

    @property
    def breadcrumb(self) -> str:
        return " > ".join(self.headings)

    @property
    def embed_text(self) -> str:
        return f"{self.breadcrumb}\n\n{self.content}" if self.headings else self.content

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)


def content_hash(text: str) -> str:
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _markdown_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def render_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [_markdown_row(header), _markdown_row(["---"] * len(header)), *(_markdown_row(r) for r in rows)]
    return "\n".join(lines)


def _split_long_text(text: str, max_tokens: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for unit in SENTENCE_END.split(text):
        words = unit.split() if estimate_tokens(unit) > max_tokens else [unit]
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and estimate_tokens(candidate) > max_tokens:
                pieces.append(current)
                current = word
            else:
                current = candidate
    if current:
        pieces.append(current)
    return pieces


def _table_pieces(table: TableBlock, max_tokens: int) -> list[str]:
    whole = render_table(table.header, table.rows)
    if estimate_tokens(whole) <= max_tokens or len(table.rows) <= 1:
        return [whole]
    pieces: list[str] = []
    group: list[tuple[str, ...]] = []
    for row in table.rows:
        if group and estimate_tokens(render_table(table.header, [*group, row])) > max_tokens:
            pieces.append(render_table(table.header, group))
            group = []
        group.append(row)
    if group:
        pieces.append(render_table(table.header, group))
    return pieces


def chunk_blocks(blocks: Sequence[Block], max_tokens: int) -> list[Chunk]:
    drafts: list[tuple[str, tuple[str, ...], ChunkKind]] = []
    pending: list[str] = []
    pending_headings: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal pending
        if pending:
            drafts.append(("\n\n".join(pending), pending_headings, "text"))
            pending = []

    for block in blocks:
        if isinstance(block, TableBlock):
            flush()
            drafts.extend((piece, block.headings, "table") for piece in _table_pieces(block, max_tokens))
            continue
        if block.headings != pending_headings:
            flush()
            pending_headings = block.headings
        for piece in _split_long_text(block.text, max_tokens):
            if pending and estimate_tokens("\n\n".join([*pending, piece])) > max_tokens:
                flush()
            pending.append(piece)
    flush()

    return [
        Chunk(index=index, content=content, headings=headings, kind=kind)
        for index, (content, headings, kind) in enumerate(d for d in drafts if d[0].strip())
    ]
