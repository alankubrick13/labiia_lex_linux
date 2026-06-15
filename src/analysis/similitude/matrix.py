"""
Layer 1: Co-occurrence matrix and association indices.

Builds a binary UCE x term matrix, computes the 2x2 contingency tables,
and applies a selected association index to produce the term x term
association matrix.

This replaces the sliding-window approach with UCE-based co-presence,
matching the IRaMuTeQ methodology.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import sparse
try:
    from scipy.stats import binomtest  # scipy >= 1.7
except ImportError:
    binomtest = None  # binomial index unavailable

from .models import ContingencyTables, SimilitudeMatrix

import logging

log = logging.getLogger(__name__)


def _is_valid_term(token: str) -> bool:
    """Apply the same token validity rule used by TextProcessor."""
    from ...core.text_processor import TextProcessor

    normalized = str(token or "").strip().lower()
    return TextProcessor._is_valid_term(normalized)


# ---------------------------------------------------------------------------
# Association index registry
# ---------------------------------------------------------------------------

_ASSOCIATION_REGISTRY: Dict[str, Callable[[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int], np.ndarray]] = {}


def _register(name: str, *aliases: str):
    """Decorator to register an association index function."""
    def decorator(fn):
        _ASSOCIATION_REGISTRY[name.lower()] = fn
        for alias in aliases:
            _ASSOCIATION_REGISTRY[alias.lower()] = fn
        return fn
    return decorator


def available_coefficients() -> List[str]:
    """Return list of available coefficient names."""
    seen = set()
    result = []
    for name, fn in _ASSOCIATION_REGISTRY.items():
        if id(fn) not in seen:
            seen.add(id(fn))
            result.append(name)
    return sorted(result)


# ---------------------------------------------------------------------------
# Association indices (all vectorized, operate on full matrices)
# ---------------------------------------------------------------------------

def _safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """Element-wise division, returning 0 where denominator is 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(den != 0, num / den, 0.0)
    return result


@_register("cooccurrence", "cooc", "raw")
def _cooccurrence(a, b, c, d, n):
    return a.astype(np.float64)


@_register("jaccard")
def _jaccard(a, b, c, d, n):
    return _safe_div(a, a + b + c)


@_register("dice", "sorensen")
def _dice(a, b, c, d, n):
    return _safe_div(2.0 * a, 2.0 * a + b + c)


@_register("ochiai")
def _ochiai(a, b, c, d, n):
    return _safe_div(a, np.sqrt((a + b) * (a + c)))


@_register("phi")
def _phi(a, b, c, d, n):
    num = a * d - b * c
    den = np.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    return _safe_div(num.astype(np.float64), den.astype(np.float64))


@_register("chi2", "chi-squared", "chi_squared")
def _chi_squared(a, b, c, d, n):
    num = n * (a * d - b * c) ** 2
    den = (a + b) * (c + d) * (a + c) * (b + d)
    return _safe_div(num.astype(np.float64), den.astype(np.float64))


@_register("russel", "russel_rao")
def _russel(a, b, c, d, n):
    return _safe_div(a, np.full_like(a, n, dtype=np.float64))


@_register("kulczynski1")
def _kulczynski1(a, b, c, d, n):
    return _safe_div(a, b + c)


@_register("kulczynski2")
def _kulczynski2(a, b, c, d, n):
    return 0.5 * (_safe_div(a, a + b) + _safe_div(a, a + c))


@_register("mountford")
def _mountford(a, b, c, d, n):
    den = a * b + a * c + 2.0 * b * c
    return _safe_div(2.0 * a, den)


@_register("fager")
def _fager(a, b, c, d, n):
    return _safe_div(a, np.sqrt((a + b) * (a + c))) - _safe_div(
        np.ones_like(a, dtype=np.float64), 2.0 * np.sqrt(a + c)
    )


@_register("simple_matching", "sokal_michener")
def _simple_matching(a, b, c, d, n):
    return _safe_div(a + d, np.full_like(a, n, dtype=np.float64))


