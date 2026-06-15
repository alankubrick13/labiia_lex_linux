"""
Testes de contrato para a classe AssociativeHeatmapAnalysis (Task 8).

Garante geracao de CSVs de associacao, listas de pares e heatmap PPMI clusterizado.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from src.core.corpus import Corpus
from src.analysis.semantic_contracts import SemanticAnalysisError
from src.analysis.associative_heatmap_analysis import AssociativeHeatmapParams, AssociativeHeatmapAnalysis


@pytest.fixture
def sample_corpus() -> Corpus:
    """Cria um corpus basico mockado para matrizes de coocorrencia."""
    corpus = MagicMock(spec=Corpus)

    words = ["crise", "governo", "economia", "politica", "juros", "inflacao"]
    formes = {}
    for word in words:
        mw = MagicMock()
        mw.forme = word
        mw.lem = word
        mw.freq = 5
        mw.act = 1
        formes[word] = mw
    corpus.formes = formes
    corpus.lems = formes

    ucis = []
    for i in range(4):
        uci = MagicMock()
        uci.ident = i
        uci.paras = {"title": f"Doc_{i}"}
        uce = MagicMock()
        uce.ident = i
        uci.uces = [uce]
        ucis.append(uci)
    
    corpus.ucis = ucis

    # Textos criados para forcar coocorrencia:
    # crise e economia aparecem juntas 3 vezes
    # politica e governo aparecem juntas 2 vezes
    texts = [
        (0, "crise economia juros"),
        (1, "crise economia inflacao"),
        (2, "politica governo crise economia"),
        (3, "politica governo")
    ]
    corpus.get_uces = MagicMock(return_value=texts)
    
    def _getconcorde(ids):
        return [(uid, t) for uid, t in texts if uid in ids]
    corpus.getconcorde = MagicMock(side_effect=_getconcorde)
    
    corpus.lexicon = None
    corpus.parametres = {}
    
    return corpus


class TestAssociativeHeatmapAnalysis:

    def test_heatmap_generates_artifacts(self, sample_corpus, tmp_path):
        """Pipeline deve gerar matriz, pares e imagem de heatmap."""
        output_dir = tmp_path / "heatmap_output"
        output_dir.mkdir()

        params = AssociativeHeatmapParams(min_freq=1, max_features=10)
        analysis = AssociativeHeatmapAnalysis()
        result = analysis.run(sample_corpus, output_dir, params)

        assert result.analysis_type == "associative_heatmap"
        
        # Arquivos esperados
        matrix_csv = output_dir / "association_matrix.csv"
        pairs_csv = output_dir / "top_pairs.csv"
        heatmap_png = output_dir / "heatmap.png"
        summary_json = output_dir / "associative_summary.json"

        assert matrix_csv.exists()
        assert pairs_csv.exists()
        assert heatmap_png.exists()
        assert summary_json.exists()

        # Validar summary
        with open(summary_json, encoding="utf-8") as f:
            summary = json.load(f)
        assert summary["analysis_type"] == "associative_heatmap"
        assert summary["n_terms"] > 0
        assert summary["n_pairs"] > 0

        # Validar CSV de pares
        with open(pairs_csv, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) > 1  # Cabecalho + pares

        # Verificar se "crise" e "economia" estao pareadas
        content = "".join(lines)
        assert "crise" in content
        assert "economia" in content

    def test_heatmap_primary_visual_is_topic_based_not_term_term(self, sample_corpus, tmp_path):
        """A imagem principal não deve degradar silenciosamente para matriz termo-termo."""
        output_dir = tmp_path / "heatmap_topic_output"
        output_dir.mkdir()

        params = AssociativeHeatmapParams(min_freq=1, max_features=10, n_topics=2)
        analysis = AssociativeHeatmapAnalysis()

        with patch.object(
            AssociativeHeatmapAnalysis,
            "_write_clustered_heatmap",
            side_effect=AssertionError("term-term fallback should not be used"),
        ):
            result = analysis.run(sample_corpus, output_dir, params)

        assert result.heatmap_image_path.exists()
        summary = json.loads((output_dir / "associative_summary.json").read_text(encoding="utf-8"))
        assert summary["heatmap_mode"] == "topic_correlation"
        assert summary["n_topics"] == 2

    def test_heatmap_raises_if_topic_modeling_fails(self, sample_corpus, tmp_path):
        """Falha de LDA deve ser visível em vez de gerar heatmap termo-termo."""
        output_dir = tmp_path / "heatmap_failure_output"
        output_dir.mkdir()

        params = AssociativeHeatmapParams(min_freq=1, max_features=10, n_topics=2)
        analysis = AssociativeHeatmapAnalysis()

        with patch(
            "src.analysis.associative_heatmap_analysis.train_lda",
            side_effect=RuntimeError("lda unavailable"),
        ):
            with pytest.raises(SemanticAnalysisError) as exc:
                analysis.run(sample_corpus, output_dir, params)

        assert "topicos" in str(exc.value).lower() or "lda" in str(exc.value).lower()
