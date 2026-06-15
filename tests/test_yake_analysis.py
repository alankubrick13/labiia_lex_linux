"""
Testes de contrato para a classe YAKEAnalysis.

Verifica se a analise YAKE gera os artefatos esperados, respeitando
a arquitetura da Suite Semantica Classica.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from src.core.corpus import Corpus
from src.analysis.semantic_contracts import SemanticAnalysisError
from src.analysis.yake_analysis import YAKEParams, YAKEAnalysis


from unittest.mock import MagicMock

@pytest.fixture
def sample_corpus(tmp_path) -> Corpus:
    """Cria um corpus basico para testes do YAKE."""
    corpus = MagicMock(spec=Corpus)

    # Word frequencies needed for vocabulary
    words = ["o", "governo", "federal", "aprovou", "a", "medida", "economica", "estuda", "crescimento", "educacao", "e", "saude", "sao", "prioridades", "do"]
    formes = {}
    for word in words:
        mock_word = MagicMock()
        mock_word.forme = word
        mock_word.lem = word
        mock_word.freq = 5
        mock_word.act = 1
        formes[word] = mock_word
    corpus.formes = formes

    # Lems
    lems = {}
    for word in words:
        mock_lem = MagicMock()
        mock_lem.lem = word
        mock_lem.freq = 5
        mock_lem.act = 1
        lems[word] = mock_lem
    corpus.lems = lems

    # UCIs and UCEs
    uci = MagicMock()
    uci.ident = 0
    uci.paras = {"title": "Doc_1"}

    uce1 = MagicMock()
    uce1.ident = 0
    uce2 = MagicMock()
    uce2.ident = 1
    uce3 = MagicMock()
    uce3.ident = 2

    uci.uces = [uce1, uce2, uce3]
    corpus.ucis = [uci]

    texts = [
        (0, "o governo federal aprovou a medida economica"),
        (1, "o governo federal estuda o crescimento economico"),
        (2, "a educacao e a saude sao prioridades do governo federal")
    ]
    corpus.get_uces = MagicMock(return_value=texts)
    def _getconcorde(ids):
        return [(uid, t) for uid, t in texts if uid in ids]
    corpus.getconcorde = MagicMock(side_effect=_getconcorde)
    corpus.lexicon = None
    corpus.parametres = {}

    return corpus


class TestYAKEAnalysis:

    def test_yake_analysis_generates_artifacts(self, sample_corpus, tmp_path):
        """YAKE deve gerar yake_keyphrases.csv, yake_summary.json e yake_ranking.png."""
        output_dir = tmp_path / "yake_output"
        output_dir.mkdir()

        params = YAKEParams(
            min_freq=1,
            min_tokens=1,
            max_tokens=4,
            top_n=10,
        )

        analysis = YAKEAnalysis()
        result = analysis.run(sample_corpus, output_dir, params)

        # Contratos do Result
        assert result.analysis_type == "yake"
        assert result.output_dir == output_dir

        # Artefatos esperados
        csv_path = output_dir / "yake_keyphrases.csv"
        json_path = output_dir / "yake_summary.json"
        png_path = output_dir / "yake_ranking.png"

        assert csv_path.exists(), "yake_keyphrases.csv nao foi gerado"
        assert json_path.exists(), "yake_summary.json nao foi gerado"
        assert png_path.exists(), "yake_ranking.png nao foi gerado"

        # Validacao do CSV
        with open(csv_path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) > 1, "CSV deveria ter pelo menos o cabecalho e uma linha de dados"

        # Validacao do JSON
        with open(json_path, encoding="utf-8") as f:
            summary = json.load(f)
        assert summary["analysis_type"] == "yake"
        assert summary["n_keyphrases"] > 0

    def test_yake_rejects_invalid_params(self, sample_corpus, tmp_path):
        """Parametros incorretos disparam SemanticAnalysisError."""
        output_dir = tmp_path / "yake_out"
        output_dir.mkdir()

        params = YAKEParams(min_freq=-1)  # invalido
        analysis = YAKEAnalysis()

        with pytest.raises(SemanticAnalysisError) as exc:
            analysis.run(sample_corpus, output_dir, params)
        assert "requer que a frequência" in str(exc.value)

    def test_yake_negative_raw_score_becomes_positive_relevance(self, monkeypatch):
        from src.analysis.keyphrase_yake import extract_ranked_keyphrases

        class _FakeExtractor:
            def __init__(self, **_kwargs):
                pass

            def extract_keywords(self, _text):
                return [
                    ("gino algumas coisas bar", -27.58),
                    ("governo federal", 0.2),
                    ("né", -32.0),
                ]

        monkeypatch.setitem(sys.modules, "yake", types.SimpleNamespace(KeywordExtractor=_FakeExtractor))

        candidates = extract_ranked_keyphrases(
            ["governo federal governo federal né gino algumas coisas bar"],
            min_freq=1,
            top_n=10,
            max_tokens=4,
        )

        phrases = {item.normalized_phrase for item in candidates}
        assert "né" not in phrases
        assert "gino algumas coisas bar" not in phrases
        assert "governo federal" in phrases
        assert all(item.score > 0 for item in candidates)
        assert all(item.raw_yake_score is not None for item in candidates)

    def test_yake_csv_preserves_raw_and_relevance_scores(self, sample_corpus, tmp_path, monkeypatch):
        from src.analysis.semantic_contracts import KeyphraseCandidate
        import src.analysis.yake_analysis as yake_analysis

        monkeypatch.setattr(
            yake_analysis,
            "extract_ranked_keyphrases",
            lambda *_args, **_kwargs: [
                KeyphraseCandidate(
                    phrase="governo federal",
                    normalized_phrase="governo federal",
                    score=5.0,
                    raw_yake_score=0.2,
                    frequency=2,
                    degree=0,
                    doc_count=1,
                )
            ],
        )

        output_dir = tmp_path / "yake_csv"
        output_dir.mkdir()
        result = YAKEAnalysis().run(sample_corpus, output_dir, YAKEParams(min_freq=1))

        content = result.keyphrases_csv_path.read_text(encoding="utf-8")
        assert "RawYAKE;Relevance" in content
        assert "0.200000;5.000" in content