@_register("hamman")
def _hamman(a, b, c, d, n):
    return _safe_div((a + d) - (b + c), np.full_like(a, n, dtype=np.float64))


@_register("faith")
def _faith(a, b, c, d, n):
    return _safe_div(a + d / 2.0, np.full_like(a, n, dtype=np.float64))


@_register("tanimoto", "rogers_tanimoto")
def _tanimoto(a, b, c, d, n):
    return _safe_div(a + d, a + 2.0 * b + 2.0 * c + d)


@_register("simpson")
def _simpson(a, b, c, d, n):
    return _safe_div(a, np.minimum(a + b, a + c))


@_register("braun_blanquet", "braun-blanquet")
def _braun_blanquet(a, b, c, d, n):
    return _safe_div(a, np.maximum(a + b, a + c))


@_register("mozley", "margalef")
def _mozley(a, b, c, d, n):
    return _safe_div(a * n, (a + b) * (a + c))


@_register("stiles")
def _stiles(a, b, c, d, n):
    num = np.abs(a * d - b * c) - 0.5 * n
    num = np.maximum(num, 0.0)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(
            (den > 0) & (num > 0),
            np.log10(n * num ** 2 / den.astype(np.float64)),
            0.0,
        )
    return result


@_register("michael")
def _michael(a, b, c, d, n):
    num = 4.0 * (a * d - b * c)
    den = (a + d) ** 2 + (b + c) ** 2
    return _safe_div(num.astype(np.float64), den.astype(np.float64))


@_register("yule")
def _yule(a, b, c, d, n):
    num = a * d - b * c
    den = a * d + b * c
    return _safe_div(num.astype(np.float64), den.astype(np.float64))


@_register("yule2")
def _yule2(a, b, c, d, n):
    sa = np.sqrt(a * d)
    sb = np.sqrt(b * c)
    return _safe_div(sa - sb, sa + sb)


@_register("pearson")
def _pearson(a, b, c, d, n):
    # Same as phi for binary data
    return _phi(a, b, c, d, n)


@_register("phi_squared", "phi-squared")
def _phi_sq(a, b, c, d, n):
    p = _phi(a, b, c, d, n)
    return p ** 2


@_register("tschuprow")
def _tschuprow(a, b, c, d, n):
    # For 2x2 tables, Tschuprow's T == |phi|
    return np.abs(_phi(a, b, c, d, n))


@_register("cramer")
def _cramer(a, b, c, d, n):
    # For 2x2 tables, Cramer's V == |phi|
    return np.abs(_phi(a, b, c, d, n))


@_register("percentage", "percentual_coocorrencia")
def _percentage(a, b, c, d, n):
    return _safe_div(a, np.full_like(a, n, dtype=np.float64))


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def build_binary_matrix(
    corpus,
    vocabulary: List[str],
    word_to_idx: Dict[str, int],
    use_lemmas: bool = True,
) -> Tuple[sparse.csr_matrix, List[int]]:
    """
    Build a binary UCE x term matrix from the corpus.

    Each cell is 1 if the term appears in the UCE, 0 otherwise.
    This is the fundamental difference from sliding-window co-occurrence:
    we capture contextual co-presence, not positional proximity.

    Returns:
        (matrix, uce_ids): sparse binary matrix and list of UCE IDs.
    """
    rows = []
    cols = []
    uce_ids = []

    for row_idx, (uce_id, text) in enumerate(corpus.get_uces()):
        uce_ids.append(uce_id)
        words = text.lower().split()

        # Collect unique term indices present in this UCE
        seen_indices: Set[int] = set()
        for word in words:
            word = word.strip(".,;:!?\"'()[]{}«»–—…·•")
            if not word:
                continue

            token = word
            if use_lemmas:
                forme = corpus.formes.get(word)
                if forme is not None and getattr(forme, "lem", None):
                    token = str(forme.lem).strip().lower()

            if not _is_valid_term(token):
                continue

            idx = word_to_idx.get(token)
            if idx is not None:
                seen_indices.add(idx)

        for idx in seen_indices:
            rows.append(row_idx)
            cols.append(idx)

    n_uces = len(uce_ids)
    n_terms = len(vocabulary)

    if not rows:
        return sparse.csr_matrix((n_uces, n_terms), dtype=np.int8), uce_ids

    data = np.ones(len(rows), dtype=np.int8)
    matrix = sparse.csr_matrix(
        (data, (rows, cols)),
        shape=(n_uces, n_terms),
        dtype=np.int8,
    )

    log.info(
        f"Built binary UCE x term matrix: {n_uces} UCEs x {n_terms} terms, "
        f"density={matrix.nnz / max(1, n_uces * n_terms):.4f}"
    )
    return matrix, uce_ids


