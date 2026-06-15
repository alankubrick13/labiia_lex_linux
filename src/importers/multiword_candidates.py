"""Multiword expression candidates for optional corpus preparation."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from ..core.stopword_policy import default_stopwords, is_stopword_like

TOKEN_PATTERN = re.compile(r"\b[a-zA-ZÀ-ÿ]{2,}\b")
DEFAULT_SELECTION_THRESHOLD = 0.35
MAX_DETECTION_LINES = 30_000
MAX_DETECTION_TOKENS = 250_000
MAX_LINE_TOKENS = 120
COMMON_TRAILING_VERBS = {
    "acontece",
    "acontecem",
    "ajuda",
    "ajudam",
    "aparece",
    "aparecem",
    "cresce",
    "crescem",
    "demonstra",
    "demonstram",
    "faz",
    "fazem",
    "gera",
    "geram",
    "indica",
    "indicam",
    "mostra",
    "mostram",
    "ocorre",
    "ocorrem",
    "permite",
    "permitem",
    "produz",
    "produzem",
    "revela",
    "revelam",
    "sugere",
    "sugerem",
}
WEAK_EDGE_TERMS = {
    "janeiro",
    "fevereiro",
    "marco",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
}
LEADING_ADJECTIVE_SUFFIXES = ("iva", "ivo", "ivas", "ivos", "ial", "iais")
TRAILING_ADJECTIVE_SUFFIXES = (
    "iva",
    "ivo",
    "ivas",
    "ivos",
    "ial",
    "iais",
    "ada",
    "ado",
    "adas",
    "ados",
    "ida",
    "ido",
    "idas",
    "idos",
)


@dataclass(slots=True, kw_only=True)
class MultiwordCandidate:
    """Internal candidate contract returned to the preparation UI."""

    expression: str
    replacement: str
    n_tokens: int
    frequency: int
    is_score: float
    is_norm: float
    doc_count: int = 0
    method: str = "is_index"
    selected_default: bool = False
    context_examples: List[Dict[str, Any]] = field(default_factory=list)


def _iter_content_lines(text: str) -> Iterable[str]:
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("****"):
            continue
        yield line


def _iter_document_lines(text: str) -> Iterable[Tuple[int, str, str]]:
    """Yield content lines with a lightweight document id/label."""
    doc_id = 0
    doc_label = "Documento 1"
    saw_marker = False
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("****"):
            saw_marker = True
            doc_id += 1
            marker = line.lstrip("*").strip()
            doc_label = marker or f"Documento {doc_id}"
            continue
        if not saw_marker and doc_id == 0:
            doc_id = 1
        yield doc_id or 1, doc_label, line


def _is_noise_ngram(tokens: Sequence[str]) -> bool:
    joined = "".join(tokens)
    return not any(ch.isalpha() for ch in joined)


def _has_suffix(token: str, suffixes: Sequence[str]) -> bool:
    return any(str(token or "").endswith(suffix) for suffix in suffixes)


def _is_weak_multiword_candidate(tokens: Sequence[str]) -> bool:
    """Reject very likely sliding-window artifacts without requiring POS tagging."""
    parts = [str(token or "").lower() for token in tokens if str(token or "").strip()]
    if len(parts) < 2:
        return True
    if parts[0] in WEAK_EDGE_TERMS or parts[-1] in WEAK_EDGE_TERMS:
        return True
    if sum(1 for part in parts if is_stopword_like(part)) / max(1, len(parts)) > 0.4:
        return True
    if parts[-1] in COMMON_TRAILING_VERBS:
        return True
    if len(parts) == 2 and _has_suffix(parts[0], LEADING_ADJECTIVE_SUFFIXES):
        return _has_suffix(parts[1], TRAILING_ADJECTIVE_SUFFIXES)
    return False


def _tokenize_line(line: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(str(line or ""))]


def _compact_context(line: str, max_chars: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(line or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _candidate_contexts(
    text: str,
    expressions: Sequence[str],
    *,
    max_examples: int = 3,
) -> Dict[str, Dict[str, Any]]:
    wanted = {str(expr or "").strip(): tuple(_tokenize_line(str(expr or ""))) for expr in expressions}
    wanted = {expr: tokens for expr, tokens in wanted.items() if expr and tokens}
    by_tokens = {tokens: expr for expr, tokens in wanted.items()}
    wanted_lengths = sorted({len(tokens) for tokens in by_tokens})
    doc_ids: Dict[str, set[int]] = defaultdict(set)
    examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if not wanted:
        return {}

    for doc_id, doc_label, line in _iter_document_lines(text):
        line_tokens = _tokenize_line(line)
        if not line_tokens:
            continue
        for n_tokens in wanted_lengths:
            if n_tokens > len(line_tokens):
                continue
            for start in range(0, len(line_tokens) - n_tokens + 1):
                expr = by_tokens.get(tuple(line_tokens[start : start + n_tokens]))
                if not expr:
                    continue
                doc_ids[expr].add(int(doc_id))
                if len(examples[expr]) < max_examples:
                    examples[expr].append(
                        {
                            "doc_id": int(doc_id),
                            "doc_label": str(doc_label or f"Documento {doc_id}"),
                            "context": _compact_context(line),
                        }
                    )

    return {
        expr: {
            "doc_count": len(doc_ids.get(expr, set())),
            "context_examples": list(examples.get(expr, [])),
        }
        for expr in wanted
    }


def _candidate_line_start_counts(text: str, expressions: Sequence[str]) -> Dict[str, int]:
    wanted = {str(expr or "").strip(): tuple(_tokenize_line(str(expr or ""))) for expr in expressions}
    wanted = {expr: tokens for expr, tokens in wanted.items() if expr and tokens}
    by_tokens = {tokens: expr for expr, tokens in wanted.items()}
    counts = {expr: 0 for expr in wanted}
    wanted_lengths = sorted({len(tokens) for tokens in by_tokens})
    if not wanted:
        return counts
    for _doc_id, _doc_label, line in _iter_document_lines(text):
        tokens = _tokenize_line(line)
        if not tokens:
            continue
        for n_tokens in wanted_lengths:
            if n_tokens <= len(tokens):
                expr = by_tokens.get(tuple(tokens[:n_tokens]))
                if expr:
                    counts[expr] += 1
    return counts


def _count_tokens(lines: Sequence[List[str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for tokens in lines:
        counter.update(tokens)
    return counter


def _score_ngram(
    tokens: Tuple[str, ...],
    *,
    frequency: int,
    unigram_counts: Counter[str],
    total_unigrams: int,
    stopwords: set[str],
) -> float:
    lexical_density = sum(1 for token in tokens if token not in stopwords) / max(1, len(tokens))
    rarity = 0.0
    for token in tokens:
        token_freq = max(1, int(unigram_counts.get(token, 1)))
        rarity += math.log1p(total_unigrams / token_freq)
    return float(frequency) * lexical_density * rarity * len(tokens)


def extract_multiword_candidates(
    text: str,
    *,
    top_n: int = 30,
    min_freq: int = 3,
    ngram_max: int = 3,
    min_is_norm: float = DEFAULT_SELECTION_THRESHOLD,
    remove_stopwords: bool = True,
    max_lines: int = MAX_DETECTION_LINES,
    max_tokens: int = MAX_DETECTION_TOKENS,
    max_line_tokens: int = MAX_LINE_TOKENS,
) -> List[Dict[str, Any]]:
    """Extract 2- to 3-word expression candidates with an IS-style score."""

    top_n = min(100, max(1, int(top_n or 30)))
    min_freq = max(1, int(min_freq or 3))
    ngram_max = min(3, max(2, int(ngram_max or 3)))
    min_is_norm = max(0.0, float(min_is_norm if min_is_norm is not None else DEFAULT_SELECTION_THRESHOLD))
    max_lines = max(100, int(max_lines or MAX_DETECTION_LINES))
    max_tokens = max(1_000, int(max_tokens or MAX_DETECTION_TOKENS))
    max_line_tokens = max(20, int(max_line_tokens or MAX_LINE_TOKENS))
    stopwords = set(default_stopwords()) if remove_stopwords else set()

    doc_token_lines: List[Tuple[int, List[str]]] = []
    consumed_tokens = 0
    for idx, (doc_id, _doc_label, line) in enumerate(_iter_document_lines(text), start=1):
        if idx > max_lines or consumed_tokens >= max_tokens:
            break
        tokens = _tokenize_line(line)[:max_line_tokens]
        consumed_tokens += len(tokens)
        doc_token_lines.append((doc_id, tokens))
    doc_token_lines = [(doc_id, tokens) for doc_id, tokens in doc_token_lines if len(tokens) >= 2]
    if not doc_token_lines:
        return []
    token_lines = [tokens for _doc_id, tokens in doc_token_lines]
    total_docs = len({doc_id for doc_id, _tokens in doc_token_lines})

    unigram_counts = _count_tokens(token_lines)
    total_unigrams = sum(unigram_counts.values())
    ngram_counts: Counter[Tuple[str, ...]] = Counter()
    ngram_docs: Dict[Tuple[str, ...], set[int]] = defaultdict(set)
    ngram_line_starts: Counter[Tuple[str, ...]] = Counter()

    for doc_id, tokens in doc_token_lines:
        upper = min(ngram_max, len(tokens))
        for n_tokens in range(2, upper + 1):
            for start in range(0, len(tokens) - n_tokens + 1):
                ngram = tuple(tokens[start : start + n_tokens])
                if "_" in " ".join(ngram):
                    continue
                if remove_stopwords and (ngram[0] in stopwords or ngram[-1] in stopwords):
                    continue
                if _is_noise_ngram(ngram):
                    continue
                if _is_weak_multiword_candidate(ngram):
                    continue
                ngram_counts[ngram] += 1
                ngram_docs[ngram].add(int(doc_id))
                if start == 0:
                    ngram_line_starts[ngram] += 1

    scored: List[tuple[Tuple[str, ...], int, float]] = []
    for ngram, frequency in ngram_counts.items():
        if int(frequency) < min_freq:
            continue
        if total_docs > 1 and len(ngram_docs.get(ngram, set())) < 2:
            continue
        if len(ngram) >= 3 and int(ngram_line_starts.get(ngram, 0) or 0) <= 0:
            continue
        score = _score_ngram(
            ngram,
            frequency=int(frequency),
            unigram_counts=unigram_counts,
            total_unigrams=total_unigrams,
            stopwords=stopwords,
        )
        if score <= 0:
            continue
        scored.append((ngram, int(frequency), score))

    if not scored:
        return []

    max_score = max(score for _, _, score in scored) or 1.0
    candidates: List[MultiwordCandidate] = []
    for ngram, frequency, score in scored:
        expression = " ".join(ngram)
        is_norm = float(score / max_score)
        if is_norm < min_is_norm:
            continue
        candidates.append(
            MultiwordCandidate(
                expression=expression,
                replacement=expression.replace(" ", "_"),
                n_tokens=len(ngram),
                frequency=frequency,
                doc_count=len(ngram_docs.get(ngram, set())),
                is_score=round(float(score), 6),
                is_norm=round(is_norm, 6),
                method="is_index",
                selected_default=frequency >= min_freq and is_norm >= DEFAULT_SELECTION_THRESHOLD,
            )
        )

    candidates.sort(
        key=lambda item: (
            -float(item.is_norm),
            -float(item.is_score),
            -int(item.frequency),
            -int(item.n_tokens),
            item.expression,
        )
    )
    rows = [asdict(item) for item in candidates[:top_n]]
    context_by_expression = _candidate_contexts(text, [str(item["expression"]) for item in rows])
    for row in rows:
        context = context_by_expression.get(str(row.get("expression", "")), {})
        row["doc_count"] = int(context.get("doc_count", 0) or 0)
        row["context_examples"] = list(context.get("context_examples", []) or [])
    return rows


def normalize_multiword_candidate(
    raw: Dict[str, Any],
    *,
    min_freq: int = 2,
    min_is_norm: float = DEFAULT_SELECTION_THRESHOLD,
) -> Dict[str, Any]:
    """Normalize R/Python candidate payload while keeping legacy keys accepted."""

    expression = str(raw.get("expression", "") or "").strip()
    replacement = str(raw.get("replacement", "") or "").strip() or expression.replace(" ", "_")
    n_tokens = int(raw.get("n_tokens", len([part for part in expression.split() if part])) or 0)
    frequency = int(raw.get("frequency", 0) or 0)
    is_score = float(raw.get("is_score", frequency) or 0.0)
    is_norm = float(raw.get("is_norm", 1.0 if frequency > 0 else 0.0) or 0.0)
    selected_default = bool(
        raw.get("selected_default", frequency >= int(min_freq or 2) and is_norm >= float(min_is_norm or 0.0))
    )
    try:
        doc_count = int(raw.get("doc_count", 0) or 0)
    except Exception:
        doc_count = 0
    context_examples = raw.get("context_examples", [])
    if not isinstance(context_examples, list):
        context_examples = []
    return {
        "expression": expression,
        "replacement": replacement,
        "n_tokens": n_tokens,
        "frequency": frequency,
        "doc_count": doc_count,
        "is_score": is_score,
        "is_norm": is_norm,
        "method": str(raw.get("method", "is_index") or "is_index"),
        "selected_default": selected_default,
        "context_examples": context_examples,
    }


def enrich_multiword_candidates_with_context(
    text: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    max_examples: int = 3,
    require_multi_document: bool = True,
) -> List[Dict[str, Any]]:
    """Add doc_count and context examples to candidate rows without changing legacy keys."""
    normalized = [normalize_multiword_candidate(dict(item or {})) for item in candidates or []]
    total_docs = len({doc_id for doc_id, _doc_label, _line in _iter_document_lines(text)})
    context_by_expression = _candidate_contexts(
        text,
        [str(item.get("expression", "")) for item in normalized],
        max_examples=max_examples,
    )
    line_start_counts = _candidate_line_start_counts(text, [str(item.get("expression", "")) for item in normalized])
    enriched: List[Dict[str, Any]] = []
    for item in normalized:
        context = context_by_expression.get(str(item.get("expression", "")), {})
        row = dict(item)
        row["doc_count"] = int(context.get("doc_count", row.get("doc_count", 0)) or 0)
        row["context_examples"] = list(context.get("context_examples", row.get("context_examples", [])) or [])
        if require_multi_document and total_docs > 1 and int(row["doc_count"]) < 2:
            continue
        if _is_weak_multiword_candidate(str(row.get("expression", "")).split()):
            continue
        if int(row.get("n_tokens", 0) or 0) >= 3 and int(line_start_counts.get(str(row.get("expression", "")), 0) or 0) <= 0:
            continue
        enriched.append(row)
    return enriched
