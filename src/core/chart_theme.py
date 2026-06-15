"""
chart_theme.py — Tema visual ggplot2-inspirado para LabiiaLex.

Centraliza todas as constantes visuais, paletas e helpers de figura.
Nenhum modulo de analise deve definir cores, fontes ou estilos localmente.

Paleta qualitativa: formula identica ao scale_colour_hue() do ggplot2.
  HCL: hues igualmente espacados em [15, 375), C=100, L=65.
Layout: fundo branco, grid sutil, spines minimas — theme_minimal() do R.
"""
from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure


# ─── Conversao HCL → sRGB ─────────────────────────────────────────────────────

def _lab_to_xyz(L: float, a: float, b: float) -> tuple[float, float, float]:
    """CIELAB → XYZ (iluminante D65)."""
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    delta = 6.0 / 29.0

    def f_inv(t: float) -> float:
        return t ** 3 if t > delta else 3.0 * delta ** 2 * (t - 4.0 / 29.0)

    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0
    return Xn * f_inv(fx), Yn * f_inv(fy), Zn * f_inv(fz)


def _xyz_to_srgb(X: float, Y: float, Z: float) -> tuple[float, float, float]:
    """XYZ → sRGB linear + gamma."""
    R_lin = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
    G_lin = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    B_lin = 0.0557 * X - 0.2040 * Y + 1.0570 * Z

    def gamma(c: float) -> float:
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055

    return gamma(R_lin), gamma(G_lin), gamma(B_lin)


# ─── Paleta Qualitativa ggplot2 ───────────────────────────────────────────────

def ggplot_hue(n: int) -> list[str]:
    """
    Gera n cores hex usando a formula identica ao scale_colour_hue() do ggplot2.

    HCL: hues igualmente espacados em [15, 375), C=100, L=65.
    Cores fora do gamut sRGB sao aproximadas por clamping.

    Exemplos pre-computados:
      n=2: #F8766D  #00BFC4
      n=4: #F8766D  #7CAE00  #00BFC4  #C77CFF
      n=6: #F8766D  #B79F00  #00BA38  #00BFC4  #619CFF  #F564E3
    """
    if n <= 0:
        return []
    hues = [15.0 + (360.0 * i / n) for i in range(n)]
    result: list[str] = []
    for h_deg in hues:
        h_rad = math.radians(h_deg)
        a_lab = 100.0 * math.cos(h_rad)
        b_lab = 100.0 * math.sin(h_rad)
        X, Y, Z = _lab_to_xyz(65.0, a_lab, b_lab)
        R, G, B = _xyz_to_srgb(X, Y, Z)
        result.append(f"#{round(R*255):02X}{round(G*255):02X}{round(B*255):02X}")
    return result


def get_sequential_cmap() -> str:
    """Cmap sequencial padrao para heatmaps (uniforme em todos os charts)."""
    return "YlGnBu"


# ─── Constantes do Tema ───────────────────────────────────────────────────────

_THEME: dict = {
    "bg_figure":   "#FFFFFF",
    "bg_axes":     "#FAFAFA",
    "grid_color":  "#E5E5E5",
    "grid_width":  0.6,
    "grid_alpha":  0.7,
    "spine_color": "#CCCCCC",
    "spine_width": 0.5,
}

_FONT: dict = {
    "family":              "sans-serif",
    "title_size":          13,
    "title_weight":        "semibold",
    "title_color":         "#2D2D2D",
    "axis_label_size":     10,
    "axis_label_color":    "#4D4D4D",
    "tick_size":           9,
    "tick_color":          "#666666",
    "annotation_size":     8.5,
    "annotation_color":    "#555555",
    "legend_title_size":   10,
    "legend_title_weight": "semibold",
    "legend_title_color":  "#2D2D2D",
    "legend_text_size":    9,
    "legend_text_color":   "#444444",
}


# ─── Setup Global ─────────────────────────────────────────────────────────────

