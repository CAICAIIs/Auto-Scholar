import re

from backend.constants import (
    HEDGING_PATTERNS_EN,
    HEDGING_PATTERNS_ZH,
    PASSIVE_PATTERN_EN,
    PASSIVE_PATTERN_ZH,
)
from backend.evaluation.citation_metrics import CITATION_PATTERN, NORMALIZED_CITATION_PATTERN
from backend.evaluation.schemas import AcademicStyleResult
from backend.schemas import DraftOutput

SENTENCE_PATTERN_EN = re.compile(r"[.!?]+")
SENTENCE_PATTERN_ZH = re.compile(r"[。！？]+")


def _split_sentences(text: str, language: str) -> list[str]:
    pattern = SENTENCE_PATTERN_ZH if language == "zh" else SENTENCE_PATTERN_EN
    sentences = pattern.split(text)
    return [s.strip() for s in sentences if s.strip()]


def _count_hedging(text: str, language: str) -> int:
    patterns = HEDGING_PATTERNS_ZH if language == "zh" else HEDGING_PATTERNS_EN
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, text, re.IGNORECASE))
    return count


def _count_passive(text: str, language: str) -> int:
    pattern = PASSIVE_PATTERN_ZH if language == "zh" else PASSIVE_PATTERN_EN
    return len(re.findall(pattern, text, re.IGNORECASE))


def _count_words(text: str, language: str) -> int:
    if language == "zh":
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        return len(chinese_chars)
    else:
        words = re.findall(r"\b\w+\b", text)
        return len(words)


def calculate_academic_style(draft: DraftOutput, language: str = "en") -> AcademicStyleResult:
    full_text = "\n".join(section.content for section in draft.sections)

    sentences = _split_sentences(full_text, language)
    total_sentences = len(sentences)

    hedging_sentences = 0
    passive_sentences = 0

    for sentence in sentences:
        if _count_hedging(sentence, language) > 0:
            hedging_sentences += 1
        if _count_passive(sentence, language) > 0:
            passive_sentences += 1

    total_words = _count_words(full_text, language)
    citation_count = len(CITATION_PATTERN.findall(full_text))
    if citation_count == 0:
        citation_count = len(NORMALIZED_CITATION_PATTERN.findall(full_text))

    return AcademicStyleResult(
        total_sentences=total_sentences,
        hedging_count=hedging_sentences,
        passive_count=passive_sentences,
        total_words=total_words,
        citation_count=citation_count,
    )
