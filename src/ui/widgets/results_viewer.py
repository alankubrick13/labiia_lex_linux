"""
Widget para exibir resultados de analises.
"""
import customtkinter as ctk
from pathlib import Path
from typing import Optional, Dict, Any, Union, List, Tuple, Callable
from PIL import Image
try:
    from PIL import ImageColor
except Exception:  # pragma: no cover - Pillow without ImageColor is unlikely
    ImageColor = None  # type: ignore[assignment]
import numpy as np
import csv
import shutil
import zipfile
import webbrowser
import logging
import tkinter as tk
import unicodedata
from tkinter import colorchooser
from tkinter import messagebox
from tkinter import ttk

from ..styles import FONTS, COLORS, get_themed_color, get_current_colors
from ..theme_bridge import apply_ttk_windows_styles
from ..component_factory import style_button
from ..result_contract import ResultViewContract

log = logging.getLogger(__name__)

VOYANT_PANEL_ORDER = [
    "termsberry",
    "trends",
    "document_terms",
    "bubblelines",
    "cooccurrences",
]
VOYANT_LABEL_BY_PANEL = {
    "termsberry": "TermsBerry",
    "trends": "Tendências",
    "document_terms": "Termos do documento",
    "bubblelines": "Gráfico de bolhas",
    "cooccurrences": "Co-ocorrências",
}

# Tentar importar tkinterweb para HTML embutido
try:
    from tkinterweb import HtmlFrame
    TKINTERWEB_AVAILABLE = True
except ImportError:
    TKINTERWEB_AVAILABLE = False
    log.warning("tkinterweb não disponível - visualização HTML embutida desabilitada")


