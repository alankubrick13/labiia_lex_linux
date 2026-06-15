"""
CCADialog - Diálogo de Connected Concept Analysis.
====================================================
Implementa a workflow Textometrica em 3 etapas:

  Aba 1 — Palavras:    Vocabulário top-N; arrastar/soltar ou botão para
                        criar Conceitos a partir das palavras selecionadas.
  Aba 2 — Conceitos:   Lista de conceitos criados + palavras de cada um;
                        permite renomear, mesclar, remover conceitos.
  Aba 3 — Rede:        Parâmetros (janela, min-peso) → executa CCA →
                        mostra tabela de co-ocorrências e botões de exportação.
"""

import json
import queue
import re
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from ..styles import COLORS, FONTS, SIZES, get_current_colors, get_themed_color
from ..iconography import create_help_button, label_with_icon
from ...utils.paths import PathManager
from ...utils.logger import get_logger

log = get_logger(__name__)

# Paleta de cores para os conceitos (até 20)
_CONCEPT_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    "#D37295", "#FABFD2", "#8CD17D", "#B6992D", "#499894",
    "#86BCB6", "#F1CE63", "#E9C46A", "#264653", "#2A9D8F",
]


def _next_color(used: List[str]) -> str:
    for c in _CONCEPT_COLORS:
        if c not in used:
            return c
    return "#888888"


def _normalize_tk_color(value: Any, fallback: str = "#888888") -> str:
    """
    Normaliza qualquer entrada de cor para formato aceito por tk/ttk (#RRGGBB).

    Evita erros como:
      invalid color name "#E8E8E8 #3A3A3A"
      invalid color name "('#E8E8E8', '#3A3A3A')"
    """
    if isinstance(value, (tuple, list)):
        for item in value:
            text = _normalize_tk_color(item, fallback="")
            if text:
                return text
        return fallback

    text = str(value or "").strip()
    if not text:
        return fallback

    matches = re.findall(r"#[0-9a-fA-F]{6}", text)
    if matches:
        return matches[0]
    return fallback


def _blend_hex_colors(top: str, bottom: str, ratio: float = 0.20) -> str:
    """
    Mistura duas cores (#RRGGBB) retornando #RRGGBB.
    ratio=0.20 significa 20% da cor `top` sobre 80% de `bottom`.
    """
    top_hex = _normalize_tk_color(top)
    bottom_hex = _normalize_tk_color(bottom, "#FFFFFF")
    ratio = max(0.0, min(1.0, float(ratio)))

    tr, tg, tb = int(top_hex[1:3], 16), int(top_hex[3:5], 16), int(top_hex[5:7], 16)
    br, bg, bb = int(bottom_hex[1:3], 16), int(bottom_hex[3:5], 16), int(bottom_hex[5:7], 16)

    rr = int(round(tr * ratio + br * (1.0 - ratio)))
    rg = int(round(tg * ratio + bg * (1.0 - ratio)))
    rb = int(round(tb * ratio + bb * (1.0 - ratio)))
    return f"#{rr:02X}{rg:02X}{rb:02X}"


