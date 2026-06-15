"""Readable static network plots for semantic and n-gram analyses."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from src.core.chart_theme import ggplot_hue, save_figure, style_network_axes


def _component_layout(graph, *, seed: int = 42) -> Dict[Any, tuple[float, float]]:
    components = [
        list(component)
        for component in nx.connected_components(graph)
    ]
    components.sort(key=lambda nodes: (-len(nodes), str(nodes[0]) if nodes else ""))
    positions: Dict[Any, tuple[float, float]] = {}
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    max_row_width = max(20.0, math.sqrt(max(1, graph.number_of_nodes())) * 8.0)
    gap = 4.0

    for idx, nodes in enumerate(components):
        subgraph = graph.subgraph(nodes).copy()
        if len(nodes) == 1:
            local = {nodes[0]: (0.0, 0.0)}
        else:
            for _u, _v, data in subgraph.edges(data=True):
                raw_weight = max(0.0, float(data.get("weight", 1.0)))
                data["layout_weight"] = 1.0 + math.log1p(raw_weight)
            k = max(1.65, 4.8 / math.sqrt(len(nodes)))
            scale = max(3.2, math.sqrt(len(nodes)) * 2.45)
            local = nx.spring_layout(
                subgraph,
                seed=seed + idx,
                weight="layout_weight",
                k=k,
                iterations=1300,
                scale=scale,
            )
        xs = [float(x) for x, _y in local.values()]
        ys = [float(y) for _x, y in local.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        if cursor_x > 0 and cursor_x + width > max_row_width:
            cursor_x = 0.0
            cursor_y -= row_height + gap
            row_height = 0.0
        for node, (x, y) in local.items():
            positions[node] = (
                float(cursor_x + (float(x) - min_x)),
                float(cursor_y + (float(y) - min_y)),
            )
        cursor_x += width + gap
        row_height = max(row_height, height)
    return positions


def _resolve_label_positions(
    positions: Dict[Any, tuple[float, float]],
    label_nodes: set,
    node_strength: Dict[Any, float],
    *,
    passes: int = 220,
) -> Tuple[Dict[Any, tuple[float, float]], int]:
    """Repel labels in data coordinates while keeping them tied to their nodes."""
    if not label_nodes:
        return {}, 0
    xs = [float(x) for x, _y in positions.values()]
    ys = [float(y) for _x, y in positions.values()]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    center_x = (max(xs) + min(xs)) / 2.0
    center_y = (max(ys) + min(ys)) / 2.0
    max_strength = max((float(node_strength.get(node, 0.0)) for node in label_nodes), default=1.0) or 1.0

    label_positions: Dict[Any, tuple[float, float]] = {}
    radii: Dict[Any, float] = {}
    for idx, node in enumerate(sorted(label_nodes, key=lambda item: str(item))):
        x, y = positions[node]
        dx = float(x) - center_x
        dy = float(y) - center_y
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            angle = (idx * 2.399963229728653) % (math.pi * 2.0)
            dx, dy, dist = math.cos(angle), math.sin(angle), 1.0
        score = float(node_strength.get(node, 0.0)) / max_strength
        offset = extent * (0.020 + 0.030 * score)
        label_positions[node] = (
            float(x) + (dx / dist) * offset,
            float(y) + (dy / dist) * offset,
        )
        text_len = min(22, max(4, len(str(node))))
        radii[node] = extent * (0.010 + text_len * 0.0018)

    nodes = list(label_nodes)
    used_passes = 0
    for pass_idx in range(max(1, int(passes))):
        moved = False
        used_passes = pass_idx + 1
        for idx, first in enumerate(nodes):
            x1, y1 = label_positions[first]
            for second in nodes[idx + 1 :]:
                x2, y2 = label_positions[second]
                dx = x2 - x1
                dy = y2 - y1
                dist = math.hypot(dx, dy)
                target = radii[first] + radii[second]
                if dist >= target:
                    continue
                if dist <= 1e-8:
                    angle = ((idx + 1) * 2.399963229728653) % (math.pi * 2.0)
                    dx, dy, dist = math.cos(angle), math.sin(angle), 1.0
                push = (target - dist) * 0.48
                ux, uy = dx / dist, dy / dist
                x1, y1 = x1 - ux * push, y1 - uy * push
                label_positions[first] = (x1, y1)
                label_positions[second] = (x2 + ux * push, y2 + uy * push)
                moved = True

        for node in nodes:
            lx, ly = label_positions[node]
            nx_, ny_ = positions[node]
            label_positions[node] = (
                lx + (float(nx_) - lx) * 0.006,
                ly + (float(ny_) - ly) * 0.006,
            )
        if not moved:
            break

    return label_positions, used_passes


def write_readable_network_plot(
    graph,
    path: Path,
    *,
    title: str,
    community_by_node: Optional[Dict[str, int]] = None,
    max_labels: int = 70,
    seed: int = 42,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if graph.number_of_nodes() <= 0:
        return path

    community_by_node = community_by_node or {}
    positions = _component_layout(graph, seed=seed)
    node_strength = dict(graph.degree(weight="weight"))
    strengths = list(node_strength.values()) or [1.0]
    min_s, max_s = min(strengths), max(strengths)
    span = max(max_s - min_s, 1.0)
    communities = sorted({int(value) for value in community_by_node.values()}) or [0]
    colors = ggplot_hue(max(1, len(communities)))
    color_by_community = {community: colors[idx % len(colors)] for idx, community in enumerate(communities)}

    edges = list(graph.edges(data=True))
    weights = [float(data.get("weight", 1.0)) for _u, _v, data in edges]
    max_w = max(weights) if weights else 1.0
    node_sizes = [
        70.0 + ((float(node_strength.get(node, min_s)) - min_s) / span) * 340.0
        for node in graph.nodes()
    ]
    node_colors = [
        color_by_community.get(int(community_by_node.get(str(node), 0)), colors[0])
        for node in graph.nodes()
    ]

    ranked_labels = sorted(
        graph.nodes(),
        key=lambda node: (float(node_strength.get(node, 0.0)), str(node)),
        reverse=True,
    )
    label_limit = min(max(1, int(max_labels)), len(ranked_labels))
    label_nodes = set(ranked_labels[:label_limit])
    label_positions, label_passes = _resolve_label_positions(positions, label_nodes, node_strength)

    fig_w = max(13.0, min(28.0, 8.5 + math.sqrt(graph.number_of_nodes()) * 1.55))
    fig_h = max(8.5, min(20.0, 6.2 + math.sqrt(graph.number_of_nodes()) * 1.10))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    for (u, v, data), weight in zip(edges, weights):
        x1, y1 = positions[u]
        x2, y2 = positions[v]
        ax.plot(
            [x1, x2],
            [y1, y2],
            color="#A8B3C2",
            linewidth=0.35 + (weight / max_w) * 1.7,
            alpha=0.38,
            zorder=1,
        )

    xs = [positions[node][0] for node in graph.nodes()]
    ys = [positions[node][1] for node in graph.nodes()]
    ax.scatter(
        xs,
        ys,
        s=node_sizes,
        c=node_colors,
        alpha=0.88,
        edgecolors="#FFFFFF",
        linewidths=0.9,
        zorder=2,
    )

    for node in graph.nodes():
        if node not in label_nodes:
            continue
        node_x, node_y = positions[node]
        x, y = label_positions.get(node, positions[node])
        score = (float(node_strength.get(node, min_s)) - min_s) / span
        if math.hypot(float(x) - float(node_x), float(y) - float(node_y)) > 0.05:
            ax.plot(
                [node_x, x],
                [node_y, y],
                color="#8FA0B2",
                linewidth=0.45,
                alpha=0.42,
                zorder=2.5,
            )
        ax.text(
            x,
            y,
            str(node).replace("_", "_"),
            ha="center",
            va="center",
            fontsize=7.2 + score * 3.6,
            color="#26313F",
            zorder=3,
            bbox={
                "boxstyle": "round,pad=0.16",
                "facecolor": "#FFFFFF",
                "edgecolor": "none",
                "alpha": 0.82,
            },
        )

    ax.set_title(title, fontsize=13, fontweight="semibold", color="#2D2D2D", pad=12)
    style_network_axes(ax)
    ax.margins(0.16)
    save_figure(fig, path, dpi=160)

    meta = {
        "renderer": "labiialex_readable_network_1.0.9",
        "n_nodes": int(graph.number_of_nodes()),
        "n_edges": int(graph.number_of_edges()),
        "n_labels_rendered": int(len(label_nodes)),
        "n_labels_hidden": int(max(0, graph.number_of_nodes() - len(label_nodes))),
        "layout": "component_spring_readable_repelled",
        "label_layout": "repelled_labels",
        "label_collision_passes": int(label_passes),
        "label_anchor_lines": True,
    }
    path.with_name(f"{path.stem}_render_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
