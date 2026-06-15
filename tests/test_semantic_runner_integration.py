"""
Integration test: simula o fluxo UI -> runner factory -> analysis module.

Cada runner factory e chamado com os mesmos kwargs que a UI produziria
(sem 'analysis_type'), usando um corpus mockado e um output_dir real.
Garante que o pipeline completo funciona sem TypeError ou NoneType.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.corpus import Corpus


def _make_corpus(n_docs: int = 3) -> MagicMock:
    """Cria corpus mockado padrao com N documentos."""
    corpus = MagicMock(spec=Corpus)

    words = [
        "governo", "federal", "aprovou", "medida", "economica",
        "estuda", "crescimento", "educacao", "saude", "prioridades",
        "imposto", "renda", "populacao", "reclama", "politica",
    ]
    formes = {}
    for word in words:
        mw = MagicMock()
        mw.forme = word
        mw.lem = word
        mw.freq = 5
        mw.act = 1
        formes[word] = mw
    corpus.formes = formes

    lems = {}
    for word in words:
        ml = MagicMock()
        ml.lem = word
        ml.freq = 5
        ml.act = 1
        lems[word] = ml
    corpus.lems = lems

    doc_texts = [
        "o governo federal aprovou a medida economica",
        "o governo estuda crescimento educacao e saude",
        "a educacao e a saude sao prioridades do governo federal",
        "imposto de renda preocupa a populacao que reclama",
    ]

    ucis = []
    all_texts = []
    uce_id = 0
    for i in range(min(n_docs, len(doc_texts))):
        uci = MagicMock()
        uci.ident = i
        uci.paras = {"title": f"Doc_{i}", "date": f"2023-01-0{i+1}"}

        uce = MagicMock()
        uce.ident = uce_id
        uci.uces = [uce]
        ucis.append(uci)

        all_texts.append((uce_id, doc_texts[i]))
        uce_id += 1

    corpus.ucis = ucis
    corpus.get_uces = MagicMock(return_value=all_texts)

    def _getconcorde(ids):
        return [(uid, t) for uid, t in all_texts if uid in ids]
    corpus.getconcorde = MagicMock(side_effect=_getconcorde)

    corpus.lexicon = None
    corpus.parametres = {}

    return corpus


# ---------------------------------------------------------------------------
# YAKE
# ---------------------------------------------------------------------------
class TestRunnerYAKE:
    def test_yake_runner_no_analysis_type(self, tmp_path):
        """Runner YAKE aceita kwargs sem 'analysis_type'."""
        from src.analysis.yake_analysis import YAKEAnalysis, YAKEParams

        corpus = _make_corpus()
        output_dir = tmp_path / "yake"
        output_dir.mkdir()

        # Simula params da UI (sem analysis_type)
        kwargs = {"min_freq": 1, "top_n": 10}
        result = YAKEAnalysis().run(corpus, output_dir, YAKEParams(**kwargs))

        assert result.analysis_type == "yake"
        assert result.output_dir == output_dir
        assert result.keyphrases_csv_path.exists()


# ---------------------------------------------------------------------------
# LDA
# ---------------------------------------------------------------------------
class TestRunnerLDA:
    def test_lda_runner_no_analysis_type(self, tmp_path):
        """Runner LDA aceita kwargs sem 'analysis_type'."""
        from src.analysis.lda_analysis import LDAAnalysis, LDAParams

        corpus = _make_corpus(n_docs=4)
        output_dir = tmp_path / "lda"
        output_dir.mkdir()

        kwargs = {"n_topics": 2, "min_freq": 1}
        result = LDAAnalysis().run(corpus, output_dir, LDAParams(**kwargs))

        assert result.analysis_type == "lda"
        assert result.output_dir == output_dir
        assert result.topics_csv_path.exists()


# ---------------------------------------------------------------------------
# Associative Heatmap
# ---------------------------------------------------------------------------
class TestRunnerHeatmap:
    def test_heatmap_runner_no_analysis_type(self, tmp_path):
        """Runner Heatmap aceita kwargs sem 'analysis_type'."""
        from src.analysis.associative_heatmap_analysis import (
            AssociativeHeatmapAnalysis,
            AssociativeHeatmapParams,
        )

        corpus = _make_corpus()
        output_dir = tmp_path / "heatmap"
        output_dir.mkdir()

        kwargs = {"min_freq": 1, "top_n_pairs": 10}
        result = AssociativeHeatmapAnalysis().run(
            corpus, output_dir, AssociativeHeatmapParams(**kwargs)
        )

        assert result.analysis_type == "associative_heatmap"
        assert result.output_dir == output_dir


class TestRunnerThematicMap:
    def test_thematic_map_params_accept_valid_kwargs(self):
        """ThematicMapParams aceita kwargs validos sem 'analysis_type'."""
        from src.analysis.thematic_map_analysis import ThematicMapParams

        params = ThematicMapParams(min_freq=1, min_cooc=1, top_edges=20, max_nodes=40)
        assert params.min_freq == 1
        assert params.min_cooc == 1
        assert params.top_edges == 20

# ---------------------------------------------------------------------------
# Thematic CHD (mocked LDA)
# ---------------------------------------------------------------------------
class TestRunnerThematicCHD:
    def test_thematic_chd_params_accept_valid_kwargs(self):
        """ThematicCHDParams aceita kwargs validos sem 'analysis_type'."""
        from src.analysis.thematic_chd_analysis import ThematicCHDParams

        # Verifica que o dataclass aceita os kwargs que a UI envia
        params = ThematicCHDParams(n_topics=2, min_freq=1)
        assert params.n_topics == 2
        assert params.min_freq == 1

    def test_thematic_chd_small_corpus_raises_friendly(self, tmp_path):
        """CHD Tematico com corpus muito pequeno gera SemanticAnalysisError."""
        from src.analysis.thematic_chd_analysis import (
            ThematicCHDAnalysis,
            ThematicCHDParams,
        )
        from src.analysis.semantic_contracts import SemanticAnalysisError

        corpus = _make_corpus(n_docs=4)
        output_dir = tmp_path / "chd"
        output_dir.mkdir()

        kwargs = {"n_topics": 2, "min_freq": 1}
        with pytest.raises(SemanticAnalysisError):
            ThematicCHDAnalysis().run(
                corpus, output_dir, ThematicCHDParams(**kwargs)
            )


# ---------------------------------------------------------------------------
# Meta: verifica que analysis_type causa TypeError nos Params dataclasses
# ---------------------------------------------------------------------------
class TestAnalysisTypeRejected:
    """Confirma que 'analysis_type' em kwargs causa TypeError nos Params."""

    @pytest.mark.parametrize("params_cls_path", [
        "src.analysis.yake_analysis.YAKEParams",
        "src.analysis.lda_analysis.LDAParams",
        "src.analysis.associative_heatmap_analysis.AssociativeHeatmapParams",
        "src.analysis.thematic_map_analysis.ThematicMapParams",
        "src.analysis.thematic_chd_analysis.ThematicCHDParams",
    ])
    def test_analysis_type_kwarg_raises(self, params_cls_path):
        """Garante que o dataclass rejeita 'analysis_type' como kwarg."""
        import importlib
        module_path, cls_name = params_cls_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)

        with pytest.raises(TypeError):
            cls(analysis_type="should_fail")
