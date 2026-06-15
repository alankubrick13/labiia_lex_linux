"""
Network renderer: ForceAtlas2 layout + Gephi-style Label Adjust.

Reproduces the Gephi workflow:
  1. Build full co-occurrence graph (NOT just MST)
  2. ForceAtlas2 on full graph (communities cluster naturally via shared edges)
  3. Louvain community detection -> color labels AND edges by community
  4. Size labels by weighted degree (power-scaled, dramatic range)
  5. Draw all edges (thin, community-colored, translucent)
  6. Iterative Label Adjust to eliminate overlaps
  7. Stretch to landscape aspect ratio
  8. Result: wide elliptical layout with readable labels
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
import numpy as np

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]

from ..utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# ForceAtlas2 (numpy-vectorized, weight-normalized)
# ---------------------------------------------------------------------------

def _forceatlas2(
    G: "nx.Graph",
    iterations: int = 3000,
    gravity: float = 0.8,
    scaling_ratio: float = 50.0,
    strong_gravity: bool = False,
    edge_weight_influence: float = 0.8,
    jitter_tolerance: float = 1.0,
    seed: Optional[int] = 42,
) -> np.ndarray:
    """
    ForceAtlas2 layout with automatic edge-weight normalization.

    Edge weights are normalized to [0, 1] so that attraction forces
    don't overwhelm repulsion regardless of raw weight magnitude.

    Returns (n, 2) position array.
    """
    n = G.number_of_nodes()
    if n == 0:
        return np.empty((0, 2))
    if n == 1:
        return np.zeros((1, 2))

    rng = np.random.RandomState(seed)
    nodes = list(G.nodes())
    node_idx = {node: i for i, node in enumerate(nodes)}

    # Initial positions: spread proportional to sqrt(n)
    spread = max(10.0, math.sqrt(n) * 3.0)
    pos = rng.randn(n, 2).astype(np.float64) * spread
    degrees = np.array([G.degree(node) + 1 for node in nodes], dtype=np.float64)

    # Build edge arrays
    edge_src = []
    edge_tgt = []
    edge_w = []
    for u, v, data in G.edges(data=True):
        i, j = node_idx[u], node_idx[v]
        w = float(data.get("weight", 1.0))
        if edge_weight_influence != 1.0:
            w = w ** edge_weight_influence
        edge_src.append(i)
        edge_tgt.append(j)
        edge_w.append(w)
    esrc = np.array(edge_src, dtype=np.intp)
    etgt = np.array(edge_tgt, dtype=np.intp)
    ew = np.array(edge_w, dtype=np.float64)
    ne = len(edge_src)

    # --- KEY FIX: Normalize edge weights ---
    # Raw co-occurrence counts (10-100+) create overwhelming attraction.
    # Normalizing to max=1.0 lets scaling_ratio properly balance forces.
    if ne > 0:
        w_max = ew.max()
        if w_max > 1e-9:
            ew = ew / w_max

    speed = 1.0
    speed_efficiency = 1.0
    prev_forces = np.zeros((n, 2), dtype=np.float64)

    for _ in range(iterations):
        forces = np.zeros((n, 2), dtype=np.float64)

        # Repulsion (all-pairs, vectorized)
        dx = pos[:, 0:1] - pos[:, 0:1].T
        dy = pos[:, 1:2] - pos[:, 1:2].T
        dist = np.sqrt(dx * dx + dy * dy)
        np.clip(dist, 0.01, None, out=dist)

        mass_prod = degrees[:, None] * degrees[None, :]
        fmag = scaling_ratio * mass_prod / dist
        np.fill_diagonal(fmag, 0.0)

        forces[:, 0] += (fmag * dx / dist).sum(axis=1)
        forces[:, 1] += (fmag * dy / dist).sum(axis=1)

        # Attraction (along edges)
        if ne > 0:
            adx = pos[etgt, 0] - pos[esrc, 0]
            ady = pos[etgt, 1] - pos[esrc, 1]
            afx = ew * adx
            afy = ew * ady
            np.add.at(forces[:, 0], esrc, afx)
            np.add.at(forces[:, 1], esrc, afy)
            np.add.at(forces[:, 0], etgt, -afx)
            np.add.at(forces[:, 1], etgt, -afy)

        # Gravity
        gdist = np.sqrt(pos[:, 0] ** 2 + pos[:, 1] ** 2)
        np.clip(gdist, 0.01, None, out=gdist)
        if strong_gravity:
            gf = gravity * degrees
        else:
            gf = gravity * degrees / gdist
        forces[:, 0] -= gf * pos[:, 0] / gdist
        forces[:, 1] -= gf * pos[:, 1] / gdist

        # Adaptive speed (Jacomy et al. 2014)
        fnorms = np.sqrt(forces[:, 0] ** 2 + forces[:, 1] ** 2)
        swing_vec = forces - prev_forces
        swing_norms = np.sqrt(swing_vec[:, 0] ** 2 + swing_vec[:, 1] ** 2)
        swing_sum = float(np.sum(swing_norms * degrees))
        pnorms = np.sqrt(prev_forces[:, 0] ** 2 + prev_forces[:, 1] ** 2)
        traction_sum = float(np.sum((fnorms + pnorms) * 0.5 * degrees)) + 0.001

        jt = max(math.sqrt(jitter_tolerance),
                 min(jitter_tolerance,
                     jitter_tolerance * traction_sum / (swing_sum + 0.001)))

        target_speed = jt * speed_efficiency * traction_sum / (swing_sum + 0.001)

        if swing_sum > jitter_tolerance * traction_sum:
            speed_efficiency = max(speed_efficiency * 0.7, 0.05)
        elif speed < 1000:
            speed_efficiency *= 1.3

        speed = speed + min(target_speed - speed, 0.5 * speed)
        speed = max(speed, 0.01)

        node_speed = speed / (1.0 + speed * np.sqrt(fnorms))
        pos[:, 0] += forces[:, 0] * node_speed
        pos[:, 1] += forces[:, 1] * node_speed
        prev_forces = forces.copy()

    return pos


# ---------------------------------------------------------------------------
# Gephi Label Adjust
# ---------------------------------------------------------------------------

def _label_adjust(
    ax: Axes,
    labels_info: List[Dict[str, Any]],
    max_iterations: int = 800,
    speed: float = 2.0,
) -> None:
    """
    Two-phase label overlap resolution:
    Phase 1: Iterative pairwise pushing (Gephi-style) for global convergence.
    Phase 2: Greedy spiral search for any labels still overlapping.
    """
    fig = ax.get_figure()
    renderer = fig.canvas.get_renderer()
    n = len(labels_info)
    if n < 2:
        return

    # --- Phase 1: Iterative pairwise pushing ---
    labels_info.sort(key=lambda info: info["x"])

    for iteration in range(max_iterations):
        t = iteration / max_iterations
        spd = speed * (1.0 - 0.3 * t)
        moved = False

        inv = ax.transData.inverted()
        for info in labels_info:
            bb = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
            info["_x0"] = bb.x0
            info["_y0"] = bb.y0
            info["_x1"] = bb.x1
            info["_y1"] = bb.y1

        for i in range(n):
            ix0 = labels_info[i]["_x0"]
            iy0 = labels_info[i]["_y0"]
            ix1 = labels_info[i]["_x1"]
            iy1 = labels_info[i]["_y1"]
            for j in range(i + 1, n):
                jx0 = labels_info[j]["_x0"]
                if jx0 > ix1:
                    break  # sweep cutoff

                jy0 = labels_info[j]["_y0"]
                jx1 = labels_info[j]["_x1"]
                jy1 = labels_info[j]["_y1"]
                if iy0 >= jy1 or iy1 <= jy0:
                    continue

                ox = min(ix1, jx1) - max(ix0, jx0)
                oy = min(iy1, jy1) - max(iy0, jy0)

                dx = (jx0 + jx1) * 0.5 - (ix0 + ix1) * 0.5
                dy = (jy0 + jy1) * 0.5 - (iy0 + iy1) * 0.5
                if abs(dx) < 1e-4 and abs(dy) < 1e-4:
                    dx = 0.01 * (1 if i % 2 == 0 else -1)
                    dy = 0.005

                if ox < oy:
                    push = (ox * 0.55 + 0.002) * spd
                    s = 1.0 if dx >= 0 else -1.0
                    labels_info[i]["x"] -= s * push * 0.5
                    labels_info[j]["x"] += s * push * 0.5
                    labels_info[i]["_x0"] -= s * push * 0.5
                    labels_info[i]["_x1"] -= s * push * 0.5
                    labels_info[j]["_x0"] += s * push * 0.5
                    labels_info[j]["_x1"] += s * push * 0.5
                else:
                    push = (oy * 0.55 + 0.002) * spd
                    s = 1.0 if dy >= 0 else -1.0
                    labels_info[i]["y"] -= s * push * 0.5
                    labels_info[j]["y"] += s * push * 0.5
                    labels_info[i]["_y0"] -= s * push * 0.5
                    labels_info[i]["_y1"] -= s * push * 0.5
                    labels_info[j]["_y0"] += s * push * 0.5
                    labels_info[j]["_y1"] += s * push * 0.5

                moved = True

        for info in labels_info:
            info["text_obj"].set_position((info["x"], info["y"]))
        labels_info.sort(key=lambda info: info["x"])

        if not moved:
            break

    # --- Phase 2: Greedy spiral fix for remaining overlaps ---
    # Sort by font size (biggest first = highest priority)
    labels_info.sort(key=lambda info: info.get("fontsize", 0), reverse=True)
    inv = ax.transData.inverted()

    placed_bboxes = []
    for info in labels_info:
        bb = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
        if not _bbox_overlaps_any(bb, placed_bboxes):
            placed_bboxes.append(bb)
            continue

        # Spiral search for nearest non-overlapping position
        orig_x, orig_y = info["x"], info["y"]
        step = max(bb.width, bb.height) * 0.5
        found = False
        for ring in range(1, 40):
            r = step * ring
            n_angles = max(8, ring * 6)
            for ai in range(n_angles):
                angle = 2 * math.pi * ai / n_angles
                nx_ = orig_x + r * math.cos(angle)
                ny_ = orig_y + r * math.sin(angle)
                info["text_obj"].set_position((nx_, ny_))
                bb2 = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
                if not _bbox_overlaps_any(bb2, placed_bboxes):
                    info["x"] = nx_
                    info["y"] = ny_
                    placed_bboxes.append(bb2)
                    found = True
                    break
            if found:
                break

        if not found:
            # Keep at phase-1 position
            info["text_obj"].set_position((orig_x, orig_y))
            placed_bboxes.append(
                inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer)))


def _bezier_points(
    p0: Tuple[float, float],
    p2: Tuple[float, float],
    curvature: float = 0.15,
    n: int = 20,
    flip: bool = False,
) -> List[Tuple[float, float]]:
    """
    Quadratic Bézier curve between two node positions.
    The control point is offset perpendicularly from the midpoint,
    creating the flowing curved-line look of Gephi.
    """
    mx = (p0[0] + p2[0]) * 0.5
    my = (p0[1] + p2[1]) * 0.5
    dx = p2[0] - p0[0]
    dy = p2[1] - p0[1]
    length = max(math.sqrt(dx * dx + dy * dy), 1e-6)
    sign = -1.0 if flip else 1.0
    ctrl_x = mx + sign * (-dy / length) * length * curvature
    ctrl_y = my + sign * (dx / length) * length * curvature
    t = np.linspace(0, 1, n)
    bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl_x + t ** 2 * p2[0]
    by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl_y + t ** 2 * p2[1]
    return list(zip(bx.tolist(), by.tolist()))


def _bbox_overlaps_any(bb, bboxes) -> bool:
    """Check if a bounding box overlaps any in a list."""
    for other in bboxes:
        if bb.x0 < other.x1 and bb.x1 > other.x0 and bb.y0 < other.y1 and bb.y1 > other.y0:
            return True
    return False


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

_COMMUNITY_COLORS_CLASSIC = [
    "#E41A1C", "#377EB8", "#4DAF4A", "#FF7F00", "#984EA3",
    "#A65628", "#F781BF", "#66C2A5", "#FC8D62", "#8DA0CB",
    "#E78AC3", "#A6D854", "#FFD92F", "#B3B3B3",
]

_COMMUNITY_COLORS_GEPHI = [
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


def _community_color_map(
    communities: Dict[Any, int],
    rendering_style: str = "gephi",
) -> Dict[int, str]:
    """Map community IDs to colors, using vibrant Gephi palette or classic."""
    palette = (
        _COMMUNITY_COLORS_GEPHI if rendering_style == "gephi"
        else _COMMUNITY_COLORS_CLASSIC
    )
    unique_ids = sorted(set(communities.values()))
    return {cid: palette[i % len(palette)]
            for i, cid in enumerate(unique_ids)}


def _lighten(hex_color: str, factor: float = 0.5) -> str:
    """Lighten a hex color toward white."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _adaptive_edge_alpha(n_edges: int, base_alpha: float = 0.30) -> float:
    """
    Scale per-edge alpha inversely to edge count so dense graphs
    create rich colored webs without oversaturation.

    Formula: alpha = base_alpha * (300 / n_edges) ^ 0.25
    Clamped to [0.08, 0.45].

    The gentle exponent (0.25) keeps edges visible even in dense graphs.
    Reference:  50 edges -> ~0.43 | 300 -> 0.30 | 1000 -> 0.22 | 5000 -> 0.14
    """
    if n_edges <= 0:
        return base_alpha
    raw = base_alpha * (300.0 / n_edges) ** 0.25
    return max(0.08, min(0.45, raw))


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

