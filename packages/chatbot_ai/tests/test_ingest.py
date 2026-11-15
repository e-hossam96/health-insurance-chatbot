from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from qdrant_client import models

from chatbot_ai.ingest import (
    NO_TEXT_MESSAGE,
    NoExtractableText,
    delete_document,
    ensure_collection,
    ingest,
)
from chatbot_ai.ingest.chunk import (
    Chunk,
    chunk_blocks,
    content_hash,
    estimate_tokens,
    render_table,
)
from chatbot_ai.ingest.index import (
    collection_name,
    document_filter,
    make_qdrant,
    point_id,
)
from chatbot_ai.ingest.parse import (
    Block,
    TableBlock,
    TextBlock,
    heading_level,
    parse_document,
)
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.fake_openai import FakeOpenAI

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "chatbot_ai" / "evals" / "kb_fixtures"
MAX_TOKENS = 512
PAYLOAD_KEYS = {"document_id", "chunk_index", "content", "headings", "kind", "content_hash"}


@pytest.fixture(scope="session")
def policy_blocks() -> list[Block]:
    return parse_document(FIXTURES / "policy_handbook.pdf", "pdf")


@pytest.fixture(scope="session")
def guide_blocks() -> list[Block]:
    return parse_document(FIXTURES / "member_guide.docx", "docx")


@pytest.fixture()
def ingest_settings(fake_openai: FakeOpenAI) -> Iterator[AISettings]:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=f"test-{uuid.uuid4().hex[:10]}")
    yield settings

    async def drop() -> None:
        client = make_qdrant(settings)
        if await client.collection_exists(collection_name(settings)):
            await client.delete_collection(collection_name(settings))
        await client.close()

    asyncio.run(drop())


def _points(settings: AISettings, document_id: int | None = None) -> list[models.Record]:
    async def scroll() -> list[models.Record]:
        client = make_qdrant(settings)
        try:
            records, _ = await client.scroll(
                collection_name(settings),
                scroll_filter=document_filter(document_id) if document_id is not None else None,
                limit=1000,
                with_payload=True,
            )
            return records
        finally:
            await client.close()

    return asyncio.run(scroll())


def _tables(chunks: list[Chunk]) -> list[Chunk]:
    return [c for c in chunks if c.kind == "table"]


def test_G4_small_tables_stay_whole_and_large_tables_repeat_the_header(policy_blocks: list[Block], guide_blocks: list[Block]) -> None:
    split_tables = 0
    for blocks in (policy_blocks, guide_blocks):
        all_chunks = [c.content for c in chunk_blocks(blocks, MAX_TOKENS)]
        for table in (b for b in blocks if isinstance(b, TableBlock)):
            header_lines = render_table(table.header, [])
            pieces = [c.content for c in chunk_blocks([table], MAX_TOKENS)]
            assert all(piece in all_chunks for piece in pieces)
            assert all(piece.startswith(header_lines + "\n") or piece == header_lines for piece in pieces)
            if estimate_tokens(render_table(table.header, table.rows)) <= MAX_TOKENS:
                assert pieces == [render_table(table.header, table.rows)]
            else:
                split_tables += 1
                assert len(pieces) > 1
                assert sum(piece.count("\n") - 1 for piece in pieces) == len(table.rows)
    assert split_tables >= 2, "both fixtures have a table over the budget"
    limits = next(c for c in _tables(chunk_blocks(policy_blocks, MAX_TOKENS)) if "Annual limit" in c.content)
    assert "| Prescription drugs | 20000 EGP | 10% |" in limits.content


def test_G4_chunks_carry_heading_breadcrumbs(policy_blocks: list[Block], guide_blocks: list[Block]) -> None:
    policy = chunk_blocks(policy_blocks, MAX_TOKENS)
    outpatient = next(c for c in policy if "co-pay of 50 EGP" in c.content)
    assert outpatient.headings == ("2 Covered services", "2.1 Outpatient care")
    assert outpatient.embed_text.startswith("2 Covered services > 2.1 Outpatient care\n\n")
    guide = chunk_blocks(guide_blocks, MAX_TOKENS)
    approvals = next(c for c in _tables(guide) if "MRI scan" in c.content)
    assert approvals.headings == ("Pre-authorization", "Services that need approval")