def compute_contingency(X: sparse.csr_matrix) -> ContingencyTables:
    """
    Compute the 2x2 contingency tables for all term pairs.

    From binary matrix X (n_uces x n_terms):
      a = X^T . X           (both present)
      b = X^T . (1 - X)     (term_i present, term_j absent)
      c = (1 - X)^T . X     (term_i absent, term_j present)
      d = n - a - b - c     (both absent)

    For efficiency with sparse matrices, we compute:
      a = X^T . X
      col_sums = X.sum(axis=0)  -> shape (1, n_terms)
      b[i,j] = col_sums[i] - a[i,j]
      c[i,j] = col_sums[j] - a[i,j]
      d = n - a - b - c

    Returns dense arrays since association index computation needs dense ops.
    """
    n_uces = X.shape[0]

    # a = co-presence count
    Xf = X.astype(np.float64)
    a = (Xf.T @ Xf).toarray()

    # Column sums = term frequencies across UCEs
    col_sums = np.asarray(X.sum(axis=0)).ravel().astype(np.float64)

    # b[i,j] = freq(i) - a[i,j]  (term i present, j absent)
    b = col_sums[:, None] - a

    # c[i,j] = freq(j) - a[i,j]  (term i absent, j present)
    c = col_sums[None, :] - a

    # d = n - a - b - c
    d = float(n_uces) - a - b - c

    # Ensure non-negative (floating point edge cases)
    np.clip(b, 0, None, out=b)
    np.clip(c, 0, None, out=c)
    np.clip(d, 0, None, out=d)

    log.info(f"Computed contingency tables: {X.shape[1]} terms, {n_uces} UCEs")
    return ContingencyTables(a=a, b=b, c=c, d=d, n_uces=n_uces)


def compute_association(
    contingency: ContingencyTables,
    coefficient: str = "cooccurrence",
) -> np.ndarray:
    """
    Compute the association matrix from contingency tables.

    Args:
        contingency: The 2x2 contingency tables.
        coefficient: Name of the association index.

    Returns:
        Symmetric (n_terms, n_terms) float64 array with association values.
        Diagonal is forced to 0.
    """
    key = coefficient.lower().strip()
    fn = _ASSOCIATION_REGISTRY.get(key)
    if fn is None:
        available = ", ".join(sorted(_ASSOCIATION_REGISTRY.keys()))
        raise ValueError(
            f"Unknown association coefficient: {coefficient!r}. "
            f"Available: {available}"
        )

    matrix = fn(
        contingency.a,
        contingency.b,
        contingency.c,
        contingency.d,
        contingency.n_uces,
    )

    # Clean up: force diagonal to 0, replace NaN/Inf
    np.fill_diagonal(matrix, 0.0)
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    # Ensure symmetry (should already be, but floating point)
    matrix = (matrix + matrix.T) / 2.0

    log.info(
        f"Computed association matrix ({coefficient}): "
        f"range=[{matrix.min():.4f}, {matrix.max():.4f}], "
        f"non-zero={np.count_nonzero(matrix)}"
    )
    return matrix


# ---------------------------------------------------------------------------
# High-level function
# ---------------------------------------------------------------------------

