"""High-quality renderer for textual network analysis outputs."""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
import matplotlib.patheffects as path_effects
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from .gephi_label_adjust import GephiLabelAdjust, GephiNoverlap

log = logging.getLogger(__name__)

COMMUNITY_PALETTE = [
    "#E63946",  # Vermelho vibrante
    "#1D8CF8",  # Azul elétrico
    "#2DC653",  # Verde vivo
    "#FF6D00",  # Laranja profundo
    "#AA46BE",  # Roxo rico
    "#00BCD4",  # Ciano / Teal
    "#FF2D87",  # Rosa quente
    "#FFB400",  # Âmbar dourado
    "#7B61FF",  # Violeta índigo
    "#00E676",  # Verde neon
    "#FF5252",  # Coral
    "#448AFF",  # Cerúleo brilhante
    "#E040FB",  # Magenta
    "#76FF03",  # Lima
    "#FF6E40",  # Pêssego profundo
    "#18FFFF",  # Aqua
    "#B388FF",  # Lavanda
    "#FFD740",  # Ouro claro
    "#69F0AE",  # Menta
    "#F50057",  # Carmim
]


def get_community_color(community_id: int, alpha: float = 1.0):
    """Return a color for a community id."""
    idx = int(community_id or 0) % len(COMMUNITY_PALETTE)
    color = COMMUNITY_PALETTE[idx]
    if alpha < 1.0:
        return mcolors.to_rgba(color, alpha=alpha)
    return color


def _apply_gephi_quality_preset(params: Dict[str, Any]) -> Dict[str, Any]:
    """Preset visual Gephi-quality que aplica defaults de render mais fiéis."""
    p = dict(params or {})
    preset = {
        "curved_edges": True,
        "edge_alpha": 0.28,
        "edge_min_alpha": 0.10,
        "edge_min_width": 0.20,
        "edge_max_width": 0.80,
        "edge_curve_ratio": 0.2,
        "edge_curve_points": 20,
        "edge_use_community_color": True,
        "label_min_size": 4.5,
        "label_max_size": 32.0,
        "label_size_gamma": 1.5,
        "label_size_boost": 0.0,
        "label_outline_width": 0.0,
        "label_use_community_color": True,
        "label_density": 0.85,
        "label_max_count": 300,
        "label_hide_overlap": True,
        "label_overlap_target": 0.08,
        "label_bbox_expand_x": 1.12,
        "label_bbox_expand_y": 1.18,
        "label_reposition_on_overlap": False,
        "label_min_keep": 6,
        "ellipse_power": 0.65,
        "show_halos": False,
        "show_nodes": False,
        "gephi_node_reflow": False,
        "label_anchor_lines": False,
        "view_trim_quantile": 0.01,
        "view_pad_ratio_initial": 0.10,
        "view_pad_ratio_final": 0.06,
        "render_quality_passes": 3,
    }
    for key, value in preset.items():
        if key in {"gephi_node_reflow", "label_reposition_on_overlap"} and key in p:
            # Keep explicit compatibility toggles when caller sets them.
            continue
        if key not in p or p.get(f"_user_set_{key}") is not True:
            p[key] = value
    return p


