"""Tests for lexical dictionary integration with Corpus/TextProcessor."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from src.core.corpus import Corpus
from src.core.lexicon import Lexicon, resolve_lexicon_path, resolve_expression_path
from src.core.text_processor import TextProcessor


@pytest.fixture
def tiny_lexicon_file(tmp_path: Path) -> Path:
    path = tmp_path / "mini_lexicon.txt"
    path.write_text(
        "abacateiros\tabacateiro\tnom\n"
        "abacateiro\tabacateiro\tnom\n"
        "os\to\tart_def\n",
        encoding="utf-8",
    )
    return path


def test_lexicon_load_lookup_and_active_types(tiny_lexicon_file: Path):
    lexicon = Lexicon()
    loaded = lexicon.load(tiny_lexicon_file)

    assert loaded == 3
    assert lexicon.lookup("abacateiros") == ("abacateiro", "nom")
    assert lexicon.lookup("inexistente") is None
    assert lexicon.is_active("nom") is True
    assert lexicon.is_active("art_def") is False


def test_resolve_lexicon_path_uses_expected_file():
    path = resolve_lexicon_path("portuguese")
    assert path.name == "lexique_pt.txt"


def test_lexicon_load_expressions_supports_tab_and_multi_space(tmp_path: Path):
    path = tmp_path / "expressions.txt"
    path.write_text(
        "inteligência artificial\tinteligencia_artificial\n"
        "redes sociais  redes_sociais\n",
        encoding="utf-8",
    )
    lexicon = Lexicon()
    expressions = lexicon.load_expressions(path)

    assert expressions["inteligência artificial"] == "inteligencia_artificial"
    assert expressions["redes sociais"] == "redes_sociais"


def test_resolve_expression_path_points_to_portuguese_dictionary():
    path = resolve_expression_path("portuguese")
    assert path.name == "expression_pt.txt"


def test_corpus_uses_lexicon_for_lemma_gram_and_activity(tiny_lexicon_file: Path):
    lexicon = Lexicon()
    lexicon.load(tiny_lexicon_file)
    corpus = Corpus(lexicon=lexicon)

    corpus.add_uci("**** *doc_1")
    corpus.add_uce(0, 0, "abacateiros os")
    corpus.add_word("abacateiros", uce_id=0)
    corpus.add_word("os", uce_id=0)

    assert corpus.formes["abacateiros"].lem == "abacateiro"
    assert corpus.formes["abacateiros"].gram == "nom"
    assert corpus.formes["abacateiros"].act == 1
    assert corpus.formes["os"].act == 2
    assert corpus.getlemuces("abacateiro") == [0]
    assert corpus.getlemuceseff("abacateiro") == {0: 1}


def test_dtm_use_lemmas_groups_word_forms(tiny_lexicon_file: Path):
    lexicon = Lexicon()
    lexicon.load(tiny_lexicon_file)
    corpus = Corpus(lexicon=lexicon)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "lexicon_corpus.db"
        corpus.connect(db_path)
        corpus.add_uci("**** *doc_1")
        uce = corpus.add_uce(0, 0, "abacateiros abacateiro")
        corpus.add_word("abacateiros", uce_id=uce.ident)
        corpus.add_word("abacateiro", uce_id=uce.ident)

        processor = TextProcessor(corpus)
        dtm = processor.build_dtm(min_freq=1, use_lemmas=True, active_only=True)
        assert "abacateiro" in processor.vocabulary
        lemma_idx = processor.vocabulary.index("abacateiro")
        assert int(dtm.toarray()[0, lemma_idx]) == 2
        corpus.close()


def test_lookup_fallback_maps_portuguese_plural_to_singular_when_variant_is_missing(tmp_path: Path):
    path = tmp_path / "mini_plural_lexicon.txt"
    path.write_text(
        "digital\tdigital\tnom\n"
        "código\tcódigo\tnom\n",
        encoding="utf-8",
    )
    lexicon = Lexicon()
    lexicon.load(path)

    assert lexicon.lookup("digitais") == ("digital", "nom")
    assert lexicon.lookup("códigos") == ("código", "nom")


def test_corpus_and_cooccurrence_use_lemma_fallback_for_plural_forms(tmp_path: Path):
    path = tmp_path / "mini_plural_lexicon.txt"
    path.write_text(
        "digital\tdigital\tnom\n"
        "código\tcódigo\tnom\n",
        encoding="utf-8",
    )
    lexicon = Lexicon()
    lexicon.load(path)
    corpus = Corpus(lexicon=lexicon)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            db_path = Path(tmpdir) / "lexicon_corpus.db"
            corpus.connect(db_path)
            corpus.add_uci("**** *doc_1")
            uce = corpus.add_uce(0, 0, "digitais digital códigos código")
            corpus.add_word("digitais", uce_id=uce.ident)
            corpus.add_word("digital", uce_id=uce.ident)
            corpus.add_word("códigos", uce_id=uce.ident)
            corpus.add_word("código", uce_id=uce.ident)

            processor = TextProcessor(corpus)
            processor.build_cooccurrence_matrix(
                window_size=2,
                min_freq=1,
                active_only=True,
                use_lemmas=True,
            )
            assert "digital" in processor.vocabulary
            assert "código" in processor.vocabulary
            assert "digitais" not in processor.vocabulary
            assert "códigos" not in processor.vocabulary
        finally:
            corpus.close()