def build_similitude_matrix(
    corpus,
    min_freq: int = 3,
    active_only: bool = True,
    use_lemmas: bool = True,
    coefficient: str = "cooccurrence",
    stopword_policy: str = "aggressive_pt",
    selected_words: Optional[List[str]] = None,
    max_terms: int = 0,
) -> SimilitudeMatrix:
    """
    Build the complete association matrix for similitude analysis.

    This is the high-level entry point for Layer 1.

    Args:
        corpus: Corpus object with UCEs, formes, lems.
        min_freq: Minimum term frequency to include.
        active_only: Only include active terms (act=1).
        use_lemmas: Use lemmas instead of raw word forms.
        coefficient: Association index name.
        stopword_policy: Stopword filtering policy.
        selected_words: Optional subset of terms to include.

    Returns:
        SimilitudeMatrix with all computed data.
    """
    # Use TextProcessor to build vocabulary (consistent with existing system)
    from ...core.text_processor import TextProcessor

    processor = TextProcessor(corpus)
    dropped_tokens = _audit_dropped_tokens(
        corpus=corpus,
        processor=processor,
        min_freq=min_freq,
        active_only=active_only,
        use_lemmas=use_lemmas,
        stopword_policy=stopword_policy,
        selected_words=selected_words,
        max_terms=max_terms,
    )
    # When stopword_policy is "legacy" (strict IRaMuTeQ mode), disable
    # both the stopword checker and the English-token filter.  IRaMuTeQ's
    # similitude analysis applies ONLY min_freq + POS act-flag filtering.
    is_strict = (str(stopword_policy).strip().lower() == "legacy")
    processor._build_vocabulary(
        min_freq=min_freq,
        use_lemmas=use_lemmas,
        active_only=active_only,
        stopword_policy=stopword_policy,
        strict_iramuteq_clone=is_strict,
        prefer_portuguese_br=not is_strict,
    )

    vocabulary = list(processor.vocabulary)
    word_to_idx = dict(processor._word_to_idx)

    # Safety: remove any remaining punctuation-only or single-char tokens
    clean_vocab = [w for w in vocabulary if _is_valid_term(w)]
    if len(clean_vocab) < len(vocabulary):
        log.info(
            f"Removed {len(vocabulary) - len(clean_vocab)} non-word tokens from vocabulary"
        )
        vocabulary = clean_vocab
        word_to_idx = {w: i for i, w in enumerate(vocabulary)}

    # Apply max_terms cap: keep highest-frequency terms
    # IRaMuTeQ does NOT cap terms — vocabulary size is controlled by min_freq.
    # Only apply cap when explicitly requested via max_terms parameter.
    effective_max = max_terms if max_terms > 0 else 0

    if effective_max > 0 and len(vocabulary) > effective_max:
        # Get term frequencies from corpus to rank terms
        freq_pairs = []
        for i, word in enumerate(vocabulary):
            forme = corpus.formes.get(word)
            freq = getattr(forme, "freq", 1) if forme else 1
            freq_pairs.append((i, freq))
        freq_pairs.sort(key=lambda x: x[1], reverse=True)
        keep_indices = sorted([fp[0] for fp in freq_pairs[:effective_max]])
        log.info(
            f"Capping vocabulary: {len(vocabulary)} -> {len(keep_indices)} terms "
            f"(max_terms={effective_max})"
        )
        vocabulary = [vocabulary[i] for i in keep_indices]
        word_to_idx = {word: idx for idx, word in enumerate(vocabulary)}

    # Apply word selection filter if specified
    if selected_words:
        selected_set = {w.strip().lower() for w in selected_words if w.strip()}
        if use_lemmas:
            # Resolve forms to lemmas
            resolved = set()
            for w in selected_set:
                forme = corpus.formes.get(w)
                if forme is not None and getattr(forme, "lem", None):
                    resolved.add(str(forme.lem).strip().lower())
                else:
                    resolved.add(w)
            selected_set = resolved

        selected_indices = [
            i for i, word in enumerate(vocabulary)
            if word.lower() in selected_set
        ]
        if len(selected_indices) < 2:
            raise ValueError(
                f"Only {len(selected_indices)} selected words found in vocabulary. "
                f"Need at least 2."
            )
        vocabulary = [vocabulary[i] for i in selected_indices]
        word_to_idx = {word: idx for idx, word in enumerate(vocabulary)}

    # Build binary matrix
    binary_matrix, uce_ids = build_binary_matrix(
        corpus, vocabulary, word_to_idx, use_lemmas=use_lemmas,
    )

    # Term frequencies (from binary matrix: how many UCEs each term appears in)
    term_frequencies = np.asarray(binary_matrix.sum(axis=0)).ravel().astype(np.float64)

    # Compute contingency
    contingency = compute_contingency(binary_matrix)

    # Compute association
    association = compute_association(contingency, coefficient)

    return SimilitudeMatrix(
        association=association,
        vocabulary=vocabulary,
        term_frequencies=term_frequencies,
        coefficient_name=coefficient,
        binary_matrix=binary_matrix,
        contingency=contingency,
        n_uces=binary_matrix.shape[0],
        n_terms=len(vocabulary),
        dropped_tokens=dropped_tokens,
    )