def _compute_bezier_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    num_points: int = 20,
    curve_ratio: float = 0.2,
) -> List[Tuple[float, float]]:
    """Compute Gephi-style cubic Bezier points sampled as a polyline."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return [(x1, y1), (x2, y2)]

    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    mid1_x = x1 + ux * length * curve_ratio
    mid1_y = y1 + uy * length * curve_ratio
    mid2_x = x2 - ux * length * curve_ratio
    mid2_y = y2 - uy * length * curve_ratio

    c1x = mid1_x + px * length * curve_ratio
    c1y = mid1_y + py * length * curve_ratio
    c2x = mid2_x + px * length * curve_ratio
    c2y = mid2_y + py * length * curve_ratio

    n_pts = max(2, int(num_points))
    points: List[Tuple[float, float]] = []
    for i in range(n_pts + 1):
        t = i / n_pts
        t2 = t * t
        t3 = t2 * t
        mt = 1.0 - t
        mt2 = mt * mt
        mt3 = mt2 * mt

        bx = mt3 * x1 + 3.0 * mt2 * t * c1x + 3.0 * mt * t2 * c2x + t3 * x2
        by = mt3 * y1 + 3.0 * mt2 * t * c1y + 3.0 * mt * t2 * c2y + t3 * y2
        points.append((bx, by))

    return points


def render_network(
    graph,
    positions: Dict,
    nodes_table: List[Dict[str, Any]],
    output_path: Path,
    params: Dict[str, Any],
) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Render textual network in publication style while preserving topology.

    Node anchors are immutable (used by edges/nodes). Label positions can move.
    """
    width_px = int(params.get("width", 3200))
    height_px = int(params.get("height", 2200))
    dpi = int(params.get("dpi", 240))
    background = str(params.get("background", "white"))

    anchor_positions = {
        node: (float(x), float(y))
        for node, (x, y) in (positions or {}).items()
    }
    if not anchor_positions:
        return None, None

    local_params = dict(params or {})
    if bool(local_params.get("gephi_quality", False)):
        local_params = _apply_gephi_quality_preset(local_params)
    gephi_mode = bool(local_params.get("gephi_fidelity", False) or local_params.get("gephi_quality", False))

    # "Expansão da rede": Scales the graph coordinates to give labels room to breathe
    expansion_factor = float(local_params.get("network_expansion", 1.0))
    if expansion_factor != 1.0:
        anchor_positions = {
            node: (x * expansion_factor, y * expansion_factor)
            for node, (x, y) in anchor_positions.items()
        }

    # -- Elliptical compression: compact layout into Gephi-like oval shape --
    if anchor_positions and len(anchor_positions) >= 3:
        import numpy as np

        nodes_list = list(anchor_positions.keys())
        coords = np.array([anchor_positions[n] for n in nodes_list])

        # Centre around (0, 0)
        center = coords.mean(axis=0)
        coords -= center

        # Normalise to 95th-percentile distance so outliers are pulled inward
        dists = np.sqrt((coords ** 2).sum(axis=1))
        scale = float(np.percentile(dists, 95))
        if scale > 1e-6:
            coords /= scale

        # Contract outliers logarithmically: nodes beyond 1.0 are compressed
        # toward the core. This prevents "floating words" at the periphery.
        dists_norm = np.sqrt((coords ** 2).sum(axis=1))
        outlier_mask = dists_norm > 1.0
        if np.any(outlier_mask):
            blend = np.clip((dists_norm[outlier_mask] - 1.0) / 2.0, 0.0, 1.0)
            linear_part = dists_norm[outlier_mask]
            log_part = 1.0 + np.log(dists_norm[outlier_mask])
            contracted = (1.0 - blend) * linear_part + blend * log_part
            ratio = contracted / dists_norm[outlier_mask]
            coords[outlier_mask, 0] *= ratio
            coords[outlier_mask, 1] *= ratio

        # Stretch to canvas aspect ratio → creates Gephi's elliptical shape
        aspect = width_px / max(height_px, 1)
        ellipse_power = float(local_params.get("ellipse_power", 0.65))
        if aspect > 1.05:
            stretch = aspect ** ellipse_power
            coords[:, 0] *= stretch
            coords[:, 1] /= stretch

        anchor_positions = {
            nodes_list[i]: (float(coords[i, 0]), float(coords[i, 1]))
            for i in range(len(nodes_list))
        }

    auto_quality = bool(local_params.get("render_quality_auto", True))
    default_passes = 2 if auto_quality else 1
    max_passes = max(
        1,
        min(4, int(local_params.get("render_quality_passes", default_passes) or default_passes)),
    )
    overlap_target = max(
        0.04,
        min(0.65, float(local_params.get("label_overlap_target", 0.16))),
    )

    fig_w = max(1.0, width_px / max(dpi, 1))
    fig_h = max(1.0, height_px / max(dpi, 1))
    typegraph = str(local_params.get("typegraph", "png")).strip().lower()
    render_attempts: List[Dict[str, Any]] = []
    noverlap_applied = False
    node_reflow_applied = False
    labels_hidden_by_overlap = 0

    png_path: Optional[Path] = None
    svg_path: Optional[Path] = None

    for attempt_idx in range(max_passes):
        fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
        fig.patch.set_facecolor(background)
        ax.set_facecolor(background)
        ax.set_aspect("equal")
        ax.axis("off")

        node_count = max(0, int(graph.number_of_nodes()))
        default_trim_quantile = 0.01 if gephi_mode else (0.02 if node_count < 30 else 0.05)
        trim_quantile = float(
            local_params.get("view_trim_quantile", default_trim_quantile)
            or default_trim_quantile
        )
        initial_pad_ratio = float(local_params.get("view_pad_ratio_initial", 0.06) or 0.06)
        final_pad_ratio = float(local_params.get("view_pad_ratio_final", 0.03) or 0.03)
        _set_axis_limits_from_points(
            ax,
            list(anchor_positions.values()),
            pad_ratio=initial_pad_ratio,
            trim_quantile=trim_quantile,
        )

        should_apply_noverlap = (
            gephi_mode
            and bool(local_params.get("noverlap_enabled", True))
            and (
                bool(local_params.get("show_nodes", False))
                or bool(local_params.get("gephi_node_reflow", False))
            )
        )
        if should_apply_noverlap:
            metric_key = str(local_params.get("node_size_metric", "weighted_degree"))
            min_node_size = float(local_params.get("node_min_size", 10.0))
            max_node_size = float(local_params.get("node_max_size", 120.0))
            
            node_lookup = {row.get("id"): row for row in nodes_table}
            vals = [float(row.get(metric_key, row.get("degree", 0))) for row in nodes_table]
            v_min = min(vals) if vals else 0.0
            v_max = max(vals) if vals else 1.0
            v_range = max(v_max - v_min, 1e-9)
            
            node_sizes = {}
            for n in graph.nodes():
                info = node_lookup.get(n, {})
                val = float(info.get(metric_key, info.get("degree", 0)))
                norm = (val - v_min) / v_range
                size = min_node_size + (max_node_size - min_node_size) * norm
                node_sizes[n] = size
                
            noverlap_runner = GephiNoverlap(
                speed=float(local_params.get("noverlap_speed", 3.0)),
                ratio=float(local_params.get("noverlap_ratio", 1.1)),
                margin=float(local_params.get("noverlap_margin", 3.0)),
                max_iterations=int(local_params.get("noverlap_iterations", 50))
            )
            anchor_positions = noverlap_runner.run(anchor_positions, node_sizes)
            noverlap_applied = True
        
        # 1. First Pass: Create labels to get their bounding boxes
        text_items, labeled_nodes = _draw_labels(
            ax=ax,
            graph=graph,
            positions=anchor_positions,
            nodes_table=nodes_table,
            params=local_params,
        )

        should_apply_node_reflow = (
            gephi_mode
            and bool(local_params.get("label_adjust", True))
            and bool(local_params.get("gephi_node_reflow", False))
        )

        if should_apply_node_reflow and text_items:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            inv = ax.transData.inverted()
            
            label_sizes = {}
            for node, text in text_items:
                bbox = text.get_window_extent(renderer=renderer)
                p0 = inv.transform((bbox.x0, bbox.y0))
                p1 = inv.transform((bbox.x1, bbox.y1))
                label_sizes[node] = (abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))
            
            adjuster = GephiLabelAdjust(
                speed=float(local_params.get("label_adjust_speed", 1.5)),
                max_iterations=int(local_params.get("label_adjust_iterations", 800)),
                margin=float(local_params.get("label_adjust_margin", 4.0))
            )
            anchor_positions = adjuster.run(anchor_positions, label_sizes)
            node_reflow_applied = True
            
            # Update label positions to match new anchors
            for node, text in text_items:
                text.set_position(anchor_positions[node])
                
        elif bool(local_params.get("label_adjust", True)) and text_items and not gephi_mode:
            _adjust_label_overlap(text_items, ax, local_params)

        # 2. Final Pass: Draw everything else with correct positions
        # In Gephi mode, we usually don't show halos by default.
        if not gephi_mode and bool(local_params.get("show_halos", True)):
            _draw_community_halos(ax, anchor_positions, nodes_table)

        if bool(local_params.get("show_edges", True)):
            _draw_edges(
                ax=ax,
                graph=graph,
                anchor_positions=anchor_positions,
                params=local_params,
                nodes_table=nodes_table,
            )

        visible_text_items = _hide_overlapping_labels(text_items, ax, local_params)
        
        # Standard mode still uses local solver for labels after hiding
        if not gephi_mode and bool(local_params.get("label_adjust", True)) and visible_text_items:
            _local_overlap_solver(
                text_items=visible_text_items,
                ax=ax,
                max_iterations=max(50, int(local_params.get("label_adjust_iterations", 120)) // 2),
                pixel_step=max(3.0, float(local_params.get("label_adjust_pixel_step", 4.0))),
                max_time_sec=max(2.0, float(local_params.get("label_adjust_time_lim", 10.0)) * 0.6),
            )
            visible_text_items = _hide_overlapping_labels(visible_text_items, ax, local_params)
        
        labels_hidden_count = max(0, len(text_items) - len(visible_text_items))
        labels_hidden_by_overlap = labels_hidden_count

        visible_nodes = {node for node, _text in visible_text_items}

        if not gephi_mode and bool(local_params.get("label_anchor_lines", True)):
            _draw_label_anchor_lines(
                ax=ax,
                anchor_positions=anchor_positions,
                text_items=visible_text_items,
                params=local_params,
            )

        # In Gephi mode, we respect the user's choice to hide nodes.
        if bool(local_params.get("show_nodes", False)):
            _draw_node_dots(
                ax=ax,
                positions=anchor_positions,
                nodes_table=nodes_table,
                labeled_nodes=visible_nodes or labeled_nodes,
                params=local_params if gephi_mode else None
            )

        label_positions = {
            node: (float(text.get_position()[0]), float(text.get_position()[1]))
            for node, text in visible_text_items
        }
        _set_axis_limits_from_points(
            ax,
            list(anchor_positions.values()) + list(label_positions.values()),
            pad_ratio=final_pad_ratio,
            trim_quantile=trim_quantile,
        )

        overlap_ratio = _compute_overlap_ratio(visible_text_items, ax, local_params)
        render_attempts.append(
            {
                "attempt": attempt_idx + 1,
                "max_passes": max_passes,
                "labels_visible": len(visible_text_items),
                "labels_drawn": len(text_items),
                "labels_hidden_by_overlap": labels_hidden_count,
                "overlap_ratio": round(float(overlap_ratio), 6),
                "label_density": float(local_params.get("label_density", 0.0) or 0.0),
                "label_max_count": int(local_params.get("label_max_count", 0) or 0),
                "label_max_size": float(local_params.get("label_max_size", 0.0) or 0.0),
                "noverlap_applied": bool(noverlap_applied),
                "node_reflow_applied": bool(node_reflow_applied),
            }
        )

        should_retry = (
            attempt_idx + 1 < max_passes
            and auto_quality
            and overlap_ratio > overlap_target
            and len(visible_text_items)
            >= max(24, int(local_params.get("label_min_keep", 8) or 8) * 2)
        )

        if should_retry:
            plt.close(fig)
            local_params = _tighten_label_plan_for_retry(
                local_params,
                overlap_ratio=overlap_ratio,
                label_count=len(visible_text_items),
            )
            continue

        png_path = output_path.with_suffix(".png")
        fig.savefig(
            str(png_path),
            dpi=dpi,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
            edgecolor="none",
            pad_inches=0.25,
        )

        if typegraph in {"svg", "both"}:
            svg_path = output_path.with_suffix(".svg")
            fig.savefig(
                str(svg_path),
                format="svg",
                bbox_inches="tight",
                facecolor=fig.get_facecolor(),
                edgecolor="none",
                pad_inches=0.25,
            )
        plt.close(fig)
        break

    params.update(
        {
            "label_density": local_params.get("label_density", params.get("label_density")),
            "label_max_count": local_params.get("label_max_count", params.get("label_max_count")),
            "label_max_size": local_params.get("label_max_size", params.get("label_max_size")),
            "label_min_keep": local_params.get("label_min_keep", params.get("label_min_keep")),
            "label_size_gamma": local_params.get("label_size_gamma", params.get("label_size_gamma")),
            "edge_alpha": local_params.get("edge_alpha", params.get("edge_alpha")),
            "edge_min_alpha": local_params.get("edge_min_alpha", params.get("edge_min_alpha")),
        }
    )
    params["_render_quality"] = {
        "target_overlap_ratio": float(overlap_target),
        "noverlap_applied": bool(noverlap_applied),
        "node_reflow_applied": bool(node_reflow_applied),
        "labels_hidden_by_overlap": int(labels_hidden_by_overlap),
        "attempts": render_attempts,
        "selected": {
            "label_density": float(local_params.get("label_density", 0.0) or 0.0),
            "label_max_count": int(local_params.get("label_max_count", 0) or 0),
            "label_max_size": float(local_params.get("label_max_size", 0.0) or 0.0),
            "label_min_keep": int(local_params.get("label_min_keep", 0) or 0),
            "label_size_gamma": float(local_params.get("label_size_gamma", 0.0) or 0.0),
        },
    }

    return (
        png_path if png_path and png_path.exists() else None,
        svg_path if svg_path and svg_path.exists() else None,
    )


def _set_axis_limits_from_points(
    ax,
    points: List[Tuple[float, float]],
    pad_ratio: float,
    trim_quantile: float = 0.0,
) -> None:
    if not points:
        return
    xs = np.asarray([float(x) for x, _ in points], dtype=float)
    ys = np.asarray([float(y) for _, y in points], dtype=float)
    q = max(0.0, min(0.2, float(trim_quantile or 0.0)))
    if q > 0.0 and len(xs) >= 30:
        lo = q
        hi = 1.0 - q
        try:
            x_min = float(np.quantile(xs, lo))
            x_max = float(np.quantile(xs, hi))
            y_min = float(np.quantile(ys, lo))
            y_max = float(np.quantile(ys, hi))
        except Exception:
            x_min, x_max = float(xs.min()), float(xs.max())
            y_min, y_max = float(ys.min()), float(ys.max())
    else:
        x_min, x_max = float(xs.min()), float(xs.max())
        y_min, y_max = float(ys.min()), float(ys.max())
    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 1.0)
    pad_x = x_span * max(0.01, float(pad_ratio))
    pad_y = y_span * max(0.01, float(pad_ratio))
    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(y_min - pad_y, y_max + pad_y)


