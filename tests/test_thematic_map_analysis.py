from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.corpus import Corpus


def _read_semicolon_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _make_corpus_with_expressions(include_expressions: bool = True) -> MagicMock:
    corpus = MagicMock(spec=Corpus)
    words = [
        "inteligencia_artificial" if include_expressions else "inteligencia",
        "aprendizado_maquina" if include_expressions else "aprendizado",
        "saude_publica" if include_expressions else "saude",
        "politica_publica" if include_expressions else "politica",
        "dados",
        "modelo",
        "hospital",
        "governo",
    ]
    corpus.formes = {}
    corpus.lems = {}
    for word in words:
        item = MagicMock()
        item.forme = word
        item.lem = word
        item.freq = 5
        item.act = 1
        corpus.formes[word] = item
        corpus.lems[word] = item

    texts = [
        (0, f"{words[0]} dados modelo {words[1]} dados"),
        (1, f"{words[0]} modelo {words[1]} dados"),
        (2, f"{words[2]} hospital governo {words[3]}"),
        (3, f"{words[2]} {words[3]} governo hospital"),
    ]
    ucis = []
    for idx, (uce_id, _text) in enumerate(texts):
        uci = MagicMock()
        uci.ident = idx
        uci.paras = {"title": f"Doc_{idx}"}
        uce = MagicMock()
        uce.ident = uce_id
        uci.uces = [uce]
        ucis.append(uci)
    corpus.ucis = ucis
    corpus.get_uces = MagicMock(return_value=texts)
    corpus.getconcorde = MagicMock(side_effect=lambda ids: [(uid, txt) for uid, txt in texts if uid in ids])
    corpus.lexicon = None
    corpus.parametres = {}
    return corpus


def _make_dense_bridge_corpus() -> MagicMock:
    corpus = MagicMock(spec=Corpus)
    core_terms = [f"tema_{idx}" for idx in range(18)]
    bridge_terms = ["lembrar", "garantir", "baixo", "uso", "estrutura", "mudanca"]
    all_terms = core_terms + bridge_terms

    corpus.formes = {}
    corpus.lems = {}
    for word in all_terms:
        item = MagicMock()
        item.forme = word
        item.lem = word
        item.freq = 8
        item.act = 1
        corpus.formes[word] = item
        corpus.lems[word] = item

    texts: list[tuple[int, str]] = []
    uid = 0
    for idx in range(24):
        first = core_terms[idx % len(core_terms)]
        second = core_terms[(idx + 1) % len(core_terms)]
        third = core_terms[(idx + 2) % len(core_terms)]
        texts.append((uid, f"{first} {second} {third} {first} {second}"))
        uid += 1

    texts.extend(
        [
            (uid, "tema_0 lembrar tema_1 lembrar"),
            (uid + 1, "tema_2 garantir tema_3 garantir"),
            (uid + 2, "baixo uso baixo uso"),
            (uid + 3, "estrutura mudanca estrutura mudanca"),
        ]
    )

    ucis = []
    for idx, (uce_id, _text) in enumerate(texts):
        uci = MagicMock()
        uci.ident = idx
        uci.paras = {"title": f"Doc_{idx}"}
        uce = MagicMock()
        uce.ident = uce_id
        uci.uces = [uce]
        ucis.append(uci)

    corpus.ucis = ucis
    corpus.get_uces = MagicMock(return_value=texts)
    corpus.getconcorde = MagicMock(side_effect=lambda ids: [(uid, txt) for uid, txt in texts if uid in ids])
    corpus.lexicon = None
    corpus.parametres = {}
    return corpus


def test_thematic_map_uses_filtered_terms_without_prepared_multiwords(tmp_path) -> None:
    from src.analysis.thematic_map_analysis import ThematicMapAnalysis, ThematicMapParams

    result = ThematicMapAnalysis().run(
        _make_corpus_with_expressions(include_expressions=False),
        tmp_path,
        ThematicMapParams(min_freq=1, min_cooc=1, top_edges=20, max_nodes=40),
    )

    summary = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary["source_mode"] == "filtered_terms"
    assert "sem expressões compostas" in summary["interpretation_note"].lower()
    assert result.strategic_map_image_path.exists()


def test_thematic_map_falls_back_when_matrix_cooccurrence_is_too_sparse(tmp_path) -> None:
    from src.analysis.thematic_map_analysis import ThematicMapAnalysis, ThematicMapParams

    result = ThematicMapAnalysis().run(
        _make_corpus_with_expressions(include_expressions=False),
        tmp_path,
        ThematicMapParams(min_freq=1, min_cooc=99, top_edges=20, max_nodes=40),
    )

    summary = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary["source_mode"] == "filtered_terms"
    assert summary["network_fallback"] in {"relaxed_cooccurrence", "sequential_window"}
    assert result.n_edges >= 1
    assert result.strategic_map_image_path.exists()


