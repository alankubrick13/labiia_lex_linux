"""Tests for the R-only keyness backend wrapper."""

from __future__ import annotations

import json
from pathlib import Path

from src.analysis.keyness_r import KeynessRAnalysis


class _DummyRunner:
    def run_script(self, script_name, args, timeout=240):
        assert script_name == "keyness_quanteda.R"
        Path(args["output_csv"]).write_text(
            (
                "term;keyness_score;p_value;target_count;reference_count;norm_a;norm_b;direction\n"
                "analise;10.0;0.001;10;2;5000.0;900.0;A\n"
                "dados;-8.0;0.010;3;9;1500.0;4100.0;B\n"
            ),
            encoding="utf-8",
        )
        Path(args["output_plot"]).write_bytes(b"PNG")
        Path(args["output_summary"]).write_text(
            json.dumps({"tokens_a": 200, "tokens_b": 220, "rows": 2}),
            encoding="utf-8",
        )
        return "ok"


def test_keyness_r_run_with_dummy_runner(tmp_path):
    analysis = KeynessRAnalysis(tmp_path / "keyness_r", runner=_DummyRunner())
    result = analysis.run(
        text_a="texto analise analise",
        text_b="texto dados dados",
        name_a="A",
        name_b="B",
        params={"min_freq": 1, "top_n": 10, "measure": "lr"},
    )

    assert result.table_path is not None and result.table_path.exists()
    assert result.graph_path is not None and result.graph_path.exists()
    assert result.total_a == 200
    assert result.total_b == 220
    assert len(result.rows) == 2
    assert result.key_in_a[0].word == "analise"


def test_keyness_r_export_csv(tmp_path):
    analysis = KeynessRAnalysis(tmp_path / "keyness_r_export", runner=_DummyRunner())
    result = analysis.run("aaa", "bbb", params={"min_freq": 1, "top_n": 10})
    out = tmp_path / "export.csv"
    KeynessRAnalysis.export_csv(result, out, metric="statistic")
    content = out.read_text(encoding="utf-8")
    assert "term" in content
    assert "analise" in content
