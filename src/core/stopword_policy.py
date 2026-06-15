"""Shared lexical stopword policy for user-facing analyses."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Iterable, Optional, Set

from .lexicon import Lexicon, build_portuguese_stopwords_from_lexicon
from .stopword_layers import MANDATORY_EXTRA_STOPWORDS, expand_stopword_entry


CONVERSATIONAL_PT_STOPWORDS: Set[str] = {
    "acho",
    "agora",
    "ai",
    "aí",
    "além",
    "alem",
    "ali",
    "assim",
    "aqui",
    "coisa",
    "coisas",
    "comigo",
    "conosco",
    "contigo",
    "daí",
    "dai",
    "desta",
    "deste",
    "disto",
    "entao",
    "então",
    "enquanto",
    "gente",
    "hoje",
    "la",
    "lá",
    "nao",
    "não",
    "nada",
    "ne",
    "né",
    "porque",
    "pra",
    "pro",
    "sim",
    "tipo",
    "tudo",
    "vosco",
}

_TOKEN_CHARS = re.compile(r"^[\wÀ-ÿ_-]+$", re.UNICODE)

VISUAL_ALLOWLIST: Set[str] = {
    "ia",
    "onu",
    "pt",
    "stf",
    "sus",
    "openai",
    "chatgpt",
}

VISUAL_EXTRA_STOPWORDS: Set[str] = {
    "ainda",
    "si",
}

CHD_N_PREFIX_ARTIFACT_SUFFIXES: Set[str] = {
    "acho",
    "palestrante",
    "terminar",
    "transcrever",
    "voce",
    "voces",
}


def normalize_policy_token(value: object) -> str:
    """Normalize token for policy lookup while preserving underscores."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.strip(".,;:!?\"'()[]{}<>|/\\")
    text = re.sub(r"\s+", " ", text)
    return text


def fold_policy_token(value: object) -> str:
    """Accent-fold normalized token for accent-insensitive comparisons."""
    normalized = normalize_policy_token(value)
    if not normalized:
        return ""
    decomposed = unicodedata.normalize("NFD", normalized)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


@lru_cache(maxsize=1)
def default_stopwords() -> frozenset[str]:
    """Return the bundled PT stopwords plus mandatory conversational noise."""
    words: Set[str] = set()
    for token in build_portuguese_stopwords_from_lexicon():
        words.add(normalize_policy_token(token))
        words.add(fold_policy_token(token))
    for token in MANDATORY_EXTRA_STOPWORDS | CONVERSATIONAL_PT_STOPWORDS:
        for expanded in expand_stopword_entry(token):
            words.add(normalize_policy_token(expanded))
            words.add(fold_policy_token(expanded))
    return frozenset(word for word in words if word)


def expand_extra_stopwords(values: Optional[Iterable[object]]) -> Set[str]:
    """Normalize custom stopwords using the same policy as built-ins."""
    words: Set[str] = set()
    for value in values or []:
        for expanded in expand_stopword_entry(str(value)):
            words.add(normalize_policy_token(expanded))
            words.add(fold_policy_token(expanded))
    return {word for word in words if word}


def is_stopword_like(
    token: object,
    *,
    extra_stopwords: Optional[Iterable[object]] = None,
    lexicon: Optional[Lexicon] = None,
) -> bool:
    """Return True when token should be treated as functional/noise."""
    normalized = normalize_policy_token(token)
    folded = fold_policy_token(normalized)
    if not normalized:
        return True
    if normalized in default_stopwords() or folded in default_stopwords():
        return True
    extras = expand_extra_stopwords(extra_stopwords)
    if normalized in extras or folded in extras:
        return True
    if lexicon is not None and lexicon.is_stopword(normalized):
        return True
    return False


def is_content_term(
    token: object,
    *,
    extra_stopwords: Optional[Iterable[object]] = None,
    lexicon: Optional[Lexicon] = None,
) -> bool:
    """Conservative content-term gate for clouds, semantic maps and keyphrases."""
    normalized = normalize_policy_token(token)
    if len(normalized) <= 1:
        return False
    if not any(ch.isalpha() for ch in normalized):
        return False
    if normalized.isdigit():
        return False
    if not _TOKEN_CHARS.match(normalized):
        return False
    if is_stopword_like(normalized, extra_stopwords=extra_stopwords, lexicon=lexicon):
        return False
    return True


def _visual_parts(token: str) -> list[str]:
    return [part for part in re.split(r"[_-]+", token) if part]


def is_visual_content_term(
    token: object,
    *,
    extra_stopwords: Optional[Iterable[object]] = None,
    lexicon: Optional[Lexicon] = None,
) -> bool:
    """Strict gate for terms displayed in charts, labels and interpretation tables."""
    normalized = normalize_policy_token(token)
    folded = fold_policy_token(normalized)
    if not normalized:
        return False
    if any(ch.isdigit() for ch in normalized):
        return False
    if folded in VISUAL_ALLOWLIST:
        return True
    if len(normalized) < 3:
        return False
    if not any(ch.isalpha() for ch in normalized):
        return False
    if not _TOKEN_CHARS.match(normalized):
        return False
    visual_stops = default_stopwords() | {fold_policy_token(item) for item in VISUAL_EXTRA_STOPWORDS}
    if folded in visual_stops or normalized in visual_stops:
        return False

    parts = _visual_parts(normalized)
    if len(parts) >= 2:
        folded_parts = [fold_policy_token(part) for part in parts]
        if not folded_parts or folded_parts[0] in visual_stops or folded_parts[-1] in visual_stops:
            return False
        content_parts = [
            part for part in folded_parts
            if part in VISUAL_ALLOWLIST or (len(part) >= 3 and part not in visual_stops)
        ]
        return len(content_parts) >= max(1, len(folded_parts) - 1)

    return not is_stopword_like(normalized, extra_stopwords=extra_stopwords, lexicon=lexicon)


def is_chd_visual_content_term(
    token: object,
    *,
    extra_stopwords: Optional[Iterable[object]] = None,
    lexicon: Optional[Lexicon] = None,
) -> bool:
    """Strict visual gate for CHD profiles and AFC labels."""
    normalized = normalize_policy_token(token)
    folded = fold_policy_token(normalized)
    if not is_visual_content_term(normalized, extra_stopwords=extra_stopwords, lexicon=lexicon):
        return False
    if folded.startswith("nao") and len(folded) > 3:
        return False
    if folded.startswith("n") and len(folded) > 4:
        suffix = folded[1:]
        if suffix in default_stopwords() or suffix in CHD_N_PREFIX_ARTIFACT_SUFFIXES:
            return False
    return True