def apply_theme() -> None:
    """
    Configura matplotlib.rcParams para o tema ggplot2-minimal.
    Idempotente — pode ser chamado multiplas vezes sem efeito colateral.
    """
    plt.rcParams.update({
        "figure.facecolor":      _THEME["bg_figure"],
        "axes.facecolor":        _THEME["bg_axes"],
        "axes.edgecolor":        _THEME["spine_color"],
        "axes.linewidth":        _THEME["spine_width"],
        "axes.grid":             True,
        "grid.color":            _THEME["grid_color"],
        "grid.linewidth":        _THEME["grid_width"],
        "grid.alpha":            _THEME["grid_alpha"],
        "axes.axisbelow":        True,
        "font.family":           "sans-serif",
        "axes.titlesize":        _FONT["title_size"],
        "axes.titleweight":      _FONT["title_weight"],
        "axes.titlecolor":       _FONT["title_color"],
        "axes.labelsize":        _FONT["axis_label_size"],
        "axes.labelcolor":       _FONT["axis_label_color"],
        "xtick.labelsize":       _FONT["tick_size"],
        "ytick.labelsize":       _FONT["tick_size"],
        "xtick.color":           _FONT["tick_color"],
        "ytick.color":           _FONT["tick_color"],
        "legend.framealpha":     0.9,
        "legend.edgecolor":      "#DDDDDD",
        "legend.fontsize":       _FONT["legend_text_size"],
        "legend.title_fontsize": _FONT["legend_title_size"],
        "figure.dpi":            120,
        "savefig.dpi":           120,
        "savefig.bbox":          "tight",
        "savefig.facecolor":     _THEME["bg_figure"],
    })


# ─── Criacao de Figuras ───────────────────────────────────────────────────────

def _legend_width_for(legend_entries: list[tuple[str, str]]) -> float:
    """Largura ideal do painel de legenda em polegadas dado o label mais longo."""
    max_len = max((len(lbl) for _, lbl in legend_entries), default=10)
    return max(3.0, min(6.0, max_len * 0.115))


def create_figure(
    width: float = 8,
    height: float = 6,
    with_legend_panel: bool = False,
    legend_entries: Optional[list[tuple[str, str]]] = None,
    legend_gap: float = 0.04,
) -> tuple[Figure, Axes, Optional[Axes]]:
    """
    Cria figura pre-estilizada, opcionalmente com painel de legenda direito.

    Args:
        width: largura da area do grafico em polegadas.
        height: altura total em polegadas.
        with_legend_panel: se True, cria GridSpec 1x2 com painel direito.
        legend_entries: lista de (codigo, label) para auto-calcular largura.
        legend_gap: espaco horizontal entre grafico e painel de legenda.

    Returns:
        (fig, ax_chart, ax_legend) — ax_legend e None se with_legend_panel=False.
    """
    apply_theme()
    if with_legend_panel:
        leg_w = _legend_width_for(legend_entries or [("T1", "placeholder_longo")])
        fig = plt.figure(figsize=(width + leg_w, height),
                         facecolor=_THEME["bg_figure"])
        gs = fig.add_gridspec(
            1, 2,
            width_ratios=[width, leg_w],
            wspace=max(0.04, float(legend_gap)),
            left=0.07, right=0.98, top=0.96, bottom=0.12,
        )
        ax = fig.add_subplot(gs[0])
        ax_leg = fig.add_subplot(gs[1])
        ax_leg.axis("off")
        return fig, ax, ax_leg
    else:
        fig, ax = plt.subplots(figsize=(width, height),
                               facecolor=_THEME["bg_figure"])
        return fig, ax, None


# ─── Estilizacao de Axes ──────────────────────────────────────────────────────

def style_axes(
    ax: Axes,
    grid_axis: str = "y",
    spines: tuple[str, ...] = ("bottom", "left"),
) -> None:
    """
    Aplica estilo ggplot2-minimal aos axes.

    Args:
        grid_axis: "x", "y", "both" ou "none".
        spines: nomes dos spines a manter visiveis.
    """
    for name, spine in ax.spines.items():
        if name in spines:
            spine.set_visible(True)
            spine.set_color(_THEME["spine_color"])
            spine.set_linewidth(_THEME["spine_width"])
        else:
            spine.set_visible(False)

    if grid_axis == "none":
        ax.grid(False)
    elif grid_axis == "both":
        ax.grid(True, axis="both",
                color=_THEME["grid_color"],
                linewidth=_THEME["grid_width"],
                alpha=_THEME["grid_alpha"])
    else:
        ax.grid(True, axis=grid_axis,
                color=_THEME["grid_color"],
                linewidth=_THEME["grid_width"],
                alpha=_THEME["grid_alpha"])
        other = "x" if grid_axis == "y" else "y"
        ax.grid(False, axis=other)

    ax.set_axisbelow(True)
    ax.tick_params(
        colors=_FONT["tick_color"],
        length=3,
        width=0.5,
        labelsize=_FONT["tick_size"],
    )


