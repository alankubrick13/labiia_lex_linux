"""
Factory de componentes UI para reduzir variacoes visuais.
"""

from __future__ import annotations

from typing import Callable, Literal, Optional

import customtkinter as ctk

from .styles import FONTS, SIZES, get_themed_color


ButtonVariant = Literal["primary", "secondary", "tertiary", "ghost", "icon", "split"]
ButtonSize = Literal["sm", "md", "lg"]


def _button_height(size: ButtonSize) -> int:
    if size == "lg":
        return int(SIZES.get("control_height_lg", 36))
    if size == "md":
        return int(SIZES.get("control_height_md", 32))
    return int(SIZES.get("button_height", 24))


def style_button(
    button: ctk.CTkButton,
    *,
    variant: ButtonVariant = "secondary",
    size: ButtonSize = "sm",
) -> None:
    """Aplica estilo padrao por variante/tamanho em botoes existentes."""
    common = {
        "height": _button_height(size),
        "font": FONTS.get("small", ("Segoe UI", 10)),
    }
    default_corner_radius = int(SIZES.get("corner_radius", 3))

    if variant == "primary":
        cfg = {
            **common,
            "corner_radius": default_corner_radius,
            "fg_color": get_themed_color("primary"),
            "hover_color": get_themed_color("primary_hover"),
            "text_color": ("#FFFFFF", "#FFFFFF"),
            "border_width": 0,
        }
        button.configure(**cfg)
        return

    if variant == "ghost":
        cfg = {
            **common,
            "corner_radius": 0,
            "fg_color": "transparent",
            "hover_color": get_themed_color("menu_hover"),
            "text_color": get_themed_color("text"),
            "border_width": 0,
        }
        button.configure(**cfg)
        return

    if variant in {"tertiary", "icon"}:
        cfg = {
            **common,
            "corner_radius": 0,
            "fg_color": get_themed_color("surface"),
            "hover_color": get_themed_color("menu_hover"),
            "text_color": get_themed_color("text"),
            "border_width": 0,
        }
        button.configure(**cfg)
        return

    # split e secondary usam base neutra com borda.
    cfg = {
        **common,
        "corner_radius": default_corner_radius,
        "fg_color": get_themed_color("button"),
        "hover_color": get_themed_color("button_hover"),
        "text_color": get_themed_color("text"),
        "border_width": 1,
        "border_color": get_themed_color("border"),
    }
    button.configure(**cfg)
    return


def create_button(
    parent,
    *,
    text: str,
    command: Optional[Callable[[], None]] = None,
    variant: ButtonVariant = "secondary",
    size: ButtonSize = "sm",
    width: Optional[int] = None,
    state: str = "normal",
    **kwargs,
) -> ctk.CTkButton:
    """Cria CTkButton com estilo padrao e parametros de layout previsiveis."""
    btn = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width if width is not None else int(SIZES.get("button_width", 80)),
        state=state,
        **kwargs,
    )
    style_button(btn, variant=variant, size=size)
    return btn