def _tighten_label_plan_for_retry(
    params: Dict[str, Any],
    overlap_ratio: float,
    label_count: int,
) -> Dict[str, Any]:
    """Refine label knobs for a new render attempt when overlap stays high."""
    tuned = dict(params)
    severity = 1.0 + min(1.0, max(0.0, (float(overlap_ratio) - 0.14) / 0.18))

    tuned["label_density"] = max(
        0.16,
        float(tuned.get("label_density", 0.42)) * (0.90 - 0.04 * severity),
    )
    tuned["label_max_count"] = max(
        28,
        int(float(tuned.get("label_max_count", 96)) * (0.91 - 0.04 * severity)),
    )
    tuned["label_max_size"] = max(
        9.4,
        float(tuned.get("label_max_size", 19.0)) * (0.86 - 0.05 * severity),
    )
    tuned["label_min_keep"] = max(
        4,
        min(int(tuned.get("label_min_keep", 8)), int(max(4, label_count * 0.12))),
    )
    tuned["label_size_gamma"] = min(
        1.95,
        float(tuned.get("label_size_gamma", 1.2)) + 0.10 * severity,
    )

    tuned["edge_alpha"] = min(0.42, max(float(tuned.get("edge_alpha", 0.26)), 0.22))
    tuned["edge_min_alpha"] = min(0.28, max(float(tuned.get("edge_min_alpha", 0.13)), 0.12))
    return tuned


