"""Fix D — política de fallback do CHD (Reinert apenas, nunca hclust).

Ordem garantida: nativo R Reinert -> engine Reinert portado (Python) -> erro
claro. O pseudo-CHD hclust/cutree foi removido do fluxo CHD.

Ver planejamentofable.md, Fase 4.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.chd_reinert import CHDAnalysis, CHDAnalysisError, CHDResult


def _ok_result(engine="native"):
    return CHDResult(
        n_classes=5,
        profiles={cid: [("t", 4.0, 6, 30.0, "+")] for cid in range(1, 6)},
        class_sizes={cid: 2 for cid in range(1, 6)},
        classification_engine=engine,
    )


def test_native_success_uses_native_engine(tmp_path, monkeypatch):
    analysis = CHDAnalysis(MagicMock(), tmp_path)
    monkeypatch.setattr(analysis, "_run_single_pipeline", lambda cfg: _ok_result("native"))
    # Ported must not be needed
    monkeypatch.setattr(analysis, "_run_legacy_reinert_pipeline",
                        lambda cfg: pytest.fail("ported should not run on native success"))
    result = analysis.run({"classif_mode": 1, "nb_classes": 5})
    assert result.classification_engine == "native"
    assert analysis._fallback_via_ported is False


def test_native_failure_falls_back_to_ported(tmp_path, monkeypatch):
    analysis = CHDAnalysis(MagicMock(), tmp_path)

    def boom(cfg):
        raise CHDAnalysisError(what="x", why="degenerate matrix", how="y")

    monkeypatch.setattr(analysis, "_run_single_pipeline", boom)
    monkeypatch.setattr(analysis, "_can_use_ported_reinert", lambda cfg: True)
    monkeypatch.setattr(analysis, "_run_legacy_reinert_pipeline", lambda cfg: _ok_result("ported_reinert"))

    result = analysis.run({"classif_mode": 1, "nb_classes": 5})
    assert result.classification_engine == "ported_reinert"
    assert analysis._fallback_via_ported is True


def test_clear_error_when_no_path_available(tmp_path, monkeypatch):
    """Native fails and ported is not applicable -> clear error, never hclust."""
    analysis = CHDAnalysis(MagicMock(), tmp_path)

    def boom(cfg):
        raise CHDAnalysisError(what="degenerada", why="matriz degenerada", how="y")

    monkeypatch.setattr(analysis, "_run_single_pipeline", boom)
    monkeypatch.setattr(analysis, "_can_use_ported_reinert", lambda cfg: False)
    # Guard: the generic hclust single pipeline must never be (re)invoked here.
    with pytest.raises(CHDAnalysisError):
        analysis.run({"classif_mode": 1, "nb_classes": 5})


def test_hclust_legacy_helpers_were_removed():
    """Regression guard: the strict->hclust retry helpers must not come back."""
    assert not hasattr(CHDAnalysis, "_should_retry_legacy_from_strict")
    assert not hasattr(CHDAnalysis, "_build_legacy_retry_config")


def test_relaxable_strict_failure_detection():
    assert CHDAnalysis._is_relaxable_strict_failure(
        Exception("O lexico nao esta carregado e strict_stopword_filter=True")
    ) is True
    assert CHDAnalysis._is_relaxable_strict_failure(
        Exception("filtro agressivo de stopwords")
    ) is True
    # A degenerate-matrix failure is NOT relaxable (must fall to ported, not retry).
    assert CHDAnalysis._is_relaxable_strict_failure(
        Exception("Too many dimensions!")
    ) is False