def test_thematic_map_generates_network_communities_and_strategy(tmp_path) -> None:
    from src.analysis.thematic_map_analysis import ThematicMapAnalysis, ThematicMapParams

    result = ThematicMapAnalysis().run(
        _make_corpus_with_expressions(include_expressions=True),
        tmp_path,
        ThematicMapParams(min_freq=1, min_cooc=1, top_edges=20, max_nodes=40),
    )

    assert result.analysis_type == "thematic_map"
    assert result.expression_network_image_path.exists()
    assert result.strategic_map_image_path.exists()
    assert result.nodes_csv_path.exists()
    assert result.edges_csv_path.exists()
    assert result.communities_csv_path.exists()
    assert result.strategic_map_csv_path.exists()
    assert result.representative_sentences_csv_path.exists()

    summary = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary["source_mode"] == "expressions"
    assert summary["multiword_expression_count"] >= 4
    assert summary["community_count"] >= 1
    assert summary["community_legend"]
    assert all(str(item["community_code"]).startswith("C") for item in summary["community_legend"])
    assert all(str(item["community_code"]).startswith("C") for item in summary["communities"])
    assert summary["representative_sentences_count"] >= 1
    assert "Temas motores" in {item["quadrant"] for item in summary["communities"]}


def test_thematic_map_removes_isolates_created_by_node_budget(tmp_path) -> None:
    from src.analysis.thematic_map_analysis import ThematicMapAnalysis, ThematicMapParams

    result = ThematicMapAnalysis().run(
        _make_dense_bridge_corpus(),
        tmp_path,
        ThematicMapParams(min_freq=1, min_cooc=1, top_edges=80, max_nodes=12, max_features=80),
    )

    node_rows = _read_semicolon_csv(result.nodes_csv_path)
    assert node_rows
    assert all(float(row["degree_centrality"]) > 0.0 for row in node_rows)

    community_rows = _read_semicolon_csv(result.communities_csv_path)
    assert all(int(row["n_nodes"]) >= 2 for row in community_rows)

    summary = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert summary["n_nodes"] == result.n_nodes
    assert summary["isolated_nodes_removed"] >= 0
    assert summary["network_component_count"] >= 1


def test_thematic_map_network_labels_all_visible_nodes(tmp_path) -> None:
    from src.analysis.thematic_map_analysis import ThematicMapAnalysis, ThematicMapParams

    result = ThematicMapAnalysis().run(
        _make_dense_bridge_corpus(),
        tmp_path,
        ThematicMapParams(min_freq=1, min_cooc=1, top_edges=120, max_nodes=80, max_features=120),
    )

    meta_path = result.expression_network_image_path.with_name("expression_network_render_meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta["n_nodes"] == result.n_nodes
    assert meta["n_labels_rendered"] == result.n_nodes
    assert meta["n_labels_hidden"] == 0


def test_strategic_map_spreads_close_points_without_changing_metrics() -> None:
    from src.analysis.thematic_map_analysis import _spread_strategic_display_coordinates

    rows = [
        {
            "community_id": 1,
            "community_code": "C1",
            "label": "a",
            "n_nodes": 5,
            "n_expressions": 0,
            "centrality": 0.0200,
            "density": 0.7000,
            "top_terms": "a",
            "quadrant": "Temas básicos",
        },
        {
            "community_id": 2,
            "community_code": "C2",
            "label": "b",
            "n_nodes": 5,
            "n_expressions": 0,
            "centrality": 0.0201,
            "density": 0.7001,
            "top_terms": "b",
            "quadrant": "Temas básicos",
        },
        {
            "community_id": 3,
            "community_code": "C3",
            "label": "c",
            "n_nodes": 5,
            "n_expressions": 0,
            "centrality": 0.0202,
            "density": 0.7002,
            "top_terms": "c",
            "quadrant": "Temas básicos",
        },
    ]

    original_metrics = [(row["centrality"], row["density"], row["quadrant"]) for row in rows]
    spread = _spread_strategic_display_coordinates(rows)

    assert [(row["centrality"], row["density"], row["quadrant"]) for row in spread] == original_metrics
    assert all("display_centrality" in row for row in spread)
    assert all("display_density" in row for row in spread)

    display_pairs = {(row["display_centrality"], row["display_density"]) for row in spread}
    assert len(display_pairs) == len(spread)
    assert any(
        row["display_centrality"] != row["centrality"] or row["display_density"] != row["density"]
        for row in spread
    )
