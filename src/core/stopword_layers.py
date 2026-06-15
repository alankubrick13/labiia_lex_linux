"""Stopword layer utilities for global/project/session customization."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable, List, Sequence, Set

from .config_manager import ConfigManager


GLOBAL_STOPWORDS_KEY = "custom_stopwords_global"

# User-requested mandatory extras for mixed PT/EN academic corpora.
MANDATORY_EXTRA_STOPWORDS = {
    "et",
    "al",
    "et al",
    "the",
    "off",
}

_SPLIT_PATTERN = re.compile(r"[,\n;\t]+")
_SPACE_PATTERN = re.compile(r"\s+")


def normalize_stopword(value: str) -> str:
    """Normalize a stopword entry preserving multiword expressions."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = _SPACE_PATTERN.sub(" ", text)
    return text


def expand_stopword_entry(value: str) -> Set[str]:
    """
    Expand one stopword entry into token-level terms.

    Multiword values (e.g., "et al") produce both:
    - full phrase "et al"
    - token parts "et", "al"
    """
    normalized = normalize_stopword(value)
    if not normalized:
        return set()
    expanded = {normalized}
    if " " in normalized:
        expanded.update(part for part in normalized.split(" ") if part)
    return expanded


def parse_stopwords_text(content: str) -> List[str]:
    """Parse plain text/CSV-ish stopword content into normalized unique entries."""
    unique: List[str] = []
    seen: Set[str] = set()
    for raw in _SPLIT_PATTERN.split(str(content or "")):
        token = normalize_stopword(raw)
        if not token or token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique


def parse_stopwords_file(path: Path) -> List[str]:
    """Load stopwords from .txt/.csv file with one or many terms per line."""
    payload = Path(path).read_text(encoding="utf-8", errors="replace")
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        values: List[str] = []
        reader = csv.reader(io.StringIO(payload))
        for row in reader:
            for item in row:
                values.append(item)
        return parse_stopwords_text("\n".join(values))
    return parse_stopwords_text(payload)


def merge_stopword_layers(
    *,
    global_words: Sequence[str] | None = None,
    project_words: Sequence[str] | None = None,
    session_words: Sequence[str] | None = None,
) -> List[str]:
    """Merge mandatory + global + project + session layers as unique normalized list."""
    merged: List[str] = []
    seen: Set[str] = set()

    def _push(raw_value: str) -> None:
        for token in expand_stopword_entry(raw_value):
            if token and token not in seen:
                seen.add(token)
                merged.append(token)

    for required in sorted(MANDATORY_EXTRA_STOPWORDS):
        _push(required)
    for source in (global_words or []):
        _push(str(source))
    for source in (project_words or []):
        _push(str(source))
    for source in (session_words or []):
        _push(str(source))
    return merged


def get_global_custom_stopwords(config: ConfigManager) -> List[str]:
    """Return normalized global custom stopwords from config."""
    raw = config.get(GLOBAL_STOPWORDS_KEY, [])
    if not isinstance(raw, list):
        return []
    return merge_stopword_layers(global_words=raw, project_words=[], session_words=[])[
        len(MANDATORY_EXTRA_STOPWORDS):
    ]


def set_global_custom_stopwords(config: ConfigManager, words: Iterable[str]) -> List[str]:
    """Persist normalized global stopwords and return stored list."""
    normalized = []
    seen: Set[str] = set()
    for raw in words or []:
        token = normalize_stopword(str(raw))
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    config.set(GLOBAL_STOPWORDS_KEY, normalized)
    return normalized