class CCADialog(ctk.CTkToplevel):
    """
    Diálogo multi-aba para Connected Concept Analysis (CCA).

    Args:
        parent:       Janela pai.
        corpus_text:  Texto do corpus (formato IRaMuTeQ ou livre).
        output_dir:   Pasta onde exportar os resultados.
    """

    def __init__(
        self,
        parent,
        corpus_text: str,
        output_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Análise de Conceitos Conectados (CCA)")
        self.geometry("940x660")
        self.minsize(800, 560)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._corpus_text = corpus_text
        self._output_dir = output_dir or Path.home() / "labiia_lex_CCA"
        self._concept_map: Dict[str, List[str]] = {}       # conceito → [palavras]
        self._concept_colors: Dict[str, str] = {}          # conceito → cor
        self._word_rows: List[Dict[str, Any]] = []         # cache para Aba 1
        self._cca_result = None                            # CCAResult
        self._analyzer = None                              # CCAAnalyzer
        self._auto_running = False
        self._btn_create_concept_manual: Optional[ctk.CTkButton] = None
        self._btn_create_concept_auto: Optional[ctk.CTkButton] = None
        self._auto_mode_selector: Optional[ctk.CTkSegmentedButton] = None
        self._auto_mode_var: ctk.StringVar = ctk.StringVar(value="Padrão")
        self._last_vocab_progress: int = -1
        self._vocab_loading: bool = False
        self._vocab_progress_queue: Optional[queue.Queue] = None
        self._vocab_worker_thread: Optional[threading.Thread] = None
        self._vocab_loading_started_at: float = 0.0
        self._vocab_debug_log_path: Path = PathManager.user_data_dir() / "cca_vocab_debug.log"
        self._vocab_debug_log_path_project: Path = PathManager.project_root() / "cca_vocab_debug.log"
        self._vocab_force_started: bool = False
        self._native_colors: Dict[str, str] = get_current_colors()

        try:
            self._create_widgets()
            self._center_on_parent(parent)
        except Exception as exc:
            log.exception("Falha ao inicializar interface do CCA")
            self._append_vocab_debug(f"ui_init_error {exc}")
            try:
                messagebox.showerror(
                    "Erro ao abrir CCA",
                    "Não foi possível inicializar a interface da CCA.\n\n"
                    f"Detalhe: {exc}\n\n"
                    "Verifique o arquivo de log:\n"
                    f"{self._vocab_debug_log_path_project}",
                    parent=parent,
                )
            except Exception:
                pass
            try:
                self.destroy()
            except Exception:
                pass
            return
        # Iniciar carregamento do vocabulário imediatamente (thread de fundo).
        # Evita depender apenas de callbacks agendados, que em alguns ambientes
        # podem atrasar/ignorar o primeiro disparo.
        try:
            self._load_vocab()
        except Exception as exc:
            log.exception("Falha ao iniciar carregamento do vocabulário CCA")
            self._status_label.configure(
                text=f"Erro ao iniciar carregamento: {exc}",
                text_color=COLORS["danger"],
            )
        self.after(900, self._ensure_vocab_loading_started)

    def _center_on_parent(self, parent) -> None:
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        dw, dh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

    def _create_help_icon(self, parent, text: str) -> ctk.CTkButton:
        """Cria ícone de ajuda padronizado com tooltip."""
        return create_help_button(parent, text, size=18)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=get_themed_color("header_bg"), corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            title_row,
            text="Analise de Conceitos Conectados  (Textometrica)",
            font=FONTS["heading"],
            anchor="w",
        ).pack(side="left")
        self._create_help_icon(
            title_row,
            "Crie conceitos a partir de palavras frequentes e gere uma rede de co-ocorrência entre conceitos.",
        ).pack(side="left", padx=(6, 0))
        self._status_label = ctk.CTkLabel(
            header,
            text="Carregando vocabulário... 0%",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="e",
        )
        self._status_label.pack(side="right", padx=12)

        # Tabview com 3 abas
        self._tabs = ctk.CTkTabview(self, corner_radius=4)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self._tab_words_name = "Palavras"
        self._tab_concepts_name = "Conceitos"
        self._tab_network_name = "Rede"
        self._tabs.add(self._tab_words_name)
        self._tabs.add(self._tab_concepts_name)
        self._tabs.add(self._tab_network_name)

        self._build_tab_words(self._tabs.tab(self._tab_words_name))
        self._build_tab_concepts(self._tabs.tab(self._tab_concepts_name))
        self._build_tab_network(self._tabs.tab(self._tab_network_name))
        self._style_tabs()

        # Rodapé
        ctk.CTkFrame(self, height=1, fg_color=get_themed_color("border")).pack(fill="x", side="bottom")
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=12, pady=8)
        ctk.CTkButton(
            btn_row, text="Fechar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self.destroy,
        ).pack(side="right")

    def _style_tabs(self) -> None:
        """Aplica estilo de abas mais legível e sem artefatos visuais."""
        try:
            self._tabs.configure(
                segmented_button_fg_color=get_themed_color("surface"),
                segmented_button_selected_color=get_themed_color("primary"),
                segmented_button_selected_hover_color=get_themed_color("primary_hover"),
                segmented_button_unselected_color=get_themed_color("button"),
                segmented_button_unselected_hover_color=get_themed_color("button_hover"),
                segmented_button_selected_text_color=("#FFFFFF", "#FFFFFF"),
                segmented_button_unselected_text_color=get_themed_color("text"),
                command=lambda _selected=None: self._on_tab_changed(_selected),
            )
        except Exception:
            pass
        self._on_tab_changed(self._tabs.get())
        self.after_idle(self._refresh_tab_text_colors)
        self.after(120, self._refresh_tab_text_colors)
        self.after(150, self._refresh_auto_mode_selector_colors)

    def _on_tab_changed(self, _selected: Optional[str] = None) -> None:
        """Refresh visual state when tab changes (manual or programmatic)."""
        self._refresh_tab_text_colors()
        if hasattr(self, "tk"):
            self.after_idle(self._refresh_tab_text_colors)

    def _refresh_tab_text_colors(self) -> None:
        """Garante texto claro na aba selecionada."""
        try:
            segmented = getattr(self._tabs, "_segmented_button", None)
            buttons_dict = getattr(segmented, "_buttons_dict", {}) if segmented is not None else {}
            active = str(self._tabs.get() or "")
            default_text = get_themed_color("text")
            for name, button in buttons_dict.items():
                is_active = str(name) == active
                if is_active:
                    button.configure(
                        text_color=("#FFFFFF", "#FFFFFF"),
                        text_color_disabled=("#FFFFFF", "#FFFFFF"),
                    )
                else:
                    button.configure(
                        text_color=default_text,
                        text_color_disabled=default_text,
                    )
        except Exception:
            pass

    def _refresh_auto_mode_selector_colors(self) -> None:
        """Garante contraste legível para o seletor 'Padrão'/'Anti-ruído'."""
        selector = self._auto_mode_selector
        if selector is None:
            return
        try:
            selector.configure(
                selected_color=get_themed_color("primary"),
                selected_hover_color=get_themed_color("primary_hover"),
                unselected_color=get_themed_color("button"),
                unselected_hover_color=get_themed_color("button_hover"),
            )
        except Exception:
            pass
        try:
            active = str(selector.get() or "")
            default_text = get_themed_color("text")
            buttons_dict = getattr(selector, "_buttons_dict", {})
            for name, button in buttons_dict.items():
                is_active = str(name) == active
                button.configure(
                    text_color=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                    text_color_disabled=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Aba 1 — Palavras
    # ------------------------------------------------------------------

    def _build_tab_words(self, tab) -> None:
        # Controles superiores
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=(4, 4))

        ctk.CTkLabel(ctrl, text="Top palavras:", font=FONTS["small"]).pack(side="left")
        self._create_help_icon(
            ctrl,
            "Define quantas palavras mais frequentes serão exibidas para seleção de conceitos.",
        ).pack(side="left", padx=(4, 6))
        self._top_n_var = ctk.IntVar(value=100)
        ctk.CTkSlider(
            ctrl, from_=20, to=300, number_of_steps=56,
            variable=self._top_n_var, width=120,
            command=lambda _: self._refresh_word_list(),
        ).pack(side="left", padx=(4, 2))
        self._top_n_label = ctk.CTkLabel(ctrl, text="100", font=FONTS["small"], width=30)
        self._top_n_label.pack(side="left", padx=(0, 16))
        self._top_n_var.trace_add("write",
            lambda *_: self._top_n_label.configure(text=str(self._top_n_var.get())))

        ctk.CTkLabel(ctrl, text="Freq. mín.:", font=FONTS["small"]).pack(side="left")
        self._create_help_icon(
            ctrl,
            "Filtra palavras raras. Aumente para reduzir ruído; diminua para incluir mais termos.",
        ).pack(side="left", padx=(4, 6))
        self._min_freq_var = ctk.IntVar(value=2)
        ctk.CTkSlider(
            ctrl, from_=1, to=20, number_of_steps=19,
            variable=self._min_freq_var, width=80,
            command=lambda _: self._refresh_word_list(),
        ).pack(side="left", padx=(4, 2))
        self._min_freq_label = ctk.CTkLabel(ctrl, text="2", font=FONTS["small"], width=24)
        self._min_freq_label.pack(side="left", padx=(0, 16))
        self._min_freq_var.trace_add("write",
            lambda *_: self._min_freq_label.configure(text=str(self._min_freq_var.get())))

        action_group = ctk.CTkFrame(ctrl, fg_color="transparent")
        action_group.pack(side="right", padx=(0, 6))

        # Botão: criar conceito a partir da seleção
        self._btn_create_concept_manual = ctk.CTkButton(
            action_group, text=label_with_icon("import", "Criar conceito com seleção"), height=26, width=220,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            border_width=0, corner_radius=3,
            command=self._create_concept_from_selection,
        )
        self._btn_create_concept_manual.pack(side="left")
        
        self._create_help_icon(
            action_group,
            "Cria um novo conceito agrupando as palavras que você selecionou na tabela."
        ).pack(side="left", padx=(4, 16))

        self._btn_create_concept_auto = ctk.CTkButton(
            action_group,
            text=label_with_icon("analyses", "Criar automaticamente"),
            height=26,
            width=180,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            border_width=0,
            corner_radius=3,
            command=self._auto_create_concepts,
        )
        self._btn_create_concept_auto.pack(side="left")
        
        self._create_help_icon(
            action_group,
            "Gera sugestões via CCA + rede (Louvain). "
            "Usa confiança >= 0.80, pontes morfológicas/ortográficas e relaxamento adaptativo "
            "quando o corpus estiver muito disperso. Sempre pede confirmação antes de aplicar.\n\n"
            "Importante: isto organiza conceitos para o CCA atual; não reescreve o corpus global.",
        ).pack(side="left", padx=(4, 16))

        self._auto_mode_selector = ctk.CTkSegmentedButton(
            action_group,
            values=["Padrão", "Anti-ruído"],
            variable=self._auto_mode_var,
            width=160,
            height=26,
            corner_radius=3,
        )
        self._auto_mode_selector.set(self._auto_mode_var.get())
        self._auto_mode_selector.pack(side="left")
        self._auto_mode_var.trace_add("write", lambda *_: self._refresh_auto_mode_selector_colors())
        self.after_idle(self._refresh_auto_mode_selector_colors)
        
        self._create_help_icon(
            action_group,
            "Padrão: equilíbrio geral entre cobertura e precisão.\n"
            "Anti-ruído: mais conservador para PDFs/artigos com afiliação, DOI, nomes e metadados.",
        ).pack(side="left", padx=(4, 0))

        # Treeview de palavras
        tv_frame = tk.Frame(tab, bg=self._native_colors.get("background", COLORS["background"]))
        tv_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        selected_bg = self._native_colors.get("primary", COLORS["primary"])
        style.configure("CCA.Treeview",
                         rowheight=20, font=("Segoe UI", 10),
                         background=self._native_colors.get("surface", COLORS["surface"]),
                         fieldbackground=self._native_colors.get("surface", COLORS["surface"]),
                         foreground=self._native_colors.get("text", COLORS["text"]))
        style.configure("CCA.Treeview.Heading",
                         font=("Segoe UI", 10, "bold"))
        style.map(
            "CCA.Treeview",
            background=[("selected", selected_bg)],
            foreground=[("selected", "#FFFFFF")],
        )

        self._word_tree = ttk.Treeview(
            tv_frame, style="CCA.Treeview",
            columns=("word", "freq", "concept"),
            show="headings", selectmode="extended",
        )
        self._word_tree.heading("word",    text="Palavra")
        self._word_tree.heading("freq",    text="Freq.")
        self._word_tree.heading("concept", text="Conceito atribuído")
        self._word_tree.column("word",    width=200, anchor="w")
        self._word_tree.column("freq",    width=60,  anchor="center", stretch=False)
        self._word_tree.column("concept", width=220, anchor="w")

        vsb = ttk.Scrollbar(tv_frame, orient="vertical",   command=self._word_tree.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=self._word_tree.xview)
        self._word_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._word_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        # Hint count
        self._word_count_label = ctk.CTkLabel(
            tab, text="", font=FONTS["small"], text_color=COLORS["text_secondary"], anchor="w"
        )
        self._word_count_label.pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------------
    # Aba 2 — Conceitos
    # ------------------------------------------------------------------

    def _build_tab_concepts(self, tab) -> None:
        # Painel esquerdo: lista de conceitos
        left = ctk.CTkFrame(tab, fg_color="transparent", width=220)
        left.pack(side="left", fill="y", padx=(0, 4), pady=4)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="Conceitos criados:", font=FONTS["heading"]).pack(anchor="w")

        self._concept_listbox_frame = tk.Frame(
            left,
            bg=self._native_colors.get("surface", COLORS["surface"]),
        )
        self._concept_listbox_frame.pack(fill="both", expand=True, pady=4)

        self._concept_listbox = tk.Listbox(
            self._concept_listbox_frame,
            font=("Segoe UI", 10),
            bg=self._native_colors.get("surface", COLORS["surface"]),
            fg=self._native_colors.get("text", COLORS["text"]),
            selectbackground=self._native_colors.get("primary", COLORS["primary"]),
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            activestyle="none",
        )
        concept_vsb = ttk.Scrollbar(self._concept_listbox_frame, orient="vertical",
                                     command=self._concept_listbox.yview)
        self._concept_listbox.configure(yscrollcommand=concept_vsb.set)
        self._concept_listbox.pack(side="left", fill="both", expand=True)
        concept_vsb.pack(side="right", fill="y")
        self._concept_listbox.bind("<<ListboxSelect>>", self._on_concept_select)

        # Botões de conceito
        btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame.pack(fill="x")

        def _small_btn(parent, text, command, width=110):
            return ctk.CTkButton(
                parent, text=text, height=24, width=width,
                fg_color=get_themed_color("button"),
                hover_color=get_themed_color("button_hover"),
                text_color=get_themed_color("text"),
                border_width=1, border_color=get_themed_color("border"),
                corner_radius=3, font=FONTS["small"],
                command=command,
            )

        _small_btn(btn_frame, label_with_icon("import", "Novo"), self._new_concept, width=100).pack(side="left", padx=(0, 2), pady=2)
        _small_btn(btn_frame, label_with_icon("settings", "Renomear"), self._rename_concept, width=118).pack(side="left", padx=2, pady=2)
        _small_btn(btn_frame, label_with_icon("delete", "Apagar"), self._delete_concept, width=104).pack(side="left", padx=2, pady=2)

        # Divisória
        ctk.CTkFrame(tab, width=1, fg_color=get_themed_color("border")).pack(side="left", fill="y")

        # Painel direito: palavras do conceito selecionado
        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        ctk.CTkLabel(right, text="Palavras do conceito selecionado:", font=FONTS["heading"]).pack(anchor="w")

        self._concept_words_frame = tk.Frame(
            right,
            bg=self._native_colors.get("surface", COLORS["surface"]),
        )
        self._concept_words_frame.pack(fill="both", expand=True, pady=4)

        self._concept_words_listbox = tk.Listbox(
            self._concept_words_frame,
            font=("Segoe UI", 10),
            bg=self._native_colors.get("surface", COLORS["surface"]),
            fg=self._native_colors.get("text", COLORS["text"]),
            selectbackground=self._native_colors.get("primary", COLORS["primary"]),
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            selectmode="extended",
            activestyle="none",
        )
        words_vsb = ttk.Scrollbar(self._concept_words_frame, orient="vertical",
                                   command=self._concept_words_listbox.yview)
        self._concept_words_listbox.configure(yscrollcommand=words_vsb.set)
        self._concept_words_listbox.pack(side="left", fill="both", expand=True)
        words_vsb.pack(side="right", fill="y")

        words_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        words_btn_row.pack(fill="x")
        _small_btn(words_btn_row, label_with_icon("import", "Adicionar palavra"), self._add_word_to_concept).pack(side="left", padx=(0,4))
        _small_btn(words_btn_row, label_with_icon("delete", "Remover selecionadas"), self._remove_words_from_concept).pack(side="left")

        # Importar/Exportar esquema de conceitos
        io_row = ctk.CTkFrame(right, fg_color="transparent")
        io_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(io_row, text="Esquema de codificação:", font=FONTS["small"],
                      text_color=COLORS["text_secondary"]).pack(side="left")
        _small_btn(io_row, label_with_icon("save", "Salvar"),   self._save_concept_scheme).pack(side="left", padx=(8,4))
        _small_btn(io_row, label_with_icon("open", "Carregar"), self._load_concept_scheme).pack(side="left")

    # ------------------------------------------------------------------
    # Aba 3 — Rede
    # ------------------------------------------------------------------

    def _build_tab_network(self, tab) -> None:
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", pady=4)

        # Parâmetros
        ctk.CTkLabel(top, text="Janela (tokens):", font=FONTS["small"]).pack(side="left")
        self._create_help_icon(
            top,
            "Número de tokens usados para considerar co-ocorrência entre conceitos.",
        ).pack(side="left", padx=(4, 6))
        self._window_var = ctk.IntVar(value=10)
        ctk.CTkSlider(
            top, from_=5, to=50, number_of_steps=45,
            variable=self._window_var, width=120,
        ).pack(side="left", padx=(4, 2))
        self._window_label = ctk.CTkLabel(top, text="10", font=FONTS["small"], width=30)
        self._window_label.pack(side="left", padx=(0, 16))
        self._window_var.trace_add("write",
            lambda *_: self._window_label.configure(text=str(self._window_var.get())))

        ctk.CTkLabel(top, text="Min. co-ocorrências:", font=FONTS["small"]).pack(side="left")
        self._create_help_icon(
            top,
            "Conexões com valor abaixo deste limite são removidas da rede final.",
        ).pack(side="left", padx=(4, 6))
        self._min_co_var = ctk.IntVar(value=1)
        ctk.CTkSlider(
            top, from_=1, to=20, number_of_steps=19,
            variable=self._min_co_var, width=80,
        ).pack(side="left", padx=(4, 2))
        self._min_co_label = ctk.CTkLabel(top, text="1", font=FONTS["small"], width=24)
        self._min_co_label.pack(side="left", padx=(0, 16))
        self._min_co_var.trace_add("write",
            lambda *_: self._min_co_label.configure(text=str(self._min_co_var.get())))

        ctk.CTkButton(
            top, text="▶  Executar CCA", height=28, width=140,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            border_width=0, corner_radius=3,
            command=self._run_cca,
        ).pack(side="right")

        # Progresso
        self._cca_progress = ctk.CTkProgressBar(tab, height=3, corner_radius=2)
        self._cca_progress.pack(fill="x", padx=0, pady=(0, 4))
        self._cca_progress.set(0)
        self._cca_status = ctk.CTkLabel(
            tab, text="", font=FONTS["small"],
            text_color=COLORS["text_secondary"], anchor="w"
        )
        self._cca_status.pack(fill="x")

        # Tabela de resultado
        res_frame = tk.Frame(tab, bg=COLORS["background"])
        res_frame.pack(fill="both", expand=True, pady=4)

        self._result_tree = ttk.Treeview(
            res_frame, style="CCA.Treeview",
            columns=("source", "target", "weight"),
            show="headings", selectmode="browse",
        )
        self._result_tree.heading("source", text="Conceito A")
        self._result_tree.heading("target", text="Conceito B")
        self._result_tree.heading("weight", text="Co-ocorrências")
        self._result_tree.column("source", width=240, anchor="w")
        self._result_tree.column("target", width=240, anchor="w")
        self._result_tree.column("weight", width=100, anchor="center", stretch=False)

        res_vsb = ttk.Scrollbar(res_frame, orient="vertical", command=self._result_tree.yview)
        self._result_tree.configure(yscrollcommand=res_vsb.set)
        self._result_tree.grid(row=0, column=0, sticky="nsew")
        res_vsb.grid(row=0, column=1, sticky="ns")
        res_frame.rowconfigure(0, weight=1)
        res_frame.columnconfigure(0, weight=1)

        # Botões de exportação
        export_row = ctk.CTkFrame(tab, fg_color="transparent")
        export_row.pack(fill="x", pady=(4, 0))

        def _exp_btn(text, cmd):
            return ctk.CTkButton(
                export_row, text=text, height=26, width=140,
                fg_color=get_themed_color("button"),
                hover_color=get_themed_color("button_hover"),
                text_color=get_themed_color("text"),
                border_width=1, border_color=get_themed_color("border"),
                corner_radius=3, font=FONTS["small"],
                command=cmd,
            )

        _exp_btn(label_with_icon("save", "Exportar GEXF (.gexf)"), self._export_gexf).pack(side="left", padx=(0, 6))
        _exp_btn(label_with_icon("export", "Exportar CSV (.csv)"),   self._export_csv).pack(side="left", padx=(0, 6))
        _exp_btn(label_with_icon("report", "Copiar tabela"),          self._copy_table).pack(side="left")

        self._concept_stats_label = ctk.CTkLabel(
            tab, text="", font=FONTS["small"],
            text_color=COLORS["text_secondary"], anchor="e"
        )
        self._concept_stats_label.pack(fill="x")

    # ------------------------------------------------------------------
    # Carregamento do vocabulário
    # ------------------------------------------------------------------

    def _ensure_vocab_loading_started(self) -> None:
        """Fallback para garantir início do carregamento caso agendamento falhe."""
        if self._analyzer is not None or self._vocab_loading:
            return
        self._append_vocab_debug("fallback_triggered _ensure_vocab_loading_started")
        self._load_vocab()

    def _load_vocab(self) -> None:
        """Carrega o analisador e vocabulário em thread de fundo."""
        if self._vocab_loading:
            self._append_vocab_debug("load_vocab_skipped already_loading")
            return

        self._vocab_loading = True
        self._last_vocab_progress = -1
        self._vocab_progress_queue = queue.Queue()
        self._vocab_loading_started_at = time.time()
        self._vocab_force_started = False
        self._append_vocab_debug(
            f"load_vocab_started chars={len(str(self._corpus_text or ''))} "
            f"lines={len(str(self._corpus_text or '').splitlines())}"
        )
        log.info(
            "CCA vocab load started (chars=%d, lines=%d)",
            len(str(self._corpus_text or "")),
            len(str(self._corpus_text or "").splitlines()),
        )

        def on_vocab_progress(percent: int, detail: str) -> None:
            if self._vocab_progress_queue is not None:
                self._vocab_progress_queue.put(("progress", int(percent or 0), str(detail or "")))
            pct = int(percent or 0)
            if pct in {1, 5, 10, 25, 50, 75, 90, 94, 100}:
                self._append_vocab_debug(f"progress_event pct={pct} detail={detail}")

        def worker():
            try:
                if self._vocab_progress_queue is not None:
                    self._vocab_progress_queue.put(("status", "Carregando vocabulário... 1%"))
                from ...analysis.cca_analysis import CCAAnalyzer
                self._analyzer = CCAAnalyzer(
                    self._corpus_text,
                    remove_stopwords=True,
                    min_word_length=3,
                    progress_callback=on_vocab_progress,
                )
                if self._vocab_progress_queue is not None:
                    self._vocab_progress_queue.put(("done", self._analyzer))
                self._append_vocab_debug("worker_done")
                log.info("CCA vocab load worker finished successfully")
            except Exception as exc:
                log.exception("Erro ao carregar vocabulário CCA")
                if self._vocab_progress_queue is not None:
                    self._vocab_progress_queue.put(("error", str(exc)))
                self._append_vocab_debug(f"worker_error {exc}")

        self._status_label.configure(
            text="Carregando vocabulário... 1%",
            text_color=COLORS["text_secondary"],
        )
        self.after(60, self._poll_vocab_progress_queue)
        self.after(3200, self._force_vocab_load_if_stuck)
        thread = threading.Thread(target=worker, daemon=True)
        self._vocab_worker_thread = thread
        thread.start()

    def _finalize_vocab_loaded(self, analyzer: Any, source: str) -> None:
        """Finaliza UI de vocabulário carregado de forma idempotente."""
        if self._analyzer is not None and analyzer is not self._analyzer:
            return
        self._analyzer = analyzer
        self._refresh_word_list()
        vocab_size = self._analyzer.get_vocab_size() if self._analyzer else 0
        self._status_label.configure(
            text=f"Vocabulário: {vocab_size} formas únicas",
            text_color=COLORS["text_secondary"],
        )
        self._append_vocab_debug(f"finalize_loaded source={source} vocab_size={vocab_size}")
        self._vocab_loading = False

    def _force_vocab_load_if_stuck(self) -> None:
        """
        Fallback definitivo para casos em que progresso/polling não evoluem.

        Executa um segundo carregamento mínimo sem callback e finaliza via
        `_safe_after`, evitando ficar em 0% indefinidamente.
        """
        if not self._vocab_loading or self._analyzer is not None or self._vocab_force_started:
            return
        if self._last_vocab_progress > 1:
            return
        self._vocab_force_started = True
        self._append_vocab_debug("force_fallback_started")

        def fallback_worker() -> None:
            try:
                from ...analysis.cca_analysis import CCAAnalyzer
                analyzer = CCAAnalyzer(
                    self._corpus_text,
                    remove_stopwords=True,
                    min_word_length=3,
                )
                self._safe_after(lambda: self._finalize_vocab_loaded(analyzer, source="fallback"))
            except Exception as exc:
                self._append_vocab_debug(f"force_fallback_error {exc}")
                self._safe_after(
                    lambda: self._status_label.configure(
                        text=f"Erro: {exc}",
                        text_color=COLORS["danger"],
                    )
                )
                self._safe_after(lambda: setattr(self, "_vocab_loading", False))

        threading.Thread(target=fallback_worker, daemon=True).start()

    def _poll_vocab_progress_queue(self) -> None:
        """Processa progresso de carregamento sem tocar Tk a partir de threads de fundo."""
        if not self._vocab_loading:
            return

        stop_poll = False
        q = self._vocab_progress_queue
        try:
            if q is not None:
                while True:
                    try:
                        event = q.get_nowait()
                    except queue.Empty:
                        break

                    kind = str(event[0] if event else "")
                    if kind == "status":
                        text = str(event[1] if len(event) > 1 else "")
                        if text:
                            self._status_label.configure(text=text, text_color=COLORS["text_secondary"])
                    elif kind == "progress":
                        pct = int(max(0, min(100, int(event[1] if len(event) > 1 else 0))))
                        detail = str(event[2] if len(event) > 2 else "")
                        if pct <= self._last_vocab_progress and pct != 100:
                            continue
                        self._last_vocab_progress = pct
                        status_text = f"Carregando vocabulário... {pct}%"
                        if detail and pct < 100:
                            status_text = f"{status_text}  ({detail})"
                        self._status_label.configure(text=status_text, text_color=COLORS["text_secondary"])
                    elif kind == "done":
                        analyzer = event[1] if len(event) > 1 else None
                        self._finalize_vocab_loaded(analyzer, source="queue_done")
                        vocab_size = self._analyzer.get_vocab_size() if self._analyzer else 0
                        log.info("CCA vocab ready (forms=%d)", vocab_size)
                        stop_poll = True
                        break
                    elif kind == "error":
                        msg = str(event[1] if len(event) > 1 else "Erro desconhecido")
                        self._status_label.configure(
                            text=f"Erro: {msg}",
                            text_color=COLORS["danger"],
                        )
                        self._append_vocab_debug(f"poll_error {msg}")
                        log.error("CCA vocab load failed: %s", msg)
                        self._vocab_loading = False
                        stop_poll = True
                        break
        except Exception as exc:
            log.exception("Falha ao processar progresso do vocabulário CCA: %s", exc)

        # Watchdog: evita ficar preso em 0/1% caso o worker trave cedo.
        if not stop_poll and self._vocab_loading:
            elapsed = float(time.time() - float(self._vocab_loading_started_at or 0.0))
            worker_alive = bool(self._vocab_worker_thread and self._vocab_worker_thread.is_alive())
            if worker_alive and self._last_vocab_progress < 2 and elapsed > 1.5:
                self._last_vocab_progress = 2
                self._status_label.configure(
                    text="Carregando vocabulário... 2%  (Preparando módulos)",
                    text_color=COLORS["text_secondary"],
                )
                self._append_vocab_debug("watchdog_bumped_to_2pct")
            elif not worker_alive and elapsed > 0.8 and self._analyzer is None:
                self._status_label.configure(
                    text="Erro: carregamento do vocabulário foi interrompido.",
                    text_color=COLORS["danger"],
                )
                self._append_vocab_debug("watchdog_worker_dead_without_analyzer")
                log.error("CCA vocab load interrupted before completion")
                self._vocab_loading = False
                stop_poll = True

        if not stop_poll and self._vocab_loading:
            self.after(80, self._poll_vocab_progress_queue)

    def _refresh_word_list(self) -> None:
        if not self._analyzer:
            return
        n = max(10, int(self._top_n_var.get() or 100))
        mf = max(1, int(self._min_freq_var.get() or 2))
        words = self._analyzer.get_top_words(n=n, min_freq=mf)

        for item in self._word_tree.get_children():
            self._word_tree.delete(item)

        # Mapa inverso: palavra → conceito
        word_to_concept: Dict[str, str] = {}
        for concept, wlist in self._concept_map.items():
            for w in wlist:
                word_to_concept[w] = concept

        for wf in words:
            concept = word_to_concept.get(wf.word, "")
            color_tag = ""
            if concept and concept in self._concept_colors:
                color_tag = f"concept_{list(self._concept_colors.keys()).index(concept)}"
            iid = self._word_tree.insert(
                "", "end",
                values=(wf.word, wf.freq, concept or "—"),
                tags=(color_tag,) if color_tag else (),
            )

        # Colorir linhas por conceito
        for i, concept in enumerate(self._concept_colors):
            tag = f"concept_{i}"
            color = _normalize_tk_color(self._concept_colors[concept], fallback="#888888")
            bg = _blend_hex_colors(
                color,
                self._native_colors.get("surface", COLORS["surface"]),
                ratio=0.18,
            )
            self._word_tree.tag_configure(tag, background=bg)

        self._word_count_label.configure(
            text=f"{len(words)} palavras exibidas  ·  {len(self._concept_map)} conceito(s) definido(s)"
        )

    def _set_auto_controls_busy(self, busy: bool) -> None:
        """Liga/desliga botões da aba Palavras durante geração automática."""
        state = "disabled" if busy else "normal"
        self._auto_running = bool(busy)
        if self._btn_create_concept_auto:
            self._btn_create_concept_auto.configure(state=state)
        if self._btn_create_concept_manual:
            self._btn_create_concept_manual.configure(state=state)
        if self._auto_mode_selector:
            self._auto_mode_selector.configure(state=state)

    def _build_auto_concept_config(self, auto_mode: str):
        """Monta configuração de auto-conceitos de acordo com o modo da UI."""
        from ...analysis.cca_analysis import AutoConceptConfig

        top_n = max(280, int(self._top_n_var.get() or 100))
        min_freq = max(2, int(self._min_freq_var.get() or 2))
        mode = str(auto_mode or "Padrão").strip().lower()
        anti_noise = mode.startswith("anti")

        if anti_noise:
            return AutoConceptConfig(
                top_n=max(320, top_n),
                min_freq=min_freq,
                window_size=8,
                min_edge_weight=2,
                min_cluster_size=3,
                confidence_threshold=0.82,
                max_concepts=16,
                resolution=1.05,
                seed=42,
                adaptive_relaxation=True,
                relaxation_steps=3,
                relaxed_confidence_floor=0.72,
                target_min_concepts=4,
                target_min_assigned_words=16,
                lemma_bridge_weight=1.05,
                orthographic_bridge_weight=0.22,
                orthographic_similarity=0.90,
                max_orthographic_pairs=260,
                external_pair_weight=0.90,
                semantic_bonus_weight=0.10,
                early_stop_min_modularity=0.18,
                early_stop_max_dominance=0.68,
            )

        return AutoConceptConfig(
            top_n=top_n,
            min_freq=min_freq,
            window_size=7,
            min_edge_weight=2,
            min_cluster_size=3,
            confidence_threshold=0.80,
            max_concepts=18,
            resolution=1.0,
            seed=42,
            adaptive_relaxation=True,
            relaxation_steps=3,
            relaxed_confidence_floor=0.68,
            target_min_concepts=4,
            target_min_assigned_words=18,
            lemma_bridge_weight=1.15,
            orthographic_bridge_weight=0.38,
            orthographic_similarity=0.88,
            max_orthographic_pairs=520,
            external_pair_weight=0.95,
            semantic_bonus_weight=0.12,
            early_stop_min_modularity=0.16,
            early_stop_max_dominance=0.74,
        )

    def _auto_create_concepts(self) -> None:
        """Executa geração automática de conceitos em thread com prévia obrigatória."""
        if not self._analyzer:
            messagebox.showinfo("Aguarde", "O vocabulário ainda está sendo carregado.", parent=self)
            return
        if self._auto_running:
            return

        selected_mode = str(self._auto_mode_var.get() or "Padrão")
        self._set_auto_controls_busy(True)
        self._status_label.configure(text=f"Gerando sugestões automáticas ({selected_mode})...")
        self._word_count_label.configure(text="Gerando sugestões automáticas...")
        self._append_vocab_debug(f"auto_start mode={selected_mode}")

        def worker():
            try:
                config = self._build_auto_concept_config(selected_mode)
                result = self._analyzer.suggest_concepts_hybrid(config)
                self._append_vocab_debug(
                    "auto_generated "
                    f"suggestions={len(list(getattr(result, 'suggestions', []) or []))} "
                    f"unassigned={len(list(getattr(result, 'unassigned_words', []) or []))}"
                )
                self._safe_after(lambda: self._open_auto_preview_safe(result))
            except Exception as exc:
                log.exception("Erro ao gerar conceitos automáticos")
                self._append_vocab_debug(f"auto_error_generate {exc}")
                self._safe_after(
                    lambda: messagebox.showerror(
                        "Erro",
                        f"Falha ao gerar conceitos automáticos:\n{exc}",
                        parent=self,
                    )
                )
            finally:
                self._append_vocab_debug("auto_worker_finished")
                self._safe_after(lambda: self._set_auto_controls_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _open_auto_preview_safe(self, auto_result: Any) -> None:
        """
        Wrapper seguro para a prévia automática.

        Evita falha silenciosa em callbacks Tk (pythonw), registrando no log e
        sinalizando erro no status da janela.
        """
        try:
            self._open_auto_preview(auto_result)
        except Exception as exc:
            log.exception("Falha inesperada ao abrir/aplicar prévia automática do CCA")
            self._append_vocab_debug(f"auto_preview_unhandled_error {exc}")
            try:
                self._status_label.configure(
                    text=f"Erro ao aplicar sugestões automáticas: {exc}",
                    text_color=COLORS["danger"],
                )
                messagebox.showerror(
                    "Erro no CCA automático",
                    (
                        "Ocorreu um erro interno ao aplicar as sugestões automáticas.\n\n"
                        f"Detalhe: {exc}\n\n"
                        "Consulte o arquivo de diagnóstico:\n"
                        f"{self._vocab_debug_log_path_project}"
                    ),
                    parent=self,
                )
            except Exception:
                pass

    @staticmethod
    def _resolve_auto_concept_name(base_name: str, concept_map: Dict[str, List[str]]) -> str:
        """Gera nome de conceito sem sobrescrever nomes já existentes."""
        name = str(base_name or "").strip() or "conceito"
        if name not in concept_map:
            return name

        candidate = f"{name} (auto)"
        if candidate not in concept_map:
            return candidate

        idx = 2
        while True:
            candidate = f"{name} (auto {idx})"
            if candidate not in concept_map:
                return candidate
            idx += 1

    @staticmethod
    def _merge_auto_suggestions(
        concept_map: Dict[str, List[str]],
        suggestions: List[Any],
    ) -> Tuple[Dict[str, List[str]], List[str], int]:
        """
        Mescla sugestões automáticas sem sobrescrever conceitos manuais.

        Regras:
          - palavras já atribuídas manualmente permanecem no conceito original
          - colisão de nome gera sufixo automático
          - conceitos com <2 palavras novas são descartados
        """
        merged: Dict[str, List[str]] = {
            str(name): [str(word).strip().lower() for word in list(words or []) if str(word).strip()]
            for name, words in concept_map.items()
        }
        existing_words = {word for words in merged.values() for word in words}
        created_names: List[str] = []
        words_added = 0

        for suggestion in suggestions:
            if hasattr(suggestion, "name"):
                raw_name = str(getattr(suggestion, "name", "") or "")
                raw_words = getattr(suggestion, "words", []) or []
            elif isinstance(suggestion, dict):
                raw_name = str(suggestion.get("name", "") or "")
                raw_words = suggestion.get("words", []) or []
            else:
                continue

            if isinstance(raw_words, str):
                candidates_raw = [
                    chunk.strip()
                    for chunk in raw_words.replace(";", ",").replace("\n", ",").split(",")
                    if chunk and chunk.strip()
                ]
            else:
                candidates_raw = []
                for item in list(raw_words):
                    text = str(item or "").strip()
                    if not text:
                        continue
                    if "," in text or ";" in text or "\n" in text:
                        split_parts = [
                            chunk.strip()
                            for chunk in text.replace(";", ",").replace("\n", ",").split(",")
                            if chunk and chunk.strip()
                        ]
                        candidates_raw.extend(split_parts)
                    else:
                        candidates_raw.append(text)

            candidate_words: List[str] = []
            local_seen = set()
            for word in candidates_raw:
                token = str(word or "").strip().lower()
                if not token or token in local_seen or token in existing_words:
                    continue
                local_seen.add(token)
                candidate_words.append(token)

            if len(candidate_words) < 2:
                continue

            concept_name = CCADialog._resolve_auto_concept_name(raw_name, merged)
            merged[concept_name] = candidate_words
            created_names.append(concept_name)
            words_added += len(candidate_words)
            existing_words.update(candidate_words)

        return merged, created_names, words_added

    def _open_auto_preview(self, auto_result: Any) -> None:
        """Abre prévia de sugestões e aplica seleção confirmada pelo usuário."""
        suggestions = list(getattr(auto_result, "suggestions", []) or [])
        unassigned_words = list(getattr(auto_result, "unassigned_words", []) or [])
        diagnostics = dict(getattr(auto_result, "diagnostics", {}) or {})
        self._append_vocab_debug(
            f"auto_preview_open suggestions={len(suggestions)} unassigned={len(unassigned_words)}"
        )

        if not suggestions:
            self._refresh_word_list()
            self._status_label.configure(
                text=(
                    "Nenhuma sugestão automática com confiança suficiente. "
                    f"Termos não atribuídos: {len(unassigned_words)}"
                )
            )
            messagebox.showinfo(
                "Sem sugestões confiáveis",
                (
                    "A geração automática não encontrou clusters com confiança alta.\n\n"
                    "Dica: aumente Top palavras ou reduza Freq. mínima para ampliar o contexto."
                ),
                parent=self,
            )
            self._append_vocab_debug("auto_preview_no_suggestions")
            return

        from .cca_auto_preview_dialog import CCAAutoPreviewDialog

        self._status_label.configure(
            text=f"Sugestões prontas: {len(suggestions)}. Revise e confirme na prévia.",
            text_color=COLORS["text_secondary"],
        )

        preview = CCAAutoPreviewDialog(
            self,
            suggestions=suggestions,
            unassigned_words=unassigned_words,
            diagnostics=diagnostics,
        )
        selected = preview.get_result()
        if not selected:
            self._refresh_word_list()
            self._status_label.configure(text="Aplicação de sugestões automáticas cancelada.")
            self._append_vocab_debug("auto_preview_cancelled")
            return

        self._append_vocab_debug(f"auto_preview_selected count={len(selected)}")
        try:
            concepts_added, words_added = self._apply_auto_suggestions(
                selected,
                switch_to_concepts_tab=False,
            )
        except Exception as exc:
            log.exception("Erro ao aplicar sugestões automáticas do CCA")
            self._append_vocab_debug(f"auto_apply_error {exc}")
            self._status_label.configure(text=f"Erro ao aplicar sugestões: {exc}", text_color=COLORS["danger"])
            messagebox.showerror(
                "Erro ao aplicar sugestões",
                f"Falha ao aplicar sugestões automáticas:\n{exc}",
                parent=self,
            )
            return

        if words_added <= 0 and suggestions and not self._concept_map:
            # Fallback defensivo: se a seleção vier em formato não previsto,
            # ainda tentamos aplicar o conjunto completo diretamente.
            self._append_vocab_debug("auto_apply_fallback_full_suggestions")
            concepts_added, words_added = self._apply_auto_suggestions(
                suggestions,
                switch_to_concepts_tab=False,
            )

        self._refresh_word_list()

        if words_added <= 0:
            messagebox.showinfo(
                "Nada aplicado",
                (
                    "Nenhuma palavra nova foi adicionada.\n"
                    "As palavras sugeridas já estavam atribuídas a conceitos existentes."
                ),
                parent=self,
            )
            self._status_label.configure(text="Sugestões automáticas não alteraram os conceitos.")
            self._append_vocab_debug("auto_apply_no_changes")
            return

        # Após aplicar, já exibe o resultado no fluxo do próprio CCA.
        try:
            self._tabs.set(self._tab_network_name)
            self._on_tab_changed(self._tab_network_name)
            self.after(80, lambda: self._on_tab_changed(self._tab_network_name))
            self.after(120, self._run_cca)
        except Exception:
            pass
        self._append_vocab_debug(
            f"auto_apply_ok concepts_added={concepts_added} words_added={words_added}"
        )
        self._status_label.configure(
            text=(
                f"Sugestões aplicadas no CCA: {concepts_added} conceito(s) e {words_added} palavra(s). "
                "O corpus global não foi alterado."
            )
        )

    def _apply_auto_suggestions(
        self,
        selected_suggestions: List[Any],
        switch_to_concepts_tab: bool = True,
    ) -> Tuple[int, int]:
        """Aplica sugestões selecionadas e atualiza cores/listas sem quebrar conceitos manuais."""
        merged_map, created_names, words_added = self._merge_auto_suggestions(
            concept_map=self._concept_map,
            suggestions=selected_suggestions,
        )

        if words_added <= 0:
            return 0, 0

        self._concept_map = merged_map

        # Adiciona cores para novos conceitos.
        used_colors = list(self._concept_colors.values())
        for concept_name in created_names:
            if concept_name not in self._concept_colors:
                color = _next_color(used_colors)
                self._concept_colors[concept_name] = color
                used_colors.append(color)

        self._refresh_concept_list()
        if created_names:
            self._select_concept(created_names[0])
            if switch_to_concepts_tab:
                self._tabs.set(self._tab_concepts_name)
                self._on_tab_changed(self._tab_concepts_name)

        return len(created_names), words_added

    # ------------------------------------------------------------------
    # Criação / edição de conceitos (Aba 1)
    # ------------------------------------------------------------------

    def _create_concept_from_selection(self) -> None:
        selected = self._word_tree.selection()
        if not selected:
            messagebox.showinfo("Seleção vazia",
                                "Selecione ao menos uma palavra na tabela.",
                                parent=self)
            return
        words = [self._word_tree.item(iid, "values")[0] for iid in selected]

        name = simpledialog.askstring(
            "Novo conceito",
            f"Nome do conceito para as palavras selecionadas:\n{', '.join(words[:5])}{'...' if len(words)>5 else ''}",
            parent=self,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        self._add_to_concept(name, words)

    def _add_to_concept(self, name: str, words: List[str]) -> None:
        if name not in self._concept_map:
            self._concept_map[name] = []
            used = list(self._concept_colors.values())
            self._concept_colors[name] = _next_color(used)

        existing = set(self._concept_map[name])
        for w in words:
            if w not in existing:
                self._concept_map[name].append(w)
                existing.add(w)

        self._refresh_concept_list()
        self._refresh_word_list()
        self._select_concept(name)
        self._tabs.set(self._tab_concepts_name)

    # ------------------------------------------------------------------
    # Aba 2: gestão de conceitos
    # ------------------------------------------------------------------

    def _refresh_concept_list(self) -> None:
        self._concept_listbox.delete(0, "end")
        for concept in self._concept_map:
            n_words = len(self._concept_map[concept])
            self._concept_listbox.insert("end", f"{concept}  ({n_words})")

    def _select_concept(self, name: str) -> None:
        for i, concept in enumerate(self._concept_map):
            if concept == name:
                self._concept_listbox.selection_clear(0, "end")
                self._concept_listbox.selection_set(i)
                self._on_concept_select(None)
                return

    def _on_concept_select(self, event) -> None:
        sel = self._concept_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        concept = list(self._concept_map.keys())[idx]
        self._concept_words_listbox.delete(0, "end")
        for w in self._concept_map.get(concept, []):
            self._concept_words_listbox.insert("end", w)

    def _selected_concept_name(self) -> Optional[str]:
        sel = self._concept_listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        concepts = list(self._concept_map.keys())
        return concepts[idx] if idx < len(concepts) else None

    def _new_concept(self) -> None:
        name = simpledialog.askstring("Novo conceito", "Nome do novo conceito:", parent=self)
        if name and name.strip():
            name = name.strip()
            if name not in self._concept_map:
                self._concept_map[name] = []
                used = list(self._concept_colors.values())
                self._concept_colors[name] = _next_color(used)
            self._refresh_concept_list()
            self._refresh_word_list()
            self._select_concept(name)

    def _rename_concept(self) -> None:
        old = self._selected_concept_name()
        if not old:
            return
        new = simpledialog.askstring("Renomear", f"Novo nome para '{old}':", parent=self)
        if not new or not new.strip() or new == old:
            return
        new = new.strip()
        # Recriar dicionário preservando ordem
        new_map: Dict[str, List[str]] = {}
        new_colors: Dict[str, str] = {}
        for k, v in self._concept_map.items():
            key = new if k == old else k
            new_map[key] = v
            new_colors[key] = _normalize_tk_color(self._concept_colors.get(k, "#888888"))
        self._concept_map = new_map
        self._concept_colors = new_colors
        self._refresh_concept_list()
        self._refresh_word_list()
        self._select_concept(new)

    def _delete_concept(self) -> None:
        name = self._selected_concept_name()
        if not name:
            return
        if not messagebox.askyesno("Confirmar",
                                   f"Apagar conceito '{name}' e suas {len(self._concept_map[name])} palavras?",
                                   parent=self):
            return
        del self._concept_map[name]
        self._concept_colors.pop(name, None)
        self._refresh_concept_list()
        self._refresh_word_list()
        self._concept_words_listbox.delete(0, "end")

    def _add_word_to_concept(self) -> None:
        name = self._selected_concept_name()
        if not name:
            messagebox.showinfo("Selecione um conceito", "Clique em um conceito na lista.", parent=self)
            return
        word = simpledialog.askstring("Adicionar palavra", f"Palavra para '{name}':", parent=self)
        if word and word.strip():
            self._add_to_concept(name, [word.strip().lower()])

    def _remove_words_from_concept(self) -> None:
        name = self._selected_concept_name()
        if not name:
            return
        sel = self._concept_words_listbox.curselection()
        if not sel:
            return
        to_remove = {self._concept_words_listbox.get(i) for i in sel}
        self._concept_map[name] = [w for w in self._concept_map[name] if w not in to_remove]
        self._on_concept_select(None)
        self._refresh_word_list()

    # ------------------------------------------------------------------
    # Salvar / carregar esquema de conceitos (JSON)
    # ------------------------------------------------------------------

    def _save_concept_scheme(self) -> None:
        if not self._concept_map:
            messagebox.showinfo("Nada para salvar", "Defina ao menos um conceito.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar esquema de conceitos",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        data = {"concept_map": self._concept_map, "concept_colors": self._concept_colors}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo("Salvo", f"Esquema salvo em:\n{path}", parent=self)

    def _load_concept_scheme(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Carregar esquema de conceitos",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._concept_map = data.get("concept_map", {})
            loaded_colors = data.get("concept_colors", {})
            self._concept_colors = {
                str(name): _normalize_tk_color(color)
                for name, color in dict(loaded_colors or {}).items()
            }
            # Atribuir cores ausentes
            used = list(self._concept_colors.values())
            for c in self._concept_map:
                if c not in self._concept_colors:
                    self._concept_colors[c] = _next_color(used)
                    used.append(self._concept_colors[c])
            self._refresh_concept_list()
            self._refresh_word_list()
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao carregar esquema:\n{exc}", parent=self)

    # ------------------------------------------------------------------
    # Aba 3 — Executar CCA
    # ------------------------------------------------------------------

    def _run_cca(self) -> None:
        if not self._analyzer:
            messagebox.showinfo("Aguarde", "O vocabulário ainda está sendo carregado.", parent=self)
            return

        # Filtrar conceitos com pelo menos 1 palavra presente no vocabulário
        vocab = set(self._analyzer.get_vocab().keys() if hasattr(self._analyzer, "get_vocab")
                    else [wf.word for wf in self._analyzer.get_top_words(n=9999, min_freq=1)])
        active_concepts: Dict[str, List[str]] = {}
        for concept, words in self._concept_map.items():
            valid = [w for w in words if w in vocab]
            if valid:
                active_concepts[concept] = valid

        if len(active_concepts) < 2:
            messagebox.showwarning(
                "Conceitos insuficientes",
                "Defina ao menos 2 conceitos com palavras presentes no corpus para executar a CCA.",
                parent=self,
            )
            return

        self._cca_progress.set(0.1)
        self._cca_status.configure(text="Calculando co-ocorrências...")

        window     = max(2, int(self._window_var.get() or 10))
        min_co     = max(1, int(self._min_co_var.get() or 1))

        def worker():
            try:
                from ...analysis.cca_analysis import CCAAnalyzer
                self._safe_after(lambda: self._cca_progress.set(0.4))
                result = self._analyzer.run(active_concepts, window_size=window)
                self._cca_result = result
                self._safe_after(lambda: self._cca_progress.set(0.85))
                self._safe_after(lambda: self._populate_result_table(result, min_co))
            except Exception as exc:
                log.exception("Erro na CCA")
                self._safe_after(lambda: self._cca_status.configure(
                    text=f"Erro: {exc}", text_color=COLORS["danger"]
                ))
            finally:
                self._safe_after(lambda: self._cca_progress.set(1.0))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_result_table(self, result, min_co: int) -> None:
        for item in self._result_tree.get_children():
            self._result_tree.delete(item)

        visible_edges = [e for e in result.edges if e.weight >= min_co]
        for edge in visible_edges:
            self._result_tree.insert("", "end", values=(edge.source, edge.target, edge.weight))

        self._cca_status.configure(
            text=f"{len(result.nodes)} conceitos  ·  {len(visible_edges)} arestas  "
                 f"(min. {min_co} co-ocorrências)  ·  {result.total_windows} janelas analisadas"
        )
        self._concept_stats_label.configure(
            text=f"Janela: {result.window_size} tokens  ·  {result.segments_used} segmentos (UCIs) usados"
        )

    # ------------------------------------------------------------------
    # Exportação
    # ------------------------------------------------------------------

    def _export_gexf(self) -> None:
        if not self._cca_result:
            messagebox.showinfo("Execute a CCA", "Execute a análise (Aba 3) antes de exportar.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar grafo CCA para GEXF",
            defaultextension=".gexf",
            filetypes=[("GEXF", "*.gexf"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            from ...analysis.cca_analysis import CCAAnalyzer
            CCAAnalyzer.export_gexf(self._cca_result, path)
            messagebox.showinfo("Exportado", f"GEXF salvo em:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)

    def _export_csv(self) -> None:
        if not self._cca_result:
            messagebox.showinfo("Execute a CCA", "Execute a análise (Aba 3) antes de exportar.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar co-ocorrências para CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            from ...analysis.cca_analysis import CCAAnalyzer
            CCAAnalyzer.export_csv(self._cca_result, path)
            messagebox.showinfo("Exportado", f"CSV salvo em:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)

    def _copy_table(self) -> None:
        if not self._cca_result:
            return
        min_co = max(1, int(self._min_co_var.get() or 1))
        lines = ["Conceito A\tConceito B\tCo-ocorrências"]
        for e in self._cca_result.edges:
            if e.weight >= min_co:
                lines.append(f"{e.source}\t{e.target}\t{e.weight}")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._cca_status.configure(text="Tabela copiada para a área de transferência.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append_vocab_debug(self, message: str) -> None:
        """Escreve rastreio de carregamento do vocabulário em arquivo local."""
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"{stamp} | {message}\n"
            self._vocab_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._vocab_debug_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
            with self._vocab_debug_log_path_project.open("a", encoding="utf-8") as handle_project:
                handle_project.write(line)
        except Exception:
            pass

    def _safe_after(self, callback) -> None:
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except Exception:
            pass
