"""
Modernized application settings sheet.
"""

from __future__ import annotations

import customtkinter as ctk
from tkinter import filedialog
from typing import Any, Dict, Optional

from ..styles import FONTS, get_themed_color, apply_theme
from ..modern_components import (
    create_option_card,
    create_section_title,
    create_sheet_footer,
    create_surface,
    set_option_card_state,
    style_inline_toggle,
)
from ...core.version import DISPLAY_APP_NAME


class SettingsDialog(ctk.CTkToplevel):
    """Dialogo de configuracoes gerais em formato de sheet."""

    LANGUAGE_LABEL_TO_CODE = {
        "Português": "portuguese",
        "English": "english",
        "Français": "french",
    }
    LANGUAGE_CODE_TO_LABEL = {v: k for k, v in LANGUAGE_LABEL_TO_CODE.items()}

    def __init__(self, parent, config_manager=None, on_theme_change=None):
        super().__init__(parent)
        self.title(f"Ajustes do Sistema {DISPLAY_APP_NAME}")
        self.geometry("760x760")
        self.minsize(680, 700)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._config = config_manager
        self._result = None
        self._on_theme_change = on_theme_change
        self._is_destroying = False
        self._loading = False

        self._original_theme = str(
            config_manager.get("theme", "light") if config_manager else "light"
        ).lower()
        if self._original_theme not in ("dark", "light", "system"):
            self._original_theme = "light"

        self.theme_preview_cards: Dict[str, ctk.CTkButton] = {}

        self._create_widgets()
        self._load_current_settings()
        self._center_on_parent(parent)

    def _center_on_parent(self, parent) -> None:
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self) -> None:
        self.configure(fg_color=get_themed_color("background"))

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=(18, 0))

        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        title_label, subtitle_label = create_section_title(
            header,
            f"Ajustes do Sistema {DISPLAY_APP_NAME}",
            "Preferências visuais e operacionais da interface moderna.",
        )
        title_label.pack(anchor="w")
        subtitle_label.pack(anchor="w", pady=(4, 0))

        self.scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self._build_r_path_section()
        self._build_theme_section()
        self._build_preferences_section()
        self._build_advanced_section()

        footer_host = ctk.CTkFrame(self, fg_color=get_themed_color("background"), corner_radius=0)
        footer_host.pack(fill="x", side="bottom", padx=0, pady=0)
        ctk.CTkFrame(footer_host, height=1, fg_color=get_themed_color("border")).pack(fill="x")
        footer, _save_btn, _cancel_btn = create_sheet_footer(
            footer_host,
            confirm_text="Salvar",
            confirm_command=self._save,
            cancel_command=self._on_cancel,
        )
        footer.pack(fill="x", padx=18, pady=14)

    def _build_r_path_section(self) -> None:
        card = create_surface(self.scroll, fg="sheet", radius=18)
        card.pack(fill="x", pady=(0, 14), padx=2)
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=18)

        title, subtitle = create_section_title(
            content,
            "Caminho do R",
            "Deixe vazio para detecção automática do Rscript no ambiente local.",
        )
        title.pack(anchor="w")
        subtitle.pack(anchor="w", pady=(4, 12))

        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x")
        self.r_path_entry = ctk.CTkEntry(
            row,
            placeholder_text="Auto-detectado se vazio",
            height=38,
            corner_radius=14,
        )
        self.r_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.r_path_button = ctk.CTkButton(
            row,
            text="Selecionar",
            width=118,
            height=38,
            corner_radius=14,
            command=self._browse_r_path,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
        )
        self.r_path_button.pack(side="left")

    def _build_theme_section(self) -> None:
        card = create_surface(self.scroll, fg="sheet", radius=18)
        card.pack(fill="x", pady=(0, 14), padx=2)
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=18)

        title, subtitle = create_section_title(
            content,
            "Aparência",
            "Escolha como a shell, os resultados e os diálogos devem ser apresentados.",
        )
        title.pack(anchor="w")
        subtitle.pack(anchor="w", pady=(4, 12))

        self.theme_var = ctk.StringVar(value="light")
        cards = ctk.CTkFrame(content, fg_color="transparent")
        cards.pack(fill="x")
        for idx, (value, label, sublabel) in enumerate(
            (
                ("light", "Claro", "Superfícies claras e contraste suave"),
                ("dark", "Escuro", "Estrutura azul-noite com foco em conteúdo"),
                ("system", "Sistema", "Segue o tema configurado no Windows"),
            )
        ):
            button = create_option_card(
                cards,
                title=label,
                subtitle=sublabel,
                selected=False,
                command=lambda v=value: self._set_theme_preview(v),
                width=210,
                height=108,
            )
            button.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 10, 0))
            cards.grid_columnconfigure(idx, weight=1)
            self.theme_preview_cards[value] = button

    def _build_preferences_section(self) -> None:
        card = create_surface(self.scroll, fg="sheet", radius=18)
        card.pack(fill="x", pady=(0, 14), padx=2)
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=18)

        title, subtitle = create_section_title(
            content,
            "Preferências da Interface",
            "Ajustes que afetam densidade, navegação e ergonomia da shell moderna.",
        )
        title.pack(anchor="w")
        subtitle.pack(anchor="w", pady=(4, 12))

        self.ui_density_var = ctk.StringVar(value="comfortable")
        density_row = ctk.CTkFrame(content, fg_color="transparent")
        density_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(density_row, text="Densidade", font=FONTS["body"]).pack(side="left")
        self.density_menu = ctk.CTkOptionMenu(
            density_row,
            values=["comfortable", "compact"],
            variable=self.ui_density_var,
            width=180,
            height=34,
            corner_radius=12,
        )
        self.density_menu.pack(side="right")

        self.nav_collapsed_var = ctk.BooleanVar(value=False)
        nav_row = ctk.CTkFrame(content, fg_color="transparent")
        nav_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            nav_row,
            text="Recolher navegação lateral por padrão",
            font=FONTS["body"],
        ).pack(side="left")
        self.nav_collapsed_switch = ctk.CTkSwitch(
            nav_row,
            text="",
            variable=self.nav_collapsed_var,
        )
        style_inline_toggle(self.nav_collapsed_switch)
        self.nav_collapsed_switch.pack(side="right")

        self.compact_toolbar_var = ctk.BooleanVar(value=False)
        toolbar_row = ctk.CTkFrame(content, fg_color="transparent")
        toolbar_row.pack(fill="x")
        ctk.CTkLabel(
            toolbar_row,
            text="Usar barra compacta de ações",
            font=FONTS["body"],
        ).pack(side="left")
        self.compact_toolbar_switch = ctk.CTkSwitch(
            toolbar_row,
            text="",
            variable=self.compact_toolbar_var,
        )
        style_inline_toggle(self.compact_toolbar_switch)
        self.compact_toolbar_switch.pack(side="right")

    def _build_advanced_section(self) -> None:
        self.advanced_section_frame = create_surface(self.scroll, fg="sheet", radius=18)
        self.advanced_section_frame.pack(fill="x", pady=(0, 14), padx=2)
        content = ctk.CTkFrame(self.advanced_section_frame, fg_color="transparent")
        content.pack(fill="x", padx=18, pady=18)

        title, subtitle = create_section_title(
            content,
            "Avançado",
            "Preferências legadas e compatibilidade durante a transição da shell.",
        )
        title.pack(anchor="w")
        subtitle.pack(anchor="w", pady=(4, 12))

        lang_row = ctk.CTkFrame(content, fg_color="transparent")
        lang_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(lang_row, text="Idioma", font=FONTS["body"]).pack(side="left")
        self.lang_var = ctk.StringVar(value="Português")
        self.lang_menu = ctk.CTkOptionMenu(
            lang_row,
            values=list(self.LANGUAGE_LABEL_TO_CODE.keys()),
            variable=self.lang_var,
            width=180,
            height=34,
            corner_radius=12,
        )
        self.lang_menu.pack(side="right")

        scope_row = ctk.CTkFrame(content, fg_color="transparent")
        scope_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(scope_row, text="Escopos de compatibilidade", font=FONTS["body"]).pack(anchor="w")
        checks = ctk.CTkFrame(content, fg_color="transparent")
        checks.pack(fill="x")
        self.scope_shell_var = ctk.BooleanVar(value=True)
        self.scope_results_var = ctk.BooleanVar(value=True)
        self.scope_dialogs_var = ctk.BooleanVar(value=False)
        self.scope_feedback_var = ctk.BooleanVar(value=True)
        self.scope_icons_var = ctk.BooleanVar(value=False)
        for idx, (label, variable) in enumerate(
            (
                ("Shell", self.scope_shell_var),
                ("Resultados", self.scope_results_var),
                ("Dialogs", self.scope_dialogs_var),
                ("Feedback", self.scope_feedback_var),
                ("Ícones", self.scope_icons_var),
            )
        ):
            check = ctk.CTkCheckBox(checks, text=label, variable=variable)
            check.grid(row=idx // 3, column=idx % 3, sticky="w", padx=(0, 18), pady=4)

    def _set_theme_preview(self, theme_value: str) -> None:
        self.theme_var.set(theme_value)
        for value, button in self.theme_preview_cards.items():
            set_option_card_state(button, selected=(value == theme_value))

    def _load_current_settings(self) -> None:
        if not self._config:
            self._set_theme_preview(self._original_theme)
            return

        r_path = self._config.get("r_path", "")
        theme = self._config.get("theme", "light")
        lang = self._config.get("language", "portuguese")
        ui_cfg = self._config.get("ui", {})
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}

        if r_path:
            self.r_path_entry.insert(0, r_path)

        theme_val = str(theme).lower()
        if theme_val not in {"light", "dark", "system"}:
            theme_val = "light"
        self._loading = True
        self._set_theme_preview(theme_val)
        self._loading = False

        lang_key = str(lang).lower()
        for short, full in (("pt", "portuguese"), ("en", "english"), ("fr", "french")):
            if lang_key.startswith(short):
                lang_key = full
                break
        self.lang_var.set(self.LANGUAGE_CODE_TO_LABEL.get(lang_key, "Português"))

        scope = ui_cfg.get("v2_scope", ["shell", "results", "feedback"])
        if isinstance(scope, str):
            scope = [part.strip().lower() for part in scope.split(",") if part.strip()]
        if not isinstance(scope, (list, tuple, set)):
            scope = ["shell", "results", "feedback"]
        scope_set = {str(item).strip().lower() for item in scope}
        self.scope_shell_var.set("shell" in scope_set)
        self.scope_results_var.set("results" in scope_set)
        self.scope_dialogs_var.set("dialogs" in scope_set)
        self.scope_feedback_var.set("feedback" in scope_set)
        self.scope_icons_var.set("icons" in scope_set)
        self.ui_density_var.set(str(ui_cfg.get("density", "comfortable") or "comfortable"))
        self.compact_toolbar_var.set(bool(ui_cfg.get("enable_compact_toolbar", False)))
        self.nav_collapsed_var.set(bool(ui_cfg.get("nav_collapsed", False)))

    def _browse_r_path(self) -> None:
        import sys
        if sys.platform == "win32":
            title = "Selecionar Rscript.exe"
            filetypes = [("Executável", "*.exe"), ("Todos", "*.*")]
        else:
            # Linux/macOS: Rscript é um executável sem extensão
            title = "Selecionar Rscript"
            filetypes = [("Rscript", "Rscript"), ("Todos os arquivos", "*")]
        file_path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
        )
        if file_path:
            self.r_path_entry.delete(0, "end")
            self.r_path_entry.insert(0, file_path)

    def _on_cancel(self) -> None:
        self.destroy()

    def _save(self) -> None:
        selected_lang = self.LANGUAGE_LABEL_TO_CODE.get(self.lang_var.get(), "portuguese")
        theme = self.theme_var.get()
        v2_scope = []
        if self.scope_shell_var.get():
            v2_scope.append("shell")
        if self.scope_results_var.get():
            v2_scope.append("results")
        if self.scope_dialogs_var.get():
            v2_scope.append("dialogs")
        if self.scope_feedback_var.get():
            v2_scope.append("feedback")
        if self.scope_icons_var.get():
            v2_scope.append("icons")
        if not v2_scope:
            v2_scope = ["shell", "results", "feedback"]

        self._result = {
            "r_path": self.r_path_entry.get().strip(),
            "theme": theme,
            "language": selected_lang,
            "ui": {
                "v2_enabled": True,
                "v2_scope": v2_scope,
                "shell_version": "modern_academic_v1",
                "nav_collapsed": bool(self.nav_collapsed_var.get()),
                "density": self.ui_density_var.get(),
                "table_row_mode": self.ui_density_var.get(),
                "enable_compact_toolbar": bool(self.compact_toolbar_var.get()),
            },
        }
        try:
            apply_theme(mode=theme)
        except Exception:
            pass
        if self._config:
            self._config.set("r_path", self._result["r_path"])
            self._config.set("theme", self._result["theme"])
            self._config.set("language", self._result["language"])
            self._config.set("ui", self._result["ui"])
            self._config.save()
        self.destroy()

    def get_result(self) -> Optional[Dict[str, Any]]:
        self.wait_window()
        return self._result

    def destroy(self) -> None:
        if self._is_destroying:
            return
        self._is_destroying = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            super().destroy()
        finally:
            self._is_destroying = False
