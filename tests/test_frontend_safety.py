from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"
RAW_HTML_SINKS = (
    "dangerouslySetInnerHTML",
    ".innerHTML =",
    "outerHTML",
    "insertAdjacentHTML",
    "rehype-raw",
    "document.write",
)


def _sources() -> list[Path]:
    return [
        p
        for p in SRC.rglob("*")
        if p.suffix in {".ts", ".tsx"} and ".test." not in p.name
    ]


def test_F17_no_component_writes_raw_html() -> None:
    offenders = [
        f"{p.relative_to(SRC)}: {sink}"
        for p in _sources()
        for sink in RAW_HTML_SINKS
        if sink in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_F17_markdown_renders_only_through_the_html_skipping_component() -> None:
    renderers = [
        p.relative_to(SRC).as_posix()
        for p in _sources()
        if "react-markdown" in p.read_text(encoding="utf-8")
    ]
    assert renderers == ["components/chat/MarkdownContent.tsx"]
    assert "skipHtml" in (
        SRC / "components" / "chat" / "MarkdownContent.tsx"
    ).read_text(encoding="utf-8")
