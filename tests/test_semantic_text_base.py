"""
Testes para ``semantic_text_base.py``.

Cobre:
- SparseMatrixBundle constroi word_to_idx automaticamente
- SemanticTextBundle.from_corpus com mock de Corpus
- Propriedades (n_documents, n_segments, n_features)
- Iteradores (iter_sentences, get_document_tokens, get_segment_tokens)
- DTM e UCE-DTM sao csr_matrix
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy import sparse

from src.analysis.semantic_contracts import SemanticAnalysisError
from src.analysis.semantic_text_base import (
    SemanticDocument,
    SemanticSegment,
    SemanticTextBundle,
    SparseMatrixBundle,
    _extract_transcript_speaker_tokens,
    _find_parent_doc_id,
    _strip_transcript_artifacts,
)


# ---------------------------------------------------------------------------
# SparseMatrixBundle
# ---------------------------------------------------------------------------

class TestSparseMatrixBundle:

    def test_word_to_idx_auto_built(self):
        vocab = ["alfa", "beta", "gama"]
        mat = sparse.csr_matrix(np.eye(3, 3))
        bundle = SparseMatrixBundle(
            matrix=mat,
            vocabulary=vocab,
            row_ids=[0, 1, 2],
        )
        assert bundle.word_to_idx == {"alfa": 0, "beta": 1, "gama": 2}

    def test_explicit_word_to_idx_preserved(self):
        vocab = ["x", "y"]
        mat = sparse.csr_matrix(np.eye(2, 2))
        w2i = {"x": 0, "y": 1}
        bundle = SparseMatrixBundle(
            matrix=mat,
            vocabulary=vocab,
            row_ids=[0, 1],
            word_to_idx=w2i,
        )
        assert bundle.word_to_idx is w2i

    def test_matrix_is_csr(self):
        mat = sparse.csr_matrix(np.zeros((2, 3)))
        bundle = SparseMatrixBundle(
            matrix=mat,
            vocabulary=["a", "b", "c"],
            row_ids=[0, 1],
        )
        assert sparse.issparse(bundle.matrix)
        assert isinstance(bundle.matrix, sparse.csr_matrix)


# ---------------------------------------------------------------------------
# SemanticDocument and SemanticSegment
# ---------------------------------------------------------------------------

class TestSemanticRecords:

    def test_document_creation(self):
        doc = SemanticDocument(
            doc_id=1,
            label="Doc_1",
            tokens=["hello", "world"],
            lemmas=["hello", "world"],
        )
        assert doc.doc_id == 1
        assert doc.date is None
        assert doc.metadata == {}

    def test_segment_creation(self):
        seg = SemanticSegment(
            uce_id=10,
            doc_id=1,
            text="hello world",
            tokens=["hello", "world"],
            lemmas=["hello", "world"],
        )
        assert seg.uce_id == 10
        assert seg.doc_id == 1


# ---------------------------------------------------------------------------
# SemanticTextBundle — unit tests with mocks
# ---------------------------------------------------------------------------

def _make_mock_corpus(n_ucis: int = 2, n_uces_per_uci: int = 3) -> MagicMock:
    """Build a minimal mock Corpus for unit testing."""
    corpus = MagicMock()

    # Mock Word objects in formes
    formes = {}
    for word in ("governo", "aprovou", "medida", "teste", "analise"):
        mock_word = MagicMock()
        mock_word.forme = word
        mock_word.lem = word  # simplified: form == lemma
        mock_word.freq = 5
        mock_word.act = 1
        formes[word] = mock_word
    corpus.formes = formes

    # Mock lems
    lems = {}
    for word in ("governo", "aprovou", "medida", "teste", "analise"):
        mock_lem = MagicMock()
        mock_lem.lem = word
        mock_lem.freq = 5
        mock_lem.act = 1
        lems[word] = mock_lem
    corpus.lems = lems

    # Mock UCIs with UCEs
    ucis = []
    uce_counter = 0
    for uci_idx in range(n_ucis):
        uci = MagicMock()
        uci.ident = uci_idx
        uci.paras = {"title": f"Doc_{uci_idx}"}
        uces = []
        for _ in range(n_uces_per_uci):
            uce = MagicMock()
            uce.ident = uce_counter
            uces.append(uce)
            uce_counter += 1
        uci.uces = uces
        ucis.append(uci)
    corpus.ucis = ucis

    # get_uces returns all UCE texts
    all_uces = []
    for uci in ucis:
        for uce in uci.uces:
            all_uces.append((int(uce.ident), "governo aprovou medida teste analise"))
    corpus.get_uces = MagicMock(return_value=all_uces)

    # getconcorde returns texts for given UCE IDs
    def _getconcorde(ids):
        return [(uid, "governo aprovou medida teste analise") for uid in ids]
    corpus.getconcorde = MagicMock(side_effect=_getconcorde)

    # lexicon and parametres
    corpus.lexicon = None
    corpus.parametres = {}

    return corpus


class TestSemanticTextBundle:

    def test_from_corpus_null_raises(self):
        with pytest.raises(SemanticAnalysisError, match="Corpus nulo"):
            SemanticTextBundle.from_corpus(None)

    def test_from_corpus_produces_documents_and_segments(self):
        corpus = _make_mock_corpus(n_ucis=2, n_uces_per_uci=3)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        assert bundle.n_documents == 2
        assert bundle.n_segments == 6
        assert bundle.n_features > 0

    def test_dtm_and_uce_dtm_are_csr(self):
        corpus = _make_mock_corpus(n_ucis=2, n_uces_per_uci=2)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        assert bundle.doc_term_matrix is not None
        assert isinstance(bundle.doc_term_matrix.matrix, sparse.csr_matrix)
        assert bundle.uce_term_matrix is not None
        assert isinstance(bundle.uce_term_matrix.matrix, sparse.csr_matrix)

    def test_iter_sentences(self):
        corpus = _make_mock_corpus(n_ucis=1, n_uces_per_uci=2)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        sentences = list(bundle.iter_sentences())
        assert len(sentences) == 2
        for uce_id, text in sentences:
            assert isinstance(uce_id, int)
            assert isinstance(text, str)

    def test_get_document_tokens_lemmas(self):
        corpus = _make_mock_corpus(n_ucis=2, n_uces_per_uci=1)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=True,
            max_features=100,
        )
        tokens = bundle.get_document_tokens(use_lemmas=True)
        assert len(tokens) == 2
        for doc_tokens in tokens:
            assert isinstance(doc_tokens, list)
            assert len(doc_tokens) > 0

    def test_get_segment_tokens(self):
        corpus = _make_mock_corpus(n_ucis=1, n_uces_per_uci=3)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        tokens = bundle.get_segment_tokens(use_lemmas=False)
        assert len(tokens) == 3

    def test_has_temporal_data_false_by_default(self):
        corpus = _make_mock_corpus(n_ucis=2, n_uces_per_uci=1)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        assert bundle.has_temporal_data() is False

    def test_doc_id_to_label(self):
        corpus = _make_mock_corpus(n_ucis=3, n_uces_per_uci=1)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        assert len(bundle.doc_id_to_label) == 3
        for doc_id, label in bundle.doc_id_to_label.items():
            assert isinstance(doc_id, int)
            assert isinstance(label, str)

    def test_strips_transcript_labels_from_segments(self):
        corpus = _make_mock_corpus(n_ucis=1, n_uces_per_uci=1)
        corpus.get_uces = MagicMock(
            return_value=[(0, "00:01:20 ANDRÉ MARINHO (ENTREVISTADOR) O que você entende por democracia?")]
        )

        def _getconcorde(ids):
            return [
                (0, "00:01:20 ANDRÉ MARINHO (ENTREVISTADOR) O que você entende por democracia?")
            ]

        corpus.getconcorde = MagicMock(side_effect=_getconcorde)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=1,
            use_lemmas=False,
            max_features=100,
        )
        assert bundle.segments[0].text == "O que você entende por democracia?"
        assert "andré" not in bundle.segments[0].tokens


# ---------------------------------------------------------------------------
# _find_parent_doc_id helper
# ---------------------------------------------------------------------------

class TestFindParentDocId:

    def test_finds_parent(self):
        corpus = _make_mock_corpus(n_ucis=2, n_uces_per_uci=2)
        # UCE 0 should belong to UCI 0
        assert _find_parent_doc_id(corpus, 0) == 0
        # UCE 2 should belong to UCI 1
        assert _find_parent_doc_id(corpus, 2) == 1

    def test_returns_zero_for_unknown(self):
        corpus = _make_mock_corpus(n_ucis=1, n_uces_per_uci=1)
        assert _find_parent_doc_id(corpus, 999) == 0


class TestTranscriptCleaning:

    def test_strip_transcript_artifacts_removes_timestamp_and_role(self):
        raw = "00:01:20 ANDRÉ MARINHO (ENTREVISTADOR) O que você entende por democracia?"
        assert _strip_transcript_artifacts(raw) == "O que você entende por democracia?"

    def test_strip_transcript_artifacts_keeps_normal_text(self):
        raw = "Democracia depende de participação popular."
        assert _strip_transcript_artifacts(raw) == raw

    def test_extract_transcript_speaker_tokens(self):
        raw = "00:01:20 ANDRÉ MARINHO (ENTREVISTADOR) O que você entende por democracia?"
        tokens = _extract_transcript_speaker_tokens(raw)
        assert "andré" in tokens
        assert "marinho" in tokens
