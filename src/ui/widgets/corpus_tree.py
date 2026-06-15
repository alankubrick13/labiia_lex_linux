"""
Widget de arvore de corpus para exibir estrutura e acoes contextuais.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any, List, Callable

import customtkinter as ctk

from ..styles import FONTS, get_themed_color, get_current_colors, style_native_menu
from ..theme_bridge import apply_ttk_windows_styles
from ..component_factory import style_button
from ..iconography import label_with_icon
from ..tk_helpers import destroy_menu_safe


class CorpusTree(ctk.CTkFrame):
    """
    Widget para exibir estrutura do corpus.

    Mostra:
    - estatisticas resumidas
    - documentos (UCIs)
    - historico de analises com filhos
    - menu de contexto (right-click)
    """

    def __init__(
        self,
        parent,
        *,
        density: str = "compact",
        ui_v2_enabled: bool = False,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self._density = str(density or "comfortable").strip().lower()
        if self._density not in {"compact", "comfortable"}:
            self._density = "comfortable"
        self._ui_v2_enabled = bool(ui_v2_enabled)
        self._corpus = None
        self._history_entries: List[Any] = []
        self._history_callback: Optional[Callable[[Any], None]] = None
        self._action_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._export_callback: Optional[Callable[[], None]] = None
        self._history_item_map: Dict[str, Any] = {}
        self._item_payload_map: Dict[str, Dict[str, Any]] = {}
        self._history_node_id: Optional[str] = None
        self._corpus_root_id: Optional[str] = None
        self._context_menu: Optional[tk.Menu] = None
        self._configure_tree_style()
        self._create_widgets()

    def _configure_tree_style(self) -> None:
        """Aplica estilo visual do Treeview alinhado ao desktop Windows."""
        style = ttk.Style(self)
        try:
            available_themes = set(style.theme_names())
            if "vista" in available_themes:
                style.theme_use("vista")
            elif "xpnative" in available_themes:
                style.theme_use("xpnative")
        except Exception:
            pass

        apply_ttk_windows_styles(
            style,
            colors=get_current_colors(),
            fonts=FONTS,
            density=("compact" if self._density == "compact" else "comfortable"),
        )

    def _create_widgets(self):
        """Cria widgets internos."""
        self.title_label = ctk.CTkLabel(
            self,
            text="Estrutura do Corpus",
            font=FONTS["heading"],
        )
        self.title_label.pack(pady=(5, 10))

        self.tree_frame = ctk.CTkFrame(self)
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("valor",),
            show="tree headings",
            selectmode="browse",
            style="Lexi.Treeview",
        )
        self.tree.heading("#0", text="Item")
        self.tree.heading("valor", text="Valor")
        self.tree.column("#0", width=210)
        self.tree.column("valor", width=95)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        scrollbar = ttk.Scrollbar(
            self.tree_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.placeholder = ctk.CTkLabel(
            self,
            text="Nenhum corpus carregado.\n\nClique em 'Importar' para começar.",
            font=FONTS["body"],
            text_color=get_themed_color("text_secondary"),
            justify="center",
        )
        self.placeholder.pack(expand=True)
        self.tree_frame.pack_forget()

        # Botões de ação abaixo da árvore
        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons_frame.pack(fill="x", padx=5, pady=(0, 5))
        
        self.export_btn = ctk.CTkButton(
            self.buttons_frame,
            text=label_with_icon("export", "Exportar Corpus (TXT)"),
            font=FONTS["small"],
            command=self._on_export_corpus,
            state="disabled",
        )
        if self._ui_v2_enabled:
            style_button(self.export_btn, variant="secondary", size="md")
        self.export_btn.pack(fill="x", pady=2)
        
        self.export_iramuteq_btn = ctk.CTkButton(
            self.buttons_frame,
            text=label_with_icon("export", "Exportar para IRaMuTeQ"),
            font=FONTS["small"],
            command=self._on_export_iramuteq,
            state="disabled",
        )
        if self._ui_v2_enabled:
            style_button(self.export_iramuteq_btn, variant="secondary", size="md")
        self.export_iramuteq_btn.pack(fill="x", pady=2)

    def load_corpus(self, corpus) -> None:
        """
        Carrega corpus na arvore.

        Args:
            corpus: Objeto Corpus com dados carregados.
        """
        self._corpus = corpus
        self._history_item_map = {}
        self._item_payload_map = {}
        self._history_node_id = None
        self._corpus_root_id = None

        for item in self.tree.get_children():
            self.tree.delete(item)

        if corpus is None:
            self.tree_frame.pack_forget()
            self.buttons_frame.pack_forget()
            self.placeholder.pack(expand=True)
            self.export_btn.configure(state="disabled")
            self.export_iramuteq_btn.configure(state="disabled")
            return

        self.placeholder.pack_forget()
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.buttons_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.export_btn.configure(state="normal")
        self.export_iramuteq_btn.configure(state="normal")

        n_ucis = corpus.getucinb() if hasattr(corpus, "getucinb") else 0
        n_uces = corpus.getucenb() if hasattr(corpus, "getucenb") else 0
        n_formes = len(corpus.formes) if hasattr(corpus, "formes") else 0

        self._corpus_root_id = self.tree.insert("", "end", text=label_with_icon("corpus", "Corpus"), open=True)
        self._item_payload_map[self._corpus_root_id] = {"type": "corpus_root"}

        info_node = self.tree.insert(
            self._corpus_root_id,
            "end",
            text=label_with_icon("info", f"Info: {n_ucis} UCIs, {n_uces} UCEs, {n_formes} formas"),
            open=True,
        )
        self._item_payload_map[info_node] = {"type": "corpus_info"}
        self.tree.insert(info_node, "end", text="UCIs", values=(n_ucis,))
        self.tree.insert(info_node, "end", text="UCEs", values=(n_uces,))
        self.tree.insert(info_node, "end", text="Formas", values=(n_formes,))

        if n_ucis > 0:
            docs_node = self.tree.insert(
                self._corpus_root_id,
                "end",
                text=label_with_icon("documents", f"Documentos ({n_ucis})"),
                open=False,
            )
            self._item_payload_map[docs_node] = {"type": "documents_root"}
            for i, uci in enumerate(corpus.ucis[:50]):
                uci_text = f"UCI {i + 1}"
                if hasattr(uci, "etoiles") and uci.etoiles:
                    vars_str = " ".join(uci.etoiles[:6])
                    if vars_str.strip():
                        uci_text = vars_str
                item_id = self.tree.insert(docs_node, "end", text=uci_text)
                self._item_payload_map[item_id] = {"type": "document", "uci_index": i}

            if n_ucis > 50:
                self.tree.insert(docs_node, "end", text=f"... (+{n_ucis - 50} mais)")

        self._populate_history_section()

    def set_export_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Define callback para exportacao do corpus."""
        self._export_callback = callback

    def set_export_iramuteq_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Define callback para exportacao IRaMuTeQ."""
        self._export_iramuteq_callback = callback

    def _on_export_corpus(self) -> None:
        """Callback para botao de exportar corpus."""
        if self._export_callback:
            self._export_callback()

    def _on_export_iramuteq(self) -> None:
        """Callback para botao de exportar para IRaMuTeQ."""
        if self._export_iramuteq_callback:
            self._export_iramuteq_callback()

    def load_history(
        self,
        history: Any,
        on_select: Optional[Callable[[Any], None]] = None,
        on_action: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        """
        Carrega historico de analises para exibicao na arvore.

        Args:
            history: AnalysisHistory ou lista de entradas.
            on_select: Callback ao selecionar/double-click em uma analise.
            on_action: Callback ao acionar opcao de menu de contexto.
        """
        if on_select is not None:
            self._history_callback = on_select
        if on_action is not None:
            self._action_callback = on_action

        entries: List[Any] = []
        if history is None:
            entries = []
        elif hasattr(history, "load_results"):
            try:
                loaded = history.load_results()
                entries = list(loaded or [])
            except Exception:
                entries = []
        elif isinstance(history, list):
            entries = history

        self._history_entries = entries
        self._populate_history_section()

    def _populate_history_section(self) -> None:
        """Atualiza secao de historico na arvore."""
        if self._corpus is None:
            return

        if self._history_node_id and self.tree.exists(self._history_node_id):
            self.tree.delete(self._history_node_id)
        self._history_item_map = {}

        parent = self._corpus_root_id or ""
        self._history_node_id = self.tree.insert(parent, "end", text=label_with_icon("analyses", "Análises"), open=True)
        self._item_payload_map[self._history_node_id] = {"type": "history_root"}

        if not self._history_entries:
            empty_id = self.tree.insert(self._history_node_id, "end", text="Nenhuma análise registrada")
            self._item_payload_map[empty_id] = {"type": "history_empty"}
            return

        for entry in self._history_entries[:80]:
            label = self._format_history_label(entry)
            analysis_item = self.tree.insert(self._history_node_id, "end", text=label, open=False)
            payload = {"type": "analysis", "entry": entry}
            self._history_item_map[analysis_item] = entry
            self._item_payload_map[analysis_item] = payload
            self._add_analysis_children(analysis_item, entry)

        if len(self._history_entries) > 80:
            overflow_id = self.tree.insert(
                self._history_node_id,
                "end",
                text=f"... (+{len(self._history_entries) - 80} mais)",
            )
            self._item_payload_map[overflow_id] = {"type": "history_overflow"}

    def _add_analysis_children(self, parent_item: str, entry: Any) -> None:
        """Adiciona filhos descritivos por tipo de analise."""
        analysis_type = str(getattr(entry, "analysis_type", "")).strip().lower()
        children: List[tuple[str, str]] = []
        if analysis_type == "chd":
            children = [
                ("Dendrograma", "view_dendrogram"),
                ("Perfis", "view_profiles"),
                ("AFC Perfis", "view_afc"),
                ("Segmentos", "view_segments"),
                ("Antiperfis", "view_antiprofiles"),
            ]
        elif analysis_type in {"similarity", "similitude"}:
            children = [("Grafo", "view_graph")]
        else:
            children = [("Resultado", "open_result")]

        for text, action in children:
            item_id = self.tree.insert(parent_item, "end", text=text)
            self._item_payload_map[item_id] = {
                "type": "analysis_detail",
                "entry": entry,
                "action": action,
            }

    @staticmethod
    def _format_history_label(entry: Any) -> str:
        """Formata titulo resumido de uma entrada do historico."""
        analysis_type = str(getattr(entry, "analysis_type", "")).lower()
        timestamp = str(getattr(entry, "timestamp", "")).replace("T", " ")[:16]
        metadata = getattr(entry, "metadata", {}) if isinstance(getattr(entry, "metadata", {}), dict) else {}
        params = getattr(entry, "params", {}) if isinstance(getattr(entry, "params", {}), dict) else {}

        icon_key_map = {
            "chd": "dendrogram",
            "similarity": "similarity",
            "similitude": "similarity",
            "wordcloud": "wordcloud",
            "specificities": "keyness",
            "prototypical": "prototypical",
            "labbe": "labbe",
            "word_tree_extra": "word_tree",
            "matrix_frequency": "frequency",
            "matrix_chi2": "chi2",
            "matrix_afc": "afc",
            "matrix_chd": "dendrogram",
            "matrix_similarity": "similarity",
        }
        icon_key = icon_key_map.get(analysis_type, "stats")
        title_map = {
            "chd": "CHD",
            "similarity": "Similitude",
            "wordcloud": "Nuvem",
            "specificities": "Especificidades",
            "prototypical": "Prototípica",
            "labbe": "Dist. Labbé",
            "word_tree_extra": "Word Tree",
            "matrix_frequency": "Freq. Matriz",
            "matrix_chi2": "Qui² Matriz",
            "matrix_afc": "AFC Matriz",
            "matrix_chd": "CHD Matriz",
            "matrix_similarity": "Similitude Matriz",
        }
        title = title_map.get(analysis_type, analysis_type.upper() if analysis_type else "Análise")

        extra = ""
        if "n_classes" in metadata:
            extra = f" [{metadata['n_classes']} classes]"
        elif "layout" in params:
            extra = f" [{params['layout']}]"
        elif "n_dimensions" in params:
            extra = f" [{params['n_dimensions']} dim]"

        base_title = f"{title}{extra}"
        if timestamp:
            return f"{label_with_icon(icon_key, base_title)} — {timestamp}"
        return label_with_icon(icon_key, base_title)

    def _on_tree_select(self, _event=None) -> None:
        """Callback para clique simples."""
        selection = self.tree.selection()
        if not selection:
            return
        item_id = selection[0]
        payload = self._item_payload_map.get(item_id, {})
        entry = payload.get("entry")
        if entry is None:
            entry = self._history_item_map.get(item_id)
        if entry is None:
            return
        if self._history_callback:
            self._history_callback(entry)

    def _on_tree_double_click(self, _event=None) -> None:
        """Double-click reabre resultado associado."""
        selection = self.tree.selection()
        if not selection:
            return
        payload = self._item_payload_map.get(selection[0], {})
        entry = payload.get("entry")
        if entry is None:
            entry = self._history_item_map.get(selection[0])
        if entry is None:
            return
        if self._history_callback:
            self._history_callback(entry)

    def _on_tree_right_click(self, event) -> None:
        """Abre menu de contexto conforme item selecionado."""
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        payload = self._item_payload_map.get(item_id, {})
        if self._context_menu is not None:
            destroy_menu_safe(self._context_menu)
            self._context_menu = None
        menu = tk.Menu(self, tearoff=0)
        style_native_menu(menu)
        self._context_menu = menu

        item_type = payload.get("type")
        entry = payload.get("entry")
        if item_type in {"corpus_root", "corpus_info", "documents_root", "document"}:
            menu.add_command(label=label_with_icon("stats", "Estatísticas"), command=lambda: self._dispatch_action("show_stats", payload))
            menu.add_command(label=label_with_icon("export", "Exportar Corpus (TXT)"), command=lambda: self._dispatch_action("export_corpus_txt", payload))
            menu.add_command(label=label_with_icon("export", "Exportar para IRaMuTeQ"), command=lambda: self._dispatch_action("export_iramuteq", payload))
            menu.add_command(label=label_with_icon("dictionary", "Exportar Dicionário"), command=lambda: self._dispatch_action("export_dictionary", payload))
            menu.add_command(label=label_with_icon("segments", "Exportar Corpus Segmentado"), command=lambda: self._dispatch_action("export_segmented", payload))
            menu.add_command(label=label_with_icon("navigator", "Abrir Navigator"), command=lambda: self._dispatch_action("open_navigator", payload))
            menu.add_separator()
            menu.add_command(label=label_with_icon("subcorpus", "Criar Sub-corpus"), command=lambda: self._dispatch_action("create_subcorpus", payload))
        elif item_type in {"analysis", "analysis_detail"} and entry is not None:
            analysis_type = str(getattr(entry, "analysis_type", "")).strip().lower()
            if analysis_type == "chd":
                menu.add_command(label=label_with_icon("dendrogram", "Ver Dendrograma"), command=lambda: self._dispatch_action("view_dendrogram", payload))
                menu.add_command(label=label_with_icon("profiles", "Ver Perfis"), command=lambda: self._dispatch_action("view_profiles", payload))
                menu.add_command(label=label_with_icon("afc", "Ver AFC Perfis"), command=lambda: self._dispatch_action("view_afc", payload))
                menu.add_command(label=label_with_icon("typical_segments", "Ver Segmentos Típicos"), command=lambda: self._dispatch_action("view_segments", payload))
                menu.add_command(label=label_with_icon("antiprofiles", "Ver Antiperfis"), command=lambda: self._dispatch_action("view_antiprofiles", payload))
                menu.add_separator()
                menu.add_command(label=label_with_icon("export", "Exportar Classes"), command=lambda: self._dispatch_action("export_classes", payload))
                menu.add_command(label=label_with_icon("report", "Gerar Corpus Colorido"), command=lambda: self._dispatch_action("export_colored_corpus", payload))
                menu.add_command(label=label_with_icon("wordcloud", "Gerar Nuvem por Classe"), command=lambda: self._dispatch_action("wordcloud_by_class", payload))
                menu.add_command(label=label_with_icon("similarity", "Similaridade por Classe"), command=lambda: self._dispatch_action("similarity_by_class", payload))
            elif analysis_type in {"similarity", "similitude"}:
                menu.add_command(label=label_with_icon("graph", "Ver Grafo"), command=lambda: self._dispatch_action("view_graph", payload))
                menu.add_command(label=label_with_icon("save", "Exportar Grafo"), command=lambda: self._dispatch_action("export_result", payload))
                menu.add_command(label=label_with_icon("report", "Abrir Relatório"), command=lambda: self._dispatch_action("open_report", payload))
                menu.add_command(label=label_with_icon("settings", "Reconfigurar"), command=lambda: self._dispatch_action("reconfigure_similarity", payload))
            else:
                menu.add_command(label=label_with_icon("open", "Reabrir Resultado"), command=lambda: self._dispatch_action("open_result", payload))
                menu.add_command(label=label_with_icon("save", "Exportar Resultado"), command=lambda: self._dispatch_action("export_result", payload))
                menu.add_command(label=label_with_icon("report", "Abrir Relatório"), command=lambda: self._dispatch_action("open_report", payload))

            if analysis_type == "chd":
                menu.add_separator()
                menu.add_command(label=label_with_icon("report", "Abrir Relatório"), command=lambda: self._dispatch_action("open_report", payload))

            menu.add_separator()
            menu.add_command(label=label_with_icon("delete", "Excluir do Histórico"), command=lambda: self._dispatch_action("delete_history", payload))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            destroy_menu_safe(menu)
            self._context_menu = None

    def _dispatch_action(self, action: str, payload: Dict[str, Any]) -> None:
        """Despacha acao de contexto para callback externo."""
        data = dict(payload or {})
        data["action"] = action
        if self._action_callback:
            self._action_callback(action, data)

    def clear(self) -> None:
        """Limpa a arvore."""
        self.load_corpus(None)

    def get_selection(self) -> Optional[str]:
        """Retorna texto do item selecionado."""
        selection = self.tree.selection()
        if selection:
            return self.tree.item(selection[0], "text")
        return None
