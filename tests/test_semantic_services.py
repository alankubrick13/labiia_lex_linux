"""
Testes para ``association_metrics.py`` e ``topic_modeling.py``.

Cobre:
- build_cooccurrence_matrix gera matriz esparsa estavel
- compute_ppmi nao gera NaN em caso simples
- rank_association_pairs ordena por PPMI (nao por frequencia bruta)
- LDA produz distribuicoes por documento somando ~1.0
- LDA gera labels curtos de topico
- LDA rejeita corpus insuficiente
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse

from src.analysis.association_metrics import (
    AssociationPair,
    build_cooccurrence_matrix,
    compute_ppmi,
    rank_association_pairs,
)
from src.analysis.topic_modeling import (
    DocTopicRow,
    LDAModelResult,
    TopicTerms,
    generate_topic_labels,
    train_lda,
)
from src.analysis.semantic_contracts import SemanticAnalysisError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_dtm():
    """DTM simples: 5 docs x 4 termos, com padroes de coocorrencia claros."""
    # Termos: [governo, economia, saude, educacao]
    data = np.array([
        [3, 2, 0, 0],  # doc 0: governo+economia
        [2, 3, 0, 0],  # doc 1: governo+economia
        [0, 0, 3, 1],  # doc 2: saude+educacao
        [0, 0, 2, 3],  # doc 3: saude+educacao
        [1, 1, 1, 1],  # doc 4: misto
    ], dtype=np.float64)
    return sparse.csr_matrix(data)


VOCAB = ["governo", "economia", "saude", "educacao"]


# ---------------------------------------------------------------------------
# Tests: association_metrics
# ---------------------------------------------------------------------------

class TestBuildCooccurrenceMatrix:

    def test_produces_sparse_symmetric(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        assert sparse.issparse(cooc)
        assert cooc.shape == (4, 4)
        # Symmetry
        diff = (cooc - cooc.T)
        assert diff.nnz == 0 or np.allclose(diff.toarray(), 0)

    def test_diagonal_is_zero(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        diag = cooc.diagonal()
        assert np.all(diag == 0)

    def test_known_cooccurrence(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        dense = cooc.toarray()
        # governo+economia appear together in docs 0, 1, 4 = 3 times
        assert dense[0, 1] == 3
        # saude+educacao appear together in docs 2, 3, 4 = 3 times
        assert dense[2, 3] == 3

    def test_empty_dtm(self):
        dtm = sparse.csr_matrix((0, 4), dtype=np.float64)
        cooc = build_cooccurrence_matrix(dtm)
        assert cooc.shape == (4, 4)
        assert cooc.nnz == 0


class TestComputePPMI:

    def test_no_nan_in_output(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        ppmi = compute_ppmi(cooc)
        assert not np.any(np.isnan(ppmi.toarray()))

    def test_all_values_non_negative(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        ppmi = compute_ppmi(cooc)
        dense = ppmi.toarray()
        assert np.all(dense >= 0)

    def test_empty_cooc(self):
        cooc = sparse.csr_matrix((4, 4), dtype=np.float64)
        ppmi = compute_ppmi(cooc)
        assert ppmi.nnz == 0


class TestRankAssociationPairs:

    def test_ordered_by_ppmi_not_frequency(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        ppmi = compute_ppmi(cooc)
        pairs = rank_association_pairs(cooc, ppmi, VOCAB, min_cooc=1)
        if len(pairs) >= 2:
            # First pair should have highest PPMI
            assert pairs[0].ppmi >= pairs[1].ppmi

    def test_filters_by_min_cooc(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        ppmi = compute_ppmi(cooc)
        pairs_strict = rank_association_pairs(cooc, ppmi, VOCAB, min_cooc=10)
        assert len(pairs_strict) == 0

    def test_returns_association_pair_dataclass(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        ppmi = compute_ppmi(cooc)
        pairs = rank_association_pairs(cooc, ppmi, VOCAB, min_cooc=1)
        for p in pairs:
            assert isinstance(p, AssociationPair)
            assert isinstance(p.term_a, str)
            assert isinstance(p.ppmi, float)

    def test_top_n_limit(self):
        dtm = _make_test_dtm()
        cooc = build_cooccurrence_matrix(dtm)
        ppmi = compute_ppmi(cooc)
        pairs = rank_association_pairs(cooc, ppmi, VOCAB, min_cooc=1, top_n=2)
        assert len(pairs) <= 2


# ---------------------------------------------------------------------------
# Tests: topic_modeling
# ---------------------------------------------------------------------------

class TestTrainLDA:

    def test_doc_topic_sums_to_one(self):
        dtm = _make_test_dtm()
        result = train_lda(
            dtm,
            vocabulary=VOCAB,
            doc_ids=[0, 1, 2, 3, 4],
            doc_labels=["d0", "d1", "d2", "d3", "d4"],
            n_topics=2,
            n_iter=50,
        )
        assert isinstance(result, LDAModelResult)
        for row in result.doc_topic_rows:
            total = sum(row.topic_probabilities)
            assert abs(total - 1.0) < 0.01, f"Doc {row.doc_id} sums to {total}"

    def test_produces_correct_number_of_topics(self):
        dtm = _make_test_dtm()
        result = train_lda(
            dtm,
            vocabulary=VOCAB,
            doc_ids=[0, 1, 2, 3, 4],
            doc_labels=["d0", "d1", "d2", "d3", "d4"],
            n_topics=2,
        )
        assert result.n_topics == 2
        assert len(result.topic_terms) == 2
        assert len(result.topic_labels) == 2

    def test_topic_labels_contain_terms(self):
        dtm = _make_test_dtm()
        result = train_lda(
            dtm,
            vocabulary=VOCAB,
            doc_ids=[0, 1, 2, 3, 4],
            doc_labels=["d0", "d1", "d2", "d3", "d4"],
            n_topics=2,
        )
        for label in result.topic_labels:
            assert "/" in label or len(label) > 0

    def test_perplexity_is_numeric(self):
        dtm = _make_test_dtm()
        result = train_lda(
            dtm,
            vocabulary=VOCAB,
            doc_ids=[0, 1, 2, 3, 4],
            doc_labels=["d0", "d1", "d2", "d3", "d4"],
            n_topics=2,
        )
        assert result.perplexity is None or isinstance(result.perplexity, float)

    def test_rejects_insufficient_corpus(self):
        # 1 doc x 2 terms - should raise
        dtm = sparse.csr_matrix(np.array([[1, 2]], dtype=np.float64))
        with pytest.raises(SemanticAnalysisError, match="insuficiente"):
            train_lda(
                dtm,
                vocabulary=["a", "b"],
                doc_ids=[0],
                doc_labels=["d0"],
                n_topics=2,
            )

    def test_caps_topics_to_terms(self):
        # 3 docs, 4 terms, request 10 topics - should cap to 4 (vocab size)
        dtm = sparse.csr_matrix(np.array([
            [1, 2, 0, 0],
            [0, 0, 3, 1],
            [1, 1, 1, 1],
        ], dtype=np.float64))
        result = train_lda(
            dtm,
            vocabulary=VOCAB,
            doc_ids=[0, 1, 2],
            doc_labels=["d0", "d1", "d2"],
            n_topics=10,
        )
        assert result.n_topics <= 4

    def test_doc_topic_matrix_shape(self):
        dtm = _make_test_dtm()
        result = train_lda(
            dtm,
            vocabulary=VOCAB,
            doc_ids=[0, 1, 2, 3, 4],
            doc_labels=["d0", "d1", "d2", "d3", "d4"],
            n_topics=2,
        )
        assert result.doc_topic_matrix.shape == (5, 2)


class TestGenerateTopicLabels:

    def test_generates_labels(self):
        topic_terms = [
            TopicTerms(
                topic_id=0,
                label="a / b / c",
                terms=[("a", 0.5), ("b", 0.3), ("c", 0.2)],
            ),
            TopicTerms(
                topic_id=1,
                label="x / y / z",
                terms=[("x", 0.4), ("y", 0.3), ("z", 0.2), ("w", 0.1)],
            ),
        ]
        labels = generate_topic_labels(topic_terms, n_words=2)
        assert len(labels) == 2
        assert "a" in labels[0]
        assert "x" in labels[1]
