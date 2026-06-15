"""
Helpers de iconografia para UI (estilo profissional, sem emojis).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import customtkinter as ctk
from PIL import Image

from .styles import get_themed_color


# Símbolos neutros (não-emoji) para manter compatibilidade visual em Tk.
_ICON_MAP: Dict[str, str] = {
    "corpus": "▦",
    "info": "ⓘ",
    "documents": "▤",
    "analyses": "◫",
    "stats": "◪",
    "export": "↗",
    "import": "↘",
    "dictionary": "≣",
    "segments": "≡",
    "navigator": "⌕",
    "subcorpus": "◧",
    "dendrogram": "⋔",
    "profiles": "▣",
    "afc": "◬",
    "typical_segments": "◨",
    "antiprofiles": "↧",
    "wordcloud": "◌",
    "similarity": "⟐",
    "graph": "◍",
    "save": "⎙",
    "report": "▥",
    "settings": "⋯",
    "open": "□",
    "delete": "×",
    "frequency": "▧",
    "chi2": "χ²",
    "matrix": "▦",
    "keyness": "◇",
    "prototypical": "◈",
    "labbe": "∥",
    "bigram": "⋈",
    "word_tree": "⊢",
    "heatmap": "▥",
    "wordfish": "↔",
    "xray": "⌁",
    "dispersion": "◫",
    "sentiment": "◔",
    "emotions": "◉",
    "warning": "!",
    "search": "⌕",
}


def get_ui_icon(name: str) -> str:
    """Retorna símbolo textual de ícone por chave."""
    return _ICON_MAP.get(str(name or "").strip().lower(), "")


def label_with_icon(name: str, text: str) -> str:
    """Prefixa texto com ícone (quando disponível)."""
    icon = get_ui_icon(name)
    base = str(text or "").strip()
    if not base:
        return icon
    return f"{icon} {base}" if icon else base


def create_help_button(parent, tooltip_text: str, size: int = 18) -> ctk.CTkButton:
    """
    Cria botão de ajuda padronizado com ícone '?' em imagem.
    """
    icon_image = _get_help_icon_image(size=max(12, int(size)))
    btn = ctk.CTkButton(
        parent,
        text="",
        width=int(size),
        height=int(size),
        image=icon_image,
        fg_color="transparent",
        border_width=0,
        border_color=get_themed_color("border"),
        text_color=get_themed_color("text_secondary"),
        hover_color=get_themed_color("secondary"),
        corner_radius=max(6, int(size // 2)),
        command=lambda: None,
    )
    # Mantém referência viva da imagem no botão.
    btn._help_icon_image_ref = icon_image
    # Import local evita ciclo com src.ui.widgets.__init__ durante import do pacote UI.
    from .widgets.tooltip import CTkTooltip

    CTkTooltip(btn, message=str(tooltip_text or "").strip())
    return btn


_HELP_ICON_CACHE: Dict[int, Image.Image] = {}


def _resolve_help_icon_path() -> Optional[Path]:
    base = Path(__file__).resolve().parents[2]
    candidates = [
        base / "assets" / "help_question.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _get_help_icon_image(size: int) -> Optional[ctk.CTkImage]:
    px = max(12, int(size))
    cached = _HELP_ICON_CACHE.get(px)
    if cached is not None:
        return ctk.CTkImage(light_image=cached, dark_image=cached, size=(px, px))

    path = _resolve_help_icon_path()
    if path is None:
        return None
    try:
        image = Image.open(path).convert("RGBA")
        _HELP_ICON_CACHE[px] = image
        return ctk.CTkImage(light_image=image, dark_image=image, size=(px, px))
    except Exception:
        return None
