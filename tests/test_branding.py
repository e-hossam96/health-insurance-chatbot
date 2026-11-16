from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
PALETTE = ("#001f3f", "#002d55", "#004b87", "#6a9bd1", "#f0f4f8")


def test_the_page_title_and_theme_colour_use_the_brand() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "<title>Health Insurance Chatbot</title>" in html
    assert 'content="#001F3F"' in html


def test_the_midnight_sky_palette_is_the_theme_with_the_light_blue_accent() -> None:
    css = (FRONTEND / "src" / "index.css").read_text(encoding="utf-8").lower()
    assert all(colour in css for colour in PALETTE)
    assert "--color-brand-400: #6a9bd1" in css


def test_no_component_uses_the_old_blue_classes_or_the_placeholder_name() -> None:
    offenders: list[str] = []
    for path in (FRONTEND / "src").rglob("*"):
        if path.suffix in {".ts", ".tsx", ".css"} and not path.name.endswith(".test.tsx"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"\b(bg|text|border|ring)-blue-\d+", text) or "Health Assistant" in text:
                offenders.append(str(path.relative_to(FRONTEND)))
    assert offenders == []


def test_the_accent_never_carries_white_text() -> None:
    for path in (FRONTEND / "src").rglob("*.tsx"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "bg-brand-400" in line:
                assert "text-white" not in line, f"{path.name}: white on #6A9BD1 is too low contrast"