def style_network_axes(ax: Axes) -> None:
    """Remove todos os axes/spines para graficos de rede.

    Torna o patch de fundo do axes invisível para que bbox_inches='tight'
    use apenas os artistas reais (nós, arestas, rótulos, título) como
    bounding box — eliminando espaço branco excedente no topo/base do PNG.
    """
    ax.set_facecolor(_THEME["bg_figure"])
    ax.patch.set_visible(False)  # Exclui o patch de fundo do cálculo tight-bbox
    ax.axis("off")


def fit_network_axes(ax: Axes, pos: dict, margin: float = 0.20) -> None:
    """Ajusta xlim/ylim ao bounding box real dos nós com margem proporcional.

    Evita que axes com coordenadas esparsas gerem área branca no topo/base
    da figura salva com bbox_inches='tight'.
    """
    if not pos:
        return
    xs = [v[0] for v in pos.values()]
    ys = [v[1] for v in pos.values()]
    x_range = max(max(xs) - min(xs), 0.1)
    y_range = max(max(ys) - min(ys), 0.1)
    ax.set_xlim(min(xs) - x_range * margin, max(xs) + x_range * margin)
    ax.set_ylim(min(ys) - y_range * margin, max(ys) + y_range * margin)


# ─── Legenda Elegante ─────────────────────────────────────────────────────────

def draw_legend_panel(
    ax_leg: Axes,
    entries: list[tuple[str, str]],
    colors: list[str],
    title: str = "Tópicos",
) -> None:
    """
    Desenha painel de legenda elegante no axes fornecido.

    Caracteristicas:
    - Caixa sutil com fundo levemente azulado e borda cinza clara.
    - Swatch retangular arredondado com a cor do topico.
    - Codigo em negrito (T1, T2...) + label completo sem truncacao.
    - Texto wrappado por palavra se o painel for estreito.
    - Separador sutil abaixo do titulo.
    """
    n = len(entries)
    if n == 0:
        return

    ax_leg.set_xlim(0, 1)
    ax_leg.set_ylim(0, 1)

    # Calcular chars_per_line a partir da largura fisica real do painel
    fig = ax_leg.get_figure()
    panel_w_in = ax_leg.get_position().width * fig.get_figwidth()
    # zona de texto = x 0.38..0.97 (59% da largura); ~10 chars/polegada a 8.5pt
    chars_per_line = max(15, int(panel_w_in * 0.59 / 0.059))

    # Caixa externa sutil
    outer = mpatches.FancyBboxPatch(
        (0.03, 0.02), 0.94, 0.96,
        boxstyle="round,pad=0.02",
        fc="#F5F9FF", ec="#CCCCCC", linewidth=1.0,
        transform=ax_leg.transAxes, clip_on=False, zorder=1,
    )
    ax_leg.add_patch(outer)

    # Titulo
    ax_leg.text(
        0.50, 0.956, title,
        transform=ax_leg.transAxes,
        fontsize=_FONT["legend_title_size"],
        fontweight=_FONT["legend_title_weight"],
        ha="center", va="top",
        color=_FONT["legend_title_color"],
        zorder=2,
    )

    # Separador sutil
    ax_leg.plot(
        [0.07, 0.93], [0.910, 0.910],
        color="#DDDDDD", linewidth=0.8,
        transform=ax_leg.transAxes, zorder=2,
    )

    # Espacamento uniforme dos itens
    margin_top    = 0.885
    margin_bottom = 0.040
    usable  = margin_top - margin_bottom
    spacing = usable / max(n, 1)
    swatch_h = min(spacing * 0.50, 0.055)

    for i, ((code, label), color) in enumerate(zip(entries, colors)):
        y_c = margin_top - (i + 0.5) * spacing

        # Swatch colorido arredondado
        swatch = mpatches.FancyBboxPatch(
            (0.07, y_c - swatch_h * 0.5), 0.09, swatch_h,
            boxstyle="round,pad=0.003",
            fc=color, ec="none",
            transform=ax_leg.transAxes, clip_on=False, zorder=2,
        )
        ax_leg.add_patch(swatch)

        # Codigo em negrito
        ax_leg.text(
            0.21, y_c, code,
            transform=ax_leg.transAxes,
            fontsize=_FONT["legend_title_size"],
            fontweight="bold",
            va="center", ha="left",
            color=_FONT["legend_title_color"],
            zorder=2,
        )

        # Label completo — sem truncacao, com word-wrap se necessario
        wrapped = textwrap.fill(label, width=chars_per_line)
        ax_leg.text(
            0.38, y_c, wrapped,
            transform=ax_leg.transAxes,
            fontsize=_FONT["legend_text_size"],
            va="center", ha="left",
            color=_FONT["legend_text_color"],
            zorder=2,
        )


