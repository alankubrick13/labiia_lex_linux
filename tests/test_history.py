"""Tests for persistent analysis history."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from src.core.history import AnalysisHistory, HistoryError


def test_history_save_load_and_get_result(tmp_path):
    history_path = tmp_path / "analysis_history.json"
    artifacts_dir = tmp_path / "artifacts"
    history = AnalysisHistory(history_path=history_path, artifacts_dir=artifacts_dir)

    artifact = tmp_path / "result.png"
    artifact.write_text("fake", encoding="utf-8")

    saved = history.save_result(
        analysis_type="chd",
        params={"n_classes": 4, "min_freq": 2},
        result_path=artifact,
    )

    loaded = history.load_results()
    assert len(loaded) == 1
    assert loaded[0].entry_id == saved.entry_id
    assert loaded[0].analysis_type == "chd"
    assert loaded[0].params["n_classes"] == 4
    assert Path(loaded[0].result_path).exists()

    fetched = history.get_result(saved.entry_id)
    assert fetched.entry_id == saved.entry_id


def test_history_save_result_copies_directory_artifacts(tmp_path):
    history = AnalysisHistory(
        history_path=tmp_path / "history.json",
        artifacts_dir=tmp_path / "artifacts",
    )
    output_dir = tmp_path / "chd_output"
    output_dir.mkdir()
    (output_dir / "dendrogram.png").write_text("png", encoding="utf-8")
    (output_dir / "profiles.csv").write_text("csv", encoding="utf-8")

    saved = history.save_result(
        analysis_type="chd",
        params={"n_classes": 4},
        result_path=output_dir,
    )

    copied_dir = Path(saved.result_path)
    assert copied_dir.exists()
    assert copied_dir.is_dir()
    assert copied_dir != output_dir
    assert (copied_dir / "dendrogram.png").exists()
    assert (copied_dir / "profiles.csv").exists()


def test_history_rewrites_manifest_paths_inside_copied_directory(tmp_path):
    history = AnalysisHistory(
        history_path=tmp_path / "history.json",
        artifacts_dir=tmp_path / "artifacts",
    )
    output_dir = tmp_path / "chd"
    output_dir.mkdir()
    dendrogram = output_dir / "dendrogramme.png"
    profiles = output_dir / "profiles_terms.csv"
    dendrogram.write_text("png", encoding="utf-8")
    profiles.write_text("csv", encoding="utf-8")
    manifest = output_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": {
                    "dendrogram": str(dendrogram),
                    "profiles_terms": str(profiles),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    saved = history.save_result(
        analysis_type="chd",
        params={"n_classes": 5},
        result_path=output_dir,
    )

    copied_dir = Path(saved.result_path)
    copied_manifest = copied_dir / "manifest.json"
    payload = json.loads(copied_manifest.read_text(encoding="utf-8"))
    for value in payload["files"].values():
        copied_path = Path(value)
        assert copied_path.exists()
        assert copied_dir in copied_path.parents


def test_history_missing_entry_raises_key_error(tmp_path):
    history = AnalysisHistory(history_path=tmp_path / "history.json", artifacts_dir=tmp_path / "artifacts")
    with pytest.raises(KeyError):
        history.get_result("nao-existe")


def test_history_load_corrupted_json_raises_friendly_error(tmp_path):
    history_path = tmp_path / "history.json"
    history_path.write_text("{ invalido", encoding="utf-8")

    history = AnalysisHistory(history_path=history_path, artifacts_dir=tmp_path / "artifacts")
    with pytest.raises(HistoryError) as exc_info:
        history.load_results()

    message = str(exc_info.value)
    assert "O que aconteceu:" in message
    assert "Por que aconteceu:" in message
    assert "Como resolver:" in message


def test_history_delete_result_removes_entry_and_artifacts(tmp_path):
    history_path = tmp_path / "analysis_history.json"
    artifacts_dir = tmp_path / "artifacts"
    history = AnalysisHistory(history_path=history_path, artifacts_dir=artifacts_dir)

    artifact = tmp_path / "result.txt"
    artifact.write_text("ok", encoding="utf-8")

    entry = history.save_result(
        analysis_type="lda",
        params={"n_dimensions": 2},
        result_path=artifact,
    )
    assert Path(entry.result_path).exists()

    removed = history.delete_result(entry.entry_id)
    assert removed is True
    assert history.load_results() == []
    assert not (artifacts_dir / entry.entry_id).exists()
