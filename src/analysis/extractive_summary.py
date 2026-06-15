"""Small extractive TextRank-style summaries for semantic analyses."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

import numpy as np

TOKEN_RE = re.compile(r"\b[\wÀ-ÿ_]{2,}\b", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(str(text or ""))]


def _pagerank(similarity: np.ndarray, *, iterations: int = 30, damping: float = 0.85) -> np.ndarray:
    n = int(similarity.shape[0]) if similarity.ndim == 2 else 0
    if n <= 0:
        return np.array([], dtype=float)
    matrix = similarity.astype(float).copy()
    np.fill_diagonal(matrix, 0.0)
    row_sums = matrix.sum(axis=1)
    for idx, total in enumerate(row_sums):
        if total > 0:
            matrix[idx, :] = matrix[idx, :] / total
        else:
            matrix[idx, :] = 1.0 / n
    scores = np.ones(n, dtype=float) / n
    teleport = (1.0 - damping) / n
    for _ in range(iterations):
        scores = teleport + damping * matrix.T.dot(scores)
    return scores


def _sentence_similarity(token_sets: Sequence[Set[str]]) -> np.ndarray:
    n = len(token_sets)
    matrix = np.zeros((n, n), dtype=float)
    for i in range(n):
        a = token_sets[i]
        if not a:
            continue
        for j in range(i + 1, n):
            b = token_sets[j]
            if not b:
                continue
            denom = len(a) + len(b)
            value = (2.0 * len(a & b) / denom) if denom else 0.0
            matrix[i, j] = value
            matrix[j, i] = value
    return matrix


def rank_representative_sentences(
    sentences: Sequence[Dict[str, Any]],
    *,
    targets: Sequence[Dict[str, Any]],
    per_target: int = 3,
) -> List[Dict[str, Any]]:
    """Rank literal sentences against target term sets using TextRank plus term overlap."""

    rows = [dict(item or {}) for item in sentences or [] if str((item or {}).get("text", "") or "").strip()]
    if not rows or not targets:
        return []

    token_sets: List[Set[str]] = []
    for row in rows:
        raw_tokens = row.get("tokens")
        if isinstance(raw_tokens, list) and raw_tokens:
            token_sets.append({str(token).lower() for token in raw_tokens if str(token).strip()})
        else:
            token_sets.append(set(_tokens(str(row.get("text", "") or ""))))
    base_scores = _pagerank(_sentence_similarity(token_sets))
    if len(base_scores) != len(rows):
        base_scores = np.ones(len(rows), dtype=float) / max(1, len(rows))

    output: List[Dict[str, Any]] = []
    seen_by_target: set[tuple[str, str, str]] = set()
    for target in targets:
        target_terms = {
            str(term).lower()
            for term in list(target.get("terms", []) or [])
            if str(term).strip()
        }
        if not target_terms:
            continue
        scored: List[tuple[float, int, List[str]]] = []
        for idx, terms in enumerate(token_sets):
            matched = sorted(terms & target_terms)
            if not matched:
                continue
            overlap = len(matched) / max(1, len(target_terms))
            score = float(base_scores[idx]) + overlap
            scored.append((score, idx, matched))
        scored.sort(key=lambda item: (-item[0], item[1]))
        for score, idx, matched in scored[: max(1, int(per_target or 3))]:
            row = rows[idx]
            key = (str(target.get("target_type", "")), str(target.get("target_id", "")), str(row.get("text", "")))
            if key in seen_by_target:
                continue
            seen_by_target.add(key)
            output.append(
                {
                    "target_type": str(target.get("target_type", "")),
                    "target_id": target.get("target_id", ""),
                    "sentence": str(row.get("text", "") or "").strip(),
                    "score": round(float(score), 6),
                    "doc_id": row.get("doc_id", ""),
                    "doc_label": str(row.get("doc_label", "") or ""),
                    "matched_terms": ", ".join(matched),
                }
            )
    return output


def sentences_from_bundle(bundle, *, use_lemmas: bool = True) -> List[Dict[str, Any]]:
    """Build sentence dictionaries from SemanticTextBundle segments."""
    out: List[Dict[str, Any]] = []
    sentence_id = 0
    labels = dict(getattr(bundle, "doc_id_to_label", {}) or {})
    for seg in getattr(bundle, "segments", []) or []:
        raw_text = str(getattr(seg, "text", "") or "").strip()
        if not raw_text:
            continue
        base_tokens = list(getattr(seg, "lemmas" if use_lemmas else "tokens", []) or [])
        for sentence in SENTENCE_SPLIT_RE.split(raw_text):
            sentence = re.sub(r"\s+", " ", str(sentence or "")).strip()
            if not sentence:
                continue
            sentence_id += 1
            out.append(
                {
                    "sentence_id": sentence_id,
                    "text": sentence,
                    "doc_id": int(getattr(seg, "doc_id", 0) or 0),
                    "doc_label": str(labels.get(int(getattr(seg, "doc_id", 0) or 0), f"Doc_{getattr(seg, 'doc_id', 0)}")),
                    "tokens": base_tokens or _tokens(sentence),
                }
            )
    return out


def write_representative_sentences_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> Path:
    """Write representative sentence rows with a stable semicolon-delimited contract."""
    fieldnames = ["target_type", "target_id", "sentence", "score", "doc_id", "doc_label", "matched_terms"]
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows or [])
    return path


def topic_targets_from_model(model_result) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for topic in getattr(model_result, "topic_terms", []) or []:
        terms = [str(term).lower() for term, _weight in list(getattr(topic, "terms", []) or [])[:12]]
        targets.append({"target_type": "topic", "target_id": int(getattr(topic, "topic_id", 0)), "terms": terms})
    return targets


def community_targets_from_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for row in rows or []:
        raw_terms = str(row.get("top_terms", "") or "")
        terms = [part.strip().lower() for part in raw_terms.split(",") if part.strip()]
        targets.append(
            {
                "target_type": "community",
                "target_id": int(row.get("community_id", 0) or 0),
                "terms": terms,
            }
        )
    return targets
