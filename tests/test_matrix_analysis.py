"""Tests for matrix analyses (frequency, chi2, adapter)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chi2_matrix import Chi2MatrixAnalysis
from src.analysis.frequency import FrequencyAnalysis
from src.analysis.matrix_adapter import MatrixAnalysisAdapter
from src.core.tableau import Tableau


@pytest.fixture
def categorical_tableau():
    frame = pd.DataFrame(
        {
            "grupo": ["A", "A", "B", "B", "B", "C"],
            "sexo": ["F", "M", "F", "M", "M", "F"],
            "idade_faixa": ["jovem", "adulto", "adulto", "adulto", "idoso", "jovem"],
        }
    )
    return Tableau(
        data=frame,
        row_names=[str(i + 1) for i in range(len(frame))],
        col_names=list(frame.columns),
        has_header=True,
        has_rownames=False,
        source_path=Path("categorica.csv"),
    )


@pytest.fixture
def numeric_tableau():
    frame = pd.DataFrame(
        {
            "termo_a": [2, 0, 1, 0],
            "termo_b": [0, 3, 1, 2],
            "termo_c": [1, 1, 0, 4],
        },
        index=["doc1", "doc2", "doc3", "doc4"],
    )
    return Tableau(
        data=frame,
        row_names=list(frame.index),
        col_names=list(frame.columns),
        has_header=True,
        has_rownames=True,
        source_path=Path("numerica.csv"),
    )


class SimpleGraphDummyRExecutor:
    """Creates graph files referenced by png()/svg() in generated script."""

    def execute(self, script_path, working_dir, timeout=600):  # noqa: D401
        script = Path(script_path).read_text(encoding="utf-8")
        run_dir = Path(working_dir)
        for graph_name in re.findall(r"(?:png|svg)\(['\"]([^'\"]+)['\"]", script):
            (run_dir / graph_name).write_text("img", encoding="utf-8")
        return None


class AdapterDummyRExecutor:
    """Emits expected adapter artifacts for AFC/CHD/Similarity."""

    def execute(self, script_path, working_dir, timeout=600):  # noqa: D401
        script_name = Path(script_path).name
        run_dir = Path(working_dir)
        script = Path(script_path).read_text(encoding="utf-8")

        for graph_name in re.findall(r"(?:png|svg)\(['\"]([^'\"]+)['\"]", script):
            (run_dir / graph_name).write_text("img", encoding="utf-8")

        if script_name == "matrix_afc_script.R":
            (run_dir / "row_coords.csv").write_text(
                '"","Dim1","Dim2"\n"doc1",0.2,0.1\n"doc2",-0.2,-0.1\n',
                encoding="utf-8",
            )
            (run_dir / "col_coords.csv").write_text(
                '"","Dim1","Dim2"\n"termo_a",0.5,-0.2\n"termo_b",-0.4,0.3\n',
                encoding="utf-8",
            )
            (run_dir / "eigenvalues.csv").write_text(
                "eigenvalue,variance\n1.4,70\n0.6,30\n",
                encoding="utf-8",
            )
        elif script_name == "matrix_chd_script.R":
            (run_dir / "clusters.csv").write_text(
                '"","x"\n"doc1",1\n"doc2",2\n"doc3",1\n"doc4",2\n',
                encoding="utf-8",
            )
        elif script_name == "matrix_similarity_script.R":
            (run_dir / "matrix_similarity_communities.csv").write_text(
                "term,community\ntermo_a,1\ntermo_b,2\n",
                encoding="utf-8",
            )
            (run_dir / "matrix_similarity_centrality.csv").write_text(
                "term,degree,weighted_degree\ntermo_a,2,3.5\ntermo_b,2,2.8\n",
                encoding="utf-8",
            )
        return None


def test_frequency_analysis_generates_table_and_graph(categorical_tableau):
    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = FrequencyAnalysis(
            Path(tmpdir),
            r_executor=SimpleGraphDummyRExecutor(),
        )
        result = analysis.run(categorical_tableau, columns=["grupo", "sexo"])

        assert "grupo" in result.columns
        assert result.tables["grupo"].exists()
        assert "grupo" in result.graphs
        assert result.graphs["grupo"].exists()
        assert result.summary_csv_path is not None
        assert result.summary_csv_path.exists()


def test_chi2_matrix_analysis_outputs_stats_and_files(categorical_tableau):
    with tempfile.TemporaryDirectory() as tmpdir:
        analysis = Chi2MatrixAnalysis(
            Path(tmpdir),
            r_executor=SimpleGraphDummyRExecutor(),
        )
        result = analysis.run(categorical_tableau, row_var="grupo", col_var="sexo")

        assert result.chi2 >= 0.0
        assert result.dof >= 1
        assert 0.0 <= result.p_value <= 1.0
        assert result.contingency_csv_path.exists()
        assert result.expected_csv_path.exists()
        assert result.residuals_csv_path.exists()
        assert result.graph_path is not None
        assert result.graph_path.exists()


def test_matrix_adapter_runs_afc_chd_similarity(numeric_tableau):
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = MatrixAnalysisAdapter(
            Path(tmpdir),
            r_executor=AdapterDummyRExecutor(),
        )

        afc_result = adapter.run_afc(numeric_tableau, {"typegraph": "png"})
        assert afc_result.graph_path is not None
        assert afc_result.graph_path.exists()
        assert afc_result.row_coords.shape[0] >= 1
        assert afc_result.col_coords.shape[0] >= 1
        assert afc_result.eigenvalues.size >= 1

        chd_result = adapter.run_chd(numeric_tableau, {"nb_classes": 2, "typegraph": "png"})
        assert chd_result.dendrogram_path is not None
        assert chd_result.dendrogram_path.exists()
        assert chd_result.clusters_path is not None
        assert chd_result.clusters_path.exists()
        assert chd_result.assignments.get("doc1") == 1

        sim_result = adapter.run_similarity(numeric_tableau, {"layout": "fruchterman"})
        assert sim_result.graph_path is not None
        assert sim_result.graph_path.exists()
        assert sim_result.adjacency_matrix_path.exists()
        assert sim_result.communities is not None
        assert sim_result.centrality is not None
