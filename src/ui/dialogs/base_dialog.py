"""
Shell base para dialogs com estrutura consistente.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from ..component_factory import create_button
from ..styles import FONTS, SIZES, get_themed_color


class BaseDialogShell(ctk.CTkToplevel):
    """
    Dialog padrao com header/body/footer.

    Nao substitui dialogs legados automaticamente; serve como base progressiva
    para novas telas e migracoes sem quebra.
    """

    def __init__(
        self,
        parent,
        *,
        title: str,
        subtitle: str = "",
        width: int = 640,
        height: int = 420,
        modal: bool = True,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(max(420, int(width * 0.7)), max(300, int(height * 0.65)))
        self.configure(fg_color=get_themed_color("background"))
        self.transient(parent)
        if modal:
            self.grab_set()

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=12, pady=12)

        self.header = ctk.CTkFrame(
            self.container,
            fg_color=get_themed_color("header_bg"),
            corner_radius=int(SIZES.get("corner_radius", 3)),
            border_width=1,
            border_color=get_themed_color("border"),
        )
        self.header.pack(fill="x", pady=(0, 10))

        self.title_label = ctk.CTkLabel(
            self.header,
            text=title,
            font=FONTS.get("heading", ("Segoe UI", 12, "bold")),
            anchor="w",
        )
        self.title_label.pack(fill="x", padx=12, pady=(10, 2))

        self.subtitle_label = ctk.CTkLabel(
            self.header,
            text=subtitle,
            font=FONTS.get("small", ("Segoe UI", 10)),
            text_color=get_themed_color("text_secondary"),
            anchor="w",
        )
        self.subtitle_label.pack(fill="x", padx=12, pady=(0, 10))

        self.body = ctk.CTkFrame(self.container, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        self.footer = ctk.CTkFrame(
            self.container,
            fg_color="transparent",
            border_width=0,
        )
        self.footer.pack(fill="x", pady=(10, 0))

        self._primary_button: Optional[ctk.CTkButton] = None
        self._secondary_button: Optional[ctk.CTkButton] = None

    def set_primary_action(self, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        if self._primary_button is not None:
            self._primary_button.destroy()
        self._primary_button = create_button(
            self.footer,
            text=text,
            command=command,
            variant="primary",
            size="md",
            width=96,
        )
        self._primary_button.pack(side="right", padx=(8, 0))
        return self._primary_button

    def set_secondary_action(self, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        if self._secondary_button is not None:
            self._secondary_button.destroy()
        self._secondary_button = create_button(
            self.footer,
            text=text,
            command=command,
            variant="secondary",
            size="md",
            width=96,
        )
        self._secondary_button.pack(side="right")
        return self._secondary_button

