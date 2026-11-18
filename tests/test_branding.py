from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
RAW_PALETTE_CLASS = re.compile(
    r"\b(?:bg|text|border|ring|from|to|fill|stroke)-"
    r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|brand)-\d+"
    r"|\b(?:bg|text|border)-(?:white|black)\b"
)


def test_the_page_title_and_theme_colours_use_the_brand() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "<title>Health Insurance Chatbot</title>" in html
    assert 'media="(prefers-color-scheme: light)" content="#f4f6fa"' in html
    assert 'media="(prefers-color-scheme: dark)" content="#0d1119"' in html


def test_the_theme_defines_the_indigo_accent_for_light_and_dark() -> None:
    css = (FRONTEND / "src" / "index.css").read_text(encoding="utf-8").lower()
    assert "--accent: light-dark(#2c4bd0, #8fa3ff);" in css
    assert "--color-accent: var(--accent);" in css


def test_components_use_theme_tokens_not_raw_palette_classes_or_the_placeholder_name() -> None:
    offenders: list[str] = []
    for path in (FRONTEND / "src").rglob("*"):
        if path.suffix in {".ts", ".tsx", ".css"} and not path.name.endswith((".test.tsx", ".test.ts")):
            text = path.read_text(encoding="utf-8")
            if RAW_PALETTE_CLASS.search(text) or "Health Assistant" in text:
                offenders.append(str(path.relative_to(FRONTEND)))
    assert offenders == []


def test_the_page_carries_link_preview_tags_with_absolute_urls_to_existing_images() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    image_urls = re.findall(r'property="og:image" content="([^"]+)"', html)
    assert image_urls == ["https://health-insurance-chatbot-demo.hossammostafa.ai/og-image.png"]
    assert '<meta property="og:title" content="Health Insurance Chatbot" />' in html
    assert '<meta name="twitter:card" content="summary_large_image" />' in html
    for name in ("og-image.png", "apple-touch-icon.png"):
        assert (FRONTEND / "public" / name).stat().st_size > 0
