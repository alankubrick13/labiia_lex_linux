"""Tests for strict Gephi Java backend diagnostics."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import networkx as nx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.layout_backends.gephi_java_backend import GephiJavaBackendError, run_layout


def test_backend_fails_with_clear_error_when_runner_missing(monkeypatch):
    graph = nx.Graph()
    graph.add_edge("a", "b", weight=1.0)

    monkeypatch.setattr(
        "src.analysis.layout_backends.gephi_java_backend._resolve_java_executable",
        lambda: ("java", "system_path"),
    )
    monkeypatch.setattr(
        "src.analysis.layout_backends.gephi_java_backend._resolve_runner_jar",
        lambda: Path("C:/tmp/runner-does-not-exist.jar"),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(GephiJavaBackendError) as exc:
            run_layout(graph=graph, params={}, output_dir=Path(tmpdir))
    assert "runner gephi" in str(exc.value).lower()
