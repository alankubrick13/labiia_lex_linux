"""Tests for project save/load support."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.project import Project, ProjectError, ProjectManager


def test_project_save_load_and_export_portable(tmp_path):
    manager = ProjectManager()
    source_db = tmp_path / "source.db"
    source_db.write_text("sqlite-placeholder", encoding="utf-8")
    artifact = tmp_path / "result.png"
    artifact.write_text("fake-image", encoding="utf-8")
    report = tmp_path / "report.html"
    report.write_text("<html>relatorio</html>", encoding="utf-8")
    gallery = tmp_path / "gallery.png"
    gallery.write_text("fake-gallery", encoding="utf-8")

    project = Project(
        name="demo",
        corpus_path=tmp_path / "corpus.txt",
        db_path=source_db,
        config={"language": "portuguese", "uce_size": 40},
        analyses=[
            {
                "entry_id": "abc123",
                "analysis_type": "chd",
                "params": {"n_classes": 4},
                "result_path": str(artifact),
                "timestamp": "2026-02-06T19:00:00+00:00",
                "metadata": {
                    "n_classes": 4,
                    "report_path": str(report),
                    "image_gallery": {"Dendrograma": str(gallery)},
                },
            }
        ],
        created_at="2026-02-06T19:00:00+00:00",
        updated_at="2026-02-06T19:00:00+00:00",
        corpus_snapshot="**** *doc_1\ntexto de exemplo\n",
    )

    saved = manager.save(project, tmp_path / "demo.lexproj")
    assert saved.lexproj_path is not None
    assert saved.lexproj_path.exists()
    assert saved.project_dir is not None
    assert saved.project_dir.exists()
    assert (saved.project_dir / "project.json").exists()
    assert (saved.project_dir / "config.json").exists()
    assert (saved.project_dir / "analysis_history.json").exists()
    assert (saved.project_dir / "corpus_snapshot.txt").exists()

    loaded = manager.load(saved.lexproj_path)
    assert loaded.name == "demo"
    assert loaded.config.get("language") == "portuguese"
    assert len(loaded.analyses) == 1
    loaded_artifact = Path(loaded.analyses[0]["result_path"])
    assert loaded_artifact.exists()
    assert "artifacts" in str(loaded_artifact)
    loaded_report = Path(loaded.analyses[0]["metadata"]["report_path"])
    loaded_gallery = Path(loaded.analyses[0]["metadata"]["image_gallery"]["Dendrograma"])
    assert loaded_report.exists()
    assert loaded_gallery.exists()
    assert loaded_report.parent == loaded_artifact.parent
    assert loaded_gallery.parent == loaded_artifact.parent

    zip_path = manager.export_portable(loaded, tmp_path / "demo_portable.zip")
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"


def test_project_load_missing_file_raises_friendly_error(tmp_path):
    manager = ProjectManager()
    with pytest.raises(ProjectError) as exc_info:
        manager.load(tmp_path / "nao_existe.lexproj")

    message = str(exc_info.value)
    assert "O que aconteceu:" in message
    assert "Por que aconteceu:" in message
    assert "Como resolver:" in message
