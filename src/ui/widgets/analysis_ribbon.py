"""Ribbon superior de análises com linguagem visual "Modern Academic".

Cada grupo de análise é construído UMA ÚNICA VEZ (na primeira seleção) e
mantido em cache — a troca entre grupos é show/hide, sem destruir widgets.
Isso elimina o rebuild quadrático que causava lag na UI.
"""

from __future__ import annotations

import math
import customtkinter as ctk
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..modern_components import create_pill_button
from ..styles import FONTS, get_themed_color


class AnalysisRibbonView(ctk.CTkFrame):
    """Ribbon de uma faixa para lançar análises diretamente.

    A faixa superior mostra [Importar] [Normalizar] | [Todos] [Essenciais] ...
    A faixa inferior mostra os botões do grupo ativo.

    Os botões de grupo são construídos uma única vez na primeira seleção e
    depois apenas mostrados/escondidos. refresh_enabled_state() atualiza o
    state de todos os botões já construídos in-place, sem rebuild.
    """

    GROUP_ORDER = ["Todos", "Essenciais", "Exploratórios", "Semânticas", "Extras"]
    DEFAULT_GROUP = "Essenciais"

    def __init__(
        self,
        parent,
        *,
        registry: Dict[str, Dict[str, Any]],
        help_entries: Optional[Dict[str, Dict[str, Any]]] = None,
        on_execute: Optional[Callable[[str], None]] = None,
        on_import: Optional[Callable[[], None]] = None,
        on_save_project: Optional[Callable[[], None]] = None,
        on_normalize: Optional[Callable[[], None]] = None,
        on_prepare_corpus: Optional[Callable[[], None]] = None,
        on_export_txt: Optional[Callable[[], None]] = None,
        on_export_iramuteq: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._registry = dict(registry or {})
        self._help_entries = dict(help_entries or {})
        self._on_execute = on_execute
        self._on_import = on_import
        self._on_save_project = on_save_project
        self._on_normalize = on_normalize
        self._on_prepare_corpus = on_prepare_corpus
        self._on_export_txt = on_export_txt
        self._on_export_iramuteq = on_export_iramuteq
        self._group_filter: str = self.DEFAULT_GROUP
        self._corpus_loaded: bool = False
        self._group_buttons: Dict[str, ctk.CTkButton] = {}
        self._group_frames: Dict[str, ctk.CTkFrame] = {}
        self._group_action_buttons: Dict[str, Dict[str, ctk.CTkButton]] = {}
        # Compatibilidade com suíte de testes legado.
        self._action_buttons: Dict[str, ctk.CTkButton] = {}
        self._active_group_frame: Optional[ctk.CTkFrame] = None
        self._import_button: Optional[ctk.CTkButton] = None
        self._export_button: Optional[ctk.CTkButton] = None
        self._save_button: Optional[ctk.CTkButton] = None
        self._normalize_button: Optional[ctk.CTkButton] = None
        self._prepare_button: Optional[ctk.CTkButton] = None
        self._about_button: Optional[ctk.CTkButton] = None
        self._help_buttons: Dict[str, ctk.CTkButton] = {}
        self._normalize_option_buttons: Dict[str, ctk.CTkButton] = {}
        self._actions_row: Optional[ctk.CTkFrame] = None
        self._export_frame: Optional[ctk.CTkFrame] = None
        self._help_frame: Optional[ctk.CTkFrame] = None
        self._normalize_frame: Optional[ctk.CTkFrame] = None
        self._export_visible: bool = False
        self._help_visible: bool = False
        self._normalize_visible: bool = False
        self._build()

    # ── public interface ────────────────────────────────────────────────────

    def groups(self) -> List[str]:
        return list(self.GROUP_ORDER)

    def get_primary_button(self, key: str) -> Optional[ctk.CTkButton]:
        mapping = {
            "import": self._import_button,
            "export": self._export_button,
            "save": self._save_button,
            "save_project": self._save_button,
            "normalize": self._normalize_button,
            "prepare": self._prepare_button,
            "prepare_corpus": self._prepare_button,
            "about": self._about_button,
        }
        return mapping.get(str(key or "").strip().lower())

    def get_group_button(self, group_name: str) -> Optional[ctk.CTkButton]:
        return self._group_buttons.get(str(group_name or "").strip())

    def get_active_group_button(self, key: str) -> Optional[ctk.CTkButton]:
        return self._action_buttons.get(str(key or "").strip())

    def get_help_button(self, key: str) -> Optional[ctk.CTkButton]:
        return self._help_buttons.get(str(key or "").strip())

    def get_normalize_option_button(self, key: str) -> Optional[ctk.CTkButton]:
        return self._normalize_option_buttons.get(str(key or "").strip().lower())

    def show_help_panel(self) -> None:
        self._show_help_options()

    def hide_help_panel(self) -> None:
        self._hide_help_options()

    def set_group_filter(self, value: str) -> None:
        self._group_filter = str(value or "").strip()
        self._render_group_buttons()
        self._show_group(self._group_filter)

    def refresh_enabled_state(self, *, corpus_loaded: bool) -> None:
        """Atualiza state de todos os botões in-place. Sem rebuild."""
        self._corpus_loaded = bool(corpus_loaded)
        if self._normalize_button is not None:
            self._normalize_button.configure(
                state=("normal" if self._corpus_loaded else "disabled")
            )
        if self._prepare_button is not None:
            self._prepare_button.configure(
                state=("normal" if self._corpus_loaded else "disabled")
            )
        if self._export_button is not None:
            self._export_button.configure(
                state=("normal" if self._corpus_loaded else "disabled")
            )
        if self._save_button is not None:
            self._save_button.configure(
                state=("normal" if self._corpus_loaded else "disabled")
            )
        # Atualiza todos os grupos já construídos
        for group_buttons in self._group_action_buttons.values():
            for key, button in group_buttons.items():
                payload = self._registry.get(key, {})
                enabled = self._is_enabled(payload)
                button.configure(state=("normal" if enabled else "disabled"))

    def collapse_actions_row(self) -> None:
        """Compat: colapsa faixa secundária de ações."""
        if self._actions_row is None:
            return
        if self._actions_row.winfo_manager():
            self._actions_row.pack_forget()
        self._help_visible = False
        self._export_visible = False
        self._normalize_visible = False

    # ── build ───────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Faixa principal: fundo escuro da rail
        shell_band = ctk.CTkFrame(
            self,
            fg_color=get_themed_color("rail_bg"),
            corner_radius=0,
            border_width=0,
        )
        shell_band.pack(fill="x", padx=0, pady=(0, 2))

        top_row = ctk.CTkFrame(shell_band, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=(10, 10))

        # Botões fixos: Importar + Normalizar
        fixed_actions = ctk.CTkFrame(top_row, fg_color="transparent")
        fixed_actions.pack(side="left", padx=(0, 12))

        self._import_button = create_pill_button(
            fixed_actions,
            text="Importar",
            command=self._dispatch_import,
            primary=True,
            width=122,
        )
        self._import_button.configure(
            height=42, corner_radius=12, font=FONTS["button"], border_width=0
        )
        self._import_button.pack(side="left", padx=(0, 8))

        self._export_button = create_pill_button(
            fixed_actions,
            text="Exportar",
            command=self._dispatch_export,
            width=122,
        )
        self._export_button.configure(
            height=42, corner_radius=12, font=FONTS["button"],
            border_width=1, state="disabled",
        )
        self._export_button.pack(side="left", padx=(0, 8))

        self._save_button = create_pill_button(
            fixed_actions,
            text="Salvar",
            command=self._dispatch_save_project,
            width=122,
        )
        self._save_button.configure(
            height=42, corner_radius=12, font=FONTS["button"],
            border_width=1, state="disabled",
        )
        self._save_button.pack(side="left", padx=(0, 8))

        self._normalize_button = create_pill_button(
            fixed_actions,
            text="Normalizar",
            command=self._dispatch_normalize,
            width=136,
        )
        self._normalize_button.configure(
            height=42, corner_radius=12, font=FONTS["button"],
            border_width=1, state="disabled",
        )
        self._normalize_button.pack(side="left")

        # Separador vertical
        ctk.CTkFrame(
            top_row, width=1, height=34,
            fg_color=get_themed_color("rail_bg_subtle"),
        ).pack(side="left", padx=(6, 12), pady=4)

        # Filtros de grupo
        tabs_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        tabs_frame.pack(side="left", fill="x", expand=True)

        for group_name in self.GROUP_ORDER:
            button = create_pill_button(
                tabs_frame,
                text=group_name,
                command=lambda target=group_name: self.set_group_filter(target),
                width=self._group_width(group_name),
            )
            button.configure(
                height=40, corner_radius=12, font=FONTS["button"], border_width=1
            )
            button.pack(side="left", padx=(0, 8))
            self._group_buttons[group_name] = button

        self._about_button = create_pill_button(
            tabs_frame,
            text="Ajuda",
            command=self._dispatch_about,
            width=90,
        )
        self._about_button.configure(
            height=40, corner_radius=12, font=FONTS["button"], border_width=1
        )
        self._about_button.pack(side="left", padx=(0, 8))

        # Mostra grupo padrão imediatamente (build-once, sem prefill)
        self._render_group_buttons()
        self._actions_row = ctk.CTkFrame(self, fg_color="transparent")
        # Pré-constroi o grupo "Todos" para popular _action_buttons sem exibir a 2ª faixa.
        if "Todos" not in self._group_frames:
            self._group_frames["Todos"] = self._build_group_frame("Todos")
        self._action_buttons = dict(self._group_action_buttons.get("Todos", {}))

    # ── group management ────────────────────────────────────────────────────

    def _show_group(self, group_name: str) -> None:
        """Troca o grupo visível. Constrói o frame na primeira vez, depois só mostra."""
        if self._actions_row is None:
            return
        # Esconde painel de exportação se estiver aberto
        if self._export_visible and self._export_frame is not None:
            try:
                self._export_frame.pack_forget()
            except Exception:
                pass
            self._export_visible = False
        if self._help_visible and self._help_frame is not None:
            try:
                self._help_frame.pack_forget()
            except Exception:
                pass
            self._help_visible = False
        if self._normalize_visible and self._normalize_frame is not None:
            try:
                self._normalize_frame.pack_forget()
            except Exception:
                pass
            self._normalize_visible = False
        if self._active_group_frame is not None:
            try:
                self._active_group_frame.pack_forget()
            except Exception:
                pass
            finally:
                self._active_group_frame = None

        if group_name not in self._group_frames:
            self._group_frames[group_name] = self._build_group_frame(group_name)

        frame = self._group_frames[group_name]
        if self._actions_row.winfo_manager() != "pack":
            self._actions_row.pack(fill="x", padx=0, pady=(0, 0))
        frame.pack(fill="x", padx=18, pady=(8, 4))
        self._active_group_frame = frame
        self._action_buttons = dict(self._group_action_buttons.get(group_name, {}))

    def _build_group_frame(self, group_name: str) -> ctk.CTkFrame:
        """Constrói (uma única vez) o grid de botões de um grupo."""
        parent = self._actions_row if self._actions_row is not None else self
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        items = self._items_for_group(group_name)
        is_todos = group_name == "Todos"
        max_columns = (
            max(1, math.ceil(len(items) / 2)) if is_todos
            else min(8, max(1, len(items)))
        )
        if is_todos:
            for col in range(max_columns):
                frame.columnconfigure(col, weight=1)
        group_btns: Dict[str, ctk.CTkButton] = {}
        for index, (key, payload) in enumerate(items):
            label = str(payload.get("label") or key)
            width = int(max(100, len(label) * 8 + 24))
            button = create_pill_button(
                frame,
                text=label,
                command=lambda k=key: self._dispatch_analysis(k),
                width=width,
            )
            enabled = self._is_enabled(payload)
            button.configure(
                state=("normal" if enabled else "disabled"),
                font=FONTS["body"],
                height=34,
                corner_radius=12,
                border_width=1,
            )
            row = index // max_columns
            column = index % max_columns
            if is_todos:
                button.grid(row=row, column=column, padx=(4, 4), pady=(0, 6), sticky="ew")
            else:
                button.grid(row=row, column=column, padx=(0, 10), pady=(0, 6), sticky="w")
            group_btns[key] = button
        # Registra no dict global do grupo para refresh in-place futuro
        self._group_action_buttons[group_name] = group_btns
        return frame

    # ── render helpers ──────────────────────────────────────────────────────

    def _render_group_buttons(self) -> None:
        active_fg = get_themed_color("primary")
        active_text = get_themed_color("text_inverse")
        inactive_fg = get_themed_color("surface")
        inactive_text = get_themed_color("text")
        for group_name, button in self._group_buttons.items():
            selected = group_name == self._group_filter
            button.configure(
                fg_color=(active_fg if selected else inactive_fg),
                hover_color=(
                    get_themed_color("primary_hover") if selected
                    else get_themed_color("button_hover")
                ),
                text_color=(active_text if selected else inactive_text),
                border_width=(0 if selected else 1),
                border_color=(
                    get_themed_color("primary") if selected
                    else get_themed_color("border")
                ),
            )

    # ── dispatch ────────────────────────────────────────────────────────────

    def _dispatch_import(self) -> None:
        if callable(self._on_import):
            self._on_import()

    def _dispatch_save_project(self) -> None:
        if not self._corpus_loaded:
            return
        if callable(self._on_save_project):
            self._on_save_project()

    def _dispatch_export(self) -> None:
        """Toggle da faixa inferior com as opções de exportação."""
        if not self._corpus_loaded:
            return
        if self._export_visible:
            self._hide_export_options()
        else:
            self._show_export_options()

    def _show_export_options(self) -> None:
        if self._actions_row is None:
            return
        if self._help_visible and self._help_frame is not None:
            try:
                self._help_frame.pack_forget()
            except Exception:
                pass
            self._help_visible = False
        if self._normalize_visible and self._normalize_frame is not None:
            try:
                self._normalize_frame.pack_forget()
            except Exception:
                pass
            self._normalize_visible = False
        # Esconde grupo ativo
        if self._active_group_frame is not None:
            try:
                self._active_group_frame.pack_forget()
            except Exception:
                pass
            self._active_group_frame = None
        if self._export_frame is None:
            self._export_frame = self._build_export_frame()
        if self._actions_row.winfo_manager() != "pack":
            self._actions_row.pack(fill="x", padx=0, pady=(0, 0))
        self._export_frame.pack(fill="x", padx=18, pady=(8, 4))
        self._export_visible = True

    def _hide_export_options(self) -> None:
        if self._export_frame is not None:
            try:
                self._export_frame.pack_forget()
            except Exception:
                pass
        self._export_visible = False
        # Restaura grupo atual
        self._show_group(self._group_filter)

    def _show_help_options(self) -> None:
        if self._actions_row is None:
            return
        if self._export_visible and self._export_frame is not None:
            try:
                self._export_frame.pack_forget()
            except Exception:
                pass
            self._export_visible = False
        if self._normalize_visible and self._normalize_frame is not None:
            try:
                self._normalize_frame.pack_forget()
            except Exception:
                pass
            self._normalize_visible = False
        if self._active_group_frame is not None:
            try:
                self._active_group_frame.pack_forget()
            except Exception:
                pass
            self._active_group_frame = None
        if self._help_frame is None:
            self._help_frame = self._build_help_frame()
        if self._actions_row.winfo_manager() != "pack":
            self._actions_row.pack(fill="x", padx=0, pady=(0, 0))
        self._help_frame.pack(fill="x", padx=18, pady=(8, 4))
        self._help_visible = True

    def _hide_help_options(self) -> None:
        if self._help_frame is not None:
            try:
                self._help_frame.pack_forget()
            except Exception:
                pass
        self._help_visible = False
        self._show_group(self._group_filter)

    def _show_normalize_options(self) -> None:
        if self._actions_row is None or not self._corpus_loaded:
            return
        if self._export_visible and self._export_frame is not None:
            try:
                self._export_frame.pack_forget()
            except Exception:
                pass
            self._export_visible = False
        if self._help_visible and self._help_frame is not None:
            try:
                self._help_frame.pack_forget()
            except Exception:
                pass
            self._help_visible = False
        if self._active_group_frame is not None:
            try:
                self._active_group_frame.pack_forget()
            except Exception:
                pass
            self._active_group_frame = None
        if self._normalize_frame is None:
            self._normalize_frame = self._build_normalize_frame()
        if self._actions_row.winfo_manager() != "pack":
            self._actions_row.pack(fill="x", padx=0, pady=(0, 0))
        self._normalize_frame.pack(fill="x", padx=18, pady=(8, 4))
        self._normalize_visible = True

    def _hide_normalize_options(self) -> None:
        if self._normalize_frame is not None:
            try:
                self._normalize_frame.pack_forget()
            except Exception:
                pass
        self._normalize_visible = False
        self._show_group(self._group_filter)

    def _build_export_frame(self) -> ctk.CTkFrame:
        parent = self._actions_row if self._actions_row is not None else self
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        specs = [
            ("Exportar Corpus (TXT)", self._on_export_txt),
            ("Exportar para IRaMuTeQ", self._on_export_iramuteq),
        ]
        for index, (label, handler) in enumerate(specs):
            width = int(max(180, len(label) * 9 + 32))
            btn = create_pill_button(
                frame,
                text=label,
                command=lambda h=handler: self._run_export(h),
                width=width,
            )
            btn.configure(
                font=FONTS["body"], height=34, corner_radius=12, border_width=1,
            )
            btn.grid(row=0, column=index, padx=(0, 10), pady=(0, 6), sticky="w")
        return frame

    def _build_help_frame(self) -> ctk.CTkFrame:
        parent = self._actions_row if self._actions_row is not None else self
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        specs = sorted(
            self._help_entries.items(),
            key=lambda item: str(item[1].get("label") or item[0]).lower(),
        )
        self._help_buttons = {}
        for index, (key, payload) in enumerate(specs):
            label = str(payload.get("label") or key)
            width = int(max(120, len(label) * 9 + 28))
            btn = create_pill_button(
                frame,
                text=label,
                command=lambda h=payload.get("command"): self._run_help(h),
                width=width,
            )
            btn.configure(
                font=FONTS["body"], height=34, corner_radius=12, border_width=1,
            )
            btn.grid(row=0, column=index, padx=(0, 10), pady=(0, 6), sticky="w")
            self._help_buttons[key] = btn
        return frame

    def _build_normalize_frame(self) -> ctk.CTkFrame:
        parent = self._actions_row if self._actions_row is not None else self
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        specs = [
            ("forms", "Normalizar formas", self._on_normalize, 170),
            ("prepare", "Preparar corpus", self._on_prepare_corpus, 170),
        ]
        self._normalize_option_buttons = {}
        for index, (key, label, handler, width) in enumerate(specs):
            btn = create_pill_button(
                frame,
                text=label,
                command=lambda h=handler: self._run_normalize_option(h),
                width=width,
            )
            btn.configure(
                font=FONTS["body"], height=34, corner_radius=12, border_width=1,
            )
            btn.grid(row=0, column=index, padx=(0, 10), pady=(0, 6), sticky="w")
            self._normalize_option_buttons[key] = btn
        return frame

    def _run_export(self, handler: Optional[Callable[[], None]]) -> None:
        self._hide_export_options()
        if callable(handler):
            handler()

    def _run_help(self, handler: Optional[Callable[[], None]]) -> None:
        if callable(handler):
            handler()

    def _run_normalize_option(self, handler: Optional[Callable[[], None]]) -> None:
        self._hide_normalize_options()
        if callable(handler):
            handler()

    def _dispatch_normalize(self) -> None:
        if not self._corpus_loaded:
            return
        if self._normalize_visible:
            self._hide_normalize_options()
        else:
            self._show_normalize_options()

    def _dispatch_prepare_corpus(self) -> None:
        if callable(self._on_prepare_corpus):
            self._on_prepare_corpus()

    def _dispatch_about(self) -> None:
        if self._help_visible:
            self._hide_help_options()
        else:
            self._show_help_options()

    def _dispatch_analysis(self, key: str) -> None:
        if callable(self._on_execute):
            self._on_execute(key)

    # ── pure logic ──────────────────────────────────────────────────────────

    def _is_enabled(self, payload: Dict[str, Any]) -> bool:
        requires_corpus = bool(payload.get("requires_corpus", False))
        predicate = payload.get("is_enabled_predicate")
        enabled = not requires_corpus or self._corpus_loaded
        if enabled and callable(predicate):
            try:
                enabled = bool(predicate())
            except Exception:
                enabled = False
        return enabled

    def _items_for_group(self, group_name: str) -> List[Tuple[str, Dict[str, Any]]]:
        # "Todos" deve listar apenas testes/análises operacionais.
        # Itens auxiliares (FAQ, glossário, tutorial, sobre) usam skip_result_tab.
        visible_items = [
            (key, payload)
            for key, payload in self._registry.items()
            if callable(payload.get("command")) and not bool(payload.get("skip_result_tab", False))
        ]
        if group_name == "Todos":
            items = visible_items
        else:
            items = [
                (key, payload)
                for key, payload in visible_items
                if str(payload.get("group", "")) == group_name
            ]
        return sorted(items, key=lambda x: x[1].get("label", x[0]).lower())

    @staticmethod
    def _group_width(group_name: str) -> int:
        widths = {
            "Todos": 92,
            "Essenciais": 118,
            "Exploratórios": 136,
            "Semânticas": 126,
            "Extras": 90,
        }
        return widths.get(group_name, 90)
