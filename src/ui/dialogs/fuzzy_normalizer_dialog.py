"""
FuzzyNormalizerDialog - Diálogo para normalizar variações ortográficas.
=======================================================================
Implementa a UI para o FuzzyNormalizer (algoritmos estilo OpenRefine).

Fluxo:
  1. Corpus já carregado → detecta vocabulário automaticamente
  2. Usuário escolhe algoritmo (fingerprint / n-gram / levenshtein)
  3. Tabela de clusters detectados é exibida
  4. Usuário marca quais clusters aplicar e pode alterar a forma canônica
  5. Preview imediato do resultado
  6. Confirmar → retorna corpus normalizado
"""

import threading
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from ..styles import COLORS, FONTS, SIZES, get_themed_color, get_current_colors
from ..iconography import create_help_button
from ...utils.logger import get_logger

log = get_logger(__name__)

_ALGO_DESCRIPTIONS = {
    "fingerprint": (
        "Fingerprint  —  Rápido. Agrupa maiúsculas/minúsculas e variações de acento.\n"
        "Ex.: Democracia / democracia / democrácia → democracia"
    ),
    "ngram2": (
        "N-gram (bigramas)  —  Médio. Captura erros de digitação internos.\n"
        "Ex.: demcracia / democracia → democracia"
    ),
    "ngram3": (
        "N-gram (trigramas)  —  Médio. Mais conservador que bigramas.\n"
        "Ex.: demcracia / democracia → democracia"
    ),
    "levenshtein1": (
        "Levenshtein 1  —  Lento. Captura diferenças de 1 caractere.\n"
        "Ex.: democrecia / democracia → democracia"
    ),
    "levenshtein2": (
        "Levenshtein 2  —  Muito lento. 2 caracteres de diferença.\n"
        "Cuidado: pode gerar falsos positivos em palavras curtas."
    ),
}


