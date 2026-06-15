"""Thematic map from prepared multiword expressions and association communities."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.analysis.association_metrics import AssociationPair, build_cooccurrence_matrix, compute_ppmi, rank_association_pairs
from src.analysis.semantic_contracts import ArtifactManifest, BaseSemanticParams, BaseSemanticResult, SemanticAnalysisError
from src.analysis.extractive_summary import (
    community_targets_from_rows,
    rank_representative_sentences,
    sentences_from_bundle,
    write_representative_sentences_csv,
)
from src.analysis.semantic_graph_exports import GraphEdge, GraphNode, write_edges_csv, write_nodes_csv
from src.analysis.semantic_text_base import SemanticTextBundle
from src.core.chart_theme import create_figure, draw_legend_panel, ggplot_hue, save_figure, style_axes
from src.core.corpus import Corpus
from src.analysis.readable_network_plot import write_readable_network_plot


@dataclass(slots=True, kw_only=True)
class ThematicMapParams(BaseSemanticParams):
    min_freq: int = 2
    max_features: int = 300
    top_edges: int = 160
    max_nodes: int = 120
    min_cooc: int = 2
    alpha: float = 0.75
    use_lemmas: bool = True

    def __post_init__(self) -> None:
        self.min_freq = max(1, int(self.min_freq))
        self.max_features = max(20, int(self.max_features))
        self.top_edges = max(10, int(self.top_edges))
        self.max_nodes = max(10, int(self.max_nodes))
        self.min_cooc = max(1, int(self.min_cooc))
        self.alpha = max(0.1, min(1.0, float(self.alpha)))
        self.use_lemmas = bool(self.use_lemmas)


@dataclass(slots=True, kw_only=True)
class ThematicMapResult(BaseSemanticResult):
    expression_network_image_path: Path
    strategic_map_image_path: Path
    nodes_csv_path: Path
    edges_csv_path: Path
    communities_csv_path: Path
    strategic_map_csv_path: Path
    representative_sentences_csv_path: Path
    summary_json_path: Path
    n_nodes: int
    n_edges: int
    community_count: int

    def primary_image_path(self) -> Optional[Path]:
        return self.strategic_map_image_path

    def primary_table_path(self) -> Optional[Path]:
        return self.communities_csv_path

    def artifact_manifest(self) -> ArtifactManifest:
        return ArtifactManifest(
            primary_image=self.primary_image_path(),
            primary_table=self.primary_table_path(),
            summary_json=self.summary_json_path,
            secondary_images=[self.expression_network_image_path],
            secondary_tables=[
                self.nodes_csv_path,
                self.edges_csv_path,
                self.strategic_map_csv_path,
                self.representative_sentences_csv_path,
            ],
        )

    def to_history_metadata(self) -> Dict[str, object]:
        meta = super().to_history_metadata()
        meta.update(
            {
                "graph_gallery": {
                    "Mapa Estratégico": str(self.strategic_map_image_path),
                    "Rede de Expressões": str(self.expression_network_image_path),
                },
                "table_gallery": {
                    "Comunidades Temáticas": str(self.communities_csv_path),
                    "Nós": str(self.nodes_csv_path),
                    "Arestas": str(self.edges_csv_path),
                    "Mapa Estratégico": str(self.strategic_map_csv_path),
                    "Frases Representativas": str(self.representative_sentences_csv_path),
                },
                "n_nodes": self.n_nodes,
                "n_edges": self.n_edges,
                "community_count": self.community_count,
            }
        )
        return meta


class ThematicMapAnalysis:
    """Build expression network, communities, and strategic map."""

    def run(self, corpus: Corpus, output_dir: Path, params: ThematicMapParams) -> ThematicMapResult:
        import networkx as nx

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=params.min_freq,
            use_lemmas=params.use_lemmas,
            max_features=params.max_features,
        )
        matrix_bundle = bundle.uce_term_matrix
        if matrix_bundle is None or matrix_bundle.matrix.shape[1] < 2:
            raise SemanticAnalysisError(
                "Vocabulário insuficiente.",
                "O mapa temático precisa de pelo menos 2 termos válidos.",
                "Reduza a frequência mínima ou use um corpus maior.",
            )

        expressions = {term for term in matrix_bundle.vocabulary if "_" in str(term)}
        source_mode = "expressions" if expressions else "filtered_terms"
        interpretation_note = (
            "Este mapa usa expressões compostas preparadas na etapa Preparar corpus."
            if expressions
            else "Este mapa foi gerado sem expressões compostas preparadas; ele usa termos filtrados do corpus."
        )

        cooc = build_cooccurrence_matrix(matrix_bundle.matrix)
        ppmi = compute_ppmi(cooc, alpha=params.alpha)
        ranked_pairs = rank_association_pairs(
            cooc=cooc,
            ppmi=ppmi,
            vocabulary=matrix_bundle.vocabulary,
            top_n=params.top_edges * 3,
            min_cooc=params.min_cooc,
        )
        if expressions:
            selected_pairs = [
                pair for pair in ranked_pairs if pair.term_a in expressions or pair.term_b in expressions
            ][: params.top_edges]
        else:
            selected_pairs = ranked_pairs[: params.top_edges]
        network_fallback = "none"
        if not selected_pairs:
            relaxed_pairs = rank_association_pairs(
                cooc=cooc,
                ppmi=ppmi,
                vocabulary=matrix_bundle.vocabulary,
                top_n=params.top_edges * 3,
                min_cooc=1,
            )
            if expressions:
                selected_pairs = [
                    pair for pair in relaxed_pairs if pair.term_a in expressions or pair.term_b in expressions
                ][: params.top_edges]
            else:
                selected_pairs = relaxed_pairs[: params.top_edges]
            if selected_pairs:
                network_fallback = "relaxed_cooccurrence"
        if not selected_pairs:
            selected_pairs = _rank_sequential_window_pairs(
                bundle,
                matrix_bundle.vocabulary,
                top_n=params.top_edges,
                use_lemmas=params.use_lemmas,
            )
            if selected_pairs:
                network_fallback = "sequential_window"
        if not selected_pairs:
            raise SemanticAnalysisError(
                "Rede temática vazia.",
                "Mesmo o fallback com termos filtrados não encontrou relações mínimas entre palavras.",
                "Reduza a frequência mínima ou use um corpus maior.",
            )

        raw_graph = nx.Graph()
        for pair in selected_pairs:
            raw_graph.add_edge(
                str(pair.term_a),
                str(pair.term_b),
                weight=float(pair.ppmi),
                cooccurrence=int(pair.cooccurrence),
            )

        legacy_trimmed_graph = raw_graph
        if legacy_trimmed_graph.number_of_nodes() > params.max_nodes:
            strengths = dict(legacy_trimmed_graph.degree(weight="weight"))
            keep = {
                node
                for node, _score in sorted(
                    strengths.items(),
                    key=lambda item: (float(item[1]), str(item[0])),
                    reverse=True,
                )[: params.max_nodes]
            }
            legacy_trimmed_graph = legacy_trimmed_graph.subgraph(keep).copy()
        legacy_isolates = list(nx.isolates(legacy_trimmed_graph))

        graph, skipped_edges_by_node_budget = _build_budgeted_graph(
            selected_pairs,
            max_nodes=params.max_nodes,
        )
        isolated_nodes_removed = len(legacy_isolates)

        if graph.number_of_edges() <= 0 or graph.number_of_nodes() < 2:
            raise SemanticAnalysisError(
                "Rede temática vazia.",
                "Os filtros e o limite de nós removeram todas as relações temáticas exibíveis.",
                "Aumente o máximo de nós, reduza a coocorrência mínima ou use um corpus maior.",
            )

        component_sizes = [len(component) for component in nx.connected_components(graph)]
        network_component_count = len(component_sizes)
        largest_component_ratio = (
            max(component_sizes) / float(graph.number_of_nodes())
            if component_sizes and graph.number_of_nodes() > 0
            else 0.0
        )

        communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
        if not communities:
            communities = [set(graph.nodes())]
        communities = [
            set(community)
            for community in communities
            if len(set(community)) >= 2 or any(graph.degree(node) > 0 for node in community)
        ]
        if not communities:
            communities = [set(graph.nodes())]
        community_by_node: Dict[str, int] = {}
        for idx, community in enumerate(communities):
            for node in community:
                if node in graph:
                    community_by_node[str(node)] = idx

        degree = nx.degree_centrality(graph)
        betweenness = nx.betweenness_centrality(graph, weight="weight", normalized=True) if graph.number_of_nodes() > 2 else {n: 0.0 for n in graph.nodes()}
        nodes = [
            GraphNode(
                node_id=str(node),
                label=str(node),
                frequency=int(matrix_bundle.matrix[:, matrix_bundle.word_to_idx[str(node)]].sum()) if str(node) in matrix_bundle.word_to_idx else 0,
                degree_centrality=float(degree.get(node, 0.0)),
                betweenness_centrality=float(betweenness.get(node, 0.0)),
                community_id=int(community_by_node.get(str(node), 0)),
                node_type="expression" if str(node) in expressions else "term",
                label_priority=float(graph.degree(node, weight="weight")),
                is_representative_label=False,
            )
            for node in graph.nodes()
        ]
        edges = [
            GraphEdge(
                source=str(u),
                target=str(v),
                cooccurrence=int(data.get("cooccurrence", 0)),
                association_weight=float(data.get("weight", 0.0)),
                edge_type="expression_association",
            )
            for u, v, data in graph.edges(data=True)
        ]
        community_rows = _community_rows(graph, communities, expressions)
        display_community_rows = _spread_strategic_display_coordinates(community_rows)

        nodes_csv = output_dir / "expression_nodes.csv"
        edges_csv = output_dir / "expression_edges.csv"
        communities_csv = output_dir / "thematic_communities.csv"
        strategic_csv = output_dir / "strategic_map.csv"
        representative_csv = output_dir / "thematic_representative_sentences.csv"
        network_png = output_dir / "expression_network.png"
        strategic_png = output_dir / "strategic_map.png"
        summary_json = output_dir / "thematic_map_summary.json"

        write_nodes_csv(nodes, nodes_csv)
        write_edges_csv(edges, edges_csv)
        _write_rows_csv(communities_csv, display_community_rows)
        _write_rows_csv(strategic_csv, display_community_rows)
        _write_network_plot(graph, community_by_node, network_png)
        _write_strategic_plot(display_community_rows, strategic_png)
        representative_sentences = rank_representative_sentences(
            sentences_from_bundle(bundle, use_lemmas=params.use_lemmas),
            targets=community_targets_from_rows(display_community_rows),
            per_target=3,
        )
        write_representative_sentences_csv(representative_csv, representative_sentences)
        community_legend = [
            {
                "community_code": str(row.get("community_code", f"C{row.get('community_id', idx)}")),
                "label": str(row.get("label", "")),
                "top_terms": str(row.get("top_terms", "")),
                "n_nodes": int(row.get("n_nodes", 0) or 0),
                "quadrant": str(row.get("quadrant", "")),
            }
            for idx, row in enumerate(community_rows)
        ]
        summary_payload = {
            "analysis_type": "thematic_map",
            "source_mode": source_mode,
            "interpretation_note": interpretation_note,
            "multiword_expression_count": len(expressions),
            "n_nodes": graph.number_of_nodes(),
            "n_edges": graph.number_of_edges(),
            "community_count": len(community_rows),
            "network_fallback": network_fallback,
            "raw_network_nodes": int(raw_graph.number_of_nodes()),
            "raw_network_edges": int(raw_graph.number_of_edges()),
            "skipped_edges_by_node_budget": int(skipped_edges_by_node_budget),
            "isolated_nodes_removed": int(isolated_nodes_removed),
            "network_component_count": int(network_component_count),
            "largest_component_ratio": round(float(largest_component_ratio), 6),
            "network_labels_hidden": 0,
            "communities": display_community_rows,
            "community_legend": community_legend,
            "representative_sentences_count": len(representative_sentences),
            "representative_sentences": representative_sentences[:30],
        }
        summary_json.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return ThematicMapResult(
            analysis_type="thematic_map",
            output_dir=output_dir,
            expression_network_image_path=network_png,
            strategic_map_image_path=strategic_png,
            nodes_csv_path=nodes_csv,
            edges_csv_path=edges_csv,
            communities_csv_path=communities_csv,
            strategic_map_csv_path=strategic_csv,
            representative_sentences_csv_path=representative_csv,
            summary_json_path=summary_json,
            n_nodes=graph.number_of_nodes(),
            n_edges=graph.number_of_edges(),
            community_count=len(community_rows),
        )


def _rank_sequential_window_pairs(
    bundle: SemanticTextBundle,
    vocabulary: Sequence[str],
    *,
    top_n: int,
    use_lemmas: bool,
    window: int = 4,
) -> List[AssociationPair]:
    """Build a light fallback network from nearby filtered terms in text order."""
    vocab_set = {str(term) for term in vocabulary}
    counts: Counter[tuple[str, str]] = Counter()
    for segment in bundle.segments:
        raw_terms = segment.lemmas if use_lemmas else segment.tokens
        terms = [str(term) for term in raw_terms if str(term) in vocab_set]
        if len(terms) < 2:
            continue
        for idx, first in enumerate(terms):
            upper = min(len(terms), idx + max(2, int(window)))
            for second in terms[idx + 1 : upper]:
                if first == second:
                    continue
                pair = tuple(sorted((first, second)))
                counts[pair] += 1

    rows = [
        AssociationPair(
            term_a=first,
            term_b=second,
            cooccurrence=int(freq),
            ppmi=float(freq),
            doc_count=int(freq),
        )
        for (first, second), freq in counts.items()
        if int(freq) > 0
    ]
    rows.sort(key=lambda row: (-float(row.ppmi), row.term_a, row.term_b))
    return rows[: max(1, int(top_n))]


def _build_budgeted_graph(
    pairs: Sequence[AssociationPair],
    *,
    max_nodes: int,
) -> tuple[Any, int]:
    """Build a graph from ranked pairs without creating post-trim isolates."""
    import networkx as nx

    graph = nx.Graph()
    max_nodes = max(2, int(max_nodes))

    ranked = sorted(
        pairs,
        key=lambda pair: (-float(pair.ppmi), -int(pair.cooccurrence), str(pair.term_a), str(pair.term_b)),
    )

    skipped_by_budget = 0
    for pair in ranked:
        first = str(pair.term_a)
        second = str(pair.term_b)
        if not first or not second or first == second:
            continue

        new_nodes = {node for node in (first, second) if node not in graph}
        if graph.number_of_nodes() + len(new_nodes) > max_nodes:
            skipped_by_budget += 1
            continue

        graph.add_edge(
            first,
            second,
            weight=float(pair.ppmi),
            cooccurrence=int(pair.cooccurrence),
        )

    isolated = list(nx.isolates(graph))
    if isolated:
        graph.remove_nodes_from(isolated)

    return graph, int(skipped_by_budget)


def _community_rows(graph, communities: Sequence[set], expressions: set[str]) -> List[Dict[str, Any]]:
    total_weight = sum(float(data.get("weight", 0.0)) for _u, _v, data in graph.edges(data=True)) or 1.0
    raw_rows: List[Dict[str, Any]] = []
    for idx, community in enumerate(communities):
        nodes = sorted(str(node) for node in community)
        subgraph = graph.subgraph(nodes)
        internal_weight = sum(float(data.get("weight", 0.0)) for _u, _v, data in subgraph.edges(data=True))
        incident_weight = 0.0
        for node in nodes:
            for _u, _v, data in graph.edges(node, data=True):
                incident_weight += float(data.get("weight", 0.0))
        external_weight = max(0.0, incident_weight - (2.0 * internal_weight))
        density = float(nx_density(subgraph, internal_weight))
        centrality = float(external_weight / total_weight)
        expressions_in = [node for node in nodes if node in expressions]
        label_terms = expressions_in[:3] if expressions_in else nodes[:3]
        raw_rows.append(
            {
                "community_id": int(idx),
                "community_code": f"C{idx}",
                "label": " / ".join(label_terms),
                "n_nodes": len(nodes),
                "n_expressions": len(expressions_in),
                "centrality": centrality,
                "density": density,
                "top_terms": ", ".join(nodes[:12]),
            }
        )
    central_median = float(np.median([row["centrality"] for row in raw_rows])) if raw_rows else 0.0
    density_median = float(np.median([row["density"] for row in raw_rows])) if raw_rows else 0.0
    for row in raw_rows:
        row["quadrant"] = _quadrant(row["centrality"], row["density"], central_median, density_median)
    return raw_rows


def nx_density(subgraph, internal_weight: float) -> float:
    n_nodes = subgraph.number_of_nodes()
    if n_nodes <= 1:
        return 0.0
    possible = n_nodes * (n_nodes - 1) / 2
    return float(internal_weight / possible)


def _quadrant(centrality: float, density: float, central_median: float, density_median: float) -> str:
    high_central = centrality >= central_median
    high_density = density >= density_median
    if high_central and high_density:
        return "Temas motores"
    if high_central and not high_density:
        return "Temas básicos"
    if (not high_central) and high_density:
        return "Temas especializados"
    return "Temas emergentes/declinantes"


def _write_rows_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _write_network_plot(graph, community_by_node: Dict[str, int], path: Path) -> None:
    write_readable_network_plot(
        graph,
        path,
        title="Rede de Expressões Compostas",
        community_by_node=community_by_node,
        max_labels=max(1, int(graph.number_of_nodes())),
    )


def _copy_community_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return dict(row)


def _spread_strategic_display_coordinates(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add display coordinates for crowded strategic-map bubbles.

    Analytical metrics remain unchanged:
    - centrality
    - density
    - quadrant

    Only display_centrality/display_density may be shifted.
    """
    spread_rows = [_copy_community_row(row) for row in rows]
    if not spread_rows:
        return spread_rows

    xs = np.asarray([float(row.get("centrality", 0.0) or 0.0) for row in spread_rows], dtype=float)
    ys = np.asarray([float(row.get("density", 0.0) or 0.0) for row in spread_rows], dtype=float)
    x_min, x_max = float(np.min(xs)), float(np.max(xs))
    y_min, y_max = float(np.min(ys)), float(np.max(ys))
    x_span = max(x_max - x_min, 0.02)
    y_span = max(y_max - y_min, 0.02)

    norm_positions: List[list[float]] = [
        [
            (float(row.get("centrality", 0.0) or 0.0) - x_min) / x_span,
            (float(row.get("density", 0.0) or 0.0) - y_min) / y_span,
        ]
        for row in spread_rows
    ]

    # Minimum normalized distance between bubble centers in display space.
    # Small enough to preserve quadrant reading, large enough to separate labels.
    min_dist = 0.055 if len(spread_rows) <= 20 else 0.045
    max_shift = 0.075

    original_positions = [pos[:] for pos in norm_positions]
    for _pass_idx in range(180):
        moved = False
        for idx in range(len(norm_positions)):
            for jdx in range(idx + 1, len(norm_positions)):
                dx = norm_positions[jdx][0] - norm_positions[idx][0]
                dy = norm_positions[jdx][1] - norm_positions[idx][1]
                dist = float((dx * dx + dy * dy) ** 0.5)
                if dist >= min_dist:
                    continue

                if dist <= 1e-9:
                    angle = ((idx + 1) * 2.399963229728653) % (np.pi * 2.0)
                    ux = float(np.cos(angle))
                    uy = float(np.sin(angle))
                    dist = 1.0
                else:
                    ux = dx / dist
                    uy = dy / dist

                push = (min_dist - dist) * 0.52
                norm_positions[idx][0] -= ux * push
                norm_positions[idx][1] -= uy * push
                norm_positions[jdx][0] += ux * push
                norm_positions[jdx][1] += uy * push
                moved = True

        for idx, pos in enumerate(norm_positions):
            ox, oy = original_positions[idx]
            dx = pos[0] - ox
            dy = pos[1] - oy
            shift = float((dx * dx + dy * dy) ** 0.5)
            if shift > max_shift:
                scale = max_shift / shift
                pos[0] = ox + dx * scale
                pos[1] = oy + dy * scale
            pos[0] = min(1.04, max(-0.04, pos[0]))
            pos[1] = min(1.04, max(-0.04, pos[1]))

        if not moved:
            break

    for row, pos in zip(spread_rows, norm_positions):
        display_x = x_min + pos[0] * x_span
        display_y = y_min + pos[1] * y_span
        row["display_centrality"] = float(display_x)
        row["display_density"] = float(display_y)

    return spread_rows


