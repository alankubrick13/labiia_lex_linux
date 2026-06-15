"""Renderer regression tests for textual network plots."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.network_text_renderer import render_network
import src.analysis.network_text_renderer as renderer_mod


def test_label_adjust_does_not_mutate_anchor_positions():
    graph = nx.Graph()
    graph.add_edge("analise", "dados", weight=5.0)
    graph.add_edge("analise", "politica", weight=4.0)
    graph.add_edge("dados", "politica", weight=3.0)

    positions = {
        "analise": (0.0, 0.0),
        "dados": (1.0, 0.5),
        "politica": (0.5, 1.0),
    }
    original = dict(positions)
    nodes_table = [
        {"id": "analise", "degree": 2, "weighted_degree": 9, "community": 0},
        {"id": "dados", "degree": 2, "weighted_degree": 8, "community": 0},
        {"id": "politica", "degree": 2, "weighted_degree": 7, "community": 1},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        png, _svg = render_network(
            graph=graph,
            positions=positions,
            nodes_table=nodes_table,
            output_path=Path(tmpdir) / "network_text",
            params={
                "typegraph": "png",
                "label_adjust": True,
                "show_halos": False,
                "show_edges": True,
            },
        )
        assert png is not None and png.exists()

    assert positions == original


def test_view_framing_params_are_forwarded_to_axis_limits():
    graph = nx.Graph()
    graph.add_edge("a", "b", weight=1.0)
    graph.add_edge("b", "c", weight=1.0)
    positions = {"a": (0.0, 0.0), "b": (1.0, 0.0), "c": (0.5, 1.0)}
    nodes_table = [
        {"id": "a", "degree": 1, "weighted_degree": 1, "community": 0},
        {"id": "b", "degree": 2, "weighted_degree": 2, "community": 0},
        {"id": "c", "degree": 1, "weighted_degree": 1, "community": 1},
    ]

    calls = []
    original = renderer_mod._set_axis_limits_from_points

    def _spy(ax, points, pad_ratio, trim_quantile=0.0):
        calls.append((float(pad_ratio), float(trim_quantile), len(points)))
        return original(ax, points, pad_ratio, trim_quantile=trim_quantile)

    renderer_mod._set_axis_limits_from_points = _spy
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            png, _svg = render_network(
                graph=graph,
                positions=positions,
                nodes_table=nodes_table,
                output_path=Path(tmpdir) / "network_text",
                params={
                    "typegraph": "png",
                    "view_trim_quantile": 0.07,
                    "view_pad_ratio_initial": 0.09,
                    "view_pad_ratio_final": 0.04,
                    "show_edges": True,
                    "label_adjust": False,
                },
            )
            assert png is not None and png.exists()
    finally:
        renderer_mod._set_axis_limits_from_points = original

    assert len(calls) >= 2
    assert calls[0][0] == 0.09
    assert calls[0][1] == 0.07
    assert calls[-1][0] == 0.04
    assert calls[-1][1] == 0.07