class FuzzyNormalizerDialog(ctk.CTkToplevel):
    """
    Diálogo para detectar e normalizar variações ortográficas no corpus.
    Retorna o corpus normalizado via get_result().
    """

    def __init__(
        self,
        parent,
        corpus_text: str,
        on_confirm: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Normalizar Variações Ortográficas")
        self.geometry("860x620")
        self.minsize(700, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._corpus_text = corpus_text
        self._on_confirm = on_confirm
        self._result: Optional[str] = None
        self._clusters: List[Dict[str, Any]] = []  # Dicts serializáveis para a Treeview
        self._cluster_objects = []                  # FuzzyCluster originais
        self._detection_running = False
        self._selected_rows: Dict[int, bool] = {}   # iid → checked

        self._create_widgets()
        self._center_on_parent(parent)
        # Detectar automaticamente com fingerprint ao abrir
        self.after(100, lambda: self._run_detection("fingerprint"))

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
    # Widgets
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        # --- Topo: seleção de algoritmo ---
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))

        title_row = ctk.CTkFrame(top, fg_color="transparent")
        title_row.pack(anchor="w")
        ctk.CTkLabel(title_row, text="Algoritmo de detecção:", font=FONTS["heading"]).pack(side="left")
        self._create_help_icon(
            title_row,
            "Escolha como detectar variações ortográficas. Fingerprint é mais rápido; Levenshtein é mais sensível.",
        ).pack(side="left", padx=(6, 0))

        algo_row = ctk.CTkFrame(top, fg_color="transparent")
        algo_row.pack(fill="x", pady=(4, 0))

        self._algo_var = ctk.StringVar(value="fingerprint")

        for algo_id, label in [
            ("fingerprint",   "Fingerprint"),
            ("ngram2",        "N-gram bi"),
            ("ngram3",        "N-gram tri"),
            ("levenshtein1",  "Levenshtein 1"),
            ("levenshtein2",  "Levenshtein 2"),
        ]:
            ctk.CTkRadioButton(
                algo_row,
                text=label,
                variable=self._algo_var,
                value=algo_id,
                command=lambda a=algo_id: self._run_detection(a),
            ).pack(side="left", padx=(0, 12))

        self._algo_desc_label = ctk.CTkLabel(
            top,
            text=_ALGO_DESCRIPTIONS["fingerprint"],
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
            anchor="w",
            justify="left",
        )
        self._algo_desc_label.pack(fill="x", pady=(4, 0))

        # --- Filtros ---
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=16, pady=(0, 4))

        ctk.CTkLabel(filter_frame, text="Freq. mín.:", font=FONTS["small"]).pack(side="left")
        self._create_help_icon(
            filter_frame,
            "Considera apenas palavras com esta frequência mínima no corpus.",
        ).pack(side="left", padx=(4, 6))
        self._min_freq_var = ctk.IntVar(value=2)
        ctk.CTkSlider(
            filter_frame, from_=2, to=20, number_of_steps=18,
            variable=self._min_freq_var, width=100,
        ).pack(side="left", padx=(4, 2))
        self._min_freq_label = ctk.CTkLabel(
            filter_frame, text="2", font=FONTS["small"], width=20
        )
        self._min_freq_label.pack(side="left", padx=(0, 16))
        self._min_freq_var.trace_add(
            "write",
            lambda *_: (
                self._min_freq_label.configure(text=str(self._min_freq_var.get())),
                self._run_detection(self._algo_var.get()),
            )
        )

        ctk.CTkLabel(filter_frame, text="Tamanho mín. da palavra:", font=FONTS["small"]).pack(side="left")
        self._create_help_icon(
            filter_frame,
            "Ignora palavras muito curtas para reduzir falsos agrupamentos.",
        ).pack(side="left", padx=(4, 6))
        self._min_len_var = ctk.IntVar(value=4)
        ctk.CTkSlider(
            filter_frame, from_=2, to=10, number_of_steps=8,
            variable=self._min_len_var, width=80,
        ).pack(side="left", padx=(4, 2))
        self._min_len_label = ctk.CTkLabel(
            filter_frame, text="4", font=FONTS["small"], width=20
        )
        self._min_len_label.pack(side="left")
        self._min_len_var.trace_add(
            "write",
            lambda *_: (
                self._min_len_label.configure(text=str(self._min_len_var.get())),
                self._run_detection(self._algo_var.get()),
            )
        )

        # --- Progresso / status ---
        self._status_label = ctk.CTkLabel(
            self, text="Detectando...",
            font=FONTS["small"], text_color=get_themed_color("text_secondary"),
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=16)
        self._progress = ctk.CTkProgressBar(self, height=3, corner_radius=2)
        self._progress.pack(fill="x", padx=16, pady=(0, 4))
        self._progress.set(0)

        # --- Treeview de clusters ---
        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        ctk.CTkLabel(
            tree_frame,
            text="Clusters detectados  (clique para marcar/desmarcar, duplo-clique para editar a forma canônica):",
            font=FONTS["small"], text_color=get_themed_color("text_secondary"), anchor="w",
        ).pack(anchor="w")

        c = get_current_colors()
        tv_frame = tk.Frame(tree_frame, bg=c["background"])
        tv_frame.pack(fill="both", expand=True, pady=4)

        style = ttk.Style()
        style.configure(
            "Fuzzy.Treeview",
            rowheight=22,
            font=("Segoe UI", 10),
            background=c["surface"],
            fieldbackground=c["surface"],
            foreground=c["text"],
        )
        style.configure(
            "Fuzzy.Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background=c["header_bg"],
            foreground=c["text"],
        )
        style.map("Fuzzy.Treeview", background=[("selected", c["selection"])])

        self._tree = ttk.Treeview(
            tv_frame,
            style="Fuzzy.Treeview",
            columns=("apply", "canonical", "variants", "freq", "algo"),
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("apply",     text="Sel.")
        self._tree.heading("canonical", text="Forma canônica")
        self._tree.heading("variants",  text="Variantes encontradas")
        self._tree.heading("freq",      text="Freq.")
        self._tree.heading("algo",      text="Algoritmo")

        self._tree.column("apply",     width=32,  minwidth=30,  anchor="center", stretch=False)
        self._tree.column("canonical", width=160, minwidth=100, anchor="w")
        self._tree.column("variants",  width=350, minwidth=200, anchor="w")
        self._tree.column("freq",      width=60,  minwidth=50,  anchor="center", stretch=False)
        self._tree.column("algo",      width=110, minwidth=80,  anchor="center", stretch=False)

        vsb = ttk.Scrollbar(tv_frame, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self._tree.bind("<Double-1>", self._on_tree_double_click)

        # Botões de seleção rápida
        sel_row = ctk.CTkFrame(tree_frame, fg_color="transparent")
        sel_row.pack(fill="x")
        ctk.CTkButton(
            sel_row, text="Marcar todos", width=100, height=24,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=lambda: self._select_all(True),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            sel_row, text="Desmarcar todos", width=110, height=24,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=lambda: self._select_all(False),
        ).pack(side="left")
        self._count_label = ctk.CTkLabel(
            sel_row, text="0 clusters", font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
        )
        self._count_label.pack(side="right")

        # --- Rodapé ---
        ctk.CTkFrame(self, height=1, fg_color=get_themed_color("border")).pack(fill="x", side="bottom")
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=12, pady=8)

        self._btn_cancel = ctk.CTkButton(
            btn_row, text="Cancelar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self.destroy,
        )
        self._btn_cancel.pack(side="right", padx=(4, 0))

        self._btn_apply = ctk.CTkButton(
            btn_row, text="Aplicar selecionados", width=150, height=26,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color=("#FFFFFF", "#FFFFFF"),
            border_width=0,
            corner_radius=3,
            command=self._on_apply,
        )
        self._btn_apply.pack(side="right", padx=(0, 4))
        
        # Flag lógica em vez de state="disabled" para evitar bugs do CustomTkinter
        self._apply_enabled = False
        self._set_apply_button_enabled(False)

    # ------------------------------------------------------------------
    # Detecção (em thread de fundo)
    # ------------------------------------------------------------------

    def _run_detection(self, algo: str) -> None:
        """Inicia detecção em thread de fundo."""
        if self._detection_running:
            return
        self._detection_running = True
        self._set_apply_button_enabled(False)
        self._status_label.configure(text="Analisando corpus...")
        self._progress.set(0.1)
        self._algo_desc_label.configure(text=_ALGO_DESCRIPTIONS.get(algo, ""))
        self._clear_tree()

        min_freq = max(1, int(self._min_freq_var.get() or 2))
        min_len  = max(2, int(self._min_len_var.get()  or 4))

        thread = threading.Thread(
            target=self._detection_worker,
            args=(algo, min_freq, min_len),
            daemon=True,
        )
        thread.start()

    def _detection_worker(self, algo: str, min_freq: int, min_len: int) -> None:
        try:
            from ...importers.fuzzy_normalizer import FuzzyNormalizer

            self._safe_after(lambda: self._progress.set(0.3))

            norm = FuzzyNormalizer(
                self._corpus_text,
                min_word_length=min_len,
                min_frequency=min_freq,
            )

            self._safe_after(lambda: self._progress.set(0.55))

            if algo == "fingerprint":
                clusters = norm.cluster_fingerprint()
            elif algo == "ngram2":
                clusters = norm.cluster_ngram(n=2)
            elif algo == "ngram3":
                clusters = norm.cluster_ngram(n=3)
            elif algo == "levenshtein1":
                clusters = norm.cluster_levenshtein(threshold=1)
            elif algo == "levenshtein2":
                clusters = norm.cluster_levenshtein(threshold=2)
            else:
                clusters = norm.cluster_fingerprint()

            self._safe_after(lambda: self._progress.set(0.9))
            self._safe_after(lambda: self._populate_tree(clusters, algo))

        except Exception as exc:
            log.exception("Erro na detecção fuzzy")
            self._safe_after(
                lambda err=exc: self._status_label.configure(
                    text=f"Erro: {err}",
                    text_color=get_themed_color("danger"),
                )
            )
        finally:
            self._detection_running = False

    # ------------------------------------------------------------------
    # Tabela
    # ------------------------------------------------------------------

    def _populate_tree(self, clusters, algo: str) -> None:
        self._clear_tree()
        self._cluster_objects = clusters
        self._selected_rows = {}

        for i, c in enumerate(clusters):
            variants_str = " | ".join(v for v in c.variants if v != c.canonical)
            iid = str(i)
            self._tree.insert(
                "", "end", iid=iid,
                values=("Sim", c.canonical, variants_str, c.frequency, c.source),
                tags=("checked",),
            )
            self._selected_rows[iid] = True

        self._tree.tag_configure("checked",   background=get_current_colors()["selection"])
        self._tree.tag_configure("unchecked", background=get_current_colors()["surface"])

        count = len(clusters)
        self._status_label.configure(
            text=f"{count} cluster(s) detectado(s). Marque os que deseja normalizar.",
            text_color=get_themed_color("text_secondary"),
        )
        self._count_label.configure(text=f"{count} clusters")
        self._progress.set(1.0)
        if count > 0:
            self._set_apply_button_enabled(True)
        else:
            self._set_apply_button_enabled(False)

    def _set_apply_button_enabled(self, enabled: bool) -> None:
        """Padroniza contraste do botão principal 'Aplicar selecionados'."""
        self._apply_enabled = enabled
        if enabled:
            self._btn_apply.configure(
                fg_color=get_themed_color("accent"),
                hover_color=get_themed_color("primary_hover"),
                text_color=("#FFFFFF", "#FFFFFF"),
                border_width=0,
                border_color=get_themed_color("accent"),
            )
        else:
            self._btn_apply.configure(
                fg_color=get_themed_color("button"),
                hover_color=get_themed_color("button"),
                text_color=get_themed_color("text_secondary"),
                border_width=1,
                border_color=get_themed_color("border"),
            )

    def _clear_tree(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._cluster_objects = []
        self._selected_rows = {}

    def _on_tree_click(self, event) -> None:
        """Toggle da seleção ao clicar especificamente na coluna de seleção."""
        region = self._tree.identify("region", event.x, event.y)
        if region not in ("cell", "tree"):
            return
        
        column = self._tree.identify_column(event.x)
        if column != "#1":  # #1 é a coluna de seleção
            return

        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        
        # Toggle checkbox
        current = self._selected_rows.get(iid, True)
        self._set_row_selected(iid, not current)

    def _on_tree_double_click(self, event) -> None:
        """Duplo clique na coluna canonical → edita a forma canônica."""
        region = self._tree.identify("region", event.x, event.y)
        col    = self._tree.identify_column(event.x)
        iid    = self._tree.identify_row(event.y)
        if not iid or col != "#2":  # #2 = canonical
            return
        self._edit_canonical(iid)

    def _set_row_selected(self, iid: str, selected: bool) -> None:
        self._selected_rows[iid] = selected
        vals = list(self._tree.item(iid, "values"))
        vals[0] = "Sim" if selected else "Não"
        self._tree.item(iid, values=vals, tags=("checked" if selected else "unchecked",))

    def _select_all(self, selected: bool) -> None:
        for iid in self._tree.get_children():
            self._set_row_selected(iid, selected)

    def _edit_canonical(self, iid: str) -> None:
        """Abre um mini-popup para editar a forma canônica."""
        vals = list(self._tree.item(iid, "values"))
        current_canonical = vals[1]

        popup = ctk.CTkInputDialog(
            text=f"Alterar forma canônica para o cluster [{current_canonical}]:",
            title="Editar forma canônica",
        )
        new_val = popup.get_input()
        if new_val and new_val.strip():
            new_val = new_val.strip()
            vals[1] = new_val
            self._tree.item(iid, values=vals)
            # Atualizar o cluster_object correspondente
            try:
                idx = int(iid)
                if 0 <= idx < len(self._cluster_objects):
                    self._cluster_objects[idx].canonical = new_val
            except (ValueError, IndexError):
                pass

    # ------------------------------------------------------------------
    # Aplicar
    # ------------------------------------------------------------------

    def _on_apply(self, *args) -> None:
        """Aplica os clusters selecionados e fecha o diálogo."""
        if getattr(self, "_detection_running", False):
            return
        if not getattr(self, "_apply_enabled", False):
            return
            
        log.info("Iniciando aplicação de clusters selecionados...")
        
        selected_clusters = []
        try:
            for iid, selected in self._selected_rows.items():
                if not selected:
                    continue
                idx = int(iid)
                if 0 <= idx < len(self._cluster_objects):
                    c = self._cluster_objects[idx]
                    vals = self._tree.item(iid, "values")
                    if vals:
                        c.canonical = vals[1]
                    selected_clusters.append(c)
        except Exception as e:
            log.error(f"Erro ao coletar clusters selecionados: {e}")

        if not selected_clusters:
            log.warning("Nenhum cluster selecionado.")
            self.destroy()
            return

        try:
            from ...importers.fuzzy_normalizer import FuzzyNormalizer
            
            # 1. Processar (geralmente rápido)
            norm = FuzzyNormalizer(self._corpus_text)
            result = norm.apply_clusters(selected_clusters)
            normalized_text = result.normalized_text
            
            # 2. Salvar resultado e referências
            self._result = normalized_text
            callback = self._on_confirm
            
            log.info(f"Sucesso: {len(selected_clusters)} clusters aplicados. Fechando diálogo.")
            
            # 3. Destruir janela primeiro para liberar a UI
            self.grab_release()
            self.destroy()
            
            # 4. Chamar callback (se existir)
            if callback:
                # Usar um pequeno delay para garantir que a janela sumiu
                # e que o processamento do callback (pesado) não trave a destruição
                if tk._default_root:
                    tk._default_root.after(10, lambda: callback(normalized_text))
                else:
                    callback(normalized_text)
                    
        except Exception as exc:
            log.exception("Erro crítico ao aplicar normalização")
            from tkinter import messagebox
            messagebox.showerror("Erro", f"Erro ao aplicar normalização: {exc}")
            self.destroy()

    def _handle_apply_error(self, exc: Exception) -> None:
        """Trata erros durante a aplicação."""
        if not self.winfo_exists():
            return
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._status_label.configure(
            text=f"Erro ao aplicar: {exc}",
            text_color=get_themed_color("danger"),
        )
        self._set_apply_button_enabled(True)
        self._btn_cancel.configure(state="normal")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_after(self, callback) -> None:
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except Exception:
            pass

    def get_result(self) -> Optional[str]:
        """Retorna o corpus normalizado (None se cancelado)."""
        return self._result
