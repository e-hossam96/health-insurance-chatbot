from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from scripts.generate_kb_fixtures import (
    DEFAULT_OUTPUT,
    MEMBER_GUIDE,
    POLICY_HANDBOOK,
    Table,
    render_all,
    write_fixtures,
)

PAGE_OBJECT = re.compile(rb"/Type /Page ")
SHOWN_TEXT = re.compile(rb"\(((?:\\.|[^\\)])*)\) Tj")


def _pdf_pages(pdf: bytes) -> list[list[str]]:
    streams = re.findall(rb"stream\n(.*?)\nendstream", pdf, re.DOTALL)
    return [[m.decode("latin-1").replace("\\(", "(").replace("\\)", ")") for m in SHOWN_TEXT.findall(s)] for s in streams]


def _tables(document_blocks: tuple[object, ...]) -> list[Table]:
    return [b for b in document_blocks if isinstance(b, Table)]


def test_generation_is_deterministic(tmp_path: Path) -> None:
    first = render_all()
    second = render_all()
    assert first == second
    written = write_fixtures(tmp_path)
    assert sorted(p.name for p in written) == sorted(first)


def test_committed_fixtures_match_the_generator() -> None:
    for name, content in render_all().items():
        committed = DEFAULT_OUTPUT / name
        assert committed.exists(), f"{name} missing: run scripts/generate_kb_fixtures.py"
        assert committed.read_bytes() == content, f"{name} is stale: run scripts/generate_kb_fixtures.py"


def test_policy_pdf_has_headings_tables_and_repeats_the_header_on_every_page() -> None:
    pdf = render_all()[POLICY_HANDBOOK.file_name]
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    pages = _pdf_pages(pdf)
    assert len(PAGE_OBJECT.findall(pdf)) == len(pages) >= 3
    all_text = [t for page in pages for t in page]
    for heading in ("2.1 Outpatient care", "2.3 Annual coverage limits", "5 Network clinic fee schedule"):
        assert heading in all_text
    small, large = _tables(POLICY_HANDBOOK.blocks)
    assert len(small.rows) <= 6 and len(large.rows) >= 50
    pages_with_fee_rows = [page for page in pages if any(cell.endswith(" EGP") and "Clinic" in " ".join(page) for cell in page)]
    assert len(pages_with_fee_rows) >= 2
    for page in pages_with_fee_rows[1:]:
        assert page[: len(large.header)] == list(large.header)


def test_member_guide_docx_has_heading_styles_and_two_tables() -> None:
    archive = zipfile.ZipFile(io.BytesIO(render_all()[MEMBER_GUIDE.file_name]))
    assert {"word/document.xml", "word/styles.xml", "[Content_Types].xml"} <= set(archive.namelist())
    document = archive.read("word/document.xml").decode("utf-8")
    assert document.count("<w:tbl>") == len(_tables(MEMBER_GUIDE.blocks)) == 2
    assert '<w:pStyle w:val="Heading1"/>' in document and '<w:pStyle w:val="Heading2"/>' in document
    assert document.count("<w:tblHeader/>") == 2
    styles = archive.read("word/styles.xml").decode("utf-8")
    assert 'w:styleId="Heading1"><w:name w:val="heading 1"/>' in styles


def test_scanned_pdf_has_a_page_but_no_text() -> None:
    pdf = render_all()["scanned_notice.pdf"]
    assert len(PAGE_OBJECT.findall(pdf)) == 1
    assert b" Tj" not in pdf and b"BT " not in pdf