def _audit_dropped_tokens(
    corpus,
    processor,
    min_freq: int,
    active_only: bool,
    use_lemmas: bool,
    stopword_policy: str,
    selected_words: Optional[List[str]],
    max_terms: int,
) -> List[Dict[str, Any]]:
    """Record tokens excluded from the strict vocabulary pipeline with reasons."""
    policy = str(stopword_policy or "aggressive_pt").strip().lower()
    stopword_checker = processor._resolve_stopword_checker(
        stopword_policy=policy,
        strict_stopword_filter=False,
        strict_iramuteq_clone=False,
    )

    selected_set = {
        str(word or "").strip().lower()
        for word in (selected_words or [])
        if str(word or "").strip()
    }
    if selected_set and use_lemmas:
        resolved = set()
        for word in selected_set:
            forme = corpus.formes.get(word)
            if forme is not None and getattr(forme, "lem", None):
                resolved.add(str(forme.lem).strip().lower())
            else:
                resolved.add(word)
        selected_set = resolved

    source = corpus.lems if use_lemmas else corpus.formes
    passed_base_filters: List[Tuple[str, int]] = []
    dropped: List[Dict[str, Any]] = []

    for raw_token, entry in source.items():
        token = str(raw_token or "").strip().lower()
        freq = int(getattr(entry, "freq", 0) or 0)
        act = int(getattr(entry, "act", 1) or 0)
        lemma = str(getattr(entry, "lem", token) or token).strip().lower()

        reason = ""
        if not _is_valid_term(token):
            reason = "invalid_token"
        elif freq < int(min_freq):
            reason = "below_min_freq"
        elif policy == "aggressive_pt" and act != 1:
            reason = "inactive_term"
        elif policy != "aggressive_pt" and active_only and act != 1:
            reason = "inactive_term"
        elif stopword_checker(token):
            reason = "stopword"
        elif processor._is_non_portuguese_english_token(
            token=token,
            lemma=lemma,
            stopword_policy=policy,
            prefer_portuguese_br=True,
        ):
            reason = "non_portuguese_english_token"

        if reason:
            dropped.append({"term": token, "reason": reason, "frequency": freq})
            continue

        passed_base_filters.append((token if not use_lemmas else lemma, freq))

    if not passed_base_filters:
        return dropped

    unique_candidates: Dict[str, int] = {}
    for token, freq in passed_base_filters:
        unique_candidates[token] = max(freq, unique_candidates.get(token, 0))

    ranked_candidates = sorted(
        unique_candidates.items(),
        key=lambda item: (-item[1], item[0]),
    )
    capped_terms = {token for token, _freq in ranked_candidates}
    if max_terms > 0 and len(ranked_candidates) > max_terms:
        capped_terms = {token for token, _freq in ranked_candidates[:max_terms]}

    for token, freq in ranked_candidates:
        if selected_set and token not in selected_set:
            dropped.append({"term": token, "reason": "not_selected", "frequency": freq})
        elif token not in capped_terms:
            dropped.append({"term": token, "reason": "vocabulary_cap", "frequency": freq})

    dropped.sort(key=lambda item: (item["reason"], item["term"]))
    return dropped