def _adjust_label_overlap(
    text_items: List[Tuple[Any, Any]],
    ax,
    params: Optional[Dict[str, Any]] = None,
) -> None:
    """Adjust label overlap using adjustText when available, else local fallback."""
    if not text_items:
        return
    texts = [item[1] for item in text_items]

    try:
        from adjustText import adjust_text

        adjust_text(
            texts,
            ax=ax,
            force_text=(1.0, 1.3),
            force_static=(0.25, 0.45),
            force_pull=(0.02, 0.02),
            expand=(1.16, 1.24),
            ensure_inside_axes=False,
            expand_axes=False,
            max_move=(24, 24),
            time_lim=float((params or {}).get("label_adjust_time_lim", 10.0)),
            min_arrow_len=0,
            arrowprops=dict(arrowstyle="-", color="gray", alpha=0.0),
        )
        _local_overlap_solver(
            text_items=text_items,
            ax=ax,
            max_iterations=int((params or {}).get("label_adjust_iterations", 140)),
            pixel_step=float((params or {}).get("label_adjust_pixel_step", 5.5)),
            max_time_sec=float((params or {}).get("label_adjust_time_lim", 10.0)),
        )
        return
    except ImportError:
        log.info("adjustText nao instalado; usando ajuste local de sobreposicao.")
    except Exception as exc:
        log.warning("adjustText falhou (%s); usando ajuste local de sobreposicao.", exc)

    _local_overlap_solver(
        text_items=text_items,
        ax=ax,
        max_iterations=int((params or {}).get("label_adjust_iterations", 180)),
        pixel_step=float((params or {}).get("label_adjust_pixel_step", 5.0)),
        max_time_sec=float((params or {}).get("label_adjust_time_lim", 10.0)),
    )


