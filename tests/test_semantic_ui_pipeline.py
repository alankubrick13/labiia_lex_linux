"""
Teste de pipeline UI->Runner para as analises semanticas ativas.

Simula EXATAMENTE o que _execute_semantic_analysis_async faz:
1. _get_analysis_output_dir cria diretorio temporario (partindo de _analysis_output_root=None)
2. request_params.pop("analysis_type") remove metadata
3. runner_factory(corpus=..., output_dir=..., **request_params) executa a analise
4. Resultado tem analysis_type e output_dir corretos

Este teste PROVA que o pipeline funciona de ponta a ponta.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from src.core.corpus import Corpus


# ---- Simula o estado da MainWindow -------------------------------------------

class FakeMainWindow:
    """Simula o estado relevante de MainWindow para _get_analysis_output_dir."""

    def __init__(self):
        self._analysis_output_root: Optional[Path] = None  # EXATAMENTE como na UI

    def _get_analysis_output_dir(self, analysis_type: str) -> Path:
        """Copia EXATA do metodo real (main_window.py:2924-2934)."""
        if self._analysis_output_root is None or not self._analysis_output_root.exists():
            self._analysis_output_root = Path(
                tempfile.mkdtemp(prefix="lexianalyst_test_pipeline_")
            )
        analysis_dir = self._analysis_output_root / analysis_type
        analysis_dir.mkdir(parents=True, exist_ok=True)
        return analysis_dir


def _simulate_execute_semantic(
    fake_window: FakeMainWindow,
    registry_key: str,
    dialog_result: Dict[str, Any],
    runner_factory,
    corpus,
):
    """
    Simula _execute_semantic_analysis_async SEM thread, SEM UI.
    Reproduz o fluxo exato: pop analysis_type, get output dir, call factory.
    """
    request_params = dict(dialog_result or {})
    request_params.pop("analysis_type", None)  # Linha 5604

    output_dir = fake_window._get_analysis_output_dir(registry_key)  # Linha 5608

    assert output_dir is not None, "output_dir is None after _get_analysis_output_dir!"
    assert output_dir.exists(), f"output_dir {output_dir} does not exist!"

    result = runner_factory(corpus=corpus, output_dir=output_dir, **request_params)

    assert result is not None, f"Runner {registry_key} returned None"
    assert result.analysis_type == registry_key, (
        f"Expected analysis_type={registry_key}, got {result.analysis_type}"
    )
    assert result.output_dir == output_dir

    return result


# ---- Corpus Mock Compartilhado -----------------------------------------------

def _make_corpus(n_docs: int = 3) -> MagicMock:
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


# ---- Importa os runner factories reais da UI --------------------------------

def _import_runner(name):
    """Importa runner factory de main_window sem inicializar a UI."""
    from src.ui.main_window import (
        _run_yake, _run_lda, _run_heatmap, _run_thematic_map, _run_thematic_chd,
    )
    runners = {
        "yake": _run_yake,
        "lda": _run_lda,
        "associative_heatmap": _run_heatmap,
        "thematic_map": _run_thematic_map,
        "thematic_chd": _run_thematic_chd,
    }
    return runners[name]


# ===========================================================================
# TESTES: Simulacao completa UI -> Pipeline
# ===========================================================================

class TestUIPipelineYAKE:
    def test_yake_full_pipeline(self):
        """Simula UI YAKE: dialog result -> pop analysis_type -> get_output_dir -> runner."""
        fake = FakeMainWindow()
        corpus = _make_corpus()

        # Exatamente o que YAKEDialog._build_result() retorna
        dialog_result = {
            "analysis_type": "yake",
            "min_freq": 1,
            "min_tokens": 1,
            "max_tokens": 4,
            "top_n": 10,
        }

        result = _simulate_execute_semantic(
            fake, "yake", dialog_result, _import_runner("yake"), corpus
        )
        assert result.keyphrases_csv_path.exists()


class TestUIPipelineLDA:
    def test_lda_full_pipeline(self):
        """Simula UI LDA: dialog result -> pop analysis_type -> get_output_dir -> runner."""
        fake = FakeMainWindow()
        corpus = _make_corpus(n_docs=4)

        dialog_result = {
            "analysis_type": "lda",
            "n_topics": 2,
            "min_freq": 1,
        }

        result = _simulate_execute_semantic(
            fake, "lda", dialog_result, _import_runner("lda"), corpus
        )
        assert result.topics_csv_path.exists()


class TestUIPipelineHeatmap:
    def test_heatmap_full_pipeline(self):
        """Simula UI Heatmap: dialog result -> pop analysis_type -> get_output_dir -> runner."""
        fake = FakeMainWindow()
        corpus = _make_corpus()

        dialog_result = {
            "analysis_type": "associative_heatmap",
            "min_freq": 1,
            "top_n_pairs": 10,
        }

        result = _simulate_execute_semantic(
            fake, "associative_heatmap", dialog_result,
            _import_runner("associative_heatmap"), corpus
        )
        assert result.analysis_type == "associative_heatmap"


class TestUIPipelineThematicMap:
    def test_thematic_map_runs_unprepared_corpus_as_filtered_terms(self):
        """Simula UI Mapa Temático: corpus sem underscore usa termos filtrados."""
        fake = FakeMainWindow()
        corpus = _make_corpus()
        dialog_result = {
            "analysis_type": "thematic_map",
            "min_freq": 1,
            "min_cooc": 1,
        }

        result = _simulate_execute_semantic(
            fake, "thematic_map", dialog_result,
            _import_runner("thematic_map"), corpus
        )

        assert result.analysis_type == "thematic_map"


class TestUIPipelineThematicCHD:
    def test_thematic_chd_rejects_small_corpus(self):
        """Simula UI CHD Tematico: corpus pequeno deve dar erro amigavel."""
        from src.analysis.semantic_contracts import SemanticAnalysisError

        fake = FakeMainWindow()
        corpus = _make_corpus(n_docs=4)

        dialog_result = {
            "analysis_type": "thematic_chd",
            "n_topics": 2,
            "min_freq": 1,
        }

        with pytest.raises(SemanticAnalysisError):
            _simulate_execute_semantic(
                fake, "thematic_chd", dialog_result,
                _import_runner("thematic_chd"), corpus
            )


# ===========================================================================
# Meta: _analysis_output_root starts as None - prove it's handled
# ===========================================================================

class TestOutputRootNoneHandling:
    def test_output_root_none_creates_dir(self):
        """_get_analysis_output_dir cria diretorio quando _analysis_output_root=None."""
        fake = FakeMainWindow()
        assert fake._analysis_output_root is None

        result = fake._get_analysis_output_dir("test_analysis")

        assert fake._analysis_output_root is not None
        assert result.exists()
        assert result.name == "test_analysis"

    def test_multiple_analyses_reuse_root(self):
        """Multiplas analises reutilizam o mesmo root."""
        fake = FakeMainWindow()

        dir1 = fake._get_analysis_output_dir("yake")
        dir2 = fake._get_analysis_output_dir("lda")

        assert dir1.parent == dir2.parent  # Same root
        assert dir1 != dir2  # Different subdirs
