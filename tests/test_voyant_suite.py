"""Tests for Voyant-inspired suite payload and report generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.voyant_suite import VoyantSuiteAnalysis
from src.core.corpus import Corpus
from src.core.report_generator import ReportGenerator


@pytest.fixture
def voyant_corpus(tmp_path: Path):
    corpus = Corpus({"ucemethod": 1, "ucesize": 40})
    db_path = tmp_path / "voyant_suite.db"
    corpus.connect(db_path)
    try:
        uci_1 = corpus.add_uci("**** *doc_1 *tema_tecnologia")
        uci_2 = corpus.add_uci("**** *doc_2 *tema_politica")

        samples = [
            (uci_1.ident, "mediação ia generativa autor agência texto ética responsabilidade"),
            (uci_1.ident, "mediação texto acadêmico ia agência autoria conhecimento"),
            (uci_1.ident, "generativa mediação modelo linguagem escrita acadêmica"),
            (uci_2.ident, "política pública agência autor decisão argumento texto"),
            (uci_2.ident, "agência mediação regulação ia ética texto"),
            (uci_2.ident, "autor agência mediação conhecimento escrita texto"),
        ]

        para_id = 0
        for uci_id, text in samples:
            uce = corpus.add_uce(uci_id, para_id, text)
            para_id += 1
            for token in text.lower().split():
                corpus.add_word(token, uce_id=uce.ident)
        yield corpus
    finally:
        corpus.close()


def test_voyant_suite_payload_v1_has_fixed_panel_structure(voyant_corpus, tmp_path: Path):
    output_dir = tmp_path / "voyant_out"
    analysis = VoyantSuiteAnalysis(voyant_corpus, output_dir)
    result = analysis.run(
        {
            "query": "mediação ia generativa",
            "mode": "mixed",
            "num_initial_terms": 20,
            "min_freq": 1,
            "bins": 8,
            "context": 4,
            "max_docs": 50,
            "max_context_rows": 500,
            "use_lemmas": True,
            "active_only": True,
            "remove_stopwords": True,
        }
    )

    payload = result.voyant_suite_payload_v1
    assert payload["version"] == "voyant_suite_payload_v1"
    assert payload["graph_tabs"] == [
        "termsberry",
        "trends",
        "document_terms",
        "bubblelines",
        "cooccurrences",
    ]

    graphs = payload["graphs"]
    tables = payload["tables"]
    for panel_id in payload["graph_tabs"]:
        graph_path = Path(str(graphs[panel_id]["image_path"]))
        table_path = Path(str(tables[panel_id]["csv_path"]))
        assert graph_path.exists(), f"graph missing for panel {panel_id}"
        assert table_path.exists(), f"table missing for panel {panel_id}"
        assert tables[panel_id]["row_count"] >= 0

    # Regressao: Trends e Document Terms devem ser artefatos distintos.
    assert graphs["trends"]["image_path"] != graphs["document_terms"]["image_path"]
    assert tables["trends"]["csv_path"] != tables["document_terms"]["csv_path"]

    # Regressao: TermsBerry deve ficar em faixa renderizavel e legivel.
    assert 0 < int(tables["termsberry"]["row_count"]) <= 220

    assert "TermsBerry" in result.graph_gallery
    assert "Tendências" in result.graph_gallery
    assert "Termos do documento" in result.graph_gallery
    assert "Gráfico de bolhas" in result.graph_gallery
    assert "Co-ocorrências" in result.graph_gallery

    assert result.summary_json_path is not None and result.summary_json_path.exists()
    summary = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert "voyant_suite_payload_v1" in summary


def test_voyant_suite_report_contains_all_panels(voyant_corpus, tmp_path: Path):
    output_dir = tmp_path / "voyant_out_report"
    analysis = VoyantSuiteAnalysis(voyant_corpus, output_dir)
    result = analysis.run({"min_freq": 1, "bins": 6, "num_initial_terms": 18})

    generator = ReportGenerator(tmp_path / "reports")
    report_path = generator.generate_voyant_suite_report(
        result=result,
        analysis_name="Pacote Voyant",
        params={"bins": 6, "min_freq": 1},
    )

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Pacote Voyant - Relatório" in content
    assert "TermsBerry" in content
    assert "Tendências" in content
    assert "Termos do documento" in content
    assert "Gráfico de bolhas" in content
    assert "Co-ocorrências" in content
