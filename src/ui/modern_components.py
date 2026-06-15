"""
Shared building blocks for the modernized application UI.
"""

from __future__ import annotations

import customtkinter as ctk

from .component_factory import create_button, style_button
from .styles import FONTS, get_themed_color


def create_surface(
    parent,
    *,
    fg: str = "surface",
    border: str = "border",
    radius: int = 14,
    padding: tuple[int, int] | None = None,
    **kwargs,
) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(
        parent,
        fg_color=get_themed_color(fg),
        border_color=get_themed_color(border),
        border_width=1,
        corner_radius=radius,
        **kwargs,
    )
    if padding is not None:
        frame.pack_propagate(False)
    return frame


def create_section_title(parent, title: str, subtitle: str = "") -> tuple[ctk.CTkLabel, ctk.CTkLabel]:
    title_label = ctk.CTkLabel(
        parent,
        text=title,
        anchor="w",
        font=FONTS["h2"],
        text_color=get_themed_color("text"),
    )
    subtitle_label = ctk.CTkLabel(
        parent,
        text=subtitle,
        anchor="w",
        justify="left",
        font=FONTS["small"],
        text_color=get_themed_color("text_secondary"),
    )
    return title_label, subtitle_label


def create_pill_button(parent, text: str, command, *, primary: bool = False, width: int | None = None) -> ctk.CTkButton:
    btn = create_button(
        parent,
        text=text,
        command=command,
        variant=("primary" if primary else "secondary"),
        size="md",
        width=width,
    )
    btn.configure(corner_radius=16, font=FONTS["button"])
    return btn


def create_nav_button(parent, text: str, command, *, selected: bool = False) -> ctk.CTkButton:
    btn = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        anchor="w",
        height=42,
        corner_radius=14,
        border_width=1,
        border_color=get_themed_color("rail_bg_subtle"),
    )
    set_nav_button_state(btn, selected=selected)
    return btn


def set_nav_button_state(button: ctk.CTkButton, *, selected: bool) -> None:
    button.configure(
        fg_color=(get_themed_color("primary") if selected else get_themed_color("rail_bg")),
        hover_color=(get_themed_color("primary_hover") if selected else get_themed_color("rail_bg_subtle")),
        text_color=(get_themed_color("text_inverse") if selected else get_themed_color("text_inverse")),
        border_width=(0 if selected else 1),
    )


def create_option_card(
    parent,
    *,
    title: str,
    subtitle: str = "",
    selected: bool = False,
    command=None,
    width: int = 160,
    height: int = 120,
) -> ctk.CTkButton:
    text = title if not subtitle else f"{title}\n{subtitle}"
    button = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width,
        height=height,
        anchor="center",
        corner_radius=16,
        border_width=1,
        font=FONTS["small"],
    )
    set_option_card_state(button, selected=selected)
    return button


def set_option_card_state(button: ctk.CTkButton, *, selected: bool) -> None:
    button.configure(
        fg_color=(get_themed_color("sheet") if not selected else get_themed_color("surface")),
        hover_color=get_themed_color("button_hover"),
        text_color=get_themed_color("text"),
        border_color=(get_themed_color("primary") if selected else get_themed_color("border")),
        border_width=(2 if selected else 1),
    )


def create_sheet_footer(parent, *, confirm_text: str, confirm_command, cancel_command) -> tuple[ctk.CTkFrame, ctk.CTkButton, ctk.CTkButton]:
    footer = ctk.CTkFrame(
        parent,
        fg_color="transparent",
        border_width=0,
        corner_radius=0,
    )
    cancel_btn = create_pill_button(footer, "Cancelar", cancel_command, width=120)
    save_btn = create_pill_button(footer, confirm_text, confirm_command, width=120, primary=True)
    cancel_btn.pack(side="right", padx=(8, 0))
    save_btn.pack(side="right")
    return footer, save_btn, cancel_btn


def style_inline_toggle(control) -> None:
    if hasattr(control, "configure"):
        control.configure(
            button_length=0,
            switch_width=48,
            switch_height=28,
        )


def style_flat_button(button: ctk.CTkButton, *, primary: bool = False) -> None:
    style_button(button, variant=("primary" if primary else "ghost"), size="md")
    button.configure(corner_radius=14, font=FONTS["small"])
