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

ARABIC_LETTER = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def reply_language(language: LanguageCode) -> ReplyLanguage:
    return REPLY_LANGUAGE_FOR[language]


def script_language(text: str) -> LanguageCode:
    return LanguageCode.arabic if ARABIC_LETTER.search(text) else LanguageCode.english