def _local_overlap_solver(
    text_items: List[Tuple[Any, Any]],
    ax,
    max_iterations: int,
    pixel_step: float,
    max_time_sec: float = 10.0,
) -> None:
    """Resolve text collisions in display-space, then convert displacement to data-space."""
    if not text_items:
        return
    fig = ax.figure
    started = time.perf_counter()

    for _ in range(max(1, max_iterations)):
        if (time.perf_counter() - started) >= max(0.5, float(max_time_sec)):
            break
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bboxes = [text.get_window_extent(renderer=renderer).expanded(1.03, 1.08) for _, text in text_items]
        overlaps_found = False
        shifts_px = [(0.0, 0.0) for _ in text_items]

        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                if not bboxes[i].overlaps(bboxes[j]):
                    continue
                overlaps_found = True
                bi, bj = bboxes[i], bboxes[j]
                dx = (bi.x0 + bi.x1) * 0.5 - (bj.x0 + bj.x1) * 0.5
                dy = (bi.y0 + bi.y1) * 0.5 - (bj.y0 + bj.y1) * 0.5
                norm = math.hypot(dx, dy) or 1.0
                ux, uy = dx / norm, dy / norm
                push_x = ux * pixel_step
                push_y = uy * pixel_step

                sx_i, sy_i = shifts_px[i]
                sx_j, sy_j = shifts_px[j]
                shifts_px[i] = (sx_i + push_x, sy_i + push_y)
                shifts_px[j] = (sx_j - push_x, sy_j - push_y)

        if not overlaps_found:
            break

        inv = ax.transData.inverted()
        base = inv.transform((0.0, 0.0))
        for idx, (_node, text) in enumerate(text_items):
            sx, sy = shifts_px[idx]
            if sx == 0.0 and sy == 0.0:
                continue
            data_shift = inv.transform((sx, sy))
            ddx = float(data_shift[0] - base[0])
            ddy = float(data_shift[1] - base[1])
            x, y = text.get_position()
            text.set_position((float(x) + ddx, float(y) + ddy))


