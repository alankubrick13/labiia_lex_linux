"""Tests for Specificities analysis and corpus lexical tables."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.analysis.specificities import SpecificitiesAnalysis
from src.core.corpus import Corpus


@pytest.fixture
def corpus_with_metadata():
    corpus = Corpus()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "specificities.db"
        corpus.connect(db_path)

        uci_a = corpus.add_uci("**** *grupo_a *sexo_f")
        uce_a1 = corpus.add_uce(uci_a.ident, 0, "educacao educacao escola politica")
        uce_a2 = corpus.add_uce(uci_a.ident, 1, "educacao saude escola")
        for word in "educacao educacao escola politica".split():
            corpus.add_word(word, uce_id=uce_a1.ident)
        for word in "educacao saude escola".split():
            corpus.add_word(word, uce_id=uce_a2.ident)

        uci_b = corpus.add_uci("**** *grupo_b *sexo_m")
        uce_b1 = corpus.add_uce(uci_b.ident, 0, "seguranca violencia policiamento")
        uce_b2 = corpus.add_uce(uci_b.ident, 1, "seguranca violencia dados")
        for word in "seguranca violencia policiamento".split():
            corpus.add_word(word, uce_id=uce_b1.ident)
        for word in "seguranca violencia dados".split():
            corpus.add_word(word, uce_id=uce_b2.ident)

        yield corpus
        corpus.close()


def test_corpus_make_lexitable_and_gram_table(corpus_with_metadata):
    etoiles = ["*grupo_a", "*grupo_b"]
    lexical_table = corpus_with_metadata.make_lexitable(mineff=1, listet=etoiles, gram=0)
    gram_table = corpus_with_metadata.make_efftype_from_etoiles(etoiles)

    assert lexical_table[0] == [""] + etoiles
    assert len(lexical_table) > 1
    assert gram_table[0] == [""] + etoiles
    assert len(gram_table) > 1


def test_specificities_chi2_python_backend(corpus_with_metadata, tmp_path):
    analysis = SpecificitiesAnalysis(corpus_with_metadata, tmp_path)
    result = analysis.run(
        {
            "index_type": "chi2",
            "min_freq": 1,
            "metadata_tokens": ["*grupo_a", "*grupo_b"],
            "backend": "python",
        }
    )

    assert result.index_type == "chi2"
    assert result.backend_used == "python"
    assert result.scores_csv_path is not None
    assert result.scores_csv_path.exists()
    assert "*grupo_a" in result.scores_by_variable
    assert len(result.scores_by_variable["*grupo_a"]) > 0


def test_specificities_hypergeo_python_backend(corpus_with_metadata, tmp_path):
    analysis = SpecificitiesAnalysis(corpus_with_metadata, tmp_path)
    result = analysis.run(
        {
            "index_type": "hypergeo",
            "min_freq": 1,
            "metadata_tokens": ["*grupo_a", "*grupo_b"],
            "backend": "python",
        }
    )

    assert result.index_type == "hypergeo"
    assert result.relative_csv_path is not None
    assert result.relative_csv_path.exists()
    assert "*grupo_b" in result.scores_by_variable
    assert any(entry.frequency > 0 for entry in result.scores_by_variable["*grupo_b"])


def test_specificities_plot_data_is_emitted(corpus_with_metadata, tmp_path):
    analysis = SpecificitiesAnalysis(corpus_with_metadata, tmp_path)
    result = analysis.run(
        {
            "index_type": "chi2",
            "min_freq": 1,
            "metadata_tokens": ["*grupo_a", "*grupo_b"],
            "backend": "python",
        }
    )

    assert result.specificities_plot_data_path is not None
    assert result.specificities_plot_data_path.exists()
    if result.specificities_plot_path is not None:
        assert result.specificities_plot_path.exists()