# ─── Labels de Valor em Barras ────────────────────────────────────────────────

def add_bar_labels(
    ax: Axes,
    bars,
    values: list,
    total: float,
    fmt: str = "{v} ({p:.0f}%)",
    horizontal: bool = True,
) -> None:
    """
    Adiciona labels de valor fora das barras e ajusta o limite do eixo.

    Args:
        horizontal: True para barh (labels a direita), False para bar (acima).
        fmt: usa {v} para valor e {p} para percentual.
    """
    max_val = max(values) if values else 1
    total = total or 1

    for bar, val in zip(bars, values):
        pct = val / total * 100
        text = fmt.format(v=val, p=pct)
        if horizontal:
            ax.text(
                val + max_val * 0.03,
                bar.get_y() + bar.get_height() / 2,
                text,
                va="center", ha="left",
                fontsize=_FONT["annotation_size"],
                color=_FONT["annotation_color"],
            )
        else:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_val * 0.03,
                text,
                va="bottom", ha="center",
                fontsize=_FONT["annotation_size"],
                color=_FONT["annotation_color"],
            )

    if horizontal:
        ax.set_xlim(right=max_val * 1.32)
    else:
        ax.set_ylim(top=max_val * 1.25)


# ─── Anotacoes em Heatmap ─────────────────────────────────────────────────────

def heatmap_text_color(value: float, vmin: float, vmax: float) -> str:
    """
    Retorna cor de texto legivel sobre o fundo do heatmap.
    Branco para fundos escuros, cinza escuro para fundos claros.
    """
    normalized = (value - vmin) / max(vmax - vmin, 1e-10)
    return "#FFFFFF" if normalized > 0.55 else "#2D2D2D"


# ─── Recorte de bordas brancas ────────────────────────────────────────────────

def crop_white_borders(path: Path, pad_px: int = 10, white_threshold: int = 245) -> None:
    """Remove bordas brancas excedentes de um PNG salvo via PIL (sem numpy).

    Útil para graficos de rede onde bbox_inches='tight' nao descarta a area
    em branco acima/abaixo dos nos devido ao axes bounding-box em figura-space.

    Algoritmo (puro-PIL):
        1. Converte a imagem para escala de cinza.
        2. Cria máscara binária: pixels >=white_threshold → 0 (fundo),
           pixels <white_threshold → 255 (conteúdo).
        3. getbbox() retorna o bounding-box dos pixels de conteúdo.
        4. Recorta a imagem original com margem pad_px e salva no lugar.

    Args:
        path:            Caminho do PNG a ser recortado no local.
        pad_px:          Margem em pixels a preservar ao redor do conteúdo.
        white_threshold: Luminância mínima para considerar um pixel como fundo
                         branco (0–255). Padrão 245 captura branco puro e
                         quase-branco sem cortar bordas de antialiasing.
    """
    try:
        from PIL import Image
        with Image.open(path) as img:
            gray = img.convert("L")
        # Mapeia: cinza >= threshold → 0 (fundo/preto), senão → 255 (conteúdo)
        mask = gray.point(lambda p: 0 if p >= white_threshold else 255)
        bbox = mask.getbbox()  # bounding-box dos pixels de conteúdo (≠ 0)
        if not bbox:
            return  # Imagem inteiramente branca — nada a recortar
        w, h = gray.size
        left  = max(0, bbox[0] - pad_px)
        top   = max(0, bbox[1] - pad_px)
        right = min(w, bbox[2] + pad_px)
        bot   = min(h, bbox[3] + pad_px)
        if right <= left or bot <= top:
            return
        with Image.open(path) as img_orig:
            cropped = img_orig.crop((left, top, right, bot))
            cropped.save(path)
    except Exception:
        pass  # Silencioso: PIL pode nao estar disponivel em alguns ambientes


# ─── Salvar Figura ────────────────────────────────────────────────────────────

def save_figure(fig: Figure, path: Path, dpi: int = 120) -> None:
    """Salva figura com configuracoes consistentes e fecha-a."""
    fig.savefig(path, bbox_inches="tight", dpi=dpi,
                facecolor=fig.get_facecolor())
    plt.close(fig)
