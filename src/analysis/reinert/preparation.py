"""Preparation and matrix building helpers for the Reinert engine."""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence

import numpy as np
from scipy import sparse

from ...core.corpus import Corpus
from ...core.stopword_policy import is_chd_visual_content_term
from ...importers.minimal_text_preparator import (
    MinimalPreparationOptions,
    MinimalTextPreparator,
)
from .models import LexicalMatrix, PreparedCorpus, PreparedUce, ReinertRunConfig


_TOKEN_RE = re.compile(r"[\w_]+", re.UNICODE)


def prepare_corpus(
    corpus: Corpus,
    config: ReinertRunConfig,
    preparator: MinimalTextPreparator | None = None,
) -> PreparedCorpus:
    """Build a prepared corpus from UCE texts already present in `Corpus`."""
    text_lookup = dict(corpus.getalluces())
    preparator = preparator or MinimalTextPreparator()
    options = MinimalPreparationOptions()
    uce_ids = [int(uce.ident) for uci in corpus.ucis for uce in uci.uces]
    use_index = _has_reliable_uce_index(corpus, uce_ids)

    prepared_uces: List[PreparedUce] = []
    row_index = 0
    for uci in corpus.ucis:
        metadata_tokens = tuple(token for token in uci.etoiles[1:] if token)
        for uce in uci.uces:
            raw_text = str(text_lookup.get(uce.ident, "") or "")
            tokens: tuple[str, ...] = ()
            if use_index:
                tokens = tuple(_tokens_from_index(corpus, int(uce.ident)))
            if tokens:
                prepared_text = " ".join(tokens)
            else:
                prepared_text = preparator.prepare_text(raw_text, options=options)
                tokens = tuple(
                    token
                    for token in tokenize(prepared_text)
                    if _is_reinert_content_token(token, corpus=corpus)
                )
            prepared_uces.append(
                PreparedUce(
                    row_index=row_index,
                    uce_id=int(uce.ident),
                    uci_id=int(uci.ident),
                    para_id=int(uce.para),
                    raw_text=raw_text,
                    prepared_text=prepared_text,
                    tokens=tokens,
                    metadata_tokens=metadata_tokens,
                )
            )
            row_index += 1

    return PreparedCorpus(uces=tuple(prepared_uces))


def tokenize(text: str) -> Iterable[str]:
    """Tokenize a prepared text into lexical items kept by the matrix."""
    for token in _TOKEN_RE.findall(str(text or "")):
        lowered = token.lower()
        if not any(ch.isalpha() for ch in lowered):
            continue
        yield lowered


def _has_reliable_uce_index(corpus: Corpus, uce_ids: Sequence[int]) -> bool:
    """Return True when corpus.idformesuces covers enough UCEs to be authoritative."""
    index = getattr(corpus, "idformesuces", None) or {}
    if not index or not uce_ids:
        return False
    expected = {int(uce_id) for uce_id in uce_ids}
    indexed: set[int] = set()
    for uce_counts in index.values():
        for raw_uce_id, count in (uce_counts or {}).items():
            try:
                if int(count or 0) > 0:
                    indexed.add(int(raw_uce_id))
            except Exception:
                continue
    covered = len(expected.intersection(indexed))
    if len(expected) <= 2:
        return covered == len(expected)
    return covered / max(1, len(expected)) >= 0.8


def _tokens_from_index(corpus: Corpus, uce_id: int) -> Iterable[str]:
    """Yield normalized active terms for one UCE from the corpus word index."""
    index = getattr(corpus, "idformesuces", None) or {}
    if not index:
        return
    idformes = corpus.make_idformes()
    for forme_id, uce_counts in sorted(index.items(), key=lambda item: int(item[0])):
        try:
            count = int((uce_counts or {}).get(int(uce_id), 0) or 0)
        except Exception:
            count = 0
        if count <= 0:
            continue
        word = idformes.get(int(forme_id))
        if word is None:
            continue
        if int(getattr(word, "act", 1)) != 1:
            continue
        token = str(getattr(word, "lem", None) or getattr(word, "forme", "") or "").strip().lower()
        if not _is_reinert_content_token(token, corpus=corpus):
            continue
        yield token


def _is_reinert_content_token(token: object, *, corpus: Corpus | None = None) -> bool:
    """Gate terms before they enter the Reinert lexical matrix."""
    return is_chd_visual_content_term(
        token,
        lexicon=getattr(corpus, "lexicon", None) if corpus is not None else None,
    )


def build_lexical_matrix(
    prepared_corpus: PreparedCorpus,
    config: ReinertRunConfig,
) -> LexicalMatrix:
    """Build the canonical binary UCE x term matrix."""
    docfreq_counter: Counter[str] = Counter()
    row_sets: List[set[str]] = []

    for uce in prepared_corpus.uces:
        unique_tokens = {
            token
            for token in uce.tokens
            if token and _is_reinert_content_token(token)
        }
        row_sets.append(unique_tokens)
        docfreq_counter.update(unique_tokens)

    terms = tuple(
        sorted(
            (
                term
                for term, freq in docfreq_counter.items()
                if int(freq) >= max(1, int(config.min_docfreq))
            ),
            key=lambda value: (-docfreq_counter[value], value),
        )
    )
    term_to_index = {term: idx for idx, term in enumerate(terms)}

    rows: List[int] = []
    cols: List[int] = []
    for row_idx, row_terms in enumerate(row_sets):
        for term in sorted(row_terms):
            term_idx = term_to_index.get(term)
            if term_idx is None:
                continue
            rows.append(row_idx)
            cols.append(term_idx)

    data = np.ones(len(rows), dtype=np.int8)
    matrix = sparse.csr_matrix(
        (data, (rows, cols)),
        shape=(len(prepared_corpus.uces), len(terms)),
        dtype=np.int8,
    )
    docfreq = np.asarray(matrix.sum(axis=0)).ravel().astype(int)
    return LexicalMatrix(
        matrix=matrix,
        terms=terms,
        docfreq=docfreq,
        prepared_corpus=prepared_corpus,
    )


def class_term_counts(
    matrix: sparse.csr_matrix,
    row_indices: Sequence[int],
) -> np.ndarray:
    """Return term counts for a row subset."""
    if not row_indices:
        return np.zeros(matrix.shape[1], dtype=float)
    subset = matrix[np.asarray(list(row_indices), dtype=int)]
    return np.asarray(subset.sum(axis=0)).ravel().astype(float)


def metadata_row_lookup(prepared_corpus: PreparedCorpus) -> Dict[str, List[int]]:
    """Map metadata token to the row indices that carry it."""
    lookup: Dict[str, List[int]] = {}
    for uce in prepared_corpus.uces:
        for token in uce.metadata_tokens:
            lookup.setdefault(token, []).append(int(uce.row_index))
    return lookup
