from __future__ import annotations

import re
from enum import StrEnum


class LanguageCode(StrEnum):
    arabic = "ar"
    english = "en"
    other = "other"


class ReplyLanguage(StrEnum):
    modern_standard_arabic = "language_arabic"
    american_english = "language_english"


REPLY_LANGUAGE_FOR: dict[LanguageCode, ReplyLanguage] = {
    LanguageCode.arabic: ReplyLanguage.modern_standard_arabic,
    LanguageCode.english: ReplyLanguage.american_english,
    LanguageCode.other: ReplyLanguage.american_english,
}

LATIN_LETTER = re.compile(r"[A-Za-z]")
ARABIC_LETTER = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def reply_language(language: LanguageCode) -> ReplyLanguage:
    return REPLY_LANGUAGE_FOR[language]


def display_language(language: LanguageCode) -> LanguageCode:
    return LanguageCode.arabic if language is LanguageCode.arabic else LanguageCode.english


def script_language(text: str) -> LanguageCode:
    return LanguageCode.arabic if ARABIC_LETTER.search(text) else LanguageCode.english


ARABIC_SHARE_FOR_ARABIC = 0.4


def written_language(text: str) -> LanguageCode:
    # database names stay in Latin letters, so an Arabic reply can still hold many of them
    arabic = len(ARABIC_LETTER.findall(text))
    letters = arabic + len(LATIN_LETTER.findall(text))
    return LanguageCode.arabic if letters and arabic / letters >= ARABIC_SHARE_FOR_ARABIC else LanguageCode.english
