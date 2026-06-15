from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


def test_chd_dendrogram_filters_visual_noise_and_aligns_class_boxes(tmp_path) -> None:
    from src.analysis.chd_visualization import render_chd_dendrogram

    profiles = {
        1: [
            ("vacina", 12.0, 8, 40.0, "+"),
            ("36", 9.0, 5, 25.0, "+"),
            ("aa", 8.0, 4, 20.0, "+"),
            ("nvoce", 7.0, 4, 20.0, "+"),
        ],
        2: [
            ("governo", 11.0, 7, 35.0, "+"),
            ("né", 9.0, 5, 25.0, "+"),
            ("si", 8.0, 4, 20.0, "+"),
            ("ntranscrever", 7.0, 4, 20.0, "+"),
        ],
        3: [
            ("pesquisa", 10.0, 6, 30.0, "+"),
            ("0", 9.0, 5, 25.0, "+"),
            ("Ainda", 8.0, 4, 20.0, "+"),
            ("mp3", 7.0, 4, 20.0, "+"),
        ],
    }
    output = tmp_path / "dendrogramme_enhanced.png"
    layout = tmp_path / "chd_dendrogram_layout.json"

    rendered = render_chd_dendrogram(
        profiles=profiles,
        class_sizes={1: 10, 2: 12, 3: 8},
        output_path=output,
        layout_path=layout,
        newick="((1,2),3);",
    )

    assert rendered == output
    assert output.exists()
    payload = json.loads(layout.read_text(encoding="utf-8"))
    assert payload["filtered_terms"]["removed_count"] >= 6
    visible_terms = {
        word
        for row in payload["classes"]
        for word in row["visible_terms"]
    }
    assert {"vacina", "governo", "pesquisa"}.issubset(visible_terms)
    assert {"36", "aa", "né", "si", "0", "Ainda", "nvoce", "ntranscrever", "mp3"}.isdisjoint(visible_terms)


def test_chd_dendrogram_limits_visible_terms_to_readable_count(tmp_path) -> None:
    from src.analysis.chd_visualization import render_chd_dendrogram

    def term(prefix: str, idx: int) -> str:
        first = chr(ord("a") + (idx // 26))
        second = chr(ord("a") + (idx % 26))
        return f"{prefix}{first}{second}"

    profiles = {
        1: [(term("termoa", i), float(100 - i), 10, 50.0, "+") for i in range(60)],
        2: [(term("termob", i), float(100 - i), 10, 50.0, "+") for i in range(60)],
    }
    output = tmp_path / "dendrogramme.png"
    layout = tmp_path / "chd_dendrogram_layout.json"

    render_chd_dendrogram(
        profiles=profiles,
        class_sizes={1: 10, 2: 10},
        output_path=output,
        layout_path=layout,
        newick="(1,2);",
        max_terms_per_class=36,
    )

    payload = json.loads(layout.read_text(encoding="utf-8"))
    for class_payload in payload["classes"]:
        assert len(class_payload["visible_terms"]) <= 18
        assert class_payload["hidden_terms_count"] > 0

    for row in payload["classes"]:
        assert abs(float(row["leaf_x"]) - float(row["box_center_x"])) <= 1.0
        assert abs(float(row["leaf_x"]) - float(row["label_center_x"])) <= 1.0


def test_chd_accepts_three_classes_when_target_is_five(tmp_path, monkeypatch, caplog) -> None:
    """A native run that legitimately emerges with fewer-than-target classes is a
    real result: it must be accepted (with a warning), never rejected. Rejecting
    it triggered the artificial hclust fallback that produced the blank AFC."""
    import logging

    from src.analysis.chd_reinert import CHDAnalysis, CHDResult

    analysis = CHDAnalysis(MagicMock(), tmp_path)

    def fake_pipeline(_config):
        return CHDResult(
            n_classes=3,
            profiles={1: [("termo", 4.0, 6, 30.0, "+")]},
            class_sizes={1: 10, 2: 8, 3: 7},
        )

    monkeypatch.setattr(analysis, "_run_single_pipeline", fake_pipeline)

    with caplog.at_level(logging.WARNING):
        result = analysis.run(
            {
                "analysis_mode": "strict",
                "strict_iramuteq_clone": True,
                "use_native_chd": True,
                "native_fallback_legacy": False,
                "classif_mode": 1,
                "nb_classes": 5,
            }
        )

    assert result.n_classes == 3
    # The shortfall is surfaced transparently, not silently nor as an error.
    assert any("abaixo do alvo de 5" in rec.getMessage() for rec in caplog.records)


def test_chd_rejects_single_class_as_degenerate(tmp_path, monkeypatch) -> None:
    """Fewer than 2 classes is genuinely degenerate and must still raise."""
    from src.analysis.chd_reinert import CHDAnalysis, CHDAnalysisError, CHDResult

    analysis = CHDAnalysis(MagicMock(), tmp_path)

    def fake_pipeline(_config):
        return CHDResult(
            n_classes=1,
            profiles={1: [("termo", 4.0, 6, 30.0, "+")]},
            class_sizes={1: 25},
        )

    monkeypatch.setattr(analysis, "_run_single_pipeline", fake_pipeline)

    with pytest.raises(CHDAnalysisError):
        analysis.run(
            {
                "analysis_mode": "strict",
                "strict_iramuteq_clone": True,
                "use_native_chd": True,
                "native_fallback_legacy": False,
                "classif_mode": 1,
                "nb_classes": 5,
            }
        )