def test_G4_no_empty_chunks_and_the_budget_holds(policy_blocks: list[Block], guide_blocks: list[Block]) -> None:
    for blocks in (policy_blocks, guide_blocks):
        chunks = chunk_blocks(blocks, MAX_TOKENS)
        assert chunks
        assert all(c.content.strip() for c in chunks)
        assert all(estimate_tokens(c.content) <= MAX_TOKENS for c in chunks)
        assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunker_merges_short_paragraphs_under_one_heading_and_splits_long_ones() -> None:
    headings = ("Claims",)
    short = [TextBlock("First rule.", headings), TextBlock("Second rule.", headings), TextBlock("Other section.", ("Appeals",))]
    merged = chunk_blocks(short, MAX_TOKENS)
    assert [c.content for c in merged] == ["First rule.\n\nSecond rule.", "Other section."]
    long_text = " ".join(f"Sentence number {i} explains a rule." for i in range(200))
    pieces = chunk_blocks([TextBlock(long_text, headings)], 64)
    assert len(pieces) > 1
    assert all(estimate_tokens(p.content) <= 64 for p in pieces)
    assert " ".join(p.content for p in pieces) == long_text


def test_numbered_headings_set_the_breadcrumb_depth() -> None:
    assert heading_level("2.1 Outpatient care", 1) == 2
    assert heading_level("4 Claims", 1) == 1
    assert heading_level("Benefit tiers", 3) == 3


def test_content_hash_ignores_case_and_whitespace() -> None:
    assert content_hash("Co-pay  is\n50 EGP") == content_hash("co-pay is 50 egp")
    assert content_hash("a") != content_hash("b")


def test_G1_a_scanned_pdf_fails_with_the_scanned_message() -> None:
    with pytest.raises(NoExtractableText, match=r"No extractable text \(scanned PDFs are not supported\)"):
        parse_document(FIXTURES / "scanned_notice.pdf", "pdf")
    assert NO_TEXT_MESSAGE == "No extractable text (scanned PDFs are not supported)"


def test_G1_empty_txt_fails_and_txt_splits_on_blank_lines(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(NoExtractableText):
        parse_document(empty, "txt")
    notes = tmp_path / "notes.txt"
    notes.write_text("Line one\ncontinues.\n\nSecond paragraph.", encoding="utf-8")
    assert [b.text for b in parse_document(notes, "txt") if isinstance(b, TextBlock)] == ["Line one continues.", "Second paragraph."]


def test_G6_ingest_upserts_deterministic_points_and_reingest_is_idempotent(
    ingest_settings: AISettings, fake_openai: FakeOpenAI, tmp_path: Path
) -> None:
    source = tmp_path / "rules.txt"
    source.write_text("\n\n".join(f"Rule {i}: " + "detail " * 300 for i in range(3)), encoding="utf-8")
    first = ingest(7, str(source), "txt", ingest_settings)
    assert first.chunk_count >= 3 and first.table_chunks == 0
    points = _points(ingest_settings, 7)
    assert sorted(str(p.id) for p in points) == sorted(point_id(7, i) for i in range(first.chunk_count))
    assert all(set(p.payload or {}) == PAYLOAD_KEYS for p in points)

    again = ingest(7, str(source), "txt", ingest_settings)
    assert again.chunk_count == first.chunk_count
    assert sorted(str(p.id) for p in _points(ingest_settings, 7)) == sorted(str(p.id) for p in points)

    source.write_text("Only one short rule now.", encoding="utf-8")
    shrunk = ingest(7, str(source), "txt", ingest_settings)
    assert shrunk.chunk_count == 1
    assert [p.payload["content"] for p in _points(ingest_settings, 7) if p.payload] == ["Only one short rule now."]
    assert fake_openai.embedding_requests[0]["model"] == ingest_settings.ai_embedding_model
    assert fake_openai.embedding_requests[0]["dimensions"] == 64


def test_G4_ingesting_the_docx_fixture_stores_table_chunks_with_payload(ingest_settings: AISettings) -> None:
    result = ingest(11, str(FIXTURES / "member_guide.docx"), "docx", ingest_settings)
    assert result.table_chunks >= 3
    assert result.timings.parse >= 0 and result.timings.upsert >= 0
    tables = [p.payload for p in _points(ingest_settings, 11) if p.payload and p.payload["kind"] == "table"]
    assert len(tables) == result.table_chunks
    assert all(t["headings"] for t in tables)


def test_G9_delete_document_removes_only_that_documents_points(ingest_settings: AISettings, tmp_path: Path) -> None:
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("Alpha rule.", encoding="utf-8")
    second.write_text("Beta rule.", encoding="utf-8")
    ingest(1, str(first), "txt", ingest_settings)
    ingest(2, str(second), "txt", ingest_settings)
    delete_document(1, ingest_settings)
    assert _points(ingest_settings, 1) == []
    assert len(_points(ingest_settings, 2)) == 1


def test_ensure_collection_is_named_after_the_embedding_model_and_is_idempotent(ingest_settings: AISettings) -> None:
    name = ensure_collection(ingest_settings)
    assert name == collection_name(ingest_settings)
    assert name.startswith("kb_test_") and name.endswith("_64")
    assert ensure_collection(ingest_settings) == name