def _draw_edges(
    ax,
    graph,
    anchor_positions,
    params: Dict[str, Any],
    nodes_table: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Draw weighted edges using anchor positions only."""
    if graph.number_of_edges() <= 0:
        return

    edges = list(graph.edges(data=True))
    if not edges:
        return

    weights = np.array([float(data.get("weight", 1.0) or 1.0) for _, _, data in edges], dtype=float)
    if weights.size <= 0:
        return
    q_cut = float(params.get("edge_weight_quantile", 0.0) or 0.0)
    q_cut = min(max(q_cut, 0.0), 0.99)
    if q_cut > 0.0:
        threshold = float(np.quantile(weights, q_cut))
        edges = [
            (u, v, d)
            for (u, v, d), weight in zip(edges, weights)
            if float(weight) >= threshold
        ]
        weights = np.array([float(d.get("weight", 1.0) or 1.0) for _, _, d in edges], dtype=float)

    if not edges:
        return

    w_min = float(np.min(weights))
    w_max = float(np.max(weights))
    w_range = max(w_max - w_min, 1e-9)
    base_alpha = float(params.get("edge_alpha", 0.26))
    min_alpha = float(params.get("edge_min_alpha", 0.13))
    min_width = float(params.get("edge_min_width", 0.34))
    max_width = float(params.get("edge_max_width", 1.40))
    base_color = str(params.get("edge_color", "#778391"))
    inter_color = str(params.get("edge_intercommunity_color", "#66727F"))
    use_community_color = bool(params.get("edge_use_community_color", True))
    gephi_fidelity = bool(params.get("gephi_fidelity", False) or params.get("gephi_quality", False))
    curved = bool(params.get("curved_edges", gephi_fidelity))
    curve_ratio = float(params.get("edge_curve_ratio", 0.2))
    curve_num_points = int(params.get("edge_curve_points", 20))
    node_lookup = {row.get("id"): row for row in (nodes_table or [])}
    degree_map = dict(graph.degree())
    if degree_map:
        degree_threshold = float(
            np.quantile(np.array(list(degree_map.values()), dtype=float), 0.35)
        )
    else:
        degree_threshold = 1.0

    segments: List[List[Tuple[float, float]]] = []
    colors_arr: List[Tuple[float, float, float, float]] = []
    widths_arr: List[float] = []

    for idx, (u, v, _data) in enumerate(edges):
        if u not in anchor_positions or v not in anchor_positions:
            continue
        x1, y1 = anchor_positions[u]
        x2, y2 = anchor_positions[v]
        norm_w = (float(weights[idx]) - w_min) / w_range
        alpha = min_alpha + (base_alpha - min_alpha) * (norm_w ** 0.7)
        alpha = max(min_alpha, min(0.95, alpha))
        lw = min_width + (max_width - min_width) * (norm_w ** 0.6)

        edge_degree = min(int(degree_map.get(u, 0)), int(degree_map.get(v, 0)))
        is_peripheral_edge = edge_degree <= max(1.0, degree_threshold)
        if not gephi_fidelity:
            if is_peripheral_edge:
                alpha = min(0.98, alpha * 1.16)
                lw = lw * 1.14
            if bool(_data.get("peripheral_boost", 0)):
                alpha = min(0.99, alpha * 1.20)
                lw = lw * 1.22

        if use_community_color and node_lookup:
            c_u = int(node_lookup.get(u, {}).get("community", -1))
            c_v = int(node_lookup.get(v, {}).get("community", -1))

            if gephi_fidelity and c_u >= 0:
                # Gephi style: ALL edges colored by source node's community.
                # Full saturation color — the accumulation of many semi-transparent
                # colored edges creates the dense "colored web" effect per cluster.
                line_color = get_community_color(c_u)
                # Keep alpha and width as-is (weight-scaled above).
                # No reduction — visibility comes from the full community color.
            elif c_u >= 0 and c_u == c_v:
                # Intra-community edge: use community color
                line_color = get_community_color(c_u)
            else:
                # Inter-community edge: muted color
                line_color = inter_color
                alpha = min(0.99, alpha * 1.10)
                lw = lw * 1.05
        else:
            line_color = base_color

        rgba = mcolors.to_rgba(line_color, alpha=alpha)
        if curved:
            points = _compute_bezier_points(
                float(x1),
                float(y1),
                float(x2),
                float(y2),
                num_points=curve_num_points,
                curve_ratio=curve_ratio,
            )
            segments.append(points)
        else:
            segments.append([(float(x1), float(y1)), (float(x2), float(y2))])

        colors_arr.append(rgba)
        widths_arr.append(float(lw))

    if segments:
        lc = LineCollection(
            segments,
            colors=colors_arr,
            linewidths=widths_arr,
            capstyle="round",
            zorder=1,
        )
        ax.add_collection(lc)


def _draw_labels(ax, graph, positions, nodes_table, params: Dict[str, Any]):
    """Draw labels and return list[(node_id, text_obj)] + labeled node ids."""
    metric_key = str(params.get("label_size_metric", "weighted_degree"))
    min_size = float(params.get("label_min_size", 5.5))
    max_size = float(params.get("label_max_size", 19.0))
    size_boost = float(params.get("label_size_boost", 3.0))
    font_family = str(params.get("font_family", "sans-serif"))
    label_color = str(params.get("label_color", "#1B1F23"))
    gephi_fidelity = bool(params.get("gephi_fidelity", False) or params.get("gephi_quality", False))
    use_community_text_color = bool(params.get("label_use_community_color", True if gephi_fidelity else False))

    label_threshold = float(params.get("label_threshold", 0.08))
    label_density = float(params.get("label_density", 0.42))
    gamma = max(0.6, min(2.4, float(params.get("label_size_gamma", 1.2))))
    label_density = max(0.02, min(1.0, label_density))
    label_threshold = max(0.0, min(1.0, label_threshold))

    node_lookup = {row.get("id"): row for row in nodes_table}
    metric_values = {
        node: float(node_lookup.get(node, {}).get(metric_key, node_lookup.get(node, {}).get("degree", 0) or 0))
        for node in graph.nodes()
    }
    vals = list(metric_values.values())
    v_min = min(vals) if vals else 0.0
    v_max = max(vals) if vals else 1.0
    v_range = max(v_max - v_min, 1e-9)
    threshold_value = v_min + (v_max - v_min) * label_threshold

    sorted_nodes = sorted(graph.nodes(), key=lambda node: metric_values.get(node, 0.0), reverse=True)
    node_count = len(sorted_nodes)
    default_cap = 70
    if node_count > 100:
        default_cap = 80
    if node_count > 180:
        default_cap = 90
    if node_count > 260:
        default_cap = 100
    max_labels_cap = max(24, int(params.get("label_max_count", default_cap)))
    max_labels = min(max_labels_cap, max(20, int(node_count * label_density)))
    nodes_to_label = [node for node in sorted_nodes[:max_labels] if metric_values.get(node, 0.0) >= threshold_value]

    items: List[Tuple[Any, Any]] = []
    labeled_nodes = set()
    for node in nodes_to_label:
        if node not in positions:
            continue
        x, y = positions[node]
        info = node_lookup.get(node, {})
        metric_val = float(metric_values.get(node, 0.0))
        normalized = (metric_val - v_min) / v_range
        scaled = math.pow(max(0.0, normalized), gamma)
        if gephi_fidelity:
            max_size_eff = max_size
            min_size_eff = min_size
        elif node_count > 260:
            max_size_eff = max_size * 0.78
            min_size_eff = min_size * 0.80
        elif node_count > 180:
            max_size_eff = max_size * 0.85
            min_size_eff = min_size * 0.84
        elif node_count > 120:
            max_size_eff = max_size * 0.92
            min_size_eff = min_size * 0.90
        else:
            max_size_eff = max_size
            min_size_eff = min_size
        font_size = min_size_eff + (max_size_eff - min_size_eff) * scaled + size_boost
        community_id = int(info.get("community", 0) or 0)
        color = get_community_color(community_id) if use_community_text_color else label_color
        fontweight = (
            ("bold" if normalized >= 0.85 else ("medium" if normalized >= 0.4 else "normal"))
            if gephi_fidelity
            else ("bold" if normalized >= 0.7 else ("semibold" if normalized >= 0.45 else "normal"))
        )
        
        outline_width = float(params.get("label_outline_width", 0.0 if gephi_fidelity else 1.4))
        outline_alpha = float(params.get("label_outline_alpha", 0.0 if gephi_fidelity else 0.85))

        # Gephi default labels are usually black/colored and crisp, without huge white blocking halos
        effects = []
        if gephi_fidelity and outline_width <= 0:
            effects.append(path_effects.withStroke(linewidth=0.3, foreground="white", alpha=0.4))
        elif outline_width > 0:
            effects.append(path_effects.withStroke(linewidth=outline_width, foreground="white", alpha=outline_alpha))

        text = ax.text(
            float(x),
            float(y),
            str(node),
            fontsize=font_size,
            fontfamily=font_family,
            fontweight=fontweight,
            color=color,
            alpha=0.98,
            ha="center",
            va="center",
            zorder=8,
            path_effects=effects,
        )
        items.append((node, text))
        labeled_nodes.add(node)

    return items, labeled_nodes


def _hide_overlapping_labels(
    text_items: List[Tuple[Any, Any]],
    ax,
    params: Dict[str, Any],
) -> List[Tuple[Any, Any]]:
    """Hide residual overlapping labels after adjustment, keeping top-priority terms."""
    if not text_items:
        return []
    if not bool(params.get("label_hide_overlap", True)):
        return text_items

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gephi_mode = bool(params.get("gephi_fidelity", False) or params.get("gephi_quality", False))
    reposition_on_overlap = bool(
        params.get("label_reposition_on_overlap", False if gephi_mode else True)
    )
    expand_x = float(params.get("label_bbox_expand_x", 1.04))
    expand_y = float(params.get("label_bbox_expand_y", 1.10))
    min_keep = max(4, int(params.get("label_min_keep", 8)))
    overlap_target = max(0.04, min(0.65, float(params.get("label_overlap_target", 0.16))))

    ranked = sorted(
        text_items,
        key=lambda pair: float(pair[1].get_fontsize()),
        reverse=True,
    )
    kept: List[Tuple[Any, Any, Any]] = []
    visible: List[Tuple[Any, Any]] = []

    for idx, (node, text) in enumerate(ranked):
        bbox = text.get_window_extent(renderer=renderer).expanded(expand_x, expand_y)
        overlaps = any(bbox.overlaps(existing_bbox) for _n, _t, existing_bbox in kept)
        if overlaps and reposition_on_overlap:
            bbox, moved = _try_reposition_text(
                text=text,
                bbox=bbox,
                existing_bboxes=[existing_bbox for _n, _t, existing_bbox in kept],
                ax=ax,
                renderer=renderer,
                expand_x=expand_x,
                expand_y=expand_y,
                max_rings=5 if idx < min_keep else 3,
            )
            overlaps = (not moved) and any(
                bbox.overlaps(existing_bbox) for _n, _t, existing_bbox in kept
            )
        if overlaps and idx < min_keep and len(visible) < min_keep:
            old_size = float(text.get_fontsize())
            text.set_fontsize(max(4.8, old_size * 0.84))
            bbox = text.get_window_extent(renderer=renderer).expanded(expand_x, expand_y)
            overlaps = any(bbox.overlaps(existing_bbox) for _n, _t, existing_bbox in kept)
        if overlaps:
            text.set_visible(False)
            continue
        text.set_visible(True)
        kept.append((node, text, bbox))
        visible.append((node, text))

    overlap_ratio = _bbox_overlap_ratio([bbox for _n, _t, bbox in kept])
    if overlap_ratio <= overlap_target or len(visible) <= max(min_keep + 8, 24):
        return visible

    strict_expand_x = expand_x + 0.05
    strict_expand_y = expand_y + 0.07
    strict_min_keep = max(3, int(min_keep * 0.75))
    strict_limit = max(strict_min_keep + 10, int(len(ranked) * 0.78))
    strict_kept: List[Tuple[Any, Any, Any]] = []
    strict_visible: List[Tuple[Any, Any]] = []

    for _node, text in text_items:
        text.set_visible(False)

    for idx, (node, text) in enumerate(ranked):
        if idx >= strict_limit and len(strict_visible) >= strict_min_keep:
            break
        bbox = text.get_window_extent(renderer=renderer).expanded(strict_expand_x, strict_expand_y)
        if idx < strict_min_keep:
            text.set_visible(True)
            strict_kept.append((node, text, bbox))
            strict_visible.append((node, text))
            continue
        overlaps = any(bbox.overlaps(existing_bbox) for _n, _t, existing_bbox in strict_kept)
        if overlaps:
            text.set_visible(False)
            continue
        text.set_visible(True)
        strict_kept.append((node, text, bbox))
        strict_visible.append((node, text))

    if strict_visible:
        return strict_visible
    return visible


def _bbox_overlap_ratio(bboxes: List[Any]) -> float:
    if len(bboxes) < 2:
        return 0.0
    overlaps = 0
    total = 0
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            total += 1
            if bboxes[i].overlaps(bboxes[j]):
                overlaps += 1
    if total <= 0:
        return 0.0
    return float(overlaps) / float(total)


def _try_reposition_text(
    text: Any,
    bbox: Any,
    existing_bboxes: List[Any],
    ax: Any,
    renderer: Any,
    expand_x: float,
    expand_y: float,
    max_rings: int = 3,
) -> Tuple[Any, bool]:
    """Attempt local radial displacement in display space to avoid collisions."""
    if not existing_bboxes:
        return bbox, True

    x0, y0 = text.get_position()
    anchor_disp = ax.transData.transform((x0, y0))
    inv = ax.transData.inverted()
    angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]

    for ring in range(1, max(1, max_rings) + 1):
        radius = 8.0 + 4.0 * ring
        for angle in angles:
            rad = math.radians(float(angle))
            cand_disp = (
                anchor_disp[0] + radius * math.cos(rad),
                anchor_disp[1] + radius * math.sin(rad),
            )
            cand_data = inv.transform(cand_disp)
            text.set_position((float(cand_data[0]), float(cand_data[1])))
            cand_bbox = text.get_window_extent(renderer=renderer).expanded(expand_x, expand_y)
            if not any(cand_bbox.overlaps(existing_bbox) for existing_bbox in existing_bboxes):
                return cand_bbox, True

    text.set_position((float(x0), float(y0)))
    return bbox, False


def _compute_overlap_ratio(
    text_items: List[Tuple[Any, Any]],
    ax,
    params: Dict[str, Any],
) -> float:
    if len(text_items) < 2:
        return 0.0
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    expand_x = float(params.get("label_bbox_expand_x", 1.04))
    expand_y = float(params.get("label_bbox_expand_y", 1.10))
    bboxes = [
        text.get_window_extent(renderer=renderer).expanded(expand_x, expand_y)
        for _node, text in text_items
        if text.get_visible()
    ]
    return _bbox_overlap_ratio(bboxes)


def _draw_community_halos(ax, positions, nodes_table) -> None:
    """Draw translucent halos around community clusters."""
    from collections import defaultdict
    from matplotlib.patches import Ellipse

    communities = defaultdict(list)
    for row in nodes_table:
        communities[int(row.get("community", 0) or 0)].append(row.get("id"))

    for comm_id, members in communities.items():
        if len(members) < 3:
            continue
        xs = [positions[m][0] for m in members if m in positions]
        ys = [positions[m][1] for m in members if m in positions]
        if not xs or not ys:
            continue

        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        rx = (max(xs) - min(xs)) / 2.0 + 0.2
        ry = (max(ys) - min(ys)) / 2.0 + 0.2
        ellipse = Ellipse(
            (cx, cy),
            width=rx * 2.15,
            height=ry * 2.15,
            facecolor=get_community_color(comm_id, alpha=0.08),
            edgecolor=get_community_color(comm_id, alpha=0.18),
            linewidth=0.45,
            zorder=0,
        )
        ax.add_patch(ellipse)


def _draw_label_anchor_lines(
    ax,
    anchor_positions: Dict[Any, Tuple[float, float]],
    text_items: List[Tuple[Any, Any]],
    params: Dict[str, Any],
) -> None:
    """Draw subtle connector lines from moved labels to their node anchors."""
    if not text_items:
        return

    color = str(params.get("label_anchor_line_color", "#6E7884"))
    alpha = max(0.0, min(0.9, float(params.get("label_anchor_line_alpha", 0.38))))
    width = max(0.1, float(params.get("label_anchor_line_width", 0.62)))
    min_px = max(2.0, float(params.get("label_anchor_line_min_px", 7.0)))
    min_px_sq = min_px * min_px

    for node, text in text_items:
        if node not in anchor_positions or not text.get_visible():
            continue
        x0, y0 = anchor_positions[node]
        x1, y1 = text.get_position()
        p0 = ax.transData.transform((x0, y0))
        p1 = ax.transData.transform((x1, y1))
        dx = float(p1[0] - p0[0])
        dy = float(p1[1] - p0[1])
        if (dx * dx + dy * dy) < min_px_sq:
            continue
        ax.plot(
            [float(x0), float(x1)],
            [float(y0), float(y1)],
            color=color,
            alpha=alpha,
            linewidth=width,
            solid_capstyle="round",
            zorder=4,
        )


def _draw_node_dots(
    ax,
    positions,
    nodes_table,
    labeled_nodes: set,
    params: Optional[Dict[str, Any]] = None,
) -> None:
    """Draw anchor dots at node positions. In Gephi mode, sizes vary by metric."""
    node_lookup = {row.get("id"): row for row in nodes_table}
    xs: List[float] = []
    ys: List[float] = []
    colors: List[Any] = []
    sizes: List[float] = []

    gephi_fidelity = bool(
        (params or {}).get("gephi_fidelity", False) or (params or {}).get("gephi_quality", False)
    )
    min_node_size = float((params or {}).get("node_min_size", 10.0))
    max_node_size = float((params or {}).get("node_max_size", 120.0))
    metric_key = str((params or {}).get("node_size_metric", "weighted_degree"))

    # In gephi_fidelity, we draw ALL nodes. Otherwise, just labeled_nodes.
    nodes_to_draw = list(positions.keys()) if gephi_fidelity else labeled_nodes
    if not nodes_to_draw:
        return

    # If gephi_fidelity is on, we use the metric to scale sizes
    vals = [float(row.get(metric_key, row.get("degree", 0))) for row in nodes_table]
    v_min = min(vals) if vals else 0.0
    v_max = max(vals) if vals else 1.0
    v_range = max(v_max - v_min, 1e-9)

    for node in nodes_to_draw:
        if node not in positions:
            continue
        x, y = positions[node]
        info = node_lookup.get(node, {})
        comm_id = int(info.get("community", 0) or 0)
        xs.append(float(x))
        ys.append(float(y))
        colors.append(get_community_color(comm_id))

        if gephi_fidelity:
            val = float(info.get(metric_key, info.get("degree", 0)))
            norm = (val - v_min) / v_range
            # Size in Matplotlib 's' is area. Gephi size is treated as diameter.
            # area = pi * (diameter/2)^2
            diameter = min_node_size + (max_node_size - min_node_size) * norm
            area = math.pi * (diameter / 2.0)**2
            sizes.append(area)
        else:
            sizes.append(11.0)

    if xs:
        edgecolors = "none" if gephi_fidelity else "white"
        linewidths = 0.0 if gephi_fidelity else 0.28
        alpha_val = float(params.get("node_alpha", 0.85 if gephi_fidelity else 1.0)) if params else 1.0
        
        if gephi_fidelity:
            # GEPHI FIDELITY: Use true data-coordinate patches instead of scatter (which uses points^2)
            # This ensures node sizes scale perfectly with the graph bounds and Noverlap.
            for x, y, color, size in zip(xs, ys, colors, sizes):
                # sizes list contains area (if scatter) or diameter (if we fix it)
                # Let's use the sizes array directly as diameter, so radius = size/2
                radius = math.sqrt(size / math.pi) if size > 0 else 1.0
                circle = mpatches.Circle(
                    (x, y),
                    radius=radius,
                    facecolor=color,
                    edgecolor=edgecolors if edgecolors != "none" else "none",
                    linewidth=linewidths,
                    alpha=alpha_val,
                    zorder=3
                )
                ax.add_patch(circle)
        else:
            ax.scatter(
                xs,
                ys,
                s=sizes,
                c=colors,
                edgecolors=edgecolors,
                linewidths=linewidths,
                zorder=3,
                marker="o",
                alpha=alpha_val,
            )