class NetworkRenderer:

    def __init__(
        self,
        cooc_matrix_path: Path,
        communities_path: Optional[Path] = None,
        centrality_path: Optional[Path] = None,
    ):
        self.cooc_matrix_path = Path(cooc_matrix_path)
        self.communities_path = Path(communities_path) if communities_path else None
        self.centrality_path = Path(centrality_path) if centrality_path else None

    def render(
        self,
        output_path: Path,
        width: int = 1200,
        height: int = 900,
        dpi: int = 150,
        use_mst: bool = True,
        min_edge: float = 0,
        show_halo: bool = True,
        grayscale: bool = False,
        fa2_iterations: int = 3000,
        fa2_gravity: float = 15.0,
        fa2_scaling: float = 1.0,
        label_adjust_iterations: int = 1200,
        font_family: str = "sans-serif",
        typegraph: str = "png",
        rendering_style: str = "gephi",
        export_per_community: bool = False,
    ) -> Path:
        if nx is None:
            raise ImportError("networkx is required")

        output_path = Path(output_path)

        # 1. Build FULL graph (for FA2 layout - many edges = better clustering)
        G_full = self._build_graph(min_edge=min_edge)
        if G_full.number_of_nodes() < 2:
            raise ValueError("Graph has fewer than 2 nodes")

        n_nodes = G_full.number_of_nodes()
        nodes = list(G_full.nodes())

        # 2. Communities
        communities = self._load_communities()
        if not communities:
            communities = self._detect_communities(G_full)

        # 3. Centrality
        centrality = self._load_centrality()
        if not centrality:
            centrality = {node: float(G_full.degree(node, weight="weight"))
                          for node in nodes}

        # 4. Adaptive font sizes with rank-based scaling
        # Rank normalization handles skewed centrality distributions properly
        # (value-based normalization would put 90%+ of labels at minimum size)
        fmin, fmax = self._font_range(n_nodes)
        cent_arr = np.array([centrality.get(n, 1.0) for n in nodes])
        if n_nodes > 1 and cent_arr.max() > cent_arr.min():
            ranks = np.argsort(np.argsort(cent_arr)).astype(np.float64)
            normalized = (ranks / (n_nodes - 1)) ** 1.3
        else:
            normalized = np.full(n_nodes, 0.5)
        font_sizes = fmin + normalized * (fmax - fmin)
        label_sizes = {nodes[i]: float(font_sizes[i]) for i in range(n_nodes)}

        # 5. FA2 on FULL graph — strong gravity keeps all communities in one central blob
        pos_arr = _forceatlas2(
            G_full,
            iterations=fa2_iterations,
            gravity=fa2_gravity,
            scaling_ratio=fa2_scaling,
            strong_gravity=True,   # gravity * mass (distance-independent) → nodes don't scatter
            seed=42,
        )

        # --- Position normalization: compress to Gephi-like compact ellipse ---
        # Center positions
        center = pos_arr.mean(axis=0)
        pos_arr -= center

        # Scale to unit sphere using 85th-percentile distance (keeps outliers visible)
        dists = np.sqrt((pos_arr ** 2).sum(axis=1))
        scale = float(np.percentile(dists, 85))
        if scale > 1e-6:
            pos_arr /= scale

        # Stretch to canvas aspect ratio (creates elliptical shape like Gephi)
        aspect = width / max(height, 1)
        if aspect > 1.05:
            pos_arr[:, 0] *= math.sqrt(aspect)
            pos_arr[:, 1] /= math.sqrt(aspect)

        pos = {nodes[i]: (float(pos_arr[i, 0]), float(pos_arr[i, 1]))
               for i in range(n_nodes)}

        # 6. Decide which edges to draw
        mst_edges = set()
        if use_mst and G_full.number_of_edges() > n_nodes * 2:
            try:
                G_neg = G_full.copy()
                for u, v, d in G_neg.edges(data=True):
                    d["weight"] = -d.get("weight", 1.0)
                mst_g = nx.minimum_spanning_tree(G_neg)
                mst_edges = set(mst_g.edges())
                mst_edges |= {(v, u) for u, v in mst_edges}
            except Exception:
                pass

        # 7. Render
        fig_w = width / dpi
        fig_h = height / dpi
        fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
        ax.axis("off")
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        # Color map
        cmap = _community_color_map(communities, rendering_style=rendering_style) if not grayscale else {}
        node_colors = {}
        for node in nodes:
            cid = communities.get(node, 0)
            if grayscale:
                node_colors[node] = "#444444"
            else:
                node_colors[node] = cmap.get(cid, "#333333")

        # 7a. Draw community halos
        if show_halo and not grayscale and cmap:
            all_x = [pos[n][0] for n in nodes]
            all_y = [pos[n][1] for n in nodes]
            extent = max(max(all_x) - min(all_x), max(all_y) - min(all_y), 1.0)
            pad = extent * 0.06
            self._draw_halos(ax, pos, communities, cmap, pad)

        # 7b. Draw edges as Bézier curves
        edge_weights = [d.get("weight", 1.0) for _, _, d in G_full.edges(data=True)]
        max_ew = max(edge_weights) if edge_weights else 1.0
        n_edges = G_full.number_of_edges()

        is_gephi_mode = (rendering_style == "gephi") and not grayscale

        if is_gephi_mode:
            # ── GEPHI MODE ──────────────────────────────────────────────
            # All edges at uniform low alpha with full community colors.
            # The accumulation of thousands of thin semi-transparent edges
            # creates the dense colored "webs" that define each cluster.
            edge_alpha = _adaptive_edge_alpha(n_edges)

            all_segs, all_colors, all_widths = [], [], []
            for idx, (u, v, data) in enumerate(G_full.edges(data=True)):
                if u not in pos or v not in pos:
                    continue

                cu = communities.get(u, -1)

                # Edge color = source node's community color (full saturation).
                # Intra-community: both nodes share color -> colored edge.
                # Inter-community: source color -> colored tendrils between clusters.
                ec = cmap.get(cu, "#888888")

                flip = bool(idx % 2)
                curve_pts = _bezier_points(pos[u], pos[v], curvature=0.14, n=18, flip=flip)

                w = data.get("weight", 1.0)
                lw = 0.5 + (w / max_ew) * 1.0   # range: 0.50-1.50

                all_segs.append(curve_pts)
                all_colors.append(ec)
                all_widths.append(lw)

            if all_segs:
                lc = LineCollection(
                    all_segs, colors=all_colors,
                    linewidths=all_widths,
                    alpha=edge_alpha, zorder=1, capstyle="round",
                )
                ax.add_collection(lc)

        else:
            # ── CLASSIC MODE ────────────────────────────────────────────
            # Two-pass MST/non-MST rendering with lightened community colors.
            non_mst_segs, non_mst_colors, non_mst_widths = [], [], []
            mst_segs, mst_colors, mst_widths = [], [], []

            for idx, (u, v, data) in enumerate(G_full.edges(data=True)):
                if u not in pos or v not in pos:
                    continue

                w = data.get("weight", 1.0)
                is_mst = (u, v) in mst_edges or (v, u) in mst_edges

                cu = communities.get(u, -1)
                cv = communities.get(v, -1)

                if grayscale:
                    ec = "#888888"
                elif cu == cv and cu in cmap:
                    ec = _lighten(cmap[cu], 0.20)
                else:
                    ec = "#CCCCCC"

                flip = bool(idx % 2)
                curve_pts = _bezier_points(pos[u], pos[v], curvature=0.14, n=18, flip=flip)

                lw = 0.5 + (w / max_ew) * 1.8
                if is_mst:
                    lw_mst = lw * 1.8
                    mst_segs.append(curve_pts)
                    mst_colors.append(ec)
                    mst_widths.append(lw_mst)
                else:
                    non_mst_segs.append(curve_pts)
                    non_mst_colors.append(ec)
                    non_mst_widths.append(lw)

            if non_mst_segs:
                lc_bg = LineCollection(
                    non_mst_segs, colors=non_mst_colors,
                    linewidths=non_mst_widths,
                    alpha=0.30, zorder=1, capstyle="round",
                )
                ax.add_collection(lc_bg)

            if mst_segs:
                lc_fg = LineCollection(
                    mst_segs, colors=mst_colors,
                    linewidths=mst_widths,
                    alpha=0.60, zorder=2, capstyle="round",
                )
                ax.add_collection(lc_fg)

        # 7c. Set initial axis limits (generous padding for label adjust)
        all_x = [pos[n][0] for n in nodes]
        all_y = [pos[n][1] for n in nodes]
        xr = max(all_x) - min(all_x) if len(all_x) > 1 else 1.0
        yr = max(all_y) - min(all_y) if len(all_y) > 1 else 1.0
        px = xr * 0.50
        py = yr * 0.50
        ax.set_xlim(min(all_x) - px, max(all_x) + px)
        ax.set_ylim(min(all_y) - py, max(all_y) + py)

        # 7d. Draw labels (biggest first for z-ordering)
        fig.canvas.draw()

        labels_info = []
        sorted_nodes = sorted(nodes, key=lambda n: label_sizes.get(n, 0), reverse=True)

        for node in sorted_nodes:
            if node not in pos:
                continue
            x, y = pos[node]
            fs = label_sizes.get(node, fmin)
            col = node_colors.get(node, "#333333")

            t = ax.text(
                x, y, str(node),
                fontsize=fs, fontfamily=font_family, fontweight="bold",
                color=col, ha="center", va="center", zorder=4,
            )
            labels_info.append({"text_obj": t, "x": x, "y": y, "node": node, "fontsize": fs})

        # 7e. Label Adjust
        fig.canvas.draw()
        _label_adjust(ax, labels_info, max_iterations=label_adjust_iterations)
        fig.canvas.draw()

        # 7f. Expand axis limits to include all displaced labels
        inv = ax.transData.inverted()
        renderer = fig.canvas.get_renderer()
        lx_min = float("inf")
        lx_max = float("-inf")
        ly_min = float("inf")
        ly_max = float("-inf")
        for info in labels_info:
            bb = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
            lx_min = min(lx_min, bb.x0)
            lx_max = max(lx_max, bb.x1)
            ly_min = min(ly_min, bb.y0)
            ly_max = max(ly_max, bb.y1)
        if lx_min < float("inf"):
            final_px = (lx_max - lx_min) * 0.03
            final_py = (ly_max - ly_min) * 0.03
            ax.set_xlim(lx_min - final_px, lx_max + final_px)
            ax.set_ylim(ly_min - final_py, ly_max + final_py)
        fig.canvas.draw()

        # 8. Save main image
        fig.tight_layout(pad=0.3)
        fmt = "svg" if typegraph == "svg" else "png"
        if not str(output_path).lower().endswith(f".{fmt}"):
            output_path = output_path.with_suffix(f".{fmt}")
        fig.savefig(str(output_path), format=fmt, bbox_inches="tight",
                    facecolor="white", dpi=dpi if fmt == "png" else 72)

        # Save axis limits for per-community images
        main_xlim = ax.get_xlim()
        main_ylim = ax.get_ylim()
        plt.close(fig)
        log.info(f"Network rendered: {n_nodes} nodes, {G_full.number_of_edges()} edges -> {output_path}")

        # 9. Per-community export: one image per cluster highlighting only
        #    that community's edges in color, all others very faint.
        if export_per_community and not grayscale and cmap:
            # Build adjusted positions from label adjust pass
            adjusted_pos = {}
            for info in labels_info:
                t_obj = info["text_obj"]
                adjusted_pos[info["node"]] = (t_obj.get_position()[0],
                                               t_obj.get_position()[1])

            comm_ids = sorted(set(communities.values()))
            stem = output_path.stem
            suffix = output_path.suffix
            parent = output_path.parent

            # Compute halo padding once (reuse extent from main figure)
            all_x = [pos[n][0] for n in nodes]
            all_y = [pos[n][1] for n in nodes]
            extent = max(max(all_x) - min(all_x), max(all_y) - min(all_y), 1.0)
            pad_comm = extent * 0.06

            for target_cid in comm_ids:
                fig_c, ax_c = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
                ax_c.axis("off")
                fig_c.patch.set_facecolor("white")
                ax_c.set_facecolor("white")

                # Halo for target community only
                if show_halo:
                    single_comm = {n: c for n, c in communities.items()
                                   if c == target_cid and n in pos}
                    if len(single_comm) >= 2:
                        self._draw_halos(ax_c, pos, single_comm, cmap, pad_comm)

                # Edges: target community in full color, others very faint
                target_color = cmap.get(target_cid, "#888888")
                comm_alpha = _adaptive_edge_alpha(n_edges, base_alpha=0.40)

                comm_segs, comm_colors, comm_widths = [], [], []
                other_segs, other_widths = [], []

                for idx2, (u2, v2, data2) in enumerate(G_full.edges(data=True)):
                    if u2 not in pos or v2 not in pos:
                        continue
                    cu2 = communities.get(u2, -1)
                    cv2 = communities.get(v2, -1)
                    flip2 = bool(idx2 % 2)
                    pts = _bezier_points(pos[u2], pos[v2], curvature=0.14, n=18, flip=flip2)
                    w2 = data2.get("weight", 1.0)

                    if cu2 == target_cid or cv2 == target_cid:
                        comm_segs.append(pts)
                        comm_colors.append(target_color)
                        comm_widths.append(0.5 + (w2 / max_ew) * 1.0)
                    else:
                        other_segs.append(pts)
                        other_widths.append(0.2)

                if other_segs:
                    lc_oth = LineCollection(
                        other_segs, colors=["#E8E8E8"] * len(other_segs),
                        linewidths=other_widths,
                        alpha=0.06, zorder=1, capstyle="round",
                    )
                    ax_c.add_collection(lc_oth)

                if comm_segs:
                    lc_comm = LineCollection(
                        comm_segs, colors=comm_colors,
                        linewidths=comm_widths,
                        alpha=comm_alpha, zorder=2, capstyle="round",
                    )
                    ax_c.add_collection(lc_comm)

                # Labels: target community in color, others light gray
                for node in sorted_nodes:
                    if node not in pos:
                        continue
                    lx, ly = adjusted_pos.get(node, pos[node])
                    fs_c = label_sizes.get(node, fmin)
                    cid_c = communities.get(node, -1)
                    col_c = cmap.get(cid_c, "#333333") if cid_c == target_cid else "#CCCCCC"

                    ax_c.text(
                        lx, ly, str(node),
                        fontsize=fs_c, fontfamily=font_family, fontweight="bold",
                        color=col_c, ha="center", va="center", zorder=4,
                    )

                ax_c.set_xlim(main_xlim)
                ax_c.set_ylim(main_ylim)

                fig_c.tight_layout(pad=0.3)
                comm_path = parent / f"{stem}_community_{target_cid}{suffix}"
                fig_c.savefig(
                    str(comm_path), format=fmt, bbox_inches="tight",
                    facecolor="white", dpi=dpi if fmt == "png" else 72,
                )
                plt.close(fig_c)
                log.info(f"Community {target_cid} image: {comm_path}")

        return output_path

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _font_range(n: int) -> Tuple[float, float]:
        """Adaptive (min, max) fontsize based on node count."""
        if n <= 25:
            return (6.0, 32.0)
        elif n <= 50:
            return (5.0, 28.0)
        elif n <= 100:
            return (4.0, 24.0)
        elif n <= 200:
            return (3.5, 22.0)
        elif n <= 350:
            return (3.0, 16.0)
        else:
            return (2.5, 12.0)

    @staticmethod
    def _draw_halos(ax, pos, communities, cmap, padding):
        comm_nodes: Dict[int, list] = {}
        for node, cid in communities.items():
            if node in pos:
                comm_nodes.setdefault(cid, []).append(node)
        for cid, nlist in comm_nodes.items():
            if len(nlist) < 2:
                continue
            xs = [pos[n][0] for n in nlist]
            ys = [pos[n][1] for n in nlist]
            cx, cy = float(np.mean(xs)), float(np.mean(ys))
            rx = (max(xs) - min(xs)) / 2 + padding
            ry = (max(ys) - min(ys)) / 2 + padding
            rx = max(rx, padding)
            ry = max(ry, padding)
            color = cmap.get(cid, "#CCCCCC")
            ax.add_patch(mpatches.Ellipse(
                (cx, cy), rx * 2, ry * 2,
                facecolor=color, edgecolor="none", alpha=0.08, zorder=0))

    def _build_graph(self, min_edge: float = 0) -> "nx.Graph":
        mat, labels = self._read_matrix(self.cooc_matrix_path)
        n = len(labels)
        G = nx.Graph()
        for i in range(n):
            G.add_node(labels[i])
        for i in range(n):
            for j in range(i + 1, n):
                w = mat[i][j]
                if w > min_edge:
                    G.add_edge(labels[i], labels[j], weight=w)
        isolates = list(nx.isolates(G))
        G.remove_nodes_from(isolates)
        return G

    def _load_communities(self) -> Optional[Dict[str, int]]:
        if not self.communities_path or not self.communities_path.exists():
            return None
        comms: Dict[str, int] = {}
        for row in self._read_csv(self.communities_path):
            term = str(row.get("term", row.get("node", ""))).strip()
            c = row.get("community", "")
            if term and c not in (None, ""):
                try:
                    comms[term] = int(float(str(c)))
                except (ValueError, TypeError):
                    pass
        return comms or None

    def _load_centrality(self) -> Optional[Dict[str, float]]:
        if not self.centrality_path or not self.centrality_path.exists():
            return None
        cent: Dict[str, float] = {}
        for row in self._read_csv(self.centrality_path):
            term = str(row.get("term", row.get("node", ""))).strip()
            v = row.get("weighted_degree", row.get("degree", ""))
            if term and v not in (None, ""):
                try:
                    cent[term] = float(str(v))
                except (ValueError, TypeError):
                    pass
        return cent or None

    def _detect_communities(self, G) -> Dict[str, int]:
        try:
            parts = nx.community.louvain_communities(G, seed=42)
            comms: Dict[str, int] = {}
            for cid, members in enumerate(parts):
                for node in members:
                    comms[str(node)] = cid
            return comms
        except Exception:
            return {str(n): 0 for n in G.nodes()}

    @staticmethod
    def _read_matrix(path: Path) -> Tuple[List[List[float]], List[str]]:
        with open(path, "r", encoding="utf-8", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            sep = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.reader(f, delimiter=sep)
            header = next(reader, None)
            if not header:
                return [], []
            matrix, labels = [], []
            for row in reader:
                if not row:
                    continue
                labels.append(row[0].strip().strip('"'))
                vals = []
                for cell in row[1:]:
                    try:
                        vals.append(float(cell))
                    except (ValueError, TypeError):
                        vals.append(0.0)
                matrix.append(vals)
            return matrix, labels

    @staticmethod
    def _read_csv(path: Path) -> List[Dict[str, str]]:
        with open(path, "r", encoding="utf-8", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                d = csv.Sniffer().sniff(sample, delimiters=",;")
                sep = d.delimiter
            except csv.Error:
                sep = ";" if ";" in sample else ","
            return [dict(row) for row in csv.DictReader(f, delimiter=sep) if row]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_similarity_network(
    cooc_matrix_path: Path,
    output_path: Path,
    communities_path: Optional[Path] = None,
    centrality_path: Optional[Path] = None,
    width: int = 1200,
    height: int = 900,
    dpi: int = 150,
    use_mst: bool = True,
    min_edge: float = 0,
    show_halo: bool = True,
    grayscale: bool = False,
    typegraph: str = "png",
    rendering_style: str = "gephi",
    export_per_community: bool = False,
) -> Optional[Path]:
    """
    Render similarity network (ForceAtlas2 + Label Adjust).

    rendering_style: "gephi" (dense colored webs) or "classic" (MST-based).
    export_per_community: if True, also saves one image per community cluster.
    Returns path to main image, or None on failure.
    """
    try:
        r = NetworkRenderer(cooc_matrix_path, communities_path, centrality_path)
        return r.render(
            output_path=output_path, width=width, height=height,
            dpi=dpi,
            use_mst=use_mst, min_edge=min_edge,
            show_halo=show_halo, grayscale=grayscale, typegraph=typegraph,
            rendering_style=rendering_style,
            export_per_community=export_per_community,
        )
    except Exception as exc:
        log.warning(f"Python network renderer failed: {exc}", exc_info=True)
        return None
