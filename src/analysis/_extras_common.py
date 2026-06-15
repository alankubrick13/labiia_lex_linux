"""Helper utilities for extra analysis modules."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, date
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from ..core.corpus import Corpus
from ..core.lexicon import build_portuguese_stopwords_from_lexicon
from ..core.stopword_policy import is_visual_content_term


TOKEN_PATTERN = re.compile(r"\b[a-zA-ZÀ-ÿ]{3,}\b")
_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
)


ENGLISH_STOPWORDS = {
    "you", "your", "yours", "the", "and", "for", "with", "from", "this",
    "that", "was", "were", "are", "not", "have", "has", "had", "can",
    "could", "will", "would", "shall", "should", "what", "when", "where",
    "which", "who", "whom", "why", "how", "into", "onto", "over", "under",
    "than", "then", "there", "their", "them",
}


@lru_cache(maxsize=1)
def _common_stopwords() -> set[str]:
    """Return cached stopword set shared across extra analyses."""
    words = set(ENGLISH_STOPWORDS)
    words.update(build_portuguese_stopwords_from_lexicon())
    return words


@dataclass
class UciRecord:
    """Flat representation of one UCI for text analyses."""

    uci_id: int
    uci_index: int
    text: str
    metadata: Dict[str, str]
    raw_etoiles: List[str]


def tokenize_text(text: str, remove_stopwords: bool = False) -> List[str]:
    """Tokenize text using alphabetical tokens with accent support."""
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text or "")]
    if not remove_stopwords:
        return tokens
    stopwords = _common_stopwords()
    return [
        token for token in tokens
        if token not in stopwords and is_visual_content_term(token)
    ]


def parse_etoile_token(token: str) -> Optional[Tuple[str, str]]:
    """
    Parse one etoile token into (variable, value).

    Expected format: ``*variavel_valor``.
    """
    clean = str(token or "").strip()
    if not clean:
        return None
    if clean.startswith("*"):
        clean = clean[1:]
    if "_" not in clean:
        return None
    variable, value = clean.split("_", 1)
    variable = variable.strip().lower()
    value = value.strip()
    if not variable or not value:
        return None
    return variable, value


def build_uci_records(corpus: Corpus) -> List[UciRecord]:
    """Build UCI-level text records with metadata tokens parsed."""
    all_uce_texts = {int(uce_id): str(text or "") for uce_id, text in corpus.get_uces()}
    records: List[UciRecord] = []

    for idx, uci in enumerate(corpus.ucis):
        text_parts = [all_uce_texts.get(int(u.ident), "") for u in uci.uces]
        merged = " ".join(part for part in text_parts if part).strip()

        metadata: Dict[str, str] = {}
        raw_etoiles = [str(token) for token in getattr(uci, "etoiles", [])]
        for token in raw_etoiles:
            parsed = parse_etoile_token(token)
            if parsed is None:
                continue
            variable, value = parsed
            metadata[variable] = value

        records.append(
            UciRecord(
                uci_id=int(getattr(uci, "ident", idx)),
                uci_index=idx,
                text=merged,
                metadata=metadata,
                raw_etoiles=raw_etoiles,
            )
        )

    return records


def detect_metadata_values(records: List[UciRecord]) -> Dict[str, List[str]]:
    """Return metadata variable -> sorted unique values."""
    mapping: Dict[str, set[str]] = {}
    for record in records:
        for variable, value in record.metadata.items():
            mapping.setdefault(variable, set()).add(value)
    return {key: sorted(values) for key, values in mapping.items()}


def most_common_variable(records: List[UciRecord]) -> Optional[str]:
    """Return most frequent metadata variable among records."""
    counter: Counter[str] = Counter()
    for record in records:
        counter.update(record.metadata.keys())
    return counter.most_common(1)[0][0] if counter else None


def parse_date_from_metadata(record: UciRecord) -> Optional[date]:
    """
    Attempt to parse a date from metadata values.

    Supported formats include ``YYYY-MM-DD`` and ``DD/MM/YYYY``.
    """
    for value in record.metadata.values():
        text = str(value).strip()
        if not text:
            continue
        for pattern in _DATE_PATTERNS:
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
    return None