class ResultsViewer(ctk.CTkFrame):
    """
    Widget para exibir resultados de analises.
    
    Suporta:
    - Imagens (PNG, JPG, SVG renderizado)
    - Tabelas de dados
    - Texto (relatorios, estatisticas)
    """
    
    def __init__(self, parent, **kwargs):
        self._ui_v2_enabled = bool(kwargs.pop("ui_v2_enabled", False))
        raw_scope = kwargs.pop("ui_v2_scope", [])
        if isinstance(raw_scope, (list, tuple, set)):
            self._ui_v2_scope = {str(item).strip().lower() for item in raw_scope}
        elif isinstance(raw_scope, str):
            self._ui_v2_scope = {item.strip().lower() for item in raw_scope.split(",") if item.strip()}
        else:
            self._ui_v2_scope = set()
        self._ui_density = str(kwargs.pop("ui_density", "comfortable") or "comfortable").strip().lower()
        if self._ui_density not in {"compact", "comfortable"}:
            self._ui_density = "comfortable"
        self._ui_v2_results = self._ui_v2_enabled and ("results" in self._ui_v2_scope)
        super().__init__(parent, **kwargs)
        
        self._current_image = None
        self._current_image_source: Optional[Image.Image] = None
        self._current_image_base_source: Optional[Image.Image] = None
        self._current_image_path: Optional[Path] = None
        self._active_image_color_key: Optional[str] = None
        self._image_color_profiles: Dict[str, Dict[str, Any]] = {}
        self._color_overrides: Dict[str, str] = {}
        self._color_tolerance: int = 34
        self._dominant_palette: List[str] = []
        self._color_editor_window: Optional[ctk.CTkToplevel] = None
        self._color_editor_palette_frame: Optional[ctk.CTkScrollableFrame] = None
        self._color_editor_tolerance_label: Optional[ctk.CTkLabel] = None
        self._color_editor_tolerance_var: Optional[ctk.IntVar] = None
        self._color_editor_preset_var: Optional[ctk.StringVar] = None
        self._image_gallery: Dict[str, Path] = {}
        self._active_image_label: Optional[str] = None
        self._updating_image_gallery_selector = False
        self._image_gallery_tab_buttons: Dict[str, ctk.CTkButton] = {}
        self._is_voyant_graph_gallery = False
        self._updating_voyant_graph_tabs = False
        self._voyant_graph_tabs: Dict[str, str] = {}
        self._current_voyant_payload: Dict[str, Any] = {}
        self._current_table_path: Optional[Path] = None
        self._current_table_treeview: Optional[ttk.Treeview] = None
        self._table_tree_style_name: str = "Lexi.DataGrid.Treeview"
        self._table_gallery: Dict[str, Path] = {}
        self._active_table_label: Optional[str] = None
        self._updating_table_gallery_selector = False
        self._has_table_content: bool = False
        self._current_text: str = ""
        self._current_data_export_path: Optional[Path] = None
        self._current_data_export_sources: List[Path] = []
        self._current_stats_dict: Optional[Dict[str, Any]] = None
        self._current_chd_profiles: Optional[Dict[int, Any]] = None
        self._current_chd_class_sizes: Optional[Dict[int, int]] = None
        self._current_chd_afc_path: Optional[Path] = None
        self._current_chd_metadata_path: Optional[Path] = None
        self._current_chd_colored_path: Optional[Path] = None
        self._current_chd_class_texts: Dict[int, Path] = {}
        self._current_chd_typical_segments: Dict[int, List[Any]] = {}
        self._current_chd_antiprofiles: Dict[int, List[Any]] = {}
        self._current_chd_repeated_segments: Dict[int, List[Any]] = {}
        self._current_report_path: Optional[Path] = None
        self._html_frame: Optional[Any] = None
        self._html_frame_container: Optional[tk.Frame] = None
        self._report_text_fallback: Optional[ctk.CTkTextbox] = None
        self._analysis_tabs: Dict[str, Dict[str, Any]] = {}
        self._analysis_tab_order: List[str] = []
        self._active_analysis_tab_key: Optional[str] = None
        self._restoring_analysis_tab = False
        self._loading_content = False  # Previne clear() durante carregamento
        self._pending_analysis_tab_key: Optional[str] = None
        self._default_zoom_levels: Dict[str, int] = {
            "Gráfico": 70,
            "Zipf": 70,
            "Distribuição de Zipf": 70,
            "Dendrograma": 70,
            "AFC": 70,
            "AFC 2D": 70,
            "CHD": 70,
            "Nuvem": 70,
            "Similitude": 70,
            "SIMILARITY": 70,
            "BIGRAM_NETWORK_EXTRA": 70,
            "Bigrama": 70,
            "Rede de Bigramas": 70,
            "TRIGRAM_NETWORK_EXTRA": 60,
            "Trigrama": 60,
            "Rede de Trigramas": 60,
            "YAKE": 60,
            "Palavras-Chave (YAKE)": 60,
            "Ranking de Palavras-Chave": 60,
            "Ranking": 60,
            "SENTIMENT_EXTRA": 70,
            "Sentimento": 70,
            "Análise de Sentimentos": 70,
            "Estatísticas": 100,
            "Tabela": 100,
        }
        self._zoom_levels: Dict[str, int] = dict(self._default_zoom_levels)
        self._zoom_min = 30
        self._zoom_fit_min = 50
        self._zoom_max = 300
        self._pending_image_autofit = False
        self._pending_image_autofit_attempts = 0
        self._pending_image_autofit_job: Optional[str] = None
        self._pending_graph_finalize_job: Optional[str] = None
        self._last_render_source_id: Optional[int] = None
        self._last_render_size: Optional[Tuple[int, int]] = None
        self._last_render_display_size: Optional[Tuple[int, int]] = None
        self._similarity_halo_callback: Optional[Callable[[bool], None]] = None
        self._suspend_similarity_halo_callback = False
        self._on_analysis_tab_click_callback: Optional[Callable[[str], None]] = None
        self._create_widgets()
        self.set_analysis_tab("Início", key="inicio", closable=False)

    def _configure_v2_ttk_styles(self) -> None:
        """Configura estilos ttk para grid da aba Tabela no modo UI v2."""
        style = ttk.Style(self)
        apply_ttk_windows_styles(
            style,
            colors=get_current_colors(),
            fonts=FONTS,
            density=("compact" if self._ui_density == "compact" else "comfortable"),
        )

    def _style_action_button(self, button: ctk.CTkButton, *, primary: bool = False) -> None:
        """Aplica estilo consistente em botões de ação do ResultsViewer."""
        if not self._ui_v2_results:
            return
        style_button(button, variant=("primary" if primary else "secondary"), size="md")

    def _render_table_v2_treeview(self, rows: List[List[str]]) -> None:
        """Renderiza tabela via ttk.Treeview quando UI v2/results estiver habilitado."""
        self._configure_v2_ttk_styles()
        self._current_table_treeview = None
        if not rows:
            self.table_placeholder = ctk.CTkLabel(
                self.table_frame,
                text="Tabela vazia.",
                font=FONTS["body"],
            )
            self.table_placeholder.pack(expand=True)
            return

        header = [str(cell or "").strip() for cell in rows[0]]
        n_cols = len(header)
        if n_cols == 0:
            self.table_placeholder = ctk.CTkLabel(
                self.table_frame,
                text="Tabela sem colunas.",
                font=FONTS["body"],
            )
            self.table_placeholder.pack(expand=True)
            return
        columns = [f"c{i}" for i in range(n_cols)]

        host = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        host.pack(fill="both", expand=True, padx=2, pady=2)
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(
            host,
            columns=columns,
            show="headings",
            style=self._table_tree_style_name,
            selectmode="browse",
        )
        self._current_table_treeview = tree

        for col_id, title in zip(columns, header):
            title_text = title if title else "-"
            tree.heading(
                col_id,
                text=title_text,
                command=lambda c=col_id: self._sort_treeview_column(tree, c, False),
            )
            tree.column(col_id, width=160, minwidth=80, anchor="w", stretch=True)

        max_rows = 500
        for row in rows[1 : max_rows + 1]:
            normalized = [str(cell or "") for cell in row]
            if len(normalized) < n_cols:
                normalized.extend([""] * (n_cols - len(normalized)))
            tree.insert("", "end", values=normalized[:n_cols])

        y_scroll = ttk.Scrollbar(host, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(host, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        overflow = len(rows) - 1 - max_rows
        if overflow > 0:
            ctk.CTkLabel(
                self.table_frame,
                text=f"... (+{overflow} linhas)",
                font=FONTS["small"],
                text_color=COLORS.get("text_secondary", "#888888"),
            ).pack(anchor="w", padx=4, pady=(6, 0))

    def _sort_treeview_column(self, tree: ttk.Treeview, col_id: str, reverse: bool) -> None:
        """Ordena coluna do Treeview (numérico quando possível)."""
        try:
            rows = [(tree.set(item, col_id), item) for item in tree.get_children("")]
        except Exception:
            return

        def _coerce(value: Any) -> Any:
            raw = str(value or "").strip()
            if not raw:
                return (1, "")
            numeric = raw.replace(".", "", 1).replace(",", "", 1)
            if numeric.isdigit():
                try:
                    return (0, float(raw.replace(",", ".")))
                except Exception:
                    return (0, raw.lower())
            return (0, raw.lower())

        rows.sort(key=lambda row: _coerce(row[0]), reverse=bool(reverse))
        for index, (_value, item) in enumerate(rows):
            tree.move(item, "", index)

        try:
            tree.heading(
                col_id,
                command=lambda: self._sort_treeview_column(tree, col_id, not reverse),
            )
        except Exception:
            pass

    def _apply_table_tree_zoom(self, scale: float) -> None:
        """Ajusta altura de linhas no Treeview conforme zoom da aba Tabela."""
        if self._current_table_treeview is None:
            return
        style = ttk.Style(self)
        base = 28 if self._ui_density == "compact" else 36
        rowheight = max(20, int(round(base * scale)))
        style.configure(
            self._table_tree_style_name,
            rowheight=rowheight,
            font=self._scaled_font(FONTS.get("small", ("Segoe UI", 10)), int(scale * 100)),
        )
        style.configure(
            f"{self._table_tree_style_name}.Heading",
            font=self._scaled_font(FONTS.get("small", ("Segoe UI", 10)), int(scale * 100)),
        )
    
    def _create_widgets(self):
        """Cria widgets internos."""
        self.analysis_tabs_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.analysis_tabs_frame.pack(fill="x", padx=8, pady=(2, 0))

        # Titulo removido para economizar espaco vertical
        # self.title_label = ctk.CTkLabel(...)
        # self.title_label.pack(pady=10)

        self.zoom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.zoom_frame.pack(fill="x", padx=8, pady=(0, 1))
        self.btn_zoom_out = ctk.CTkButton(
            self.zoom_frame,
            text="-",
            width=34,
            height=28,
            command=lambda: self._adjust_zoom(-10),
        )
        self._style_action_button(self.btn_zoom_out)
        self.btn_zoom_out.pack(side="left", padx=(0, 6))
        self.zoom_label = ctk.CTkLabel(
            self.zoom_frame,
            text="100%",
            font=FONTS["body"],
            width=52,
        )
        self.zoom_label.pack(side="left", padx=(0, 6))
        self.btn_zoom_in = ctk.CTkButton(
            self.zoom_frame,
            text="+",
            width=34,
            height=28,
            command=lambda: self._adjust_zoom(+10),
        )
        self._style_action_button(self.btn_zoom_in)
        self.btn_zoom_in.pack(side="left", padx=(0, 10))
        self.btn_zoom_reset = ctk.CTkButton(
            self.zoom_frame,
            text="1:1",
            width=56,
            height=28,
            command=self._set_zoom_one_to_one,
        )
        self._style_action_button(self.btn_zoom_reset)
        self.btn_zoom_reset.pack(side="left", padx=(0, 6))
        self.btn_zoom_fit = ctk.CTkButton(
            self.zoom_frame,
            text="Ajustar",
            width=72,
            height=28,
            command=self._fit_current_view,
        )
        self._style_action_button(self.btn_zoom_fit)
        self.btn_zoom_fit.pack(side="left")
        self.btn_graph_colors = ctk.CTkButton(
            self.zoom_frame,
            text="Cores",
            width=72,
            height=28,
            command=self._open_color_editor,
            state="disabled",
        )
        self._style_action_button(self.btn_graph_colors)
        self.btn_graph_colors.pack(side="left", padx=(8, 0))
        self.similarity_halo_var = ctk.BooleanVar(value=False)
        self.similarity_halo_toggle = ctk.CTkCheckBox(
            self.zoom_frame,
            text="Halos",
            variable=self.similarity_halo_var,
            command=self._on_similarity_halo_toggle,
        )
        self.similarity_halo_toggle.pack(side="left", padx=(14, 0))
        self.similarity_halo_toggle.pack_forget()
        
        # Notebook para diferentes tipos de visualizacao
        self.tabview = ctk.CTkTabview(self, fg_color=get_themed_color("surface"))
        self.tabview.pack(fill="both", expand=True, padx=6, pady=(4, 4))
        self.update_idletasks()
        self._apply_content_tab_theme()
        
        # Tab de imagem
        self.tab_image = self.tabview.add("Gráfico")
        # CTkFrame tem height=200 default e NAO propaga shrink para 0 quando
        # os filhos estao com pack_forget (causa 250px de espaço morto acima
        # da imagem). Forcamos height=0 inicial; pack_propagate(True) garante
        # que o frame cresça apenas quando gallery/voyant forem realmente
        # exibidos e volte a 0 quando pack_forget'd.
        self.image_controls_frame = ctk.CTkFrame(
            self.tab_image, fg_color="transparent", height=0,
        )
        self.image_controls_frame.pack(fill="x", padx=2, pady=(2, 0))
        try:
            self.image_controls_frame.pack_propagate(True)
        except Exception:
            pass
        self.image_gallery_frame = ctk.CTkFrame(self.image_controls_frame, fg_color="transparent")
        self.image_gallery_label = ctk.CTkLabel(
            self.image_gallery_frame,
            text="Visualizações:",
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
        )
        self.image_gallery_label.pack(side="left", padx=(4, 8), pady=(4, 0))
        self.image_gallery_tabs_frame = ctk.CTkFrame(
            self.image_gallery_frame,
            fg_color="transparent",
        )
        self.image_gallery_tabs_frame.pack(side="left", fill="x", expand=True, pady=(2, 0))
        self.image_gallery_frame.pack_forget()

        self.voyant_graph_tabview = ctk.CTkTabview(self.image_controls_frame, height=56)
        self.voyant_graph_tabview.pack_forget()
        try:
            self.voyant_graph_tabview.configure(command=self._on_voyant_graph_tab_changed)
        except Exception:
            pass
        self._apply_tabview_selected_text_theme(self.voyant_graph_tabview)

        image_bg = "#FFFFFF"
        self.image_canvas_container = tk.Frame(self.tab_image, bg=image_bg)
        self.image_canvas_container.pack(fill="both", expand=True, padx=2, pady=2)
        self.image_canvas_container.grid_rowconfigure(0, weight=1)
        self.image_canvas_container.grid_columnconfigure(0, weight=1)

        self.image_canvas = tk.Canvas(
            self.image_canvas_container,
            bg=image_bg,
            highlightthickness=0,
            borderwidth=0,
        )
        self.image_scroll_y = ctk.CTkScrollbar(
            self.image_canvas_container,
            orientation="vertical",
            command=self.image_canvas.yview,
        )
        self.image_scroll_x = ctk.CTkScrollbar(
            self.image_canvas_container,
            orientation="horizontal",
            command=self.image_canvas.xview,
        )
        self.image_canvas.configure(
            yscrollcommand=self.image_scroll_y.set,
            xscrollcommand=self.image_scroll_x.set,
        )
        self.image_canvas.grid(row=0, column=0, sticky="nsew")
        self.image_scroll_y.grid(row=0, column=1, sticky="ns")
        self.image_scroll_x.grid(row=1, column=0, sticky="ew")
        self.image_scroll_y.grid_remove()
        self.image_scroll_x.grid_remove()

        self.image_inner = tk.Frame(self.image_canvas, bg=image_bg)
        self._image_canvas_window = self.image_canvas.create_window(
            (0, 0),
            window=self.image_inner,
            anchor="nw",
        )
        self.image_inner.bind("<Configure>", self._on_image_inner_configure)
        self.image_canvas.bind("<Configure>", self._on_image_canvas_configure)

        self.image_label = ctk.CTkLabel(
            self.image_inner,
            text="Nenhum gráfico para exibir.\n\nExecute uma análise para ver os resultados.",
            font=FONTS['body'],
            text_color=get_themed_color('text'),
            fg_color="transparent",
            anchor="nw",  # Ancora imagem no canto superior esquerdo (evita espaço morto)
        )
        # place() em (0,0) — label fica no tamanho pedido (= tamanho da imagem)
        # no canto superior-esquerdo, sem expandir/centralizar. Isso impede
        # que o label cresça junto com image_inner (quando reqsize > imagem
        # em HiDPI/DPI-scaling) e o CTkLabel interno recentre a imagem.
        self.image_label.place(x=0, y=0)
        
        # Tab de texto (estatisticas)
        self.tab_text = self.tabview.add("Estatísticas")
        self.text_box = ctk.CTkTextbox(
            self.tab_text,
            font=FONTS['mono'],
            wrap="word"
        )
        self.text_box.pack(fill="both", expand=True, padx=3, pady=3)
        self.text_box.insert("1.0", "Nenhuma estatística disponível.\n\nImporte um corpus e execute uma análise.")
        self.text_box.configure(state="disabled")
        
        # Tab de tabela
        self.tab_table = self.tabview.add("Tabela")
        # Mesmo problema do image_controls_frame: CTkFrame default height=200
        # mantem 200px mesmo com gallery_frame pack_forget'd. height=0 +
        # pack_propagate(True) elimina o teto morto acima da tabela.
        self.table_controls_frame = ctk.CTkFrame(
            self.tab_table, fg_color="transparent", height=0,
        )
        self.table_controls_frame.pack(fill="x", padx=2, pady=(2, 0))
        try:
            self.table_controls_frame.pack_propagate(True)
        except Exception:
            pass
        self.table_gallery_frame = ctk.CTkFrame(self.table_controls_frame, fg_color="transparent")
        self.table_gallery_label = ctk.CTkLabel(
            self.table_gallery_frame,
            text="Tabelas:",
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
        )
        self.table_gallery_label.pack(side="left", padx=(4, 8), pady=(4, 0))
        self.table_gallery_selector = ctk.CTkSegmentedButton(
            self.table_gallery_frame,
            values=["Tabela"],
            font=FONTS["heading"],
            command=self._on_table_gallery_selected,
        )
        try:
            self.table_gallery_selector.configure(
                selected_color=get_themed_color("primary"),
                selected_hover_color=get_themed_color("primary_hover"),
                unselected_color=get_themed_color("button"),
                unselected_hover_color=get_themed_color("button_hover"),
            )
        except Exception:
            pass
        self.table_gallery_selector.pack(side="left", fill="x", expand=True, pady=(2, 0))
        self.table_gallery_frame.pack_forget()

        self.table_frame = ctk.CTkScrollableFrame(self.tab_table)
        self.table_frame.pack(fill="both", expand=True, padx=3, pady=3)
        self.table_placeholder = ctk.CTkLabel(
            self.table_frame,
            text="Nenhuma tabela para exibir.",
            font=FONTS['body'],
            text_color=get_themed_color('text'),
            fg_color="transparent",
        )
        self.table_placeholder.pack(fill="both", expand=True)
        
        try:
            # Preserve CTkTabview internal callback chain; do not override segmented button directly.
            self.tabview.configure(command=self._on_content_tab_changed)
        except Exception:
            pass
        # Garantir que a tab inicial esteja ativa
        try:
            self.tabview.set("Gráfico")
        except Exception:
            pass
        self._update_zoom_label()
        self.update_idletasks()
        self._refresh_content_tab_text_colors()
        
        # Botoes de acao
        self.btn_frame = ctk.CTkFrame(self)
        self.btn_frame.pack(fill="x", padx=8, pady=(3, 4))
        
        self.btn_export = ctk.CTkButton(
            self.btn_frame,
            text="Exportar",
            width=100,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            command=self._export_result,
            state="disabled"
        )
        self._style_action_button(self.btn_export)
        self.btn_export.pack(side="right", padx=5)

        self.btn_report = ctk.CTkButton(
            self.btn_frame,
            text="Ver Relatório",
            width=130,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            command=self._open_report,
            state="disabled",
        )
        self._style_action_button(self.btn_report)
        self.btn_report.pack(side="right", padx=5)

        self.btn_export_data = ctk.CTkButton(
            self.btn_frame,
            text="Exportar Dados",
            width=130,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            command=self._export_data_source,
            state="disabled",
        )
        self._style_action_button(self.btn_export_data)
        self.btn_export_data.pack(side="right", padx=5)

    def _on_similarity_halo_toggle(self) -> None:
        """Encaminha alternância do toggle de halos para callback externo."""
        if self._suspend_similarity_halo_callback:
            return
        callback = self._similarity_halo_callback
        if callback is None:
            return
        try:
            callback(bool(self.similarity_halo_var.get()))
        except Exception:
            log.exception("Falha ao processar toggle de halos da similitude")

    def configure_similarity_halo_toggle(
        self,
        *,
        visible: bool,
        enabled: bool = True,
        value: bool = False,
        callback: Optional[Callable[[bool], None]] = None,
    ) -> None:
        """Configura botão de halos (visível apenas em resultados de similitude)."""
        self._similarity_halo_callback = callback
        self._suspend_similarity_halo_callback = True
        try:
            self.similarity_halo_var.set(bool(value))
        finally:
            self._suspend_similarity_halo_callback = False

        if visible:
            if not self.similarity_halo_toggle.winfo_manager():
                self.similarity_halo_toggle.pack(side="left", padx=(14, 0))
            self.similarity_halo_toggle.configure(state="normal" if enabled else "disabled")
        else:
            if self.similarity_halo_toggle.winfo_manager():
                self.similarity_halo_toggle.pack_forget()

    def set_analysis_tab_click_callback(
        self,
        callback: Optional[Callable[[str], None]],
    ) -> None:
        """Registra callback chamado quando o usuário clica em uma aba de análise.

        O callback recebe a chave interna da aba (ex: 'history_<id>').
        Se o callback disparar a renderização, a restauração do snapshot local
        é suprimida. Caso contrário (callback=None ou não registrado), o
        comportamento padrão de restauração de snapshot é mantido.
        """
        self._on_analysis_tab_click_callback = callback

    def _on_tab_button_pressed(self, tab_key: str) -> None:
        """Despachante de clique em botão de aba.

        Tenta primeiro o callback externo (registrado pelo MainWindow).
        Se nenhum callback externo estiver configurado, cai no
        comportamento padrão de restauração de snapshot local.
        """
        cb = self._on_analysis_tab_click_callback
        if cb is not None:
            try:
                cb(tab_key)
                return
            except Exception:
                log.exception(
                    "Falha no callback externo de clique de aba '%s'; usando fallback local.",
                    tab_key,
                )
        # Fallback: restauração de snapshot local (comportamento anterior)
        self._activate_analysis_tab(tab_key)

    def _make_analysis_tab_key(self, label: str) -> str:
        """Gera chave estável para aba de análise."""
        clean = "".join(
            char.lower() if char.isalnum() else "_"
            for char in str(label or "").strip()
        )
        while "__" in clean:
            clean = clean.replace("__", "_")
        clean = clean.strip("_")
        return clean or "analise"

    def _new_tab_snapshot(self, label: str, closable: bool) -> Dict[str, Any]:
        """Cria estrutura de estado para uma aba."""
        return {
            "label": str(label or "Análise"),
            "closable": bool(closable),
            "status": "ready",
            "error_message": "",
            "image_path": None,
            "image_gallery": {},
            "active_image_label": None,
            "image_color_overrides": {},
            "image_color_tolerance": 34,
            "is_voyant_graph_gallery": False,
            "voyant_payload": {},
            "table_path": None,
            "table_gallery": {},
            "active_table_label": None,
            "text": "",
            "stats_dict": None,
            "chd_profiles": None,
            "chd_class_sizes": None,
            "chd_afc_path": None,
            "chd_metadata_path": None,
            "chd_colored_path": None,
            "chd_class_texts": {},
            "chd_typical_segments": {},
            "chd_antiprofiles": {},
            "chd_repeated_segments": {},
            "report_path": None,
            "data_export_path": None,
            "data_export_paths": [],
            "active_content_tab": "Gráfico",
            "zoom_levels": dict(self._default_zoom_levels),
            "has_table_content": False,
        }

    def has_analysis_tab(self, key: str) -> bool:
        """Retorna True quando a aba de análise já existe."""
        return str(key or "") in self._analysis_tabs

    def focus_analysis_tab(self, key: str) -> None:
        """Ativa aba existente sem recriá-la."""
        tab_key = str(key or "")
        if tab_key in self._analysis_tabs:
            self._activate_analysis_tab(tab_key)

    def create_pending_analysis_tab(self, key: str, label: str) -> None:
        """Cria ou reutiliza uma aba em estado de execução."""
        tab_key = self.set_analysis_tab(label, key=key, closable=True)
        snapshot = self._analysis_tabs.get(tab_key)
        if isinstance(snapshot, dict):
            snapshot["status"] = "pending"
            snapshot["error_message"] = ""
            snapshot["label"] = str(label or snapshot.get("label", "Análise"))
        self._render_analysis_tab_header()

    def finalize_analysis_tab(self, key: str, label: Optional[str] = None) -> None:
        """Marca aba como concluída e atualiza rótulo final."""
        tab_key = str(key or "")
        snapshot = self._analysis_tabs.get(tab_key)
        if not isinstance(snapshot, dict):
            return
        snapshot["status"] = "ready"
        snapshot["error_message"] = ""
        if label:
            snapshot["label"] = str(label)
        self._render_analysis_tab_header()
        self._activate_analysis_tab(tab_key)

    def mark_analysis_tab_error(self, key: str, message: Optional[str] = None) -> None:
        """Marca aba como erro sem removê-la."""
        tab_key = str(key or "")
        snapshot = self._analysis_tabs.get(tab_key)
        if not isinstance(snapshot, dict):
            return
        snapshot["status"] = "error"
        snapshot["error_message"] = str(message or "").strip()
        self._render_analysis_tab_header()

    def rekey_analysis_tab(self, old_key: str, new_key: str, label: Optional[str] = None) -> None:
        """Troca a chave interna de uma aba preservando snapshot e ordem."""
        old = str(old_key or "")
        new = str(new_key or "")
        if not old or not new or old == new or old not in self._analysis_tabs:
            if new and label and new in self._analysis_tabs:
                self._analysis_tabs[new]["label"] = str(label)
                self._render_analysis_tab_header()
            return
        snapshot = self._analysis_tabs.pop(old)
        if label:
            snapshot["label"] = str(label)
        self._analysis_tabs[new] = snapshot
        self._analysis_tab_order = [new if key == old else key for key in self._analysis_tab_order]
        if self._active_analysis_tab_key == old:
            self._active_analysis_tab_key = new
        if self._pending_analysis_tab_key == old:
            self._pending_analysis_tab_key = new
        self._render_analysis_tab_header()

    def list_analysis_tabs(self) -> List[Dict[str, Any]]:
        """Lista abas abertas em ordem de renderização."""
        listed: List[Dict[str, Any]] = []
        for tab_key in self._analysis_tab_order:
            snapshot = self._analysis_tabs.get(tab_key, {})
            listed.append(
                {
                    "key": tab_key,
                    "label": str(snapshot.get("label", tab_key)),
                    "status": str(snapshot.get("status", "ready") or "ready"),
                    "closable": bool(snapshot.get("closable", True)),
                    "is_active": tab_key == self._active_analysis_tab_key,
                }
            )
        return listed

    def set_analysis_tab(
        self,
        label: str,
        key: Optional[str] = None,
        closable: bool = True,
    ) -> str:
        """
        Cria/ativa aba de análise no topo do visualizador.

        Returns:
            Chave interna da aba ativa.
        """
        tab_key = str(key or self._make_analysis_tab_key(label))
        if tab_key not in self._analysis_tabs:
            self._analysis_tabs[tab_key] = self._new_tab_snapshot(label=label, closable=closable)
            self._analysis_tab_order.append(tab_key)
        else:
            self._analysis_tabs[tab_key]["label"] = str(label or self._analysis_tabs[tab_key]["label"])
            if not self._analysis_tabs[tab_key].get("closable", True):
                self._analysis_tabs[tab_key]["closable"] = False
            else:
                self._analysis_tabs[tab_key]["closable"] = bool(closable)

        self._activate_analysis_tab(tab_key)
        return tab_key

    def reset_analysis_tabs(self) -> None:
        """Reseta abas de análise e volta para a aba inicial."""
        self._analysis_tabs = {}
        self._analysis_tab_order = []
        self._active_analysis_tab_key = None
        self.clear(sync=False)
        self.set_analysis_tab("Início", key="inicio", closable=False)

    def _show_blank_start_state(self) -> None:
        """Força estado visual vazio (sem conteúdo restaurado)."""
        self._active_analysis_tab_key = "inicio"
        if "inicio" not in self._analysis_tabs:
            self._analysis_tabs["inicio"] = self._new_tab_snapshot(
                label="Início",
                closable=False,
            )
            self._analysis_tab_order.insert(0, "inicio")
        self._render_analysis_tab_header()
        self.clear(sync=False, force=True)
        try:
            self.tabview.set("Gráfico")
        except Exception:
            pass
        self._sync_active_tab_state()

    def _activate_analysis_tab(self, tab_key: str) -> None:
        """Ativa aba e restaura estado visual correspondente."""
        if tab_key not in self._analysis_tabs:
            return
        
        # Se estamos carregando conteúdo, agenda restauração para o fim do ciclo.
        if self._loading_content:
            self._pending_analysis_tab_key = tab_key
            log.debug(
                "Ativacao de aba adiada (loading ativo): requested=%s active=%s pending=%s",
                tab_key,
                self._active_analysis_tab_key,
                self._pending_analysis_tab_key,
            )
            # Nao trocamos aba ativa aqui para evitar sobrescrever snapshot da aba clicada.
            self.after(80, self._flush_pending_analysis_tab_activation)
            return
        
        if self._active_analysis_tab_key is not None and self._active_analysis_tab_key != tab_key:
            self._sync_active_tab_state()
        
        self._active_analysis_tab_key = tab_key
        self._render_analysis_tab_header()
        
        # Verificar se o snapshot tem conteúdo real antes de restaurar
        snapshot = self._analysis_tabs.get(tab_key, {})
        has_content = (
            snapshot.get("image_path") or
            snapshot.get("image_gallery") or
            snapshot.get("chd_profiles") or
            snapshot.get("table_path") or
            snapshot.get("table_gallery") or
            snapshot.get("stats_dict") or
            (snapshot.get("text") or "").strip()
        )
        if has_content:
            self._restore_active_tab_state()
        elif tab_key == "inicio":
            self._show_blank_start_state()
        else:
            # Evita "vazamento" do último conteúdo para abas ainda não hidratadas.
            self.clear(sync=False, force=True)
            try:
                self.tabview.set("Gráfico")
            except Exception:
                pass
            self._sync_active_tab_state()

    def _flush_pending_analysis_tab_activation(self) -> None:
        """Conclui troca de aba adiada quando não há carregamento ativo."""
        pending_key = self._pending_analysis_tab_key
        if not pending_key:
            return
        if self._loading_content:
            self.after(80, self._flush_pending_analysis_tab_activation)
            return
        self._pending_analysis_tab_key = None
        if pending_key in self._analysis_tabs:
            log.debug(
                "Aplicando ativacao pendente de aba: pending=%s active=%s loading=%s",
                pending_key,
                self._active_analysis_tab_key,
                self._loading_content,
            )
            self._activate_analysis_tab(pending_key)

    def _close_analysis_tab(self, tab_key: str) -> None:
        """Fecha aba de análise e remove estado salvo."""
        if tab_key not in self._analysis_tabs:
            return
        if not self._analysis_tabs[tab_key].get("closable", True):
            return

        was_active = tab_key == self._active_analysis_tab_key
        self._analysis_tabs.pop(tab_key, None)
        self._analysis_tab_order = [key for key in self._analysis_tab_order if key != tab_key]
        has_closable_tabs = any(
            key in self._analysis_tabs and bool(self._analysis_tabs[key].get("closable", True))
            for key in self._analysis_tab_order
        )
        if not self._analysis_tab_order or not has_closable_tabs:
            self._analysis_tabs = {}
            self._analysis_tab_order = []
            self._show_blank_start_state()
            return

        if was_active:
            self._show_blank_start_state()
        else:
            self._render_analysis_tab_header()

    def _render_analysis_tab_header(self) -> None:
        """Renderiza botões de abas no topo."""
        for widget in self.analysis_tabs_frame.winfo_children():
            widget.destroy()

        for tab_key in self._analysis_tab_order:
            snapshot = self._analysis_tabs.get(tab_key, {})
            label = str(snapshot.get("label", tab_key))
            status = str(snapshot.get("status", "ready") or "ready")
            if status == "pending":
                label = f"● {label}"
            elif status == "error":
                label = f"! {label}"
            closable = bool(snapshot.get("closable", True))
            is_active = tab_key == self._active_analysis_tab_key
            active_fg = get_themed_color("surface")
            inactive_fg = get_themed_color("button")
            active_border = get_themed_color("primary")
            inactive_border = get_themed_color("border")
            text_color = get_themed_color("text")
            if status == "pending":
                active_border = get_themed_color("warning")
                inactive_border = get_themed_color("warning")
            elif status == "error":
                active_border = get_themed_color("danger")
                inactive_border = get_themed_color("danger")

    def _close_analysis_tab(self, tab_key: str) -> None:
        """Fecha aba de análise e remove estado salvo."""
        if tab_key not in self._analysis_tabs:
            return
        if not self._analysis_tabs[tab_key].get("closable", True):
            return

        was_active = tab_key == self._active_analysis_tab_key
        self._analysis_tabs.pop(tab_key, None)
        self._analysis_tab_order = [key for key in self._analysis_tab_order if key != tab_key]
        has_closable_tabs = any(
            key in self._analysis_tabs and bool(self._analysis_tabs[key].get("closable", True))
            for key in self._analysis_tab_order
        )
        if not self._analysis_tab_order or not has_closable_tabs:
            self._analysis_tabs = {}
            self._analysis_tab_order = []
            self._show_blank_start_state()
            return

        if was_active:
            self._show_blank_start_state()
        else:
            self._render_analysis_tab_header()

    def _render_analysis_tab_header(self) -> None:
        """Renderiza botões de abas no topo."""
        for widget in self.analysis_tabs_frame.winfo_children():
            widget.destroy()

        for tab_key in self._analysis_tab_order:
            snapshot = self._analysis_tabs.get(tab_key, {})
            label = str(snapshot.get("label", tab_key))
            closable = bool(snapshot.get("closable", True))
            is_active = tab_key == self._active_analysis_tab_key
            active_fg = get_themed_color("surface")
            inactive_fg = get_themed_color("button")
            active_border = get_themed_color("primary")
            inactive_border = get_themed_color("border")
            text_color = get_themed_color("text")

            tab_item = ctk.CTkFrame(self.analysis_tabs_frame, fg_color="transparent")
            tab_item.pack(side="left", padx=(0, 1))

            tab_button = ctk.CTkButton(
                tab_item,
                text=label,
                width=max(64, len(label) * 6 + 14),
                height=28,
                fg_color=active_fg if is_active else inactive_fg,
                hover_color=active_fg if is_active else COLORS["button_hover"],
                text_color=text_color,
                border_width=1,
                border_color=active_border if is_active else inactive_border,
                corner_radius=0,
                command=lambda key=tab_key: self._on_tab_button_pressed(key),
            )
            if self._ui_v2_results:
                try:
                    style_button(tab_button, variant=("primary" if is_active else "secondary"), size="md")
                except Exception:
                    log.exception("Falha ao aplicar estilo visual da aba '%s'.", label)
                tab_button.configure(height=30)
            tab_button.pack(side="left")

            if closable:
                close_button = ctk.CTkButton(
                    tab_item,
                    text="x",
                    width=18,
                    height=28,
                    fg_color=active_fg if is_active else inactive_fg,
                    hover_color=get_themed_color("button_hover") if not is_active else active_fg,
                    text_color=get_themed_color("danger"),
                    border_width=1,
                    border_color=active_border if is_active else inactive_border,
                    corner_radius=0,
                    command=lambda key=tab_key: self._close_analysis_tab(key),
                )
                if self._ui_v2_results:
                    try:
                        style_button(close_button, variant="ghost", size="md")
                    except Exception:
                        log.exception("Falha ao aplicar estilo do botao de fechar da aba '%s'.", label)
                    close_button.configure(width=18, height=30)
                close_button.pack(side="left", padx=(0, 0))

    def _sync_active_tab_state(self) -> None:
        """Sincroniza estado visual atual para a aba ativa."""
        if self._restoring_analysis_tab:
            return
        if not self._active_analysis_tab_key:
            return
        # Evita escrita cruzada de snapshot enquanto troca de aba está pendente durante loading.
        if (
            self._loading_content
            and self._pending_analysis_tab_key
            and self._pending_analysis_tab_key != self._active_analysis_tab_key
        ):
            log.debug(
                "Sync ignorado durante transicao de aba: active=%s pending=%s loading=%s",
                self._active_analysis_tab_key,
                self._pending_analysis_tab_key,
                self._loading_content,
            )
            return
        snapshot = self._analysis_tabs.get(self._active_analysis_tab_key)
        if snapshot is None:
            return
        snapshot["image_path"] = getattr(self, "_current_image_path", None)
        snapshot["image_gallery"] = {
            str(label): str(path)
            for label, path in getattr(self, "_image_gallery", {}).items()
            if path
        }
        snapshot["active_image_label"] = getattr(self, "_active_image_label", None)
        snapshot["image_color_overrides"] = dict(getattr(self, "_color_overrides", {}))
        snapshot["image_color_tolerance"] = int(getattr(self, "_color_tolerance", 34))
        snapshot["is_voyant_graph_gallery"] = bool(getattr(self, "_is_voyant_graph_gallery", False))
        current_voyant_payload = getattr(self, "_current_voyant_payload", {})
        snapshot["voyant_payload"] = dict(current_voyant_payload) if isinstance(current_voyant_payload, dict) else {}
        snapshot["table_path"] = getattr(self, "_current_table_path", None)
        snapshot["table_gallery"] = {
            str(label): str(path)
            for label, path in getattr(self, "_table_gallery", {}).items()
            if path
        }
        snapshot["active_table_label"] = getattr(self, "_active_table_label", None)
        snapshot["text"] = getattr(self, "_current_text", "")
        current_stats_dict = getattr(self, "_current_stats_dict", None)
        snapshot["stats_dict"] = dict(current_stats_dict) if isinstance(current_stats_dict, dict) else None
        snapshot["chd_profiles"] = getattr(self, "_current_chd_profiles", None)
        snapshot["chd_class_sizes"] = getattr(self, "_current_chd_class_sizes", None)
        snapshot["chd_afc_path"] = getattr(self, "_current_chd_afc_path", None)
        snapshot["chd_metadata_path"] = getattr(self, "_current_chd_metadata_path", None)
        snapshot["chd_colored_path"] = getattr(self, "_current_chd_colored_path", None)
        snapshot["chd_class_texts"] = dict(getattr(self, "_current_chd_class_texts", {}))
        snapshot["chd_typical_segments"] = dict(getattr(self, "_current_chd_typical_segments", {}))
        snapshot["chd_antiprofiles"] = dict(getattr(self, "_current_chd_antiprofiles", {}))
        snapshot["chd_repeated_segments"] = dict(getattr(self, "_current_chd_repeated_segments", {}))
        snapshot["report_path"] = getattr(self, "_current_report_path", None)
        snapshot["data_export_path"] = getattr(self, "_current_data_export_path", None)
        snapshot["data_export_paths"] = [
            str(path) for path in getattr(self, "_current_data_export_sources", []) if path
        ]
        snapshot["zoom_levels"] = dict(getattr(self, "_zoom_levels", self._default_zoom_levels))
        snapshot["has_table_content"] = bool(getattr(self, "_has_table_content", False))
        try:
            snapshot["active_content_tab"] = self.tabview.get()
        except Exception:
            snapshot["active_content_tab"] = "Gráfico"

    def _restore_active_tab_state(self) -> None:
        """Restaura UI usando snapshot da aba ativa."""
        if not self._active_analysis_tab_key:
            return
        snapshot = self._analysis_tabs.get(self._active_analysis_tab_key)
        if snapshot is None:
            return

        self._restoring_analysis_tab = True
        self._loading_content = True
        try:
            self.clear(sync=False, force=True)
            self._clear_report()

            chd_profiles = snapshot.get("chd_profiles")
            if chd_profiles:
                from types import SimpleNamespace

                result_proxy = SimpleNamespace(
                    afc_graph_path=None,
                    profile_afc_path=snapshot.get("chd_afc_path"),
                    metadata_profiles_path=snapshot.get("chd_metadata_path"),
                    colored_corpus_path=snapshot.get("chd_colored_path"),
                    class_text_paths=snapshot.get("chd_class_texts", {}),
                    typical_segments=snapshot.get("chd_typical_segments", {}),
                    antiprofiles=snapshot.get("chd_antiprofiles", {}),
                    repeated_segments=snapshot.get("chd_repeated_segments", {}),
                )
                self.show_chd_profiles(
                    chd_profiles,
                    snapshot.get("chd_class_sizes") or {},
                    result=result_proxy,
                )

            stats_payload = snapshot.get("stats_dict")
            if isinstance(stats_payload, dict) and stats_payload:
                self.show_statistics(stats_payload)
            else:
                text_payload = str(snapshot.get("text") or "").strip()
                if text_payload:
                    self.show_text(text_payload, title="")

            restored_voyant = False
            voyant_payload = snapshot.get("voyant_payload", {})
            if isinstance(voyant_payload, dict) and voyant_payload and hasattr(self, "show_voyant_suite"):
                try:
                    self.show_voyant_suite(voyant_payload)
                    restored_voyant = True
                except Exception:
                    log.exception("Falha ao restaurar payload Voyant da aba ativa.")

            if not restored_voyant:
                raw_table_gallery = snapshot.get("table_gallery", {})
                table_gallery: Dict[str, Path] = {}
                if isinstance(raw_table_gallery, dict):
                    for label, raw_path in raw_table_gallery.items():
                        try:
                            candidate = Path(raw_path)
                        except Exception:
                            continue
                        if candidate.exists() and candidate.is_file():
                            table_gallery[str(label)] = candidate
                if table_gallery:
                    self.show_table_gallery(
                        table_gallery,
                        default_label=snapshot.get("active_table_label"),
                    )
                else:
                    table_path = snapshot.get("table_path")
                    if table_path and Path(table_path).exists():
                        self.show_table(table_path)

                raw_gallery = snapshot.get("image_gallery", {})
                gallery: Dict[str, Path] = {}
                if isinstance(raw_gallery, dict):
                    for label, raw_path in raw_gallery.items():
                        try:
                            candidate = Path(raw_path)
                        except Exception:
                            continue
                        if candidate.exists() and candidate.is_file():
                            gallery[str(label)] = candidate
                if gallery:
                    self.show_image_gallery(
                        gallery,
                        default_label=snapshot.get("active_image_label"),
                    )
                else:
                    image_path = snapshot.get("image_path")
                    if image_path and Path(image_path).exists():
                        self.show_image(image_path)
                self._restore_snapshot_image_colors(snapshot)

            report_path = snapshot.get("report_path")
            if report_path:
                self.set_report_path(report_path)
            restored_data_export_paths = snapshot.get("data_export_paths")
            if isinstance(restored_data_export_paths, list) and restored_data_export_paths:
                self.set_data_export_source(restored_data_export_paths)
            else:
                self.set_data_export_source(
                    snapshot.get("data_export_path", snapshot.get("network_net_path"))
                )

            raw_zoom_levels = snapshot.get("zoom_levels", {})
            self._zoom_levels = dict(self._default_zoom_levels)
            if isinstance(raw_zoom_levels, dict):
                for tab_name in self._default_zoom_levels:
                    try:
                        self._zoom_levels[tab_name] = int(raw_zoom_levels.get(tab_name, self._zoom_levels[tab_name]))
                    except (TypeError, ValueError):
                        continue
            self._has_table_content = bool(snapshot.get("has_table_content", self._has_table_content))

            desired_tab = str(snapshot.get("active_content_tab") or "Gráfico")
            desired_tab = self._resolve_restorable_tab(desired_tab, has_chd=bool(chd_profiles))
            try:
                self.tabview.set(desired_tab)
            except Exception:
                pass
            self._apply_zoom(desired_tab, sync=False)
            self._update_zoom_label(desired_tab)
        finally:
            self._restoring_analysis_tab = False
            self._loading_content = False

    def _resolve_restorable_tab(self, desired_tab: str, has_chd: bool = False) -> str:
        """Evita restaurar aba vazia quando não há conteúdo correspondente."""
        normalized = str(desired_tab or "Gráfico")
        if normalized == "Relatório":
            normalized = "Gráfico"
        if normalized == "Gráfico":
            if self._current_image_source is not None:
                return "Gráfico"
            if has_chd or self._current_chd_profiles or self._has_table_content:
                return "Tabela"
            if self._current_text.strip():
                return "Estatísticas"
            return "Gráfico"
        if normalized == "Tabela":
            if has_chd or self._current_chd_profiles or self._has_table_content:
                return "Tabela"
            if self._current_image_source is not None:
                return "Gráfico"
            if self._current_text.strip():
                return "Estatísticas"
            return "Tabela"
        if normalized == "Estatísticas":
            if self._current_text.strip():
                return "Estatísticas"
            if has_chd or self._current_chd_profiles or self._has_table_content:
                return "Tabela"
            if self._current_image_source is not None:
                return "Gráfico"
            return "Estatísticas"
        return normalized

    def _restore_snapshot_image_colors(self, snapshot: Dict[str, Any]) -> None:
        """Restaura customizações de cor salvas na snapshot da aba."""
        if self._current_image_base_source is None:
            return
        raw_overrides = snapshot.get("image_color_overrides", {})
        restored: Dict[str, str] = {}
        if isinstance(raw_overrides, dict):
            for raw_src, raw_dst in raw_overrides.items():
                src = self._normalize_hex_color(str(raw_src))
                dst = self._normalize_hex_color(str(raw_dst))
                if src and dst and src != dst:
                    restored[src] = dst
        self._color_overrides = restored
        try:
            tolerance = int(snapshot.get("image_color_tolerance", self._color_tolerance))
        except Exception:
            tolerance = self._color_tolerance
        self._color_tolerance = max(4, min(96, int(tolerance)))
        if self._current_image_path is not None:
            self._persist_current_color_profile()
        self._apply_current_color_overrides(sync=False)

    def _on_image_inner_configure(self, _event=None) -> None:
        """Atualiza limites de rolagem quando conteúdo do gráfico muda.

        Garante que o scrollregion comece em (0,0) mesmo quando a janela
        embutida (image_inner) está com offset de centralização, para que
        o espaço branco das margens permaneça visível e a imagem apareça
        de fato centralizada.
        """
        try:
            bbox = self.image_canvas.bbox("all")
            if bbox:
                x0, y0, x1, y1 = bbox
                sr = (0, 0, max(x1, 1), max(y1, 1))
                self.image_canvas.configure(scrollregion=sr)
        except Exception:
            pass
        self._update_image_scrollbar_visibility()

    def _center_canvas_window(self, img_w: int, img_h: int) -> None:
        """Centraliza image_inner no canvas quando a imagem é menor que o
        viewport. Mantém (0,0) quando a imagem é maior (para rolagem).
        """
        try:
            cw = max(1, int(self.image_canvas.winfo_width()))
            ch = max(1, int(self.image_canvas.winfo_height()))
        except Exception:
            cw = ch = 1
        off_x = max(0, (cw - int(img_w)) // 2)
        off_y = max(0, (ch - int(img_h)) // 2)
        try:
            self.image_canvas.coords(self._image_canvas_window, off_x, off_y)
        except Exception:
            pass
        # scrollregion precisa englobar [0, off+size] para que
        # (0,0) continue sendo o topo ao usar yview_moveto(0.0).
        try:
            sr_w = max(cw, off_x + int(img_w))
            sr_h = max(ch, off_y + int(img_h))
            self.image_canvas.configure(scrollregion=(0, 0, sr_w, sr_h))
        except Exception:
            pass

    def _on_image_canvas_configure(self, event) -> None:
        """Mantém placeholder legível quando não há imagem ativa e
        re-centraliza a imagem quando o canvas muda de tamanho."""
        try:
            if self._current_image_source is None:
                self.image_canvas.itemconfigure(
                    self._image_canvas_window,
                    width=max(1, int(event.width)),
                    height=max(1, int(event.height)),
                )
                self.image_canvas.coords(self._image_canvas_window, 0, 0)
            else:
                # Re-centraliza usando o tamanho atual do image_inner.
                try:
                    iw = int(self.image_inner.winfo_width())
                    ih = int(self.image_inner.winfo_height())
                    if iw > 1 and ih > 1:
                        self._center_canvas_window(iw, ih)
                except Exception:
                    pass
                if self._pending_image_autofit:
                    self._schedule_image_autofit(delay_ms=90)
        except Exception:
            pass
        self._on_image_inner_configure()
        self._update_image_scrollbar_visibility()

    def _update_image_scrollbar_visibility(self) -> None:
        """Oculta barras quando o conteúdo cabe no viewport."""
        try:
            bbox = self.image_canvas.bbox("all")
            if not bbox:
                self.image_scroll_x.grid_remove()
                self.image_scroll_y.grid_remove()
                return
            content_width = max(1, int(bbox[2] - bbox[0]))
            content_height = max(1, int(bbox[3] - bbox[1]))
            canvas_width = max(1, int(self.image_canvas.winfo_width()))
            canvas_height = max(1, int(self.image_canvas.winfo_height()))
            needs_x = content_width > (canvas_width + 1)
            needs_y = content_height > (canvas_height + 1)
            if needs_x:
                self.image_scroll_x.grid()
            else:
                self.image_scroll_x.grid_remove()
            if needs_y:
                self.image_scroll_y.grid()
            else:
                self.image_scroll_y.grid_remove()
        except Exception:
            pass

    def _refresh_image_scrollregion(self) -> None:
        """Força atualização da região rolável do canvas de imagem."""
        try:
            self.image_label.update_idletasks()
            self.image_inner.update_idletasks()
            self.image_canvas.update_idletasks()
        except Exception:
            pass
        self._on_image_inner_configure()
        self._update_image_scrollbar_visibility()

    @staticmethod
    def _normalize_gallery_label_key(value: str) -> str:
        """Normaliza labels para comparação tolerante a acentos/pontuação."""
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        cleaned = []
        for ch in normalized:
            if ch.isalnum():
                cleaned.append(ch)
            elif ch in {" ", "_", "-"}:
                cleaned.append("_")
        key = "".join(cleaned).strip("_")
        while "__" in key:
            key = key.replace("__", "_")
        return key

    def _looks_like_voyant_graph_gallery(self, labels: List[str]) -> bool:
        """Detecta galeria Voyant para ativar subabas fixas."""
        if not labels:
            return False
        expected = {
            self._normalize_gallery_label_key("TermsBerry"),
            self._normalize_gallery_label_key("Tendências"),
            self._normalize_gallery_label_key("Termos do documento"),
            self._normalize_gallery_label_key("Gráfico de bolhas"),
            self._normalize_gallery_label_key("Co-ocorrências"),
        }
        seen = {
            self._normalize_gallery_label_key(label)
            for label in labels
        }
        return len(expected.intersection(seen)) >= 4

    def _clear_voyant_graph_tabs(self) -> None:
        """Oculta tabview dedicada da suíte Voyant."""
        if hasattr(self, "voyant_graph_tabview") and self.voyant_graph_tabview is not None:
            if self.voyant_graph_tabview.winfo_manager():
                self.voyant_graph_tabview.pack_forget()
            try:
                for tab_name in list(self._voyant_graph_tabs.keys()):
                    self.voyant_graph_tabview.delete(tab_name)
            except Exception:
                pass
        self._voyant_graph_tabs = {}

    def _ordered_voyant_labels(self, labels: List[str]) -> List[str]:
        """Ordena labels de gráficos Voyant de forma estável."""
        normalized_by_label = {
            label: self._normalize_gallery_label_key(label)
            for label in labels
        }
        expected_by_panel = {
            panel_id: self._normalize_gallery_label_key(VOYANT_LABEL_BY_PANEL[panel_id])
            for panel_id in VOYANT_PANEL_ORDER
        }
        ordered: List[str] = []
        used: set[str] = set()
        for panel_id in VOYANT_PANEL_ORDER:
            expected_key = expected_by_panel[panel_id]
            match = next(
                (
                    label
                    for label, normalized_key in normalized_by_label.items()
                    if normalized_key == expected_key and label not in used
                ),
                None,
            )
            if match is not None:
                ordered.append(match)
                used.add(match)
        for label in labels:
            if label not in used:
                ordered.append(label)
        return ordered

    def _on_voyant_graph_tab_changed(self, _value: Optional[str] = None) -> None:
        """Sincroniza seleção de subaba Voyant com gráfico ativo."""
        self._apply_tabview_selected_text_theme(self.voyant_graph_tabview)
        if self._updating_voyant_graph_tabs:
            return
        if not self._voyant_graph_tabs:
            return
        try:
            selected_tab = str(self.voyant_graph_tabview.get() or "").strip()
        except Exception:
            selected_tab = ""
        label = self._voyant_graph_tabs.get(selected_tab)
        if not label:
            return
        self._on_image_gallery_selected(label)

    def _refresh_image_gallery_selector(self) -> None:
        """Atualiza seletor de sub-abas de gráficos."""
        labels = list(self._image_gallery.keys())
        if not labels:
            if self.image_gallery_frame.winfo_manager():
                self.image_gallery_frame.pack_forget()
            for widget in self.image_gallery_tabs_frame.winfo_children():
                widget.destroy()
            self._image_gallery_tab_buttons = {}
            self._clear_voyant_graph_tabs()
            self._is_voyant_graph_gallery = False
            return

        active_label = str(self._active_image_label or "").strip()
        if active_label not in self._image_gallery:
            active_label = labels[0]
        self._active_image_label = active_label

        is_voyant_gallery = bool(self._is_voyant_graph_gallery or self._looks_like_voyant_graph_gallery(labels))
        self._is_voyant_graph_gallery = is_voyant_gallery
        if is_voyant_gallery:
            if self.image_gallery_frame.winfo_manager():
                self.image_gallery_frame.pack_forget()
            for widget in self.image_gallery_tabs_frame.winfo_children():
                widget.destroy()
            self._image_gallery_tab_buttons = {}
            ordered_labels = self._ordered_voyant_labels(labels)
            self._updating_voyant_graph_tabs = True
            try:
                self._clear_voyant_graph_tabs()
                for label in ordered_labels:
                    tab_name = str(label)
                    self.voyant_graph_tabview.add(tab_name)
                    tab_body = self.voyant_graph_tabview.tab(tab_name)
                    ctk.CTkLabel(
                        tab_body,
                        text=f"Painel: {tab_name}",
                        font=FONTS["small"],
                        text_color=get_themed_color("text_secondary"),
                    ).pack(anchor="w", padx=8, pady=(2, 0))
                    self._voyant_graph_tabs[tab_name] = label
                if not self.voyant_graph_tabview.winfo_manager():
                    self.voyant_graph_tabview.pack(fill="x", expand=False, pady=(0, 2))
                selected_tab = active_label if active_label in self._voyant_graph_tabs else ordered_labels[0]
                self.voyant_graph_tabview.set(selected_tab)
                self._apply_tabview_selected_text_theme(self.voyant_graph_tabview)
            except Exception:
                log.exception("Falha ao montar subabas de gráfico da suíte Voyant.")
            finally:
                self._updating_voyant_graph_tabs = False
            return

        self._clear_voyant_graph_tabs()

        if len(labels) <= 1:
            if self.image_gallery_frame.winfo_manager():
                self.image_gallery_frame.pack_forget()
            for widget in self.image_gallery_tabs_frame.winfo_children():
                widget.destroy()
            self._image_gallery_tab_buttons = {}
            return

        if not self.image_gallery_frame.winfo_manager():
            self.image_gallery_frame.pack(fill="x", expand=False, pady=(0, 2))

        self._updating_image_gallery_selector = True
        try:
            for widget in self.image_gallery_tabs_frame.winfo_children():
                widget.destroy()
            self._image_gallery_tab_buttons = {}
            for label in labels:
                is_active = label == active_label
                button = ctk.CTkButton(
                    self.image_gallery_tabs_frame,
                    text=label,
                    height=28,
                    corner_radius=0,
                    font=FONTS["small"],
                    command=lambda value=label: self._on_image_gallery_selected(value),
                    fg_color=(get_themed_color("primary") if is_active else get_themed_color("button")),
                    hover_color=(get_themed_color("primary") if is_active else get_themed_color("button_hover")),
                    text_color=("#FFFFFF" if is_active else get_themed_color("text")),
                    border_width=1,
                    border_color=(get_themed_color("primary") if is_active else get_themed_color("border")),
                )
                button.pack(side="left", padx=(0, 4))
                self._image_gallery_tab_buttons[label] = button
        finally:
            self._updating_image_gallery_selector = False

    def _set_image_gallery(
        self,
        gallery: Dict[str, Path],
        active_label: Optional[str] = None,
        force_voyant: bool = False,
    ) -> None:
        """Define galeria de gráficos para a aba atual."""
        self._image_gallery = dict(gallery or {})
        labels = list(self._image_gallery.keys())
        self._is_voyant_graph_gallery = bool(
            force_voyant or self._looks_like_voyant_graph_gallery(labels)
        )
        if self._image_gallery:
            candidate = str(active_label or "").strip()
            if candidate in self._image_gallery:
                self._active_image_label = candidate
            else:
                self._active_image_label = next(iter(self._image_gallery.keys()))
        else:
            self._active_image_label = None
        self._refresh_image_gallery_selector()

    def _clear_image_gallery(self) -> None:
        """Limpa galeria de gráficos e oculta sub-aba."""
        self._set_image_gallery({}, active_label=None)

    def _refresh_table_gallery_selector(self) -> None:
        """Atualiza seletor de sub-abas de tabelas."""
        labels = list(self._table_gallery.keys())
        if len(labels) <= 1:
            if self.table_gallery_frame.winfo_manager():
                self.table_gallery_frame.pack_forget()
            self._updating_table_gallery_selector = True
            try:
                self.table_gallery_selector.configure(values=["Tabela"])
                self.table_gallery_selector.set("Tabela")
            except Exception:
                pass
            self._updating_table_gallery_selector = False
            self._refresh_table_gallery_selector_text_colors()
            return

        active_label = str(self._active_table_label or "").strip()
        if active_label not in self._table_gallery:
            active_label = labels[0]
        self._active_table_label = active_label

        if not self.table_gallery_frame.winfo_manager():
            # Evita dependência frágil de pack(before=...) que pode falhar em restaurações.
            self.table_gallery_frame.pack(fill="x", expand=False, pady=(0, 2))

        self._updating_table_gallery_selector = True
        try:
            self.table_gallery_selector.configure(values=labels)
            self.table_gallery_selector.set(active_label)
        except Exception:
            pass
        self._updating_table_gallery_selector = False
        self._refresh_table_gallery_selector_text_colors()

    def _refresh_table_gallery_selector_text_colors(self) -> None:
        """Garante texto branco no item selecionado e texto padrão nos demais."""
        try:
            segmented = self.table_gallery_selector
            buttons_dict = getattr(segmented, "_buttons_dict", {}) if segmented is not None else {}
            active = str(self._active_table_label or segmented.get() or "")
            default_text = get_themed_color("text")
            for name, button in buttons_dict.items():
                is_active = str(name) == active
                button.configure(
                    text_color=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                    text_color_disabled=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                )
        except Exception:
            pass

    def _set_table_gallery(
        self,
        gallery: Dict[str, Path],
        active_label: Optional[str] = None,
    ) -> None:
        """Define galeria de tabelas para a aba ativa."""
        self._table_gallery = dict(gallery or {})
        if self._table_gallery:
            candidate = str(active_label or "").strip()
            if candidate in self._table_gallery:
                self._active_table_label = candidate
            else:
                self._active_table_label = next(iter(self._table_gallery.keys()))
        else:
            self._active_table_label = None
        self._refresh_table_gallery_selector()

    def _clear_table_gallery(self) -> None:
        """Limpa galeria de tabelas e oculta sub-aba."""
        self._set_table_gallery({}, active_label=None)

    def _on_table_gallery_selected(self, value: str) -> None:
        """Troca tabela ativa ao selecionar sub-aba."""
        if self._updating_table_gallery_selector:
            return
        label = str(value or "").strip()
        table_path = self._table_gallery.get(label)
        if table_path is None:
            return
        self.show_table(
            table_path,
            preserve_gallery=True,
            gallery_label=label,
        )

    def show_table_gallery(
        self,
        tables: Dict[str, Union[str, Path]],
        default_label: Optional[str] = None,
    ) -> None:
        """Exibe conjunto de tabelas com seletor de sub-abas."""
        normalized: Dict[str, Path] = {}
        used_paths: set[str] = set()
        for idx, (raw_label, raw_path) in enumerate((tables or {}).items(), start=1):
            label = str(raw_label or "").strip() or f"Tabela {idx}"
            try:
                candidate = Path(raw_path)
            except Exception:
                continue
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                path_key = str(candidate.resolve())
            except Exception:
                path_key = str(candidate)
            if path_key in used_paths:
                continue
            if label in normalized:
                suffix = 2
                unique_label = f"{label} ({suffix})"
                while unique_label in normalized:
                    suffix += 1
                    unique_label = f"{label} ({suffix})"
                label = unique_label
            used_paths.add(path_key)
            normalized[label] = candidate

        if not normalized:
            self._clear_table_gallery()
            for widget in self.table_frame.winfo_children():
                widget.destroy()
            self._clear_zoom_font_cache(self.table_frame)
            self.table_placeholder = ctk.CTkLabel(
                self.table_frame,
                text="Nenhuma tabela para exibir.",
                font=FONTS["body"],
                text_color=get_themed_color("text"),
                fg_color="transparent",
            )
            self.table_placeholder.pack(fill="both", expand=True)
            self._current_table_path = None
            self._has_table_content = False
            self._sync_active_tab_state()
            return

        chosen = str(default_label or "").strip()
        if chosen not in normalized:
            chosen = next(iter(normalized.keys()))

        self._set_table_gallery(normalized, active_label=chosen)
        self.show_table(
            normalized[chosen],
            preserve_gallery=True,
            gallery_label=chosen,
        )

    def _set_graph_placeholder(self, text: Optional[str] = None) -> None:
        """Força placeholder no gráfico e remove qualquer imagem residual."""
        placeholder = (
            str(text).strip()
            if str(text or "").strip()
            else "Nenhum gráfico para exibir.\n\nExecute uma análise para ver os resultados."
        )
        self._current_image = None
        try:
            self.image_label.configure(text=placeholder, image=None)
        except Exception:
            try:
                self.image_label.configure(text=placeholder)
            except Exception:
                pass

        # Algumas versões do CustomTkinter mantêm a imagem via atributos internos.
        for attr_name in ("_displayed_image", "_image", "image"):
            if hasattr(self.image_label, attr_name):
                try:
                    setattr(self.image_label, attr_name, None)
                except Exception:
                    pass
        try:
            # Limpa imagem diretamente no label Tk interno para evitar warning do CTk.
            inner_label = getattr(self.image_label, "_label", None)
            if inner_label is not None:
                inner_label.configure(image="")
            else:
                self.image_label.configure(image="")
        except Exception:
            pass

    def _on_image_gallery_selected(self, value: str) -> None:
        """Troca gráfico ativo ao selecionar sub-aba."""
        if self._updating_image_gallery_selector:
            return
        label = str(value or "").strip()
        image_path = self._image_gallery.get(label)
        if image_path is None:
            return
        self.show_image(
            image_path,
            preserve_gallery=True,
            gallery_label=label,
        )

    def show_image_gallery(
        self,
        images: Dict[str, Union[str, Path]],
        default_label: Optional[str] = None,
    ) -> None:
        """Exibe conjunto de gráficos com seletor de sub-abas."""
        normalized: Dict[str, Path] = {}
        used_paths: set[str] = set()
        for idx, (raw_label, raw_path) in enumerate((images or {}).items(), start=1):
            label = str(raw_label or "").strip() or f"Gráfico {idx}"
            try:
                candidate = Path(raw_path)
            except Exception:
                continue
            if not candidate.exists() or not candidate.is_file():
                continue
            display_candidate, _warning = self._resolve_display_image_path(candidate)
            if display_candidate is None:
                continue
            key_path = str(candidate.resolve())
            if key_path in used_paths:
                continue
            if label in normalized:
                suffix = 2
                unique_label = f"{label} ({suffix})"
                while unique_label in normalized:
                    suffix += 1
                    unique_label = f"{label} ({suffix})"
                label = unique_label
            used_paths.add(key_path)
            normalized[label] = candidate

        if not normalized:
            self._clear_image_gallery()
            self._set_graph_placeholder()
            self._current_image_source = None
            self._current_image_base_source = None
            self._current_image_path = None
            self._active_image_color_key = None
            self._dominant_palette = []
            self._color_overrides = {}
            self._set_color_tool_enabled(False)
            self._sync_active_tab_state()
            return

        chosen = str(default_label or "").strip()
        if chosen not in normalized:
            chosen = next(iter(normalized.keys()))

        if not self._looks_like_voyant_graph_gallery(list(normalized.keys())):
            self._current_voyant_payload = {}
        self._set_image_gallery(normalized, active_label=chosen)
        self.show_image(
            normalized[chosen],
            preserve_gallery=True,
            gallery_label=chosen,
        )

    def show_voyant_suite(self, payload: Dict[str, Any]) -> None:
        """Renderiza suíte Voyant (5 painéis) com subabas fixas em Gráfico."""
        if not isinstance(payload, dict):
            return

        self._loading_content = True
        try:
            self._current_voyant_payload = dict(payload)
            graphs_payload = payload.get("graphs", {})
            tables_payload = payload.get("tables", {})
            graph_tabs = payload.get("graph_tabs", [])
            if not isinstance(graph_tabs, list) or not graph_tabs:
                graph_tabs = list(VOYANT_PANEL_ORDER)
            if not isinstance(graphs_payload, dict):
                graphs_payload = {}
            if not isinstance(tables_payload, dict):
                tables_payload = {}

            image_gallery: Dict[str, Path] = {}
            for panel_id in graph_tabs:
                graph_item = graphs_payload.get(str(panel_id), {})
                if not isinstance(graph_item, dict):
                    continue
                label = str(
                    graph_item.get("title_pt")
                    or VOYANT_LABEL_BY_PANEL.get(str(panel_id), str(panel_id))
                )
                image_path_raw = graph_item.get("image_path")
                try:
                    image_path = Path(image_path_raw)
                except Exception:
                    continue
                if image_path.exists() and image_path.is_file():
                    image_gallery[label] = image_path

            table_gallery: Dict[str, Path] = {}
            for panel_id in VOYANT_PANEL_ORDER:
                table_item = tables_payload.get(str(panel_id), {})
                if not isinstance(table_item, dict):
                    continue
                label = str(
                    table_item.get("title_pt")
                    or VOYANT_LABEL_BY_PANEL.get(str(panel_id), str(panel_id))
                )
                csv_path_raw = table_item.get("csv_path")
                try:
                    csv_path = Path(csv_path_raw)
                except Exception:
                    csv_path = None
                if csv_path is not None and csv_path.exists() and csv_path.is_file():
                    table_gallery[label] = csv_path

                extra_csv = table_item.get("extra_csv", [])
                if isinstance(extra_csv, list):
                    for extra in extra_csv:
                        if not isinstance(extra, dict):
                            continue
                        extra_label = str(extra.get("title_pt", extra.get("id", "Tabela complementar")))
                        extra_path_raw = extra.get("csv_path")
                        try:
                            extra_path = Path(extra_path_raw)
                        except Exception:
                            continue
                        if extra_path.exists() and extra_path.is_file():
                            if extra_label in table_gallery:
                                suffix = 2
                                unique_label = f"{extra_label} ({suffix})"
                                while unique_label in table_gallery:
                                    suffix += 1
                                    unique_label = f"{extra_label} ({suffix})"
                                extra_label = unique_label
                            table_gallery[extra_label] = extra_path

            if image_gallery:
                active_label = next(iter(image_gallery.keys()))
                self._set_image_gallery(
                    image_gallery,
                    active_label=active_label,
                    force_voyant=True,
                )
                self.show_image(
                    image_gallery[active_label],
                    preserve_gallery=True,
                    gallery_label=active_label,
                )
            else:
                self._clear_image_gallery()
                self._set_graph_placeholder("Nenhum gráfico da suíte Voyant para exibir.")

            if table_gallery:
                self.show_table_gallery(table_gallery, default_label=next(iter(table_gallery.keys())))
            else:
                self._clear_table_gallery()

            try:
                self.tabview.set("Gráfico")
                self.update_idletasks()
                self._fit_image_to_view(sync=False, allow_below_min=True)
                self._render_current_image(sync=False)
                self._schedule_image_autofit(delay_ms=90)
                self._schedule_graph_finalize(delay_ms=180)
                self._update_zoom_label("Gráfico")
            except Exception:
                pass
            self._sync_active_tab_state()
        finally:
            self._loading_content = False
    
    def show_image(
        self,
        path: Union[str, Path],
        preserve_gallery: bool = False,
        gallery_label: Optional[str] = None,
    ) -> None:
        """
        Exibe imagem.
        
        Args:
            path: Caminho para arquivo de imagem
        """
        if not preserve_gallery:
            self._clear_image_gallery()
        elif self._image_gallery:
            chosen_label = str(gallery_label or "").strip()
            if chosen_label in self._image_gallery:
                self._active_image_label = chosen_label
            self._refresh_image_gallery_selector()

        self._cancel_pending_image_autofit()
        self._cancel_pending_graph_finalize()
        path = Path(path)
        if not path.exists():
            self._pending_image_autofit = False
            self._last_render_source_id = None
            self._last_render_size = None
            self._set_graph_placeholder(f"Arquivo não encontrado:\n{path}")
            return
        display_path, warning_text = self._resolve_display_image_path(path)
        if display_path is None:
            self._current_image_source = None
            self._current_image_base_source = None
            self._current_image_path = None
            self._active_image_color_key = None
            self._dominant_palette = []
            self._color_overrides = {}
            self._set_color_tool_enabled(False)
            self._pending_image_autofit = False
            self._last_render_source_id = None
            self._last_render_size = None
            self._set_graph_placeholder(
                warning_text or f"Formato de imagem não suportado:\n{path.name}"
            )
            self.tabview.set("Gráfico")
            self._update_zoom_label("Gráfico")
            self._sync_active_tab_state()
            return
        if warning_text:
            log.info(warning_text)
        
        # Ativar proteção contra interferência
        self._loading_content = True
        try:
            with Image.open(display_path) as img:
                source = img.copy()
            # Guard rail: imagens muito grandes degradam bastante no Tk/CTk.
            # Reduzimos apenas para visualização interativa, sem afetar export.
            max_source_dim = 4200
            if max(source.size) > max_source_dim:
                source.thumbnail((max_source_dim, max_source_dim), Image.Resampling.LANCZOS)
            self._current_image_base_source = source
            self._current_image_path = display_path
            self._restore_color_profile_for_image(display_path)
            self._apply_current_color_overrides(sync=False)
            if self._current_image_source is None:
                self._current_image_source = source.copy()
            self._set_color_tool_enabled(True)
            self._pending_image_autofit = True
            self._pending_image_autofit_attempts = 0
            self._last_render_source_id = None
            self._last_render_size = None
            self.btn_export.configure(state="normal")
            self.tabview.set("Gráfico")
            
            # Renderizar IMEDIATAMENTE - não atrasar
            # Forçar update da UI para garantir dimensões corretas
            try:
                self.update_idletasks()
                self._fit_image_to_view(sync=False, allow_below_min=True)
                self._render_current_image(sync=False)
                self._update_zoom_label("Gráfico")
                self._schedule_image_autofit(delay_ms=120)
                self._schedule_graph_finalize(delay_ms=240)
            except Exception as render_err:
                log.warning("Renderização inicial falhou: %s", render_err)
                # Fallback: renderizar com tamanho fixo
                try:
                    self._render_current_image(sync=False)
                    self._schedule_image_autofit(delay_ms=120)
                    self._schedule_graph_finalize(delay_ms=240)
                except Exception:
                    pass
            
            # Sincronizar estado DEPOIS da renderização para preservar
            self._sync_active_tab_state()
            
            log.debug("show_image completo: %s, source=%s", 
                     display_path.name, self._current_image_source is not None)
            
        except Exception as e:
            self._current_image_source = None
            self._current_image_base_source = None
            self._current_image_path = None
            self._active_image_color_key = None
            self._dominant_palette = []
            self._color_overrides = {}
            self._set_color_tool_enabled(False)
            self._pending_image_autofit = False
            self._last_render_source_id = None
            self._last_render_size = None
            self._set_graph_placeholder(f"Erro ao carregar imagem:\n{e}")
            self._sync_active_tab_state()
        finally:
            self._loading_content = False

    @staticmethod
    def _resolve_display_image_path(path: Path) -> Tuple[Optional[Path], Optional[str]]:
        """Resolve caminho de imagem visualizável na UI (PNG/JPG/BMP etc)."""
        suffix = path.suffix.lower()
        if suffix != ".svg":
            return path, None

        png_candidate = path.with_suffix(".png")
        if png_candidate.exists():
            return png_candidate, (
                f"SVG detectado em {path.name}; exibindo PNG equivalente {png_candidate.name}."
            )

        return None, (
            "Gráfico em SVG sem versão PNG para visualização.\n"
            "Selecione formato PNG na análise para exibir o gráfico na interface."
        )

    @staticmethod
    def _normalize_hex_color(value: str) -> Optional[str]:
        """Normaliza cor em formato #RRGGBB."""
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            if ImageColor is not None:
                rgb = ImageColor.getrgb(raw)
            else:
                if raw.startswith("#") and len(raw) == 7:
                    rgb = (
                        int(raw[1:3], 16),
                        int(raw[3:5], 16),
                        int(raw[5:7], 16),
                    )
                else:
                    return None
            return "#{:02X}{:02X}{:02X}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        except Exception:
            return None

    @staticmethod
    def _pick_contrast_text_color(hex_color: str) -> str:
        """Retorna branco/preto de maior contraste para fundo informado."""
        normalized = ResultsViewer._normalize_hex_color(hex_color) or "#1A1A1A"
        try:
            r = int(normalized[1:3], 16)
            g = int(normalized[3:5], 16)
            b = int(normalized[5:7], 16)
        except Exception:
            return "#FFFFFF"
        luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
        return "#1A1A1A" if luminance > 0.62 else "#FFFFFF"

    @staticmethod
    def _color_distance_sq(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
        """Distância quadrática simples entre duas cores RGB."""
        return (int(a[0]) - int(b[0])) ** 2 + (int(a[1]) - int(b[1])) ** 2 + (int(a[2]) - int(b[2])) ** 2

    def _extract_dominant_palette(self, image: Image.Image, max_colors: int = 10) -> List[str]:
        """Extrai paleta dominante para editor de cores."""
        try:
            rgb = image.convert("RGB")
            if max(rgb.size) > 480:
                rgb = rgb.copy()
                rgb.thumbnail((480, 480), Image.Resampling.BILINEAR)
            quant = rgb.quantize(colors=max(16, max_colors * 4), method=Image.Quantize.MEDIANCUT)
            colors = quant.getcolors() or []
            palette = quant.getpalette() or []
            if not colors or not palette:
                return []
            colors.sort(key=lambda item: int(item[0]), reverse=True)
            selected: List[Tuple[int, int, int]] = []
            for _count, idx in colors:
                base = int(idx) * 3
                if base + 2 >= len(palette):
                    continue
                rgb_triplet = (
                    int(palette[base]),
                    int(palette[base + 1]),
                    int(palette[base + 2]),
                )
                # Evita duplicatas muito próximas.
                if any(self._color_distance_sq(rgb_triplet, prev) <= (16 * 16 * 3) for prev in selected):
                    continue
                selected.append(rgb_triplet)
                if len(selected) >= max_colors:
                    break
            return ["#{:02X}{:02X}{:02X}".format(*triplet) for triplet in selected]
        except Exception:
            return []

    @staticmethod
    def _make_image_color_key(path: Path) -> str:
        """Chave estável para perfil de cor por imagem."""
        try:
            return str(path.resolve())
        except Exception:
            return str(path)

    def _set_color_tool_enabled(self, enabled: bool) -> None:
        """Habilita/desabilita botão do editor de cores."""
        try:
            self.btn_graph_colors.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _restore_color_profile_for_image(self, image_path: Path) -> None:
        """Restaura perfil de cor salvo para imagem ativa."""
        self._active_image_color_key = self._make_image_color_key(image_path)
        profile = self._image_color_profiles.get(self._active_image_color_key, {})
        raw_overrides = profile.get("overrides", {}) if isinstance(profile, dict) else {}
        normalized_overrides: Dict[str, str] = {}
        if isinstance(raw_overrides, dict):
            for raw_src, raw_dst in raw_overrides.items():
                src = self._normalize_hex_color(str(raw_src))
                dst = self._normalize_hex_color(str(raw_dst))
                if src and dst and src != dst:
                    normalized_overrides[src] = dst
        self._color_overrides = normalized_overrides
        tolerance = int(profile.get("tolerance", 34)) if isinstance(profile, dict) else 34
        self._color_tolerance = max(4, min(96, tolerance))

        if self._current_image_base_source is not None:
            self._dominant_palette = self._extract_dominant_palette(self._current_image_base_source, max_colors=10)
        else:
            self._dominant_palette = []

        if self._dominant_palette:
            palette_set = set(self._dominant_palette)
            extras = [src for src in self._color_overrides if src not in palette_set]
            self._dominant_palette.extend(extras)

    def _persist_current_color_profile(self) -> None:
        """Persiste overrides de cor para imagem ativa."""
        key = self._active_image_color_key
        if not key:
            return
        clean_overrides = {
            src: dst
            for src, dst in self._color_overrides.items()
            if src and dst and src != dst
        }
        if not clean_overrides and int(self._color_tolerance) == 34:
            self._image_color_profiles.pop(key, None)
            return
        self._image_color_profiles[key] = {
            "overrides": clean_overrides,
            "tolerance": int(self._color_tolerance),
        }

    def _apply_color_overrides_to_image(self, image: Image.Image) -> Image.Image:
        """Aplica mapeamento de cores em uma imagem e retorna cópia alterada."""
        if image is None:
            return image
        clean_overrides = {
            src: dst for src, dst in self._color_overrides.items() if src and dst and src != dst
        }
        if not clean_overrides:
            return image.copy()
        if ImageColor is None:
            return image.copy()
        try:
            rgba = image.convert("RGBA")
            array = np.array(rgba, dtype=np.int16)
            rgb = array[:, :, :3]
            tol2 = int(max(1, self._color_tolerance)) ** 2
            for src_hex, dst_hex in clean_overrides.items():
                src_rgb = np.array(ImageColor.getrgb(src_hex), dtype=np.int16).reshape((1, 1, 3))
                dst_rgb = np.array(ImageColor.getrgb(dst_hex), dtype=np.int16)
                delta = rgb - src_rgb
                dist2 = np.sum(delta * delta, axis=2)
                mask = dist2 <= tol2
                if np.any(mask):
                    rgb[mask] = dst_rgb
            array[:, :, :3] = np.clip(rgb, 0, 255)
            return Image.fromarray(array.astype(np.uint8), mode="RGBA").convert(image.mode)
        except Exception:
            return image.copy()

    def _apply_current_color_overrides(self, sync: bool = True) -> None:
        """Reaplica customização de cor na imagem ativa."""
        if self._current_image_base_source is None:
            self._current_image_source = None
            return
        self._current_image_source = self._apply_color_overrides_to_image(self._current_image_base_source)
        self._persist_current_color_profile()
        self._last_render_source_id = None
        self._last_render_size = None
        self._render_current_image(sync=False)
        if sync:
            self._sync_active_tab_state()

    def _open_color_editor(self) -> None:
        """Abre editor de cores para gráfico ativo."""
        if self._current_image_base_source is None:
            return
        existing = self._color_editor_window
        if existing is not None and existing.winfo_exists():
            try:
                existing.lift()
                existing.focus_force()
            except Exception:
                pass
            return

        win = ctk.CTkToplevel(self)
        win.title("Editor de Cores do Gráfico")
        win.geometry("520x560")
        win.resizable(True, True)
        win.transient(self.winfo_toplevel())
        self._color_editor_window = win

        def close_editor() -> None:
            try:
                if win.winfo_exists():
                    win.destroy()
            finally:
                if self._color_editor_window is win:
                    self._color_editor_window = None
                    self._color_editor_palette_frame = None
                    self._color_editor_tolerance_label = None
                    self._color_editor_tolerance_var = None
                    self._color_editor_preset_var = None

        win.protocol("WM_DELETE_WINDOW", close_editor)

        ctk.CTkLabel(
            win,
            text="Personalize as cores do gráfico ativo",
            font=FONTS["title"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            win,
            text=(
                "Selecione uma cor base do gráfico e escolha a nova cor.\n"
                "A edição é visual (não altera os dados da análise)."
            ),
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        tol_row = ctk.CTkFrame(win, fg_color="transparent")
        tol_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            tol_row,
            text="Sensibilidade da cor:",
            font=FONTS["body"],
            width=160,
        ).pack(side="left")
        tol_var = ctk.IntVar(value=int(self._color_tolerance))
        self._color_editor_tolerance_var = tol_var
        ctk.CTkSlider(
            tol_row,
            from_=4,
            to=96,
            number_of_steps=92,
            variable=tol_var,
            width=220,
            command=lambda _v: self._on_color_tolerance_changed(),
        ).pack(side="left", padx=8)
        tol_label = ctk.CTkLabel(tol_row, text=str(int(self._color_tolerance)), width=42)
        tol_label.pack(side="left")
        self._color_editor_tolerance_label = tol_label

        palette_frame = ctk.CTkScrollableFrame(win)
        palette_frame.pack(fill="both", expand=True, padx=14, pady=(6, 10))
        self._color_editor_palette_frame = palette_frame

        preset_row = ctk.CTkFrame(win, fg_color="transparent")
        preset_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            preset_row,
            text="Preset:",
            font=FONTS["body"],
            width=60,
        ).pack(side="left")
        preset_var = ctk.StringVar(value="Personalizado")
        self._color_editor_preset_var = preset_var
        ctk.CTkOptionMenu(
            preset_row,
            values=["Personalizado", "CHD", "Alto contraste", "Daltônico-safe"],
            variable=preset_var,
            width=190,
        ).pack(side="left", padx=(6, 8))
        ctk.CTkButton(
            preset_row,
            text="Aplicar preset",
            width=130,
            command=self._apply_selected_color_preset,
        ).pack(side="left")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            btn_row,
            text="Restaurar Original",
            width=150,
            command=self._reset_all_color_overrides,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row,
            text="Fechar",
            width=100,
            command=close_editor,
        ).pack(side="right")

        self._refresh_color_editor_palette()

    def _on_color_tolerance_changed(self) -> None:
        """Aplica novo nível de sensibilidade do editor de cores."""
        var = self._color_editor_tolerance_var
        if var is None:
            return
        try:
            tolerance = int(var.get())
        except Exception:
            tolerance = int(self._color_tolerance)
        self._color_tolerance = max(4, min(96, tolerance))
        if self._color_editor_tolerance_label is not None:
            self._color_editor_tolerance_label.configure(text=str(int(self._color_tolerance)))
        self._apply_current_color_overrides(sync=True)

    def _refresh_color_editor_palette(self) -> None:
        """Re-renderiza lista de cores no editor."""
        frame = self._color_editor_palette_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()

        palette = list(self._dominant_palette)
        if not palette and self._current_image_base_source is not None:
            palette = self._extract_dominant_palette(self._current_image_base_source, max_colors=10)
            self._dominant_palette = list(palette)
        if not palette:
            ctk.CTkLabel(
                frame,
                text="Não foi possível extrair cores do gráfico.",
                font=FONTS["small"],
                text_color=get_themed_color("text_secondary"),
            ).pack(anchor="w", padx=8, pady=8)
            return

        for source_hex in palette:
            target_hex = self._color_overrides.get(source_hex, source_hex)
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=4)

            ctk.CTkFrame(
                row,
                width=28,
                height=24,
                fg_color=source_hex,
                corner_radius=4,
                border_width=1,
                border_color=get_themed_color("border"),
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=source_hex,
                width=88,
                font=FONTS["small"],
            ).pack(side="left", padx=(8, 6))
            ctk.CTkLabel(
                row,
                text="→",
                width=20,
                font=FONTS["heading"],
            ).pack(side="left")

            target_btn = ctk.CTkButton(
                row,
                text=target_hex,
                width=110,
                fg_color=target_hex,
                hover_color=target_hex,
                text_color=self._pick_contrast_text_color(target_hex),
                command=lambda src=source_hex: self._choose_override_color(src),
            )
            target_btn.pack(side="left", padx=(6, 8))

            reset_btn = ctk.CTkButton(
                row,
                text="Resetar",
                width=74,
                command=lambda src=source_hex: self._reset_one_color_override(src),
            )
            reset_btn.pack(side="left")

    def _choose_override_color(self, source_hex: str) -> None:
        """Seleciona cor destino para uma cor origem."""
        current = self._color_overrides.get(source_hex, source_hex)
        chosen = colorchooser.askcolor(color=current, parent=self._color_editor_window)
        if not chosen or not chosen[1]:
            return
        target = self._normalize_hex_color(str(chosen[1]))
        if not target:
            return
        if target == source_hex:
            self._color_overrides.pop(source_hex, None)
        else:
            self._color_overrides[source_hex] = target
        if self._color_editor_preset_var is not None:
            self._color_editor_preset_var.set("Personalizado")
        self._apply_current_color_overrides(sync=True)
        self._refresh_color_editor_palette()

    def _reset_one_color_override(self, source_hex: str) -> None:
        """Remove override de uma cor específica."""
        if source_hex in self._color_overrides:
            self._color_overrides.pop(source_hex, None)
            if self._color_editor_preset_var is not None:
                self._color_editor_preset_var.set("Personalizado")
            self._apply_current_color_overrides(sync=True)
        self._refresh_color_editor_palette()

    def _reset_all_color_overrides(self) -> None:
        """Restaura todas as cores originais da imagem ativa."""
        self._color_overrides = {}
        self._color_tolerance = 34
        if self._color_editor_tolerance_var is not None:
            self._color_editor_tolerance_var.set(self._color_tolerance)
        if self._color_editor_tolerance_label is not None:
            self._color_editor_tolerance_label.configure(text=str(self._color_tolerance))
        if self._color_editor_preset_var is not None:
            self._color_editor_preset_var.set("Personalizado")
        self._apply_current_color_overrides(sync=True)
        self._refresh_color_editor_palette()

    @staticmethod
    def _palette_luminance(hex_color: str) -> float:
        """Calcula luminância relativa para ordenação estável de paletas."""
        normalized = ResultsViewer._normalize_hex_color(hex_color) or "#000000"
        try:
            r = int(normalized[1:3], 16)
            g = int(normalized[3:5], 16)
            b = int(normalized[5:7], 16)
        except Exception:
            return 0.0
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _apply_selected_color_preset(self) -> None:
        """Aplica preset de paleta ao gráfico ativo."""
        if self._current_image_base_source is None:
            return
        preset_var = self._color_editor_preset_var
        preset_name = str(preset_var.get() if preset_var is not None else "Personalizado").strip()
        if preset_name == "Personalizado":
            return

        sources = list(self._dominant_palette)
        if not sources:
            return
        sources.sort(key=self._palette_luminance)

        preset_palettes: Dict[str, List[str]] = {
            # Paleta com boa separação para classes e perfis.
            "CHD": [
                "#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD",
                "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF",
            ],
            "Alto contraste": [
                "#003F5C", "#FFA600", "#BC5090", "#2F4B7C", "#F95D6A",
                "#00A676", "#7A5195", "#EF5675", "#FF764A", "#1A1A1A",
            ],
            # Baseada em Okabe-Ito (colorblind-safe).
            "Daltônico-safe": [
                "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
                "#56B4E9", "#F0E442", "#000000",
            ],
        }
        targets = preset_palettes.get(preset_name)
        if not targets:
            return

        self._color_overrides = {}
        for idx, source_hex in enumerate(sources):
            src = self._normalize_hex_color(source_hex)
            dst = self._normalize_hex_color(targets[idx % len(targets)])
            if src and dst and src != dst:
                self._color_overrides[src] = dst

        # Presets funcionam melhor com tolerância moderada.
        self._color_tolerance = 28
        if self._color_editor_tolerance_var is not None:
            self._color_editor_tolerance_var.set(self._color_tolerance)
        if self._color_editor_tolerance_label is not None:
            self._color_editor_tolerance_label.configure(text=str(self._color_tolerance))
        self._apply_current_color_overrides(sync=True)
        self._refresh_color_editor_palette()
    
    def show_statistics(self, stats: Dict[str, Any]) -> None:
        """
        Exibe estatisticas em formato de texto.
        
        Args:
            stats: Dicionario com estatisticas
        """
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self._current_stats_dict = dict(stats)
        
        # Formata estatisticas
        lines = ["=" * 40, "ESTATÍSTICAS DO CORPUS", "=" * 40, ""]
        
        for key, value in stats.items():
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                lines.append(f"{label}: {value:.2f}")
            elif isinstance(value, dict):
                lines.append(f"\n{label}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{label}: {value}")
        
        lines.extend(["", "=" * 40])
        
        self.text_box.insert("1.0", "\n".join(lines))
        self.text_box.configure(state="disabled")
        self._current_text = "\n".join(lines)
        self._apply_zoom("Estatísticas", sync=False)
        self.tabview.set("Estatísticas")
        self._update_zoom_label("Estatísticas")
        self.btn_export.configure(state="normal")
        self._sync_active_tab_state()
    
    def show_table(
        self,
        path: Union[str, Path],
        preserve_gallery: bool = False,
        gallery_label: Optional[str] = None,
    ) -> None:
        """
        Exibe tabela CSV.
        
        Args:
            path: Caminho para arquivo CSV
        """
        if not preserve_gallery:
            self._clear_table_gallery()
        elif self._table_gallery:
            chosen_label = str(gallery_label or "").strip()
            if chosen_label in self._table_gallery:
                self._active_table_label = chosen_label
            self._refresh_table_gallery_selector()

        path = Path(path)
        if not path.exists():
            self._current_table_treeview = None
            for widget in self.table_frame.winfo_children():
                widget.destroy()
            self._clear_zoom_font_cache(self.table_frame)
            ctk.CTkLabel(
                self.table_frame,
                text=f"Arquivo não encontrado:\n{path.name}",
                font=FONTS["body"],
                text_color=COLORS.get("text_secondary", "#888888"),
            ).pack(fill="both", expand=True)
            self._current_table_path = None
            self._has_table_content = False
            if self._current_data_export_sources:
                self._current_data_export_sources = [
                    candidate for candidate in self._current_data_export_sources if candidate.exists()
                ]
            if self._current_data_export_sources:
                self._current_data_export_path = self._current_data_export_sources[0]
            elif self._current_data_export_path is not None and not self._current_data_export_path.exists():
                self._current_data_export_path = None
            self._update_data_export_button_state()
            self.tabview.set("Tabela")
            self._update_zoom_label("Tabela")
            self._sync_active_tab_state()
            log.warning("CSV file not found for table display: %s", path)
            return
        
        # Proteção contra race conditions
        self._loading_content = True
        try:
            # Limpa tabela anterior
            self._current_table_treeview = None
            for widget in self.table_frame.winfo_children():
                widget.destroy()
            self._clear_zoom_font_cache(self.table_frame)
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    # Detecta delimitador
                    sample = f.read(1024)
                    f.seek(0)
                    delimiter = ';' if ';' in sample else ','
                    
                    reader = csv.reader(f, delimiter=delimiter)
                    rows = list(reader)
                
                if not rows:
                    self.table_placeholder = ctk.CTkLabel(
                        self.table_frame,
                        text="Tabela vazia.",
                        font=FONTS['body']
                    )
                    self.table_placeholder.pack(expand=True)
                    return

                if self._ui_v2_results:
                    self._render_table_v2_treeview(rows)
                else:
                    # Cria header
                    header = rows[0]
                    for col, cell in enumerate(header):
                        label = ctk.CTkLabel(
                            self.table_frame,
                            text=str(cell),
                            font=FONTS['heading'],
                            width=100
                        )
                        label.grid(row=0, column=col, padx=2, pady=2, sticky="w")

                    # Cria linhas de dados (limita a 100)
                    for row_idx, row in enumerate(rows[1:101], start=1):
                        for col, cell in enumerate(row):
                            label = ctk.CTkLabel(
                                self.table_frame,
                                text=str(cell)[:30],  # Trunca texto longo
                                font=FONTS['small'],
                                width=100
                            )
                            label.grid(row=row_idx, column=col, padx=2, pady=1, sticky="w")

                    if len(rows) > 101:
                        more_label = ctk.CTkLabel(
                            self.table_frame,
                            text=f"... (+{len(rows) - 101} linhas)",
                            font=FONTS['small'],
                            text_color=COLORS['text_secondary']
                        )
                        more_label.grid(row=102, column=0, columnspan=len(header), pady=5)
                self._current_table_path = path
                self._has_table_content = True
                if self._current_data_export_path is None or not self._current_data_export_path.exists():
                    self._current_data_export_path = path
                    self._current_data_export_sources = [path]
                self._update_data_export_button_state()
                self.btn_export.configure(state="normal")
                
                # Renderização SÍNCRONA e robusta
                self._apply_zoom("Tabela", sync=False)
                self.tabview.set("Tabela")
                self.update_idletasks() # Força layout
                self._update_zoom_label("Tabela")
                self._sync_active_tab_state()
                
            except Exception as e:
                error_label = ctk.CTkLabel(
                    self.table_frame,
                    text=f"Erro ao carregar tabela:\n{e}",
                    font=FONTS['body']
                )
                error_label.pack(expand=True)
        finally:
            self._loading_content = False
    
    def show_text(self, text: str, title: str = "Resultado") -> None:
        """
        Exibe texto generico.
        
        Args:
            text: Texto para exibir
            title: Titulo opcional
        """
        # Proteção contra race conditions
        self._loading_content = True
        try:
            self.text_box.configure(state="normal")
            self.text_box.delete("1.0", "end")
            
            if title:
                self.text_box.insert("1.0", f"{'=' * 40}\n{title}\n{'=' * 40}\n\n")
            
            self.text_box.insert("end", text)
            self.text_box.configure(state="disabled")
            self._current_text = text
            self._current_stats_dict = None
            self.btn_export.configure(state="normal")
            
            # Renderização SÍNCRONA e robusta
            self._apply_zoom("Estatísticas", sync=False)
            self.tabview.set("Estatísticas")
            self.update_idletasks() # Força layout
            self._update_zoom_label("Estatísticas")
            self._sync_active_tab_state()
        finally:
            self._loading_content = False

    def show_chd_profiles(
        self,
        profiles: Dict[int, Any],
        class_sizes: Dict[int, int],
        top_n: int = 40,
        result: Optional[Any] = None,
    ) -> None:
        """Exibe resultados CHD (perfis, AFC, variaveis e segmentos)."""
        # Proteção contra race conditions
        self._loading_content = True
        try:
            self._clear_table_gallery()
            for widget in self.table_frame.winfo_children():
                widget.destroy()
            self._clear_zoom_font_cache(self.table_frame)

            details_tabview = ctk.CTkTabview(self.table_frame)
            details_tabview.pack(fill="both", expand=True, padx=5, pady=5)
            self._apply_tabview_selected_text_theme(details_tabview)
            perfis_tab = details_tabview.add("Perfis")
            afc_tab = details_tabview.add("AFC Perfis")
            variaveis_tab = details_tabview.add("Variáveis")
            segmentos_tab = details_tabview.add("Segmentos")

            if not profiles:
                placeholder = ctk.CTkLabel(
                    self.table_frame,
                    text="Perfis CHD indisponíveis.",
                    font=FONTS['body'],
                    text_color=COLORS['text_secondary'],
                )
                placeholder.pack(expand=True)
                return

            class_tabview = ctk.CTkTabview(perfis_tab)
            class_tabview.pack(fill="both", expand=True, padx=4, pady=4)
            self._apply_tabview_selected_text_theme(class_tabview)

            for class_id in sorted(profiles):
                class_size = class_sizes.get(class_id, 0)
                tab = class_tabview.add(f"Classe {class_id} ({class_size})")
                rows = profiles.get(class_id, [])[:top_n]

                header = ctk.CTkLabel(
                    tab,
                    text="Palavra | Chi² | Freq | % Classe | Sinal",
                    font=FONTS['heading'],
                    anchor="w",
                )
                header.pack(fill="x", padx=10, pady=(10, 4))

                body = ctk.CTkTextbox(tab, font=FONTS['mono'], wrap="none", height=340)
                body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

                lines = []
                for row in rows:
                    word, chi2, freq, pct, sign = row
                    lines.append(
                        f"{word:<20} {chi2:>8.3f} {int(freq):>6} {pct:>9.2f}% {sign:>3}"
                    )
                body.insert("1.0", "\n".join(lines) if lines else "Sem termos para esta classe.")
                body.configure(state="disabled")

            afc_path = None
            if result is not None:
                afc_path = (
                    getattr(result, "profile_afc_path", None)
                    or getattr(result, "native_profile_afc_path", None)
                    or getattr(result, "polished_profile_afc_path", None)
                    or getattr(result, "afc_graph_path", None)
                )
            self._current_chd_afc_path = Path(afc_path) if afc_path else None
            if self._current_chd_afc_path and self._current_chd_afc_path.exists():
                self._render_inline_image(
                    parent=afc_tab,
                    image_path=self._current_chd_afc_path,
                    fallback_text="Falha ao carregar gráfico AFC Perfis pós-CHD.",
                )
            else:
                ctk.CTkLabel(
                    afc_tab,
                    text="AFC Perfis pós-CHD indisponível para esta execução.",
                    font=FONTS["body"],
                    text_color=COLORS["text_secondary"],
                ).pack(expand=True, padx=8, pady=8)

            metadata_path = getattr(result, "metadata_profiles_path", None) if result is not None else None
            self._current_chd_metadata_path = Path(metadata_path) if metadata_path else None
            self._render_metadata_profiles(variaveis_tab, self._current_chd_metadata_path)

            self._current_chd_typical_segments = (
                dict(getattr(result, "typical_segments", {}) or {})
                if result is not None else {}
            )
            self._current_chd_antiprofiles = (
                dict(getattr(result, "antiprofiles", {}) or {})
                if result is not None else {}
            )
            self._current_chd_repeated_segments = (
                dict(getattr(result, "repeated_segments", {}) or {})
                if result is not None else {}
            )
            self._render_chd_segments(segmentos_tab)

            class_text_paths_raw = getattr(result, "class_text_paths", {}) if result is not None else {}
            self._current_chd_class_texts = {}
            if isinstance(class_text_paths_raw, dict):
                for class_id, path in class_text_paths_raw.items():
                    try:
                        self._current_chd_class_texts[int(class_id)] = Path(path)
                    except Exception:
                        continue

            colored_path = getattr(result, "colored_corpus_path", None) if result is not None else None
            self._current_chd_colored_path = Path(colored_path) if colored_path else None

            actions_frame = ctk.CTkFrame(self.table_frame, fg_color="transparent")
            actions_frame.pack(fill="x", padx=6, pady=(0, 6))
            ctk.CTkButton(
                actions_frame,
                text="Exportar Classe",
                width=150,
                command=self._export_chd_class_texts,
                state="normal" if self._current_chd_class_texts else "disabled",
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                actions_frame,
                text="Corpus Colorido",
                width=150,
                command=self._export_chd_colored_corpus,
                state="normal" if (self._current_chd_colored_path and self._current_chd_colored_path.exists()) else "disabled",
            ).pack(side="left", padx=4)

            self._current_chd_profiles = profiles
            self._current_chd_class_sizes = class_sizes
            self._current_text = ""
            self._current_stats_dict = None
            self._current_table_path = None
            self._has_table_content = True
            
            # Garantir estado antes de renderizar (contrário de show_image, pois aqui construímos widgets)
            self.btn_export.configure(state="normal")
            
            # Renderização SÍNCRONA e robusta
            self._apply_zoom("Tabela", sync=False)
            self.tabview.set("Tabela")
            self.update_idletasks() # Força layout
            self._update_zoom_label("Tabela")
            self._sync_active_tab_state()
        finally:
            self._loading_content = False

    def _render_inline_image(self, parent, image_path: Path, fallback_text: str) -> None:
        """Renderiza imagem em aba interna de forma simplificada."""
        try:
            display_path, _ = self._resolve_display_image_path(image_path)
            if display_path is None:
                raise ValueError("SVG sem fallback PNG")
            with Image.open(display_path) as loaded_image:
                img = loaded_image.copy()
            widget_scaling = self._get_widget_scaling(parent)
            max_width = 620
            max_height = 380
            logical_max_width = max(180, int(max_width / widget_scaling))
            logical_max_height = max(120, int(max_height / widget_scaling))
            ratio = min(logical_max_width / img.width, logical_max_height / img.height)
            if ratio < 1:
                img = img.resize(
                    (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                    Image.Resampling.LANCZOS,
                )
            ctk_image = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            label = ctk.CTkLabel(parent, text="", image=ctk_image)
            label.image = ctk_image
            label.pack(expand=True, padx=8, pady=8)
        except Exception:
            ctk.CTkLabel(
                parent,
                text=fallback_text,
                font=FONTS["body"],
                text_color=COLORS["text_secondary"],
            ).pack(expand=True, padx=8, pady=8)

    def _get_widget_scaling(self, widget) -> float:
        """Retorna fator de escala efetivo do customtkinter para o widget."""
        try:
            scale = float(ctk.ScalingTracker.get_widget_scaling(widget))
            if scale > 0:
                return scale
        except Exception:
            pass
        return 1.0

    def _ctk_image_display_size(self, pixel_size: Tuple[int, int]) -> Tuple[int, int]:
        """Converte pixels reais para tamanho lógico do CTkImage.

        CTkImage aplica a escala do Windows/CustomTkinter ao tamanho informado.
        Se o tamanho físico do bitmap for passado diretamente em telas 125% ou
        150%, a imagem é ampliada novamente dentro do CTkLabel e acaba cortada.
        """
        width, height = int(pixel_size[0]), int(pixel_size[1])
        try:
            scale = self._get_widget_scaling(self.image_label)
        except Exception:
            scale = 1.0
        scale = max(0.25, float(scale or 1.0))
        return (
            max(1, int(round(width / scale))),
            max(1, int(round(height / scale))),
        )

    def _cancel_pending_image_autofit(self) -> None:
        """Cancela tarefa pendente de autoajuste de imagem."""
        job_id = self._pending_image_autofit_job
        if job_id is not None:
            try:
                self.after_cancel(job_id)
            except Exception:
                pass
        self._pending_image_autofit_job = None

    def _cancel_pending_graph_finalize(self) -> None:
        """Cancela tarefa pendente de finalização do gráfico."""
        job_id = self._pending_graph_finalize_job
        if job_id is not None:
            try:
                self.after_cancel(job_id)
            except Exception:
                pass
        self._pending_graph_finalize_job = None

    def _schedule_graph_finalize(self, delay_ms: int = 220) -> None:
        """Agenda ajuste final do gráfico após estabilização de layout."""
        if self._current_image_source is None:
            self._cancel_pending_graph_finalize()
            return
        self._cancel_pending_graph_finalize()
        try:
            self._pending_graph_finalize_job = self.after(
                max(40, int(delay_ms)),
                self._run_graph_finalize,
            )
        except Exception:
            self._pending_graph_finalize_job = None

    def _run_graph_finalize(self) -> None:
        """Força render final no gráfico preservando o autoajuste de encaixe."""
        self._pending_graph_finalize_job = None
        if self._current_image_source is None:
            return

        try:
            current_tab = self._current_content_tab()
        except Exception:
            current_tab = "Gráfico"
        if current_tab != "Gráfico":
            return

        try:
            self.tabview.set("Gráfico")
        except Exception:
            pass
        try:
            self.update_idletasks()
        except Exception:
            pass

        # Mantém o zoom de "Ajustar" e evita regressão para zoom padrão (ex.: 70%).
        try:
            self._fit_image_to_view(sync=False, allow_below_min=True)
        except Exception:
            pass
        self._render_current_image(sync=False)
        self._update_zoom_label("Gráfico")
        self._sync_active_tab_state()

    def _schedule_image_autofit(self, delay_ms: int = 80) -> None:
        """Agenda autoajuste após estabilização de layout para evitar cortes."""
        if self._current_image_source is None:
            self._pending_image_autofit = False
            self._pending_image_autofit_attempts = 0
            self._cancel_pending_image_autofit()
            return
        self._cancel_pending_image_autofit()
        try:
            self._pending_image_autofit_job = self.after(
                max(20, int(delay_ms)),
                self._run_pending_image_autofit,
            )
        except Exception:
            self._pending_image_autofit_job = None

    def _run_pending_image_autofit(self) -> None:
        """Executa autoajuste adiado quando o canvas já tem dimensões confiáveis."""
        self._pending_image_autofit_job = None
        if self._current_image_source is None:
            self._pending_image_autofit = False
            self._pending_image_autofit_attempts = 0
            return
        raw_width = int(self.image_canvas.winfo_width())
        raw_height = int(self.image_canvas.winfo_height())
        if (raw_width < 120 or raw_height < 120) and self._pending_image_autofit_attempts < 8:
            self._pending_image_autofit_attempts += 1
            self._schedule_image_autofit(delay_ms=100)
            return
        self._fit_image_to_view(sync=False, allow_below_min=True)
        current_tab = self.tabview.get()
        self._update_zoom_label(str(current_tab))
        self._sync_active_tab_state()
        self._pending_image_autofit = False
        self._pending_image_autofit_attempts = 0

    def _render_metadata_profiles(self, parent, metadata_path: Optional[Path]) -> None:
        """Renderiza tabela textual de variaveis x classes."""
        text_widget = ctk.CTkTextbox(parent, font=FONTS["mono"], wrap="none", height=340)
        text_widget.pack(fill="both", expand=True, padx=8, pady=8)
        if not metadata_path or not metadata_path.exists():
            text_widget.insert("1.0", "Perfil de variáveis indisponível.")
            text_widget.configure(state="disabled")
            return

        lines = ["variável | classe | chi² | freq | %classe | sinal", "-" * 70]
        with metadata_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file, delimiter=";")
            for row in reader:
                variable = row.get("variable", "")
                class_id = row.get("class_id", "")
                chi2 = row.get("chi2", "")
                freq = row.get("freq", "")
                pct = row.get("pct_in_class", "")
                sign = row.get("sign", "")
                lines.append(
                    f"{variable:<24} {class_id:>3} {chi2:>10} {freq:>6} {pct:>10} {sign:>4}"
                )
        text_widget.insert("1.0", "\n".join(lines))
        text_widget.configure(state="disabled")

    def _render_chd_segments(self, parent) -> None:
        """Renderiza segmentos típicos e antiperfis por classe."""
        text_widget = ctk.CTkTextbox(parent, font=FONTS["mono"], wrap="word", height=340)
        text_widget.pack(fill="both", expand=True, padx=8, pady=8)

        repeated = self._current_chd_repeated_segments or {}
        typical = self._current_chd_typical_segments or {}
        if not typical and not repeated:
            text_widget.insert("1.0", "Segmentos indisponíveis.")
            text_widget.configure(state="disabled")
            return

        lines: List[str] = []
        class_ids = sorted(set(typical.keys()) | set(repeated.keys()))
        for class_id in class_ids:
            lines.append(f"[Classe {class_id}] Segmentos típicos")
            segments = typical.get(class_id, [])
            if not segments:
                lines.append("  (sem segmentos típicos)")
            for idx, item in enumerate(segments[:10], start=1):
                text, score = item
                preview = str(text).replace("\n", " ").strip()
                if len(preview) > 180:
                    preview = preview[:180] + "..."
                lines.append(f"  {idx:>2}. score={float(score):.3f} | {preview}")

            anti = self._current_chd_antiprofiles.get(class_id, [])
            if anti:
                anti_preview = ", ".join(f"{word}({chi2:.2f})" for word, chi2, *_ in anti[:8])
                lines.append(f"  Antiperfis: {anti_preview}")
            repeated_segments = repeated.get(class_id, [])
            if repeated_segments:
                lines.append("  Segmentos repetidos:")
                for idx, (ngram, freq, chi2) in enumerate(repeated_segments[:15], start=1):
                    lines.append(f"    {idx:>2}. freq={int(freq):>3} chi²={float(chi2):.2f} | {ngram}")
            lines.append("")

        text_widget.insert("1.0", "\n".join(lines).strip())
        text_widget.configure(state="disabled")

    def _export_chd_class_texts(self) -> None:
        """Exporta texto de uma classe CHD selecionada pelo usuario."""
        from tkinter import filedialog, messagebox

        if not self._current_chd_class_texts:
            messagebox.showwarning("Exportar Classe", "Nao ha textos de classe disponiveis.")
            return

        class_ids = sorted(self._current_chd_class_texts.keys())
        class_list = ", ".join(str(class_id) for class_id in class_ids)
        target = filedialog.asksaveasfilename(
            title=f"Exportar Classe CHD (classes disponíveis: {class_list})",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not target:
            return

        target_path = Path(target)
        source = self._current_chd_class_texts.get(class_ids[0])
        if source is None:
            return
        if len(class_ids) == 1:
            shutil.copy2(source, target_path)
            return

        # Se existem varias classes, exporta um pacote TXT unico com separadores.
        lines: List[str] = []
        for class_id in class_ids:
            class_path = self._current_chd_class_texts[class_id]
            if not class_path.exists():
                continue
            lines.append(f"[Classe {class_id}]")
            lines.append(class_path.read_text(encoding="utf-8", errors="replace"))
            lines.append("")
        target_path.write_text("\n".join(lines).strip(), encoding="utf-8")

    def _export_chd_colored_corpus(self) -> None:
        """Exporta HTML de corpus colorido."""
        from tkinter import filedialog, messagebox

        if not self._current_chd_colored_path or not self._current_chd_colored_path.exists():
            messagebox.showwarning("Corpus Colorido", "Arquivo HTML de corpus colorido indisponível.")
            return
        target = filedialog.asksaveasfilename(
            title="Exportar Corpus Colorido",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("Todos", "*.*")],
        )
        if not target:
            return
        shutil.copy2(self._current_chd_colored_path, Path(target))

    def _current_content_tab(self) -> str:
        """Retorna nome da aba de conteúdo ativa."""
        try:
            return ResultViewContract.normalize_content_tab(self.tabview.get() or "Gráfico")
        except Exception:
            return "Gráfico"

    def _update_zoom_label(self, tab_name: Optional[str] = None) -> None:
        """Atualiza rótulo de zoom da aba ativa."""
        active_tab = tab_name or self._current_content_tab()
        zoom_value = int(self._zoom_levels.get(active_tab, 100))
        self.zoom_label.configure(text=f"{zoom_value}%")

    def _on_content_tab_changed(self, _value: Optional[str] = None) -> None:
        """Sincroniza controles quando usuário troca aba de conteúdo."""
        # Não redirecionar durante restauração de estado para evitar loops
        if self._restoring_analysis_tab:
            return
        active_tab = self._current_content_tab()
        if active_tab == "Gráfico" and self._current_image_source is None:
            # Não há imagem, redirecionar para outra aba
            if self._has_table_content or self._current_chd_profiles:
                try:
                    self.tabview.set("Tabela")
                    active_tab = "Tabela"
                except Exception:
                    pass
            elif self._current_text.strip():
                try:
                    self.tabview.set("Estatísticas")
                    active_tab = "Estatísticas"
                except Exception:
                    pass
        self._apply_zoom(active_tab, sync=False)
        self._update_zoom_label(active_tab)
        self._refresh_content_tab_text_colors()
        self._apply_tabview_selected_text_theme(self.tabview)
        self._update_data_export_button_state()

    def _normalize_data_export_sources(
        self,
        source: Optional[Union[str, Path, List[Any], Tuple[Any, ...], Dict[str, Any]]],
    ) -> List[Path]:
        """Normaliza entrada de exportação em caminhos válidos e únicos."""
        if not source:
            return []
        if isinstance(source, dict):
            raw_items = list(source.values())
        elif isinstance(source, (list, tuple, set)):
            raw_items = list(source)
        else:
            raw_items = [source]

        normalized: List[Path] = []
        seen: set[str] = set()
        for item in raw_items:
            if not item:
                continue
            try:
                candidate = Path(item)
            except Exception:
                continue
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                key = str(candidate.resolve())
            except Exception:
                key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(candidate)
        return normalized

    def set_data_export_source(
        self,
        path: Optional[Union[str, Path, List[Any], Tuple[Any, ...], Dict[str, Any]]],
    ) -> None:
        """Define artefato(s) de dados disponível(is) para exportação dedicada."""
        sources = self._normalize_data_export_sources(path)
        self._current_data_export_sources = sources
        self._current_data_export_path = sources[0] if sources else None
        self._update_data_export_button_state()
        self._sync_active_tab_state()

    def _update_data_export_button_state(self) -> None:
        """Habilita exportação de dados quando há um artefato válido."""
        valid_sources = [
            candidate
            for candidate in self._current_data_export_sources
            if candidate is not None and candidate.exists() and candidate.is_file()
        ]
        if not valid_sources and self._current_data_export_path is not None:
            if self._current_data_export_path.exists() and self._current_data_export_path.is_file():
                valid_sources = [self._current_data_export_path]
        self._current_data_export_sources = valid_sources
        self._current_data_export_path = valid_sources[0] if valid_sources else None
        has_data = bool(valid_sources)
        self.btn_export_data.configure(state="normal" if has_data else "disabled")

    @staticmethod
    def _lighten_hex_color(color: str, factor: float = 0.22) -> str:
        """Clareia cor hexadecimal misturando com branco (0..1)."""
        raw = str(color or "").strip()
        if not raw.startswith("#") or len(raw) != 7:
            return "#2B88D8"
        try:
            r = int(raw[1:3], 16)
            g = int(raw[3:5], 16)
            b = int(raw[5:7], 16)
            k = max(0.0, min(1.0, float(factor)))
            lr = int(round(r + (255 - r) * k))
            lg = int(round(g + (255 - g) * k))
            lb = int(round(b + (255 - b) * k))
            return f"#{lr:02X}{lg:02X}{lb:02X}"
        except Exception:
            return "#2B88D8"

    def _apply_content_tab_theme(self) -> None:
        """Aplica paleta mais legível para abas de conteúdo."""
        colors = get_current_colors()
        selected = self._lighten_hex_color(colors.get("primary", "#0067C0"), factor=0.22)
        selected_hover = self._lighten_hex_color(colors.get("primary", "#0067C0"), factor=0.30)
        unselected = colors.get("button", "#FFFFFF")
        unselected_hover = colors.get("button_hover", "#F5F5F5")
        frame_bg = colors.get("surface", "#F5F5F5")
        text_unselected = colors.get("text", "#1A1A1A")

        try:
            self.tabview.configure(
                segmented_button_fg_color=frame_bg,
                segmented_button_selected_color=selected,
                segmented_button_selected_hover_color=selected_hover,
                segmented_button_unselected_color=unselected,
                segmented_button_unselected_hover_color=unselected_hover,
                segmented_button_selected_text_color=("#FFFFFF", "#FFFFFF"),
                segmented_button_unselected_text_color=text_unselected,
            )
        except Exception:
            pass
        self._apply_tabview_selected_text_theme(self.tabview)

    def _apply_tabview_selected_text_theme(self, tabview: Any) -> None:
        """Força texto branco na aba selecionada em qualquer CTkTabview."""
        if tabview is None:
            return
        try:
            tabview.configure(segmented_button_selected_text_color=("#FFFFFF", "#FFFFFF"))
        except Exception:
            pass

        def _apply_button_colors() -> None:
            try:
                segmented = getattr(tabview, "_segmented_button", None)
                buttons_dict = getattr(segmented, "_buttons_dict", {}) if segmented is not None else {}
                try:
                    current = str(tabview.get() or "")
                except Exception:
                    current = ""
                default_text = get_themed_color("text")
                for name, button in buttons_dict.items():
                    is_active = str(name) == current
                    button.configure(
                        text_color=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                        text_color_disabled=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                    )
            except Exception:
                pass

        try:
            self.after(0, _apply_button_colors)
        except Exception:
            _apply_button_colors()

    def _refresh_content_tab_text_colors(self) -> None:
        """Garante texto claro na aba ativa e texto padrão nas inativas."""
        try:
            segmented = getattr(self.tabview, "_segmented_button", None)
            buttons_dict = getattr(segmented, "_buttons_dict", {}) if segmented is not None else {}
            active = self._current_content_tab()
            text_default = get_themed_color("text")
            for name, button in buttons_dict.items():
                is_active = str(name) == active
                button.configure(
                    text_color=("#FFFFFF", "#FFFFFF") if is_active else text_default,
                    text_color_disabled=("#FFFFFF", "#FFFFFF") if is_active else text_default,
                )
        except Exception:
            pass

    def _adjust_zoom(self, delta: int) -> None:
        """Incrementa/decrementa zoom na aba ativa."""
        active_tab = self._current_content_tab()
        current = int(self._zoom_levels.get(active_tab, 100))
        self._set_zoom(active_tab, current + int(delta))

    def _set_zoom(
        self,
        tab_name: str,
        value: int,
        sync: bool = True,
        min_override: Optional[int] = None,
    ) -> None:
        """Define nível de zoom para uma aba de conteúdo."""
        tab_key = str(tab_name or "Gráfico")
        min_value = max(1, int(min_override)) if min_override is not None else self._zoom_min
        clamped = max(min_value, min(self._zoom_max, int(value)))
        self._zoom_levels[tab_key] = clamped
        self._apply_zoom(tab_key, sync=sync)
        self._update_zoom_label(tab_key)

    def _set_zoom_one_to_one(self) -> None:
        """Restaura zoom 100% da aba ativa."""
        self._set_zoom(self._current_content_tab(), 100)

    def set_graph_zoom_percent(
        self,
        value: int,
        sync: bool = False,
        persist: bool = True,
    ) -> None:
        """Define zoom da aba Gráfico com persistência opcional no snapshot ativo."""
        self._set_zoom("Gráfico", int(value), sync=sync)
        if persist:
            self._sync_active_tab_state()

    def _fit_current_view(self) -> None:
        """Ajusta zoom para caber no espaço visível da aba ativa."""
        active_tab = self._current_content_tab()
        if active_tab == "Gráfico":
            self._fit_image_to_view(sync=True, allow_below_min=True)
            return
        self._set_zoom(active_tab, 100)

    def _fit_image_to_view(
        self,
        sync: bool = True,
        allow_below_min: bool = False,
        allow_upscale: bool = False,
    ) -> None:
        """Calcula zoom para encaixar imagem disponível na área visível."""
        if self._current_image_source is None:
            self._set_zoom("Gráfico", 100, sync=sync)
            return
        # Processa layout pendente antes de medir canvas.
        try:
            self.update_idletasks()
        except Exception:
            pass
        raw_width = int(self.image_canvas.winfo_width())
        raw_height = int(self.image_canvas.winfo_height())
        # Se os valores são muito pequenos, usar defaults baseados na janela principal
        if raw_width < 100 or raw_height < 100:
            try:
                toplevel = self.winfo_toplevel()
                avail_width = max(600, int(toplevel.winfo_width() * 0.5))
                avail_height = max(400, int(toplevel.winfo_height() * 0.6))
            except Exception:
                avail_width = 800
                avail_height = 500
        else:
            avail_width = max(220, raw_width - 24)
            avail_height = max(180, raw_height - 24)
        widget_scaling = self._get_widget_scaling(self.image_label)
        avail_width = max(1.0, float(avail_width) / widget_scaling)
        avail_height = max(1.0, float(avail_height) / widget_scaling)
        img_width, img_height = self._current_image_source.size
        if img_width <= 0 or img_height <= 0:
            self._set_zoom("Gráfico", 100, sync=sync)
            return
        fit_ratio = min(avail_width / img_width, avail_height / img_height)
        if not allow_upscale:
            # Permite um leve upscale (ate 1.3x) quando a imagem é menor que
            # o viewport — usa mais area util sem degradacao percebida de
            # nitidez. Graficos de rede costumam ficar entre 50% e 70% do
            # canvas; 1.3x os leva para proximo de 100% do viewport.
            fit_ratio = min(fit_ratio, 1.3)
        fit_zoom = int(round(fit_ratio * 100))
        min_zoom = self._zoom_fit_min if allow_below_min else self._zoom_min
        target_zoom = fit_zoom if fit_zoom > 0 else 100
        self._set_zoom("Gráfico", target_zoom, sync=sync, min_override=min_zoom)

    def _apply_zoom(self, tab_name: str, sync: bool = True) -> None:
        """Aplica zoom para a aba informada."""
        tab_key = str(tab_name or "Gráfico")
        if tab_key == "Gráfico":
            self._render_current_image(sync=sync)
            return
        if tab_key == "Estatísticas":
            font = self._scaled_font(FONTS["mono"], self._zoom_levels.get("Estatísticas", 100))
            self.text_box.configure(font=font)
        elif tab_key == "Tabela":
            scale = float(self._zoom_levels.get("Tabela", 100)) / 100.0
            self._apply_table_tree_zoom(scale)
            self._apply_font_zoom_recursive(self.table_frame, scale)
        if sync:
            self._sync_active_tab_state()

    def _render_current_image(self, sync: bool = True) -> None:
        """Renderiza imagem ativa considerando zoom atual."""
        if self._current_image_source is None:
            self._last_render_source_id = None
            self._last_render_size = None
            current_text = str(self.image_label.cget("text") or "").strip()
            self._set_graph_placeholder(current_text)
            try:
                cw = max(1, int(self.image_canvas.winfo_width()))
                ch = max(1, int(self.image_canvas.winfo_height()))
                self.image_canvas.itemconfigure(
                    self._image_canvas_window,
                    width=cw,
                    height=ch,
                )
                # Placeholder: label preenche image_inner (centraliza texto).
                self.image_label.place_configure(x=0, y=0, width=cw, height=ch)
            except Exception:
                pass
            try:
                self.image_canvas.xview_moveto(0.0)
                self.image_canvas.yview_moveto(0.0)
            except Exception:
                pass
            self._refresh_image_scrollregion()
            if sync:
                self._sync_active_tab_state()
            return
        zoom = float(self._zoom_levels.get("Gráfico", 100)) / 100.0
        base = self._current_image_source
        width = max(1, int(base.width * zoom))
        height = max(1, int(base.height * zoom))
        max_dim = 4096
        top_size = max(width, height)
        if top_size > max_dim:
            ratio = max_dim / top_size
            width = max(1, int(width * ratio))
            height = max(1, int(height * ratio))
        source_id = id(base)
        target_size = (width, height)
        display_size = self._ctk_image_display_size(target_size)
        if (
            self._current_image is None
            or self._last_render_source_id != source_id
            or self._last_render_size != target_size
            or self._last_render_display_size != display_size
        ):
            # Prioriza nitidez para gráficos/texto, evitando aspecto apagado.
            resample_filter = (
                Image.Resampling.BICUBIC
                if (width * height) > 2_500_000
                else Image.Resampling.LANCZOS
            )
            resized = base.resize(target_size, resample_filter)
            ctk_image = ctk.CTkImage(light_image=resized, dark_image=resized, size=display_size)
            self._current_image = ctk_image
            try:
                self.image_label.configure(image=ctk_image, text="")
            except Exception:
                # Recuperação para estados em que a referência de imagem interna ficou inválida.
                try:
                    inner_label = getattr(self.image_label, "_label", None)
                    if inner_label is not None:
                        inner_label.configure(image="")
                    else:
                        self.image_label.configure(image="")
                    self.image_label.configure(image=ctk_image, text="")
                except Exception:
                    self._set_graph_placeholder("Falha ao renderizar gráfico.")
                    return
            # Manter referência extra para evitar garbage collection
            self.image_label._displayed_image = ctk_image
            self._last_render_source_id = source_id
            self._last_render_size = target_size
            self._last_render_display_size = display_size

        # O tamanho do image_inner DEVE ser exatamente o tamanho em pixels da
        # imagem (width/height já incluem o zoom). Usar reqwidth/reqheight do
        # CTkLabel inflacionava image_inner em displays com DPI-scaling,
        # fazendo o CTkLabel interno recentralizar a imagem e criar espaço
        # morto acima/abaixo.
        try:
            self.image_label.update_idletasks()
        except Exception:
            pass
        window_width = width
        window_height = height
        # Garante que o próprio image_label fica no tamanho da imagem,
        # ancorado em (0,0), evitando que um frame maior o centralize.
        try:
            self.image_label.place_configure(x=0, y=0, width=window_width, height=window_height)
        except Exception:
            pass
        # Centraliza image_inner no canvas quando a imagem é menor que o
        # viewport — ocupa o espaço vazio ao redor sem afetar o scroll
        # quando a imagem é maior (nesse caso offset=0 e scrollregion cobre).
        try:
            self._center_canvas_window(window_width, window_height)
        except Exception:
            pass

        try:
            self.image_canvas.itemconfigure(
                self._image_canvas_window,
                width=window_width,
                height=window_height,
            )
        except Exception:
            pass
        self._refresh_image_scrollregion()
        try:
            self.image_canvas.xview_moveto(0.0)
            self.image_canvas.yview_moveto(0.0)
        except Exception:
            pass
        if sync:
            self._sync_active_tab_state()

    def _scaled_font(self, base_font: Tuple[Any, ...], zoom_value: int) -> Tuple[Any, ...]:
        """Retorna fonte escalada preservando estilo base."""
        if not isinstance(base_font, tuple) or len(base_font) < 2:
            return base_font
        try:
            base_size = int(base_font[1])
        except (TypeError, ValueError):
            return base_font
        new_size = max(8, int(round(base_size * (float(zoom_value) / 100.0))))
        return (base_font[0], new_size, *base_font[2:])

    def _clear_zoom_font_cache(self, widget) -> None:
        """Remove cache de fontes base usada no zoom recursivo."""
        if hasattr(widget, "_zoom_base_font"):
            try:
                delattr(widget, "_zoom_base_font")
            except Exception:
                pass
        for child in widget.winfo_children():
            self._clear_zoom_font_cache(child)

    def _apply_font_zoom_recursive(self, widget, scale: float) -> None:
        """Aplica zoom recursivo em widgets textuais da aba de tabela."""
        if hasattr(widget, "cget"):
            try:
                current_font = widget.cget("font")
            except Exception:
                current_font = None
            if current_font:
                base_font = getattr(widget, "_zoom_base_font", None)
                if base_font is None:
                    if isinstance(current_font, tuple) and len(current_font) >= 2:
                        base_font = tuple(current_font)
                    elif isinstance(current_font, list) and len(current_font) >= 2:
                        base_font = tuple(current_font)
                    if base_font is not None:
                        setattr(widget, "_zoom_base_font", base_font)
                if base_font is not None and len(base_font) >= 2:
                    try:
                        base_size = int(base_font[1])
                        new_size = max(8, int(round(base_size * scale)))
                        widget.configure(font=(base_font[0], new_size, *base_font[2:]))
                    except Exception:
                        pass
        for child in widget.winfo_children():
            self._apply_font_zoom_recursive(child, scale)
    
    def clear(self, sync: bool = True, force: bool = False) -> None:
        """Limpa todos os resultados."""
        # Se estamos carregando conteúdo novo, não limpar para evitar race conditions
        if self._loading_content and not force:
            return

        self._cancel_pending_image_autofit()
        self._cancel_pending_graph_finalize()
        self._pending_image_autofit = False
        self._pending_image_autofit_attempts = 0
        self._clear_image_gallery()
        self._current_voyant_payload = {}
        self._clear_table_gallery()
        self._current_table_treeview = None

        self._set_graph_placeholder()
        self._current_image_source = None
        self._current_image_base_source = None
        self._current_image_path = None
        self._active_image_color_key = None
        self._color_overrides = {}
        self._dominant_palette = []
        self._set_color_tool_enabled(False)
        self._last_render_source_id = None
        self._last_render_size = None
        self._refresh_image_scrollregion()
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", "Nenhuma estatística disponível.")
        self.text_box.configure(state="disabled")
        self._current_text = ""
        self._current_data_export_path = None
        self._current_data_export_sources = []
        self._current_stats_dict = None
        
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        self._clear_zoom_font_cache(self.table_frame)
        self.table_placeholder = ctk.CTkLabel(
            self.table_frame,
            text="Nenhuma tabela para exibir.",
            font=FONTS['body'],
            text_color=COLORS['text'],
            fg_color="transparent",
        )
        self.table_placeholder.pack(fill="both", expand=True)
        self._current_table_path = None
        self._has_table_content = False
        self._reset_chd_context()
        self._clear_report()
        self._zoom_levels = dict(self._default_zoom_levels)
        self._update_zoom_label()
        
        self.btn_export.configure(state="disabled")
        self.btn_export_data.configure(state="disabled")
        if sync:
            self._sync_active_tab_state()

    def set_report_path(self, path: Optional[Union[str, Path]]) -> None:
        """Define caminho do relatório HTML atual (abertura no navegador)."""
        if not path:
            self._clear_report()
            return
        report_path = Path(path)
        if report_path.exists() and report_path.is_file():
            self._current_report_path = report_path
            self.btn_report.configure(state="normal")
        else:
            self._clear_report()
        self._sync_active_tab_state()

    def _show_report_fallback(self, report_path: Path) -> None:
        """Exibe conteúdo do relatório como texto quando HtmlFrame não está disponível."""
        if self._report_text_fallback is None:
            return
        try:
            import re

            html_content = report_path.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                text = f"Relatório disponível em:\n{report_path}"
            self._report_text_fallback.configure(state="normal")
            self._report_text_fallback.delete("1.0", "end")
            self._report_text_fallback.insert("1.0", text)
            self._report_text_fallback.configure(state="disabled")
        except Exception as exc:
            log.warning("Fallback de relatório falhou: %s", exc)

    def _clear_report(self) -> None:
        """Limpa relatório associado ao resultado atual."""
        self._current_report_path = None
        if hasattr(self, "btn_report"):
            self.btn_report.configure(state="disabled")
        if self._report_text_fallback is not None:
            self._report_text_fallback.configure(state="normal")
            self._report_text_fallback.delete("1.0", "end")
            self._report_text_fallback.insert(
                "1.0",
                "Nenhum relatório disponível.\n\nExecute uma análise para gerar o relatório.",
            )
            self._report_text_fallback.configure(state="disabled")

    def _open_report(self) -> None:
        """Abre o relatório HTML no navegador padrão."""
        if not self._current_report_path or not self._current_report_path.exists():
            messagebox.showwarning(
                "Relatório",
                "Não há relatório disponível para o resultado atual.",
            )
            return
        try:
            webbrowser.open(self._current_report_path.resolve().as_uri(), new=2)
        except Exception as exc:
            messagebox.showerror(
                "Erro ao abrir relatório",
                (
                    "O que aconteceu: Falha ao abrir o relatório HTML.\n"
                    f"Por que aconteceu: {exc}\n"
                    "Como resolver: Verifique o navegador padrão e tente novamente."
                ),
            )

    def open_report(self) -> None:
        """API pública para abrir o relatório associado ao resultado atual."""
        self._open_report()

    def _reset_chd_context(self) -> None:
        """Limpa estado auxiliar de visualizacao CHD."""
        self._current_chd_profiles = None
        self._current_chd_class_sizes = None
        self._current_chd_afc_path = None
        self._current_chd_metadata_path = None
        self._current_chd_colored_path = None
        self._current_chd_class_texts = {}
        self._current_chd_typical_segments = {}
        self._current_chd_antiprofiles = {}
        self._current_chd_repeated_segments = {}

    def _export_current_graph_png(self, target_path: Path) -> None:
        """Exporta gráfico atual como PNG."""
        has_color_customization = bool(self._color_overrides)
        if has_color_customization and self._current_image_path and self._current_image_path.exists():
            with Image.open(self._current_image_path) as original:
                recolored = self._apply_color_overrides_to_image(original.copy())
                recolored.save(target_path, format="PNG")
            return
        if has_color_customization and self._current_image_source is not None:
            self._current_image_source.save(target_path, format="PNG")
            return
        if self._current_image_path and self._current_image_path.exists():
            with Image.open(self._current_image_path) as img:
                img.save(target_path, format="PNG")
            return
        if self._current_image_source is not None:
            self._current_image_source.save(target_path, format="PNG")
            return
        raise FileNotFoundError("Gráfico indisponível para exportação.")
    
    def _export_result(self) -> None:
        """Exporta resultado atual."""
        from tkinter import filedialog, messagebox

        try:
            current_tab = self.tabview.get()

            if current_tab == "Gráfico" and self._current_image_path and self._current_image_path.exists():
                filepath = filedialog.asksaveasfilename(
                    title="Exportar Gráfico",
                    defaultextension=".png",
                    filetypes=[
                        ("PNG", "*.png"),
                        ("Todos", "*.*"),
                    ],
                )
                if filepath:
                    target = Path(filepath)
                    if target.suffix.lower() != ".png":
                        target = target.with_suffix(".png")
                    self._export_current_graph_png(target)
                return

            if current_tab == "Tabela" and self._current_table_path and self._current_table_path.exists():
                filepath = filedialog.asksaveasfilename(
                    title="Exportar Tabela",
                    defaultextension=".csv",
                    filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
                )
                if filepath:
                    shutil.copy2(self._current_table_path, filepath)
                return

            if current_tab == "Tabela" and self._current_chd_profiles:
                filepath = filedialog.asksaveasfilename(
                    title="Exportar Perfis CHD",
                    defaultextension=".csv",
                    filetypes=[("CSV", "*.csv"), ("TXT", "*.txt"), ("Todos", "*.*")],
                )
                if not filepath:
                    return
                export_path = Path(filepath)
                if export_path.suffix.lower() == ".txt":
                    lines = []
                    for class_id in sorted(self._current_chd_profiles):
                        lines.append(f"[Classe {class_id}]")
                        for word, chi2, freq, pct, sign in self._current_chd_profiles[class_id]:
                            lines.append(f"{word}\t{chi2:.6f}\t{freq}\t{pct:.4f}\t{sign}")
                        lines.append("")
                    export_path.write_text("\n".join(lines), encoding="utf-8")
                else:
                    with export_path.open("w", encoding="utf-8", newline="") as file:
                        writer = csv.writer(file, delimiter=";")
                        writer.writerow(["class_id", "word", "chi2", "freq", "pct_in_class", "sign"])
                        for class_id in sorted(self._current_chd_profiles):
                            for word, chi2, freq, pct, sign in self._current_chd_profiles[class_id]:
                                writer.writerow([class_id, word, f"{chi2:.6f}", freq, f"{pct:.4f}", sign])
                return

            if current_tab == "Estatísticas" and self._current_text.strip():
                filepath = filedialog.asksaveasfilename(
                    title="Exportar Texto",
                    defaultextension=".txt",
                    filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
                )
                if filepath:
                    Path(filepath).write_text(self._current_text, encoding="utf-8")
                return

            messagebox.showwarning(
                "Exportar",
                "Nao ha resultado disponivel para exportacao.",
            )
        except Exception as exc:
            messagebox.showerror(
                "Erro ao exportar",
                (
                    "O que aconteceu: Falha ao exportar resultado.\n"
                    f"Por que aconteceu: {exc}\n"
                    "Como resolver: Escolha outro local de destino e tente novamente."
                ),
            )

    def _export_data_source(self) -> None:
        """Exporta artefato de dados associado ao resultado atual."""
        from tkinter import filedialog, messagebox

        sources = [
            candidate
            for candidate in self._current_data_export_sources
            if candidate is not None and candidate.exists() and candidate.is_file()
        ]
        if not sources and self._current_data_export_path is not None:
            if self._current_data_export_path.exists() and self._current_data_export_path.is_file():
                sources = [self._current_data_export_path]

        if not sources:
            messagebox.showwarning(
                "Exportar Dados",
                "Nao ha arquivo de dados disponivel para este resultado.",
            )
            self._update_data_export_button_state()
            return

        try:
            if len(sources) > 1:
                filepath = filedialog.asksaveasfilename(
                    title="Exportar Dados",
                    defaultextension=".zip",
                    initialfile="dados_exportados.zip",
                    filetypes=[("Pacote ZIP", "*.zip"), ("Todos", "*.*")],
                )
                if not filepath:
                    return
                target_path = Path(filepath)
                if target_path.suffix.lower() != ".zip":
                    target_path = target_path.with_suffix(".zip")
                used_names: set[str] = set()
                with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for source in sources:
                        arcname = source.name
                        if arcname in used_names:
                            stem = source.stem
                            suffix = source.suffix
                            idx = 2
                            while f"{stem}_{idx}{suffix}" in used_names:
                                idx += 1
                            arcname = f"{stem}_{idx}{suffix}"
                        used_names.add(arcname)
                        archive.write(source, arcname=arcname)
                return

            source = sources[0]
            source_suffix = source.suffix.lower()
            default_extension = source_suffix if source_suffix else ".txt"
            source_label = source_suffix[1:].upper() if source_suffix else "Arquivo"
            filetypes = [
                (source_label, f"*{source_suffix}"),
                ("Todos", "*.*"),
            ] if source_suffix else [("Todos", "*.*")]

            filepath = filedialog.asksaveasfilename(
                title="Exportar Dados",
                defaultextension=default_extension,
                initialfile=source.name,
                filetypes=filetypes,
            )
            if not filepath:
                return
            target_path = Path(filepath)
            if source_suffix and target_path.suffix.lower() != source_suffix:
                target_path = target_path.with_suffix(source_suffix)
            shutil.copy2(source, target_path)
        except Exception as exc:
            messagebox.showerror(
                "Erro ao exportar dados",
                (
                    "O que aconteceu: Falha ao exportar arquivo de dados.\n"
                    f"Por que aconteceu: {exc}\n"
                    "Como resolver: Escolha outro local de destino e tente novamente."
                ),
            )

    def get_active_analysis_tab(self) -> Optional[str]:
        """Retorna chave da aba de análise ativa."""
        return self._active_analysis_tab_key

    def get_analysis_tab_header_rect(self) -> Optional[Tuple[int, int, int, int]]:
        """Retorna retângulo absoluto da barra de abas de resultados."""
        frame = getattr(self, "analysis_tabs_frame", None)
        try:
            if frame is None or not frame.winfo_exists() or not frame.winfo_ismapped():
                return None
            self.update_idletasks()
            x1 = int(frame.winfo_rootx())
            y1 = int(frame.winfo_rooty())
            x2 = x1 + int(frame.winfo_width())
            y2 = y1 + int(frame.winfo_height())
            return x1, y1, x2, y2
        except Exception:
            return None

    def get_content_tab_button_rect(self, tab_name: str) -> Optional[Tuple[int, int, int, int]]:
        """Retorna retângulo (coordenadas de tela) do botão da aba de conteúdo."""
        try:
            segmented = getattr(self.tabview, "_segmented_button", None)
            if segmented is None:
                return None
            buttons_dict = getattr(segmented, "_buttons_dict", {}) or {}
            button = buttons_dict.get(str(tab_name))
            if button is None or not button.winfo_exists() or not button.winfo_ismapped():
                return None
            self.update_idletasks()
            x1 = int(button.winfo_rootx())
            y1 = int(button.winfo_rooty())
            x2 = x1 + int(button.winfo_width())
            y2 = y1 + int(button.winfo_height())
            return x1, y1, x2, y2
        except Exception:
            return None
