"""
Bridge de tema para widgets ttk/tk usados junto ao CustomTkinter.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple


def _resolve_rowheight(density: str) -> int:
    density_key = str(density or "comfortable").lower()
    if density_key == "compact":
        return 22
    if density_key == "spacious":
        return 30
    return 26


def build_treeview_style_options(
    colors: Mapping[str, str],
    fonts: Mapping[str, tuple],
    density: str = "comfortable",
) -> Dict[str, Any]:
    """Retorna opcoes padrao para estilizar Treeview sem side effects."""
    return {
        "rowheight": _resolve_rowheight(density),
        "font": fonts.get("small", ("Segoe UI", 10)),
        "background": colors.get("surface", "#FFFFFF"),
        "fieldbackground": colors.get("surface", "#FFFFFF"),
        "foreground": colors.get("text", "#242424"),
        "borderwidth": 0,
        "relief": "flat",
    }


def build_treeview_heading_style_options(
    colors: Mapping[str, str],
    fonts: Mapping[str, tuple],
) -> Dict[str, Any]:
    return {
        "font": fonts.get("small", ("Segoe UI", 10)),
        "background": colors.get("header_bg", colors.get("surface", "#FAFAFA")),
        "foreground": colors.get("text", "#242424"),
        "relief": "flat",
        "borderwidth": 0,
    }


def build_treeview_style_map(colors: Mapping[str, str]) -> Dict[str, Tuple[Tuple[str, str], ...]]:
    return {
        "background": (("selected", colors.get("selection", "#CCE4F7")),),
        "foreground": (("selected", colors.get("text", "#242424")),),
    }


def apply_ttk_windows_styles(
    style: Any,
    *,
    colors: Mapping[str, str],
    fonts: Mapping[str, tuple],
    density: str = "comfortable",
) -> None:
    """
    Aplica estilos ttk de forma centralizada.

    Mantem estilo padrao em classes usadas no app sem depender de cada widget.
    """
    tree_options = build_treeview_style_options(colors, fonts, density=density)
    heading_options = build_treeview_heading_style_options(colors, fonts)
    tree_map = build_treeview_style_map(colors)

    style.configure("Lexi.Treeview", **tree_options)
    style.configure("Lexi.Treeview.Heading", **heading_options)
    style.map("Lexi.Treeview", **tree_map)

    style.configure("Lexi.DataGrid.Treeview", **tree_options)
    style.configure("Lexi.DataGrid.Treeview.Heading", **heading_options)
    style.map("Lexi.DataGrid.Treeview", **tree_map)

    style.configure(
        "Lexi.Status.Horizontal.TProgressbar",
        troughcolor=colors.get("surface", "#E2E2E2"),
        bordercolor=colors.get("border", "#BCBCBC"),
        background=colors.get("primary", "#0078D4"),
        lightcolor=colors.get("primary", "#0078D4"),
        darkcolor=colors.get("primary", "#0078D4"),
    )

