"""Readable CHD dendrogram rendering for LabiiaLex 1.0.9."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt

from src.core.chart_theme import ggplot_hue, save_figure
from src.core.stopword_policy import is_chd_visual_content_term


ProfileRow = Tuple[str, float, int, float, str]


@dataclass
class _TreeNode:
    label: Optional[int] = None
    children: Optional[List["_TreeNode"]] = None

    @property
    def is_leaf(self) -> bool:
        return self.label is not None


def _tokenize_newick(value: str) -> List[str]:
    return re.findall(r"\d+|[(),;]", str(value or ""))


def _parse_newick(value: str, allowed: set[int]) -> Optional[_TreeNode]:
    tokens = _tokenize_newick(value)
    if not tokens:
        return None
    idx = 0

    def parse_node() -> Optional[_TreeNode]:
        nonlocal idx
        if idx >= len(tokens):
            return None
        token = tokens[idx]
        if token == "(":
            idx += 1
            children: List[_TreeNode] = []
            while idx < len(tokens) and tokens[idx] != ")":
                child = parse_node()
                if child is not None:
                    children.append(child)
                if idx < len(tokens) and tokens[idx] == ",":
                    idx += 1
            if idx < len(tokens) and tokens[idx] == ")":
                idx += 1
            return _TreeNode(children=children) if children else None
        if token.isdigit():
            idx += 1
            label = int(token)
            return _TreeNode(label=label) if label in allowed else None
        idx += 1
        return None

    return parse_node()


def _leaf_order_from_tree(node: Optional[_TreeNode]) -> List[int]:
    if node is None:
        return []
    if node.is_leaf:
        return [int(node.label)]
    leaves: List[int] = []
    for child in node.children or []:
        leaves.extend(_leaf_order_from_tree(child))
    return leaves


def _balanced_tree(class_ids: Sequence[int]) -> Optional[_TreeNode]:
    ids = [int(cid) for cid in class_ids]
    if not ids:
        return None
    if len(ids) == 1:
        return _TreeNode(label=ids[0])
    mid = len(ids) // 2
    children = [
        node for node in (_balanced_tree(ids[:mid]), _balanced_tree(ids[mid:])) if node is not None
    ]
    return _TreeNode(children=children)


def _tree_depth(node: Optional[_TreeNode]) -> int:
    if node is None or node.is_leaf:
        return 0
    return 1 + max((_tree_depth(child) for child in node.children or []), default=0)


def _filter_profile_rows(rows: Iterable[ProfileRow], *, limit: int) -> tuple[List[str], int, int]:
    visible: List[str] = []
    removed = 0
    hidden = 0
    seen: set[str] = set()
    limit = max(1, min(int(limit), 18))
    for item in rows or []:
        if len(item) < 2:
            continue
        word = str(item[0] or "").strip()
        if not word:
            continue
        if not is_chd_visual_content_term(word):
            removed += 1
            continue
        if word.lower() in seen:
            continue
        seen.add(word.lower())
        if len(visible) < limit:
            visible.append(word)
        else:
            hidden += 1
    return visible, removed, hidden


def _draw_tree(
    ax,
    node: Optional[_TreeNode],
    x_by_class: Dict[int, float],
    *,
    base_y: float,
    y_step: float,
    color: str,
) -> tuple[float, float]:
    if node is None:
        return 0.0, base_y
    if node.is_leaf:
        return float(x_by_class.get(int(node.label), 0.0)), base_y
    child_points = [
        _draw_tree(ax, child, x_by_class, base_y=base_y, y_step=y_step, color=color)
        for child in node.children or []
    ]
    child_points = [point for point in child_points if point[0] > 0]
    if not child_points:
        return 0.0, base_y
    y = max(point[1] for point in child_points) + y_step
    xs = [point[0] for point in child_points]
    ax.plot([min(xs), max(xs)], [y, y], color=color, linewidth=1.8, solid_capstyle="round")
    for x_child, y_child in child_points:
        ax.plot([x_child, x_child], [y_child, y], color=color, linewidth=1.8, solid_capstyle="round")
    return sum(xs) / len(xs), y


def render_chd_dendrogram(
    *,
    profiles: Dict[int, List[ProfileRow]],
    class_sizes: Dict[int, int],
    output_path: Path,
    layout_path: Path,
    newick: Optional[str] = None,
    max_terms_per_class: int = 16,
) -> Path:
    """Render a readable CHD dendrogram and write layout diagnostics."""
    output_path = Path(output_path)
    layout_path = Path(layout_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    layout_path.parent.mkdir(parents=True, exist_ok=True)

    class_ids = [
        int(cid)
        for cid in sorted(int(raw) for raw in (profiles or {}).keys())
        if int(cid) > 0 and int(class_sizes.get(int(cid), 0)) > 0
    ]
    if len(class_ids) < 2:
        raise ValueError("CHD dendrogram needs at least two non-empty classes")

    parsed = _parse_newick(str(newick or ""), set(class_ids))
    order = [cid for cid in _leaf_order_from_tree(parsed) if cid in class_ids]
    for cid in class_ids:
        if cid not in order:
            order.append(cid)
    tree = parsed if parsed is not None and len(order) >= 2 else _balanced_tree(order)

    n_classes = len(order)
    colors = ggplot_hue(n_classes)
    color_by_class = {cid: colors[idx % len(colors)] for idx, cid in enumerate(order)}
    x_by_class = {cid: float(idx + 1) for idx, cid in enumerate(order)}
    total_segments = float(sum(max(0, int(class_sizes.get(cid, 0))) for cid in order)) or 1.0

    fig_width = max(11.0, 2.25 * n_classes)
    fig_height = max(8.8, 7.2 + min(2.4, max_terms_per_class * 0.05))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    ax.set_xlim(0.35, n_classes + 0.65)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    depth = max(1, _tree_depth(tree))
    base_y = 0.68
    y_step = 0.22 / depth
    _draw_tree(ax, tree, x_by_class, base_y=base_y, y_step=y_step, color="#2D2D2D")

    filtered_removed = 0
    classes_payload: List[Dict[str, Any]] = []
    for idx, cid in enumerate(order):
        x = x_by_class[cid]
        color = color_by_class[cid]
        pct = (float(class_sizes.get(cid, 0)) / total_segments) * 100.0
        visible_terms, removed, hidden_terms_count = _filter_profile_rows(
            profiles.get(cid, []),
            limit=max_terms_per_class,
        )
        filtered_removed += removed

        ax.text(
            x,
            0.60,
            f"classe {cid}",
            ha="center",
            va="center",
            fontsize=11,
            fontweight="bold",
            color=color,
        )
        rect_w = min(0.92, max(0.68, 4.2 / max(n_classes, 1)))
        rect_h = 0.065
        rect = patches.FancyBboxPatch(
            (x - rect_w / 2, 0.515 - rect_h / 2),
            rect_w,
            rect_h,
            boxstyle="round,pad=0.008,rounding_size=0.006",
            linewidth=1.0,
            edgecolor="#1F1F1F",
            facecolor=color,
        )
        ax.add_patch(rect)
        ax.text(
            x,
            0.515,
            f"{pct:.1f}%",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="#FFFFFF",
        )

        y = 0.43
        visible_count = max(1, len(visible_terms))
        term_step = min(0.036, max(0.019, 0.405 / visible_count))
        for rank, word in enumerate(visible_terms):
            size = max(7.2, min(11.4, 11.0 - rank * 0.055))
            ax.text(
                x - rect_w / 2,
                y,
                word,
                ha="left",
                va="top",
                fontsize=size,
                color=color,
            )
            y -= term_step
            if y < 0.035:
                break

        classes_payload.append(
            {
                "class_id": int(cid),
                "leaf_x": float(x),
                "label_center_x": float(x),
                "box_center_x": float(x),
                "percentage": round(float(pct), 4),
                "visible_terms": visible_terms,
                "hidden_terms_count": int(hidden_terms_count),
                "color": color,
            }
        )

    ax.set_title(
        "Classificação Hierárquica Descendente (CHD)",
        fontsize=14,
        fontweight="semibold",
        color="#2D2D2D",
        pad=14,
    )

    layout_payload = {
        "renderer": "labiialex_chd_readable_1.0.9",
        "classes": classes_payload,
        "filtered_terms": {"removed_count": int(filtered_removed)},
        "newick": str(newick or ""),
    }
    layout_path.write_text(json.dumps(layout_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_figure(fig, output_path, dpi=160)
    return output_path
