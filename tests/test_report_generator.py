"""Tests for HTML report generation."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.report_generator import ReportGenerator


class _DummyChi2:
    row_var = "grupo"
    col_var = "sexo"
    chi2 = 4.2
    dof = 2
    p_value = 0.12

    def __init__(self, graph_path: Path, contingency: Path, expected: Path, residuals: Path):
        self.graph_path = graph_path
        self.contingency_csv_path = contingency
        self.expected_csv_path = expected
        self.residuals_csv_path = residuals


def test_generate_statistics_report_with_graphs():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        png = out / "zipf.png"
        png.write_bytes(b"fakepng")
        generator = ReportGenerator(out)
        report = generator.generate_statistics_report(
            stats={"total_ucis": 3, "total_uces": 7},
            graphs={"zipf": png},
            analysis_name="Estatísticas",
            params={"min_freq": 3},
        )

        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "Estatísticas - Relatório" in content
        assert "total_ucis" in content
        assert "data:image/png;base64" in content


def test_generate_chi2_and_generic_reports():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        graph = out / "chi2.png"
        graph.write_bytes(b"png")

        contingency = out / "cont.csv"
        expected = out / "exp.csv"
        residuals = out / "res.csv"
        contingency.write_text("a;b\n1;2\n", encoding="utf-8")
        expected.write_text("a;b\n1;2\n", encoding="utf-8")
        residuals.write_text("a;b\n0.1;0.2\n", encoding="utf-8")

        generator = ReportGenerator(out)
        chi2_report = generator.generate_chi2_report(
            _DummyChi2(graph, contingency, expected, residuals),
            analysis_name="Qui-Quadrado (Matriz)",
            params={"row_var": "grupo", "col_var": "sexo"},
        )
        assert chi2_report.exists()
        chi2_content = chi2_report.read_text(encoding="utf-8")
        assert "Qui-Quadrado (Matriz) - Relatório" in chi2_content
        assert "Resumo Estatístico" in chi2_content

        generic_report = generator.generate_generic_report(
            analysis_name="Similitude",
            analysis_type="similarity",
            params={"layout": "fruchterman"},
            result={"backend_used": "python+r"},
            result_path=graph,
        )
        assert generic_report.exists()
        generic_content = generic_report.read_text(encoding="utf-8")
        assert "Similitude - Relatório" in generic_content


def test_generate_voyant_suite_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        img = out / "panel.png"
        img.write_bytes(b"png")
        csv_path = out / "panel.csv"
        csv_path.write_text("a;b\n1;2\n", encoding="utf-8")

        class _DummyVoyant:
            voyant_suite_payload_v1 = {
                "version": "voyant_suite_payload_v1",
                "graph_tabs": [
                    "termsberry",
                    "trends",
                    "document_terms",
                    "bubblelines",
                    "cooccurrences",
                ],
                "graphs": {
                    "termsberry": {"title_pt": "TermsBerry", "image_path": str(img), "stats": {"nodes": 10}},
                    "trends": {"title_pt": "Tendências", "image_path": str(img), "stats": {"segments": 10}},
                    "document_terms": {"title_pt": "Termos do documento", "image_path": str(img), "stats": {"terms": 20}},
                    "bubblelines": {"title_pt": "Gráfico de bolhas", "image_path": str(img), "stats": {"documents": 3}},
                    "cooccurrences": {"title_pt": "Co-ocorrências", "image_path": str(img), "stats": {"pairs": 12}},
                },
                "tables": {
                    "termsberry": {"title_pt": "TermsBerry", "csv_path": str(csv_path)},
                    "trends": {"title_pt": "Tendências", "csv_path": str(csv_path)},
                    "document_terms": {"title_pt": "Termos do documento", "csv_path": str(csv_path)},
                    "bubblelines": {"title_pt": "Gráfico de bolhas", "csv_path": str(csv_path)},
                    "cooccurrences": {"title_pt": "Co-ocorrências", "csv_path": str(csv_path)},
                },
                "meta": {"doc_count": 2, "tokens": 120},
            }

        generator = ReportGenerator(out)
        report = generator.generate_voyant_suite_report(
            result=_DummyVoyant(),
            analysis_name="Pacote Voyant",
            params={"bins": 10},
        )
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "Pacote Voyant - Relatório" in content
        assert "TermsBerry" in content
        assert "Tendências" in content


def test_generate_generic_report_collects_multiple_artifacts():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        graph = out / "similarity.png"
        table = out / "centrality.csv"
        text = out / "run.log"
        graph.write_bytes(b"png")
        table.write_text("n;v\na;1\n", encoding="utf-8")
        text.write_text("ok", encoding="utf-8")

        class _DummyResult:
            graph_path = graph
            centrality_path = table
            diagnostics_path = text
            n_nodes = 12

        generator = ReportGenerator(out)
        report = generator.generate_generic_report(
            analysis_name="Similitude",
            analysis_type="similarity",
            params={"layout": "fruchterman"},
            result=_DummyResult(),
            result_path=graph,
        )

        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "Visualizações" in content
        assert "Tabelas" in content
        assert "Saídas textuais" in content
        assert "data:image/png;base64" in content
        assert "centrality" in content.lower()


def test_generate_generic_report_collects_net_artifact_as_text():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        net_path = out / "network.net"
        net_path.write_text("*Vertices 1\n1 \"teste\"\n*Edges\n", encoding="utf-8")

        class _DummyResult:
            n_nodes = 1

        dummy = _DummyResult()
        dummy.net_path = net_path

        generator = ReportGenerator(out)
        report = generator.generate_generic_report(
            analysis_name="Rede Textual",
            analysis_type="network_text",
            params={"export_net": True},
            result=dummy,
            result_path=None,
        )

        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "Saídas textuais" in content
        assert "net path" in content.lower() or "network.net" in content.lower()