def _write_strategic_plot(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    legend_entries = [
        (
            str(row.get("community_code", f"C{row.get('community_id', idx)}")),
            str(row.get("label") or row.get("top_terms") or "Comunidade"),
        )
        for idx, row in enumerate(rows)
    ]
    fig, ax, ax_leg = create_figure(
        width=9.2,
        height=7.2,
        with_legend_panel=bool(legend_entries),
        legend_entries=legend_entries,
    )
    centrality = [float(row["centrality"]) for row in rows]
    density = [float(row["density"]) for row in rows]
    sizes = [180 + 35 * int(row["n_nodes"]) for row in rows]
    colors = ggplot_hue(max(1, len(rows)))
    c_med = float(np.median(centrality)) if centrality else 0.0
    d_med = float(np.median(density)) if density else 0.0
    ax.axvline(c_med, color="#666666", linestyle="--", linewidth=1.0)
    ax.axhline(d_med, color="#666666", linestyle="--", linewidth=1.0)
    for idx, row in enumerate(rows):
        raw_x = float(row["centrality"])
        raw_y = float(row["density"])
        display_x = float(row.get("display_centrality", raw_x))
        display_y = float(row.get("display_density", raw_y))

        if abs(display_x - raw_x) > 1e-12 or abs(display_y - raw_y) > 1e-12:
            ax.plot(
                [raw_x, display_x],
                [raw_y, display_y],
                color="#8A8A8A",
                linewidth=0.55,
                alpha=0.55,
                zorder=1,
            )

        ax.scatter(
            display_x,
            display_y,
            s=sizes[idx],
            color=colors[idx],
            alpha=0.75,
            edgecolors="#FFFFFF",
            linewidths=0.8,
            zorder=2,
        )
        code = str(row.get("community_code", f"C{row['community_id']}"))
        ax.text(
            display_x,
            display_y,
            code,
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            zorder=3,
        )
    ax.set_xlabel("Centralidade")
    ax.set_ylabel("Densidade")
    ax.set_title("Mapa Estratégico de Temas")
    ax.text(0.98, 0.98, "Temas motores", transform=ax.transAxes, ha="right", va="top", fontsize=9)
    ax.text(0.02, 0.98, "Temas especializados", transform=ax.transAxes, ha="left", va="top", fontsize=9)
    ax.text(0.98, 0.02, "Temas básicos", transform=ax.transAxes, ha="right", va="bottom", fontsize=9)
    ax.text(0.02, 0.02, "Emergentes/declinantes", transform=ax.transAxes, ha="left", va="bottom", fontsize=9)

    plot_x_values = [float(row.get("display_centrality", row["centrality"])) for row in rows] + centrality
    plot_y_values = [float(row.get("display_density", row["density"])) for row in rows] + density
    if plot_x_values and plot_y_values:
        x_min, x_max = min(plot_x_values), max(plot_x_values)
        y_min, y_max = min(plot_y_values), max(plot_y_values)
        x_pad = max((x_max - x_min) * 0.10, 0.002)
        y_pad = max((y_max - y_min) * 0.10, 0.15)
        ax.set_xlim(x_min - x_pad, x_max + x_pad)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)

    style_axes(ax, grid_axis="both", spines=("bottom", "left"))
    if ax_leg is not None:
        draw_legend_panel(ax_leg, legend_entries, colors, title="Comunidades")
    save_figure(fig, path)
