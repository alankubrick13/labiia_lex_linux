"""Unit tests for textual network analysis."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.layout_backends import GephiJavaBackendError, GephiJavaBackendResult
from src.core.corpus import Corpus


def _mock_backend_layout(graph, params, output_dir):
    nodes = sorted(graph.nodes())
    positions = {}
    total = max(len(nodes), 1)
    for idx, node in enumerate(nodes):
        angle = (2.0 * math.pi * idx) / total
        positions[node] = (math.cos(angle), math.sin(angle))

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    diag_path = output / "layout_diag.json"
    diag_path.write_text(
        '{"backend":"gephi_java","fa2_elapsed_sec":0.11,"noverlap_elapsed_sec":0.02}',
        encoding="utf-8",
    )
    return GephiJavaBackendResult(
        positions=positions,
        diagnostics={
            "backend": "gephi_java",
            "fa2_elapsed_sec": 0.11,
            "noverlap_elapsed_sec": 0.02,
        },
        diagnostics_path=diag_path,
    )


@pytest.fixture
def sample_corpus():
    """Create a compact corpus with enough co-occurrence structure."""
    corpus = Corpus({"ucemethod": 0, "ucesize": 100})
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "network_test.db"
        corpus.connect(db_path)
        corpus.add_uci("**** *doc_1 *group_a")
        corpus.add_uci("**** *doc_2 *group_b")
        corpus.add_uce(0, 0, "analise texto qualitativa pesquisa dados metodo")
        corpus.add_uce(0, 0, "pesquisa qualitativa estudo caso metodo dados")
        corpus.add_uce(1, 0, "analise quantitativa estatistica dados numeros")
        corpus.add_uce(1, 0, "estatistica analise dados quantitativa resultados")
        for word in [
            "analise",
            "texto",
            "qualitativa",
            "pesquisa",
            "dados",
            "metodo",
            "estudo",
            "caso",
            "quantitativa",
            "estatistica",
            "numeros",
            "resultados",
        ]:
            corpus.add_word(word, gram="noun", lem=word)
        yield corpus
        corpus.close()


@pytest.fixture
def dense_corpus():
    """Create a deliberately dense corpus to validate auto tuning."""
    corpus = Corpus({"ucemethod": 0, "ucesize": 120})
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dense_network_test.db"
        corpus.connect(db_path)
        corpus.add_uci("**** *doc_dense")
        terms = [f"termo{i}" for i in range(1, 46)]
        for _ in range(30):
            corpus.add_uce(0, 0, " ".join(terms))
        for token in terms:
            corpus.add_word(token, gram="noun", lem=token)
        yield corpus
        corpus.close()


def test_network_builds_graph_metrics_and_diagnostics(monkeypatch, sample_corpus):
    from src.analysis.network_text_analysis import NetworkTextAnalysis

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _mock_backend_layout,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = NetworkTextAnalysis(sample_corpus, tmpdir).run(
            {
                "min_freq": 1,
                "max_nodes": 120,
                "stopword_policy": "legacy",
                "strict_stopword_filter": False,
            }
        )
        assert result.n_nodes > 0
        assert result.n_edges > 0
        assert result.average_degree > 0
        assert isinstance(result.report_data, dict)
        assert result.layout_backend_used == "gephi_java"
        assert result.diagnostics_path is not None and result.diagnostics_path.exists()


def test_network_exports_csv_gexf_and_net(monkeypatch, sample_corpus):
    from src.analysis.network_text_analysis import NetworkTextAnalysis

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _mock_backend_layout,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = NetworkTextAnalysis(sample_corpus, tmpdir).run(
            {
                "min_freq": 1,
                "export_csv": True,
                "export_gexf": True,
                "export_net": True,
                "stopword_policy": "legacy",
                "strict_stopword_filter": False,
            }
        )
        assert result.nodes_csv_path is not None and result.nodes_csv_path.exists()
        assert result.edges_csv_path is not None and result.edges_csv_path.exists()
        assert result.gexf_path is not None and result.gexf_path.exists()
        assert result.net_path is not None and result.net_path.exists()
        net_text = result.net_path.read_text(encoding="utf-8")
        assert "*Vertices" in net_text
        assert "*Edges" in net_text


def test_network_renders_png_and_svg(monkeypatch, sample_corpus):
    from src.analysis.network_text_analysis import NetworkTextAnalysis

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _mock_backend_layout,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = NetworkTextAnalysis(sample_corpus, tmpdir).run(
            {
                "min_freq": 1,
                "typegraph": "both",
                "width": 1200,
                "height": 900,
                "stopword_policy": "legacy",
                "strict_stopword_filter": False,
            }
        )
        assert result.graph_image_path is not None and result.graph_image_path.exists()
        assert result.graph_image_path.stat().st_size > 500
        assert result.graph_svg_path is not None and result.graph_svg_path.exists()


def test_strict_layout_backend_surfaces_backend_error(monkeypatch, sample_corpus):
    from src.analysis.network_text_analysis import NetworkTextAnalysis, NetworkTextAnalysisError

    def _raise_backend(*_args, **_kwargs):
        raise GephiJavaBackendError("Runner Gephi nao encontrado")

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _raise_backend,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(NetworkTextAnalysisError):
            NetworkTextAnalysis(sample_corpus, tmpdir).run(
                {
                    "min_freq": 1,
                    "stopword_policy": "legacy",
                    "strict_stopword_filter": False,
                    "strict_layout_backend": True,
                }
            )


def test_aggressive_stopword_policy_removes_functional_hubs(monkeypatch):
    from src.analysis.network_text_analysis import NetworkTextAnalysis

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _mock_backend_layout,
    )

    corpus = Corpus({"ucemethod": 0, "ucesize": 100})
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            db_path = Path(tmpdir) / "stopword_test.db"
            corpus.connect(db_path)
            corpus.add_uci("**** *doc_1")
            corpus.add_uce(
                0,
                0,
                "que com para uma jornalismo analise politica que com para uma pesquisa",
            )
            corpus.add_uce(
                0,
                0,
                "que com para uma jornalismo dados redes que com para uma teoria",
            )
            for token in "que com para uma jornalismo analise politica pesquisa dados redes teoria".split():
                corpus.add_word(token, gram="noun", lem=token)

            result = NetworkTextAnalysis(corpus, tmpdir).run(
                {
                    "min_freq": 1,
                    "max_nodes": 60,
                    "stopword_policy": "aggressive_pt",
                    "strict_stopword_filter": False,
                }
            )
            top_ids = [str(row["id"]).lower() for row in result.nodes_table[:10]]
            assert "que" not in top_ids
            assert "com" not in top_ids
            assert "para" not in top_ids
            assert "uma" not in top_ids
        finally:
            corpus.close()


def test_strict_stopword_filter_falls_back_without_lexicon(monkeypatch, sample_corpus):
    from src.analysis.network_text_analysis import NetworkTextAnalysis

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _mock_backend_layout,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = NetworkTextAnalysis(sample_corpus, tmpdir).run(
            {
                "min_freq": 1,
                "stopword_policy": "aggressive_pt",
                "strict_stopword_filter": True,
            }
        )
        assert result.n_nodes > 0
        diagnostics_path = Path(result.diagnostics_path)
        payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        notes = payload.get("auto_tuning", {}) if isinstance(payload.get("auto_tuning", {}), dict) else {}
        fallback = notes.get("stopword_fallback", {}) if isinstance(notes.get("stopword_fallback", {}), dict) else {}
        assert fallback.get("applied") is True
        assert fallback.get("strict_stopword_filter_effective") is False


def test_auto_tune_reduces_density_on_dense_corpus(monkeypatch, dense_corpus):
    from src.analysis.network_text_analysis import NetworkTextAnalysis

    monkeypatch.setattr(
        "src.analysis.network_text_analysis.run_gephi_java_layout",
        _mock_backend_layout,
    )

    with tempfile.TemporaryDirectory() as tmpdir_a, tempfile.TemporaryDirectory() as tmpdir_b:
        base_params = {
            "min_freq": 1,
            "min_cooc": 1,
            "max_nodes": 300,
            "edge_threshold": 0,
            "stopword_policy": "legacy",
            "strict_stopword_filter": False,
        }
        manual = NetworkTextAnalysis(dense_corpus, tmpdir_a).run(
            {**base_params, "auto_tune": False}
        )
        auto = NetworkTextAnalysis(dense_corpus, tmpdir_b).run(
            {
                **base_params,
                "auto_tune": True,
                "min_freq": 20,
                "min_cooc": 20,
                "edge_threshold": 20,
                "max_nodes": 50,
                "arbremax": True,
            }
        )

        assert auto.n_edges <= manual.n_edges
        assert auto.n_nodes > 0
        assert auto.average_degree >= 2.0
        assert auto.n_edges > auto.n_nodes - 1
        payload = json.loads(Path(auto.diagnostics_path).read_text(encoding="utf-8"))
        assert payload["selected_params"]["arbremax"] is False
        assert "render_plan" in payload["auto_tuning"]
        assert "render_feedback" in payload["auto_tuning"]
        assert (
            "peripheral_reinforcement" in payload["auto_tuning"]
            or "post_graph" in payload["auto_tuning"]
        )
