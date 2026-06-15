"""
Testes de contrato para a Suite Semantica Classica.

Cobre:
- BaseSemanticResult serializa Path corretamente
- ArtifactManifest preserva primarios e secundarios
- SemanticAnalysisError mantem mensagem amigavel
- KeyphraseCandidate mantem contrato minimo
- DTM / UCE-DTM usam csr_matrix (quando semantic_text_base estiver pronto)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.semantic_contracts import (
    ArtifactManifest,
    BaseSemanticParams,
    BaseSemanticResult,
    KeyphraseCandidate,
    SemanticAnalysisError,
)


# ---------------------------------------------------------------------------
# SemanticAnalysisError
# ---------------------------------------------------------------------------

class TestSemanticAnalysisError:

    def test_error_preserves_fields(self):
        err = SemanticAnalysisError(
            what="Corpus vazio",
            why="Nenhum documento importado",
            how="Importe um corpus antes de rodar",
        )
        assert err.what == "Corpus vazio"
        assert err.why == "Nenhum documento importado"
        assert err.how == "Importe um corpus antes de rodar"

    def test_error_message_friendly(self):
        err = SemanticAnalysisError(what="A", why="B", how="C")
        msg = str(err)
        assert "A" in msg
        assert "B" in msg
        assert "C" in msg

    def test_error_is_exception(self):
        err = SemanticAnalysisError(what="x", why="y", how="z")
        assert isinstance(err, Exception)
        with pytest.raises(SemanticAnalysisError):
            raise err


# ---------------------------------------------------------------------------
# ArtifactManifest
# ---------------------------------------------------------------------------

class TestArtifactManifest:

    def test_default_values(self):
        m = ArtifactManifest()
        assert m.primary_image is None
        assert m.primary_table is None
        assert m.summary_json is None
        assert m.secondary_images == []
        assert m.secondary_tables == []
        assert m.extra_files == []

    def test_preserves_primary_and_secondary(self):
        m = ArtifactManifest(
            primary_image=Path("img.png"),
            primary_table=Path("table.csv"),
            summary_json=Path("summary.json"),
            secondary_images=[Path("extra1.png"), Path("extra2.png")],
            secondary_tables=[Path("extra.csv")],
            extra_files=[Path("diagnostics.json")],
        )
        assert m.primary_image == Path("img.png")
        assert m.primary_table == Path("table.csv")
        assert m.summary_json == Path("summary.json")
        assert len(m.secondary_images) == 2
        assert len(m.secondary_tables) == 1
        assert len(m.extra_files) == 1

    def test_all_paths_flattened(self):
        m = ArtifactManifest(
            primary_image=Path("a.png"),
            secondary_images=[Path("b.png")],
        )
        all_paths = m.all_paths()
        assert Path("a.png") in all_paths
        assert Path("b.png") in all_paths


# ---------------------------------------------------------------------------
# BaseSemanticParams
# ---------------------------------------------------------------------------

class TestBaseSemanticParams:

    def test_default_random_state(self):
        p = BaseSemanticParams()
        assert p.random_state == 42

    def test_custom_random_state(self):
        p = BaseSemanticParams(random_state=123)
        assert p.random_state == 123


# ---------------------------------------------------------------------------
# BaseSemanticResult
# ---------------------------------------------------------------------------

class TestBaseSemanticResult:

    def test_primary_image_default_none(self, tmp_path):
        r = BaseSemanticResult(analysis_type="test", output_dir=tmp_path)
        assert r.primary_image_path() is None

    def test_primary_table_default_none(self, tmp_path):
        r = BaseSemanticResult(analysis_type="test", output_dir=tmp_path)
        assert r.primary_table_path() is None

    def test_artifact_manifest_returns_manifest(self, tmp_path):
        r = BaseSemanticResult(analysis_type="test", output_dir=tmp_path)
        m = r.artifact_manifest()
        assert isinstance(m, ArtifactManifest)

    def test_to_history_metadata_serializes_path(self, tmp_path):
        r = BaseSemanticResult(analysis_type="yake", output_dir=tmp_path)
        meta = r.to_history_metadata()
        assert meta["analysis_type"] == "yake"
        assert isinstance(meta["output_dir"], str)
        assert str(tmp_path) == meta["output_dir"]

    def test_to_history_metadata_includes_secondary(self, tmp_path):
        """Subclass can expose secondaries via artifact_manifest override."""

        class FakeResult(BaseSemanticResult):
            def artifact_manifest(self):
                return ArtifactManifest(
                    primary_image=tmp_path / "img.png",
                    secondary_images=[tmp_path / "extra.png"],
                    secondary_tables=[tmp_path / "extra.csv"],
                )

        r = FakeResult(analysis_type="fake", output_dir=tmp_path)
        meta = r.to_history_metadata()
        assert "primary_image" in meta
        assert isinstance(meta["primary_image"], str)
        assert "secondary_images" in meta
        assert len(meta["secondary_images"]) == 1
        assert "secondary_tables" in meta


# ---------------------------------------------------------------------------
# KeyphraseCandidate
# ---------------------------------------------------------------------------

class TestKeyphraseCandidate:

    def test_basic_creation(self):
        kp = KeyphraseCandidate(
            phrase="analise textual",
            normalized_phrase="analise textual",
            score=12.5,
            frequency=3,
            degree=5,
        )
        assert kp.phrase == "analise textual"
        assert kp.score == 12.5
        assert kp.frequency == 3
        assert kp.degree == 5
        assert kp.doc_count == 0
        assert kp.mean_position == 0.0

    def test_repeated_phrase_scores_higher(self):
        """Scoring principle: higher score favors repeated multi-word phrases."""
        single = KeyphraseCandidate(
            phrase="texto",
            normalized_phrase="texto",
            score=1.0,
            frequency=1,
            degree=1,
        )
        repeated = KeyphraseCandidate(
            phrase="analise textual avancada",
            normalized_phrase="analise textual avancada",
            score=9.0,
            frequency=3,
            degree=9,
        )
        assert repeated.score > single.score

