"""Utilities for optional bigram-to-compound suggestions during import."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from ..core.lexicon import build_portuguese_stopwords_from_lexicon
from .multiword_candidates import extract_multiword_candidates

TOKEN_PATTERN = re.compile(r"\b[a-zA-ZÀ-ÿ]{3,}\b")
WORD_SPAN_PATTERN = re.compile(r"[A-Za-zÀ-ÿ_]+")


def _iter_content_lines(text: str) -> Iterable[str]:
    """Yield corpus lines excluding IRaMuTeQ command markers."""
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("****"):
            continue
        yield line


def extract_bigram_candidates(
    text: str,
    *,
    top_n: int = 20,
    min_freq: int = 2,
    remove_stopwords: bool = True,
) -> List[Dict[str, Any]]:
    """
    Extract top frequent bigrams as optional compound suggestions.

    Returns dictionaries with keys:
    - expression: "palavra um"
    - replacement: "palavra_um"
    - frequency: int
    """
    return extract_multiword_candidates(
        text,
        top_n=top_n,
        min_freq=min_freq,
        ngram_max=2,
        min_is_norm=0.0,
        remove_stopwords=remove_stopwords,
    )


def selected_bigrams_to_expressions(selected: Iterable[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Normalize selected multiword payload into CorpusCleaner custom expressions."""
    results: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for item in selected or []:
        if not isinstance(item, dict):
            continue
        expression = str(item.get("expression", "")).strip().lower()
        replacement = str(item.get("replacement", "")).strip().lower()
        if not expression or not replacement:
            continue
        parts = [part for part in expression.split() if part]
        if len(parts) not in {2, 3} or "_" not in replacement:
            continue
        pair = (expression, replacement)
        if pair in seen:
            continue
        seen.add(pair)
        results.append(pair)
    return results


def _fold_token(value: str) -> str:
    """Normalize token for case/accent-insensitive matching."""
    normalized = unicodedata.normalize("NFD", str(value or ""))
    normalized = "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn"
    )
    return normalized.lower().strip()


def apply_selected_bigrams_to_text(
    text: str,
    expressions: Sequence[Tuple[str, str]],
    *,
    allow_stopword_bridge: bool = True,
) -> Tuple[str, int]:
    """
    Force-apply selected 2- or 3-token unions over cleaned corpus text.

    This pass is intentionally conservative:
    - skips IRaMuTeQ command lines (`**** ...`);
    - replaces only selected pairs (no dictionary-wide side effects);
    - supports optional bridge of one stopword (e.g. "sistema de wayfinding").
    """
    patterns: Dict[Tuple[str, ...], str] = {}
    for expr, repl in expressions or []:
        parts = [p for p in str(expr or "").split() if p]
        replacement = str(repl or "").strip().lower()
        if len(parts) not in {2, 3} or not replacement or "_" not in replacement:
            continue
        key = tuple(_fold_token(part) for part in parts)
        if any(not part for part in key):
            continue
        patterns[key] = replacement

    if not patterns:
        return str(text or ""), 0

    max_pattern_len = max(len(key) for key in patterns)
    stopwords = build_portuguese_stopwords_from_lexicon() if allow_stopword_bridge else set()
    total_replacements = 0
    out_lines: List[str] = []

    for raw_line in str(text or "").splitlines():
        line = str(raw_line)
        if line.strip().startswith("****"):
            out_lines.append(line)
            continue

        matches = list(WORD_SPAN_PATTERN.finditer(line))
        if len(matches) < 2:
            out_lines.append(line)
            continue

        spans: List[Tuple[int, int, str]] = []
        i = 0
        while i < len(matches):
            current = matches[i]
            replaced = False

            for size in range(min(max_pattern_len, len(matches) - i), 1, -1):
                current_matches = matches[i : i + size]
                key = tuple(_fold_token(match.group(0)) for match in current_matches)
                repl = patterns.get(key)
                if repl:
                    spans.append((current_matches[0].start(), current_matches[-1].end(), repl))
                    total_replacements += 1
                    i += size
                    replaced = True
                    break

            if replaced:
                continue

            token_i = _fold_token(current.group(0))

            if (not replaced) and allow_stopword_bridge and i + 2 < len(matches):
                mid = matches[i + 1]
                nxt2 = matches[i + 2]
                token_mid = _fold_token(mid.group(0))
                token_k = _fold_token(nxt2.group(0))
                if token_mid in stopwords:
                    repl = patterns.get((token_i, token_k))
                    if repl:
                        spans.append((current.start(), nxt2.end(), repl))
                        total_replacements += 1
                        i += 3
                        replaced = True

            if not replaced:
                i += 1

        if not spans:
            out_lines.append(line)
            continue

        rebuilt: List[str] = []
        cursor = 0
        for start, end, repl in spans:
            if start < cursor:
                continue
            rebuilt.append(line[cursor:start])
            rebuilt.append(repl)
            cursor = end
        rebuilt.append(line[cursor:])
        out_lines.append("".join(rebuilt))

    return "\n".join(out_lines), total_replacements
