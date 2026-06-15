"""Unit tests for concordance/KWIC analysis."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.analysis.concordancer import Concordancer, ConcordancerError
from src.core.corpus import Corpus


@pytest.fixture
def corpus_for_concordance():
    corpus = Corpus()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "concordance.db"
        corpus.connect(db_path)

        uci1 = corpus.add_uci("**** *grupo_a *sexo_f")
        corpus.add_uce(uci1.ident, 0, "A pesquisa qualitativa avançou no grupo A.")
        corpus.add_uce(uci1.ident, 1, "Outro trecho com pesquisa e método.")

        uci2 = corpus.add_uci("**** *grupo_b *sexo_m")
        corpus.add_uce(uci2.ident, 0, "No grupo B, a análise estatística foi destaque.")
        corpus.add_uce(uci2.ident, 1, "Pesquisa quantitativa e análise de dados.")

        yield corpus
        corpus.close()


def test_search_word_returns_kwic_contexts(corpus_for_concordance):
    concordancer = Concordancer(corpus_for_concordance)
    result = concordancer.search("pesquisa", context_size=20)

    assert result.query == "pesquisa"
    assert result.occurrences >= 3
    assert len(result.contexts) == result.occurrences
    assert any("grupo" in ctx.metadata for ctx in result.contexts)
    assert any(ctx.keyword.lower() == "pesquisa" for ctx in result.contexts)


def test_search_regex_returns_matches(corpus_for_concordance):
    concordancer = Concordancer(corpus_for_concordance)
    result = concordancer.search_regex(r"an[aá]lise", context_size=18)

    assert result.occurrences >= 2
    assert any("análise" in ctx.keyword.lower() for ctx in result.contexts)


def test_word_distribution_aggregates_metadata(corpus_for_concordance):
    concordancer = Concordancer(corpus_for_concordance)
    distribution = concordancer.get_word_distribution("pesquisa")

    assert distribution
    # Pesquisa aparece em UCIs com ambos grupos no fixture
    assert "grupo_a" in distribution
    assert "grupo_b" in distribution


def test_invalid_regex_raises_friendly_error(corpus_for_concordance):
    concordancer = Concordancer(corpus_for_concordance)
    with pytest.raises(ConcordancerError) as exc_info:
        concordancer.search_regex(r"(pesquisa", context_size=20)

    message = str(exc_info.value)
    assert "O que aconteceu:" in message
    assert "Por que aconteceu:" in message
    assert "Como resolver:" in message
