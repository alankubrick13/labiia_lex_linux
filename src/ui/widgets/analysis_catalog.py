"""
Catálogo central de análises da shell moderna.
"""

from __future__ import annotations

import customtkinter as ctk
from typing import Any, Callable, Dict, List, Optional

from ..styles import FONTS, get_themed_color
from ..modern_components import create_pill_button, create_section_title, create_surface


class AnalysisCatalogView(ctk.CTkScrollableFrame):
    """Renderiza catálogo central de análises agrupado por função."""

    def __init__(
        self,
        parent,
        *,
        registry: Dict[str, Dict[str, Any]],
        on_execute: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._registry: Dict[str, Dict[str, Any]] = dict(registry or {})
        self._on_execute = on_execute
        self._group_filter: str = "Todos"
        self._tile_buttons: Dict[str, ctk.CTkButton] = {}
        self._group_sections: Dict[str, ctk.CTkFrame] = {}
        self._state_labels: Dict[str, ctk.CTkLabel] = {}
        self._description_labels: Dict[str, ctk.CTkLabel] = {}
        self._header_label: Optional[ctk.CTkLabel] = None
        self._subtitle_label: Optional[ctk.CTkLabel] = None
        self._group_selector: Optional[ctk.CTkSegmentedButton] = None
        self._recent_section: Optional[ctk.CTkFrame] = None
        self._recent_buttons: List[ctk.CTkButton] = []
        self._build()

    def _build(self) -> None:
        self._header_label, self._subtitle_label = create_section_title(
            self,
            "Análises Disponíveis",
            "Escolha o teste que deseja executar. O resultado abrirá no workspace de resultados sem perder o estado anterior.",
        )
        self._header_label.pack(anchor="w", pady=(8, 0), padx=4)
        self._subtitle_label.pack(anchor="w", pady=(4, 14), padx=4)

        group_values = ["Todos"] + self.groups()
        self._group_selector = ctk.CTkSegmentedButton(
            self,
            values=group_values,
            command=self.set_group_filter,
            font=FONTS["small"],
            selected_color=get_themed_color("primary"),
            selected_hover_color=get_themed_color("primary_hover"),
            unselected_color=get_themed_color("sheet"),
            unselected_hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            corner_radius=14,
            height=34,
        )
        self._group_selector.pack(fill="x", pady=(0, 14), padx=2)
        self._group_selector.set("Todos")

        self._recent_section = create_surface(self, fg="card", radius=18)
        self._recent_section.pack(fill="x", pady=(0, 14), padx=2)
        recent_content = ctk.CTkFrame(self._recent_section, fg_color="transparent")
        recent_content.pack(fill="x", padx=18, pady=16)
        title, subtitle = create_section_title(
            recent_content,
            "Mais Usadas Recentemente",
            "Atalhos rápidos com base no histórico e no fluxo operacional da sessão.",
        )
        title.pack(anchor="w")
        subtitle.pack(anchor="w", pady=(4, 10))
        self._recent_buttons_row = ctk.CTkFrame(recent_content, fg_color="transparent")
        self._recent_buttons_row.pack(fill="x")

        for group in self.groups():
            section = create_surface(self, fg="card", radius=18)
            section.pack(fill="x", pady=(0, 14), padx=2)
            self._group_sections[group] = section
            content = ctk.CTkFrame(section, fg_color="transparent")
            content.pack(fill="x", padx=18, pady=18)
            group_title, _group_subtitle = create_section_title(content, group, "")
            group_title.pack(anchor="w", pady=(0, 8))

            for key, payload in self._items_for_group(group):
                tile = ctk.CTkFrame(
                    content,
                    fg_color=get_themed_color("sheet"),
                    border_width=1,
                    border_color=get_themed_color("border"),
                    corner_radius=16,
                )
                tile.pack(fill="x", pady=(0, 10))
                top = ctk.CTkFrame(tile, fg_color="transparent")
                top.pack(fill="x", padx=14, pady=(14, 4))
                label = ctk.CTkLabel(
                    top,
                    text=str(payload.get("label", key)),
                    font=FONTS["heading"],
                    text_color=get_themed_color("text"),
                    anchor="w",
                )
                label.pack(side="left")
                state_label = ctk.CTkLabel(
                    top,
                    text="",
                    font=FONTS["small"],
                    text_color=get_themed_color("text_secondary"),
                    anchor="e",
                )
                state_label.pack(side="right")
                self._state_labels[key] = state_label

                description = ctk.CTkLabel(
                    tile,
                    text=str(payload.get("description", "")),
                    font=FONTS["small"],
                    text_color=get_themed_color("text_secondary"),
                    justify="left",
                    anchor="w",
                    wraplength=800,
                )
                description.pack(fill="x", padx=14, pady=(0, 10))
                self._description_labels[key] = description

                actions = ctk.CTkFrame(tile, fg_color="transparent")
                actions.pack(fill="x", padx=14, pady=(0, 14))
                button = create_pill_button(
                    actions,
                    text="Executar",
                    command=lambda item_key=key: self._dispatch(item_key),
                    primary=False,
                    width=112,
                )
                button.pack(side="right")
                self._tile_buttons[key] = button

        self.refresh_enabled_state(corpus_loaded=False)
        self.refresh_recent([])

    def groups(self) -> List[str]:
        groups = {
            str(payload.get("group", "")).strip()
            for payload in self._registry.values()
            if str(payload.get("group", "")).strip()
        }
        return sorted(groups)

    def keys(self) -> List[str]:
        return list(self._registry.keys())

    def get_visible_analysis_keys(self) -> List[str]:
        visible: List[str] = []
        for group, section in self._group_sections.items():
            if section.winfo_manager() != "pack":
                continue
            for key, payload in self._items_for_group(group):
                if self._group_filter in {"", "Todos"} or payload.get("group") == self._group_filter:
                    visible.append(key)
        return visible

    def _items_for_group(self, group: str) -> List[tuple[str, Dict[str, Any]]]:
        return [
            (key, payload)
            for key, payload in self._registry.items()
            if str(payload.get("group", "")) == group
        ]

    def set_group_filter(self, value: str) -> None:
        self._group_filter = str(value or "Todos")
        for group, section in self._group_sections.items():
            should_show = self._group_filter in {"Todos", group}
            is_packed = section.winfo_manager() == "pack"
            if should_show and not is_packed:
                section.pack(fill="x", pady=(0, 14), padx=2)
            elif not should_show and is_packed:
                section.pack_forget()

    def refresh_enabled_state(self, *, corpus_loaded: bool) -> None:
        for key, payload in self._registry.items():
            requires_corpus = bool(payload.get("requires_corpus", False))
            predicate = payload.get("is_enabled_predicate")
            enabled = True
            if requires_corpus and not corpus_loaded:
                enabled = False
            elif callable(predicate):
                try:
                    enabled = bool(predicate())
                except Exception:
                    enabled = False

            button = self._tile_buttons.get(key)
            state_label = self._state_labels.get(key)
            if button is not None:
                button.configure(state=("normal" if enabled else "disabled"))
            if state_label is not None:
                state_label.configure(
                    text=("Disponível" if enabled else "Requer corpus"),
                    text_color=(
                        get_themed_color("success")
                        if enabled
                        else get_themed_color("text_secondary")
                    ),
                )

    def refresh_recent(self, keys: List[str]) -> None:
        for button in self._recent_buttons:
            try:
                button.destroy()
            except Exception:
                pass
        self._recent_buttons = []

        unique_keys: List[str] = []
        for key in keys:
            normalized = str(key or "").strip().lower()
            if normalized and normalized in self._registry and normalized not in unique_keys:
                unique_keys.append(normalized)
        if not unique_keys:
            unique_keys = [key for key in ("statistics", "similarity", "chd") if key in self._registry]

        for key in unique_keys[:4]:
            payload = self._registry.get(key, {})
            button = create_pill_button(
                self._recent_buttons_row,
                text=str(payload.get("label", key)),
                command=lambda item_key=key: self._dispatch(item_key),
                width=148,
            )
            button.pack(side="left", padx=(0, 10))
            self._recent_buttons.append(button)

    def _dispatch(self, key: str) -> None:
        if callable(self._on_execute):
            self._on_execute(key)
