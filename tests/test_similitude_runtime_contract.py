from __future__ import annotations

from unittest.mock import MagicMock

from src.analysis.similitude import SimilitudeAnalysis
from src.analysis.similitude.matrix import build_similitude_matrix
from src.core.corpus import Corpus
from src.core.text_processor import TextProcessor


def test_text_processor_exposes_term_validity_helper_for_similitude() -> None:
    assert hasattr(TextProcessor, "_is_valid_term")
    assert TextProcessor._is_valid_term("humano") is True
    assert TextProcessor._is_valid_term(".") is False
    assert TextProcessor._is_valid_term("a") is False


def test_strict_similitude_preserves_manual_selection_and_aggressive_filter(tmp_path) -> None:
    analysis = SimilitudeAnalysis(MagicMock(), tmp_path)

    config = analysis._build_config(
        {
            "strict_iramuteq_style": True,
            "stopword_policy": "aggressive_pt",
            "selected_words": ["vacina", "governo"],
        }
    )

    assert config.stopword_policy == "aggressive_pt"
    assert config.selected_words == ["vacina", "governo"]


def test_similitude_matrix_applies_selected_words_after_stopword_filter(tmp_path) -> None:
    corpus = Corpus({"ucemethod": 0, "ucesize": 100})
    db_path = tmp_path / "similitude.db"
    corpus.connect(db_path)
    try:
        corpus.add_uci("**** *doc_1")
        corpus.add_uci("**** *doc_2")
        corpus.add_uce(0, 0, "vacina governo então coisa vacina governo")
        corpus.add_uce(1, 0, "vacina governo assim porque vacina governo")
        for token in ["vacina", "governo", "então", "coisa", "assim", "porque"]:
            corpus.add_word(token, gram="noun", lem=token)

        matrix = build_similitude_matrix(
            corpus=corpus,
            min_freq=1,
            active_only=True,
            use_lemmas=True,
            coefficient="cooccurrence",
            stopword_policy="aggressive_pt",
            selected_words=["vacina", "governo", "então", "coisa"],
        )

        assert matrix.vocabulary == ["governo", "vacina"]
        assert {"então", "coisa", "assim", "porque"}.isdisjoint(matrix.vocabulary)
    finally:
        corpus.close()
