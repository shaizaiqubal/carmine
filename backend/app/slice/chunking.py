from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start: int
    end: int


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _sentences(text: str) -> list[tuple[int, int]]:
    spans = []
    for match in re.finditer(r".*?(?:[.!?]+(?=\s|$)|$)", text, re.S):
        if match.start() == match.end():
            continue
        start, end = match.span()
        if text[start:end].strip():
            spans.append((start, end))
    return spans


def chunk_text(text: str, min_words: int = 200, max_words: int = 300, overlap_words: int = 30) -> list[TextChunk]:
    """Group whole sentences into bounded chunks and retain exact text offsets."""
    if not text.strip():
        return []
    spans = _sentences(text)
    if not spans:
        return [TextChunk(0, text, 0, len(text))]
    chunks: list[TextChunk] = []
    cursor = 0
    index = 0
    while cursor < len(spans):
        start_i = cursor
        end_i = cursor
        words = 0
        while end_i < len(spans):
            sentence_words = _word_count(text[spans[end_i][0]:spans[end_i][1]])
            if end_i > start_i and words + sentence_words > max_words:
                break
            words += sentence_words
            end_i += 1
            if words >= min_words:
                break
        if end_i == start_i:
            end_i += 1
        start, end = spans[start_i][0], spans[end_i - 1][1]
        chunks.append(TextChunk(index, text[start:end], start, end))
        if end_i >= len(spans):
            break
        overlap_start = end_i - 1
        overlap = 0
        while overlap_start > start_i and overlap < overlap_words:
            overlap += _word_count(text[spans[overlap_start][0]:spans[overlap_start][1]])
            overlap_start -= 1
        cursor = max(start_i + 1, overlap_start + 1)
        index += 1
    return chunks


def whitespace_normalize(text: str) -> str:
    return " ".join(text.split())


def quote_in_passages(quote: str, passages: list[str]) -> bool:
    normalized_quote = whitespace_normalize(quote)
    return bool(normalized_quote) and any(normalized_quote in whitespace_normalize(passage) for passage in passages)
