"""
KWICDialog — Concordancer / Keyword-in-Context.
================================================
Interface estilo AntConc com:
  - Barra de busca (literal ou regex)
  - Tabela de concordâncias alinhada à palavra-chave
  - Sortável por: posição, contexto esq., contexto dir., UCI
  - Painel de detalhe (prévia do segmento completo)
  - Aba de Collocates (frequência dos vizinhos imediatos)
  - Aba de Estatísticas por UCI (dispersão, co-ocorrência)
  - Export CSV e TXT
"""

import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from ..styles import COLORS, FONTS, get_themed_color
from ...utils.logger import get_logger

log = get_logger(__name__)

_SORT_OPTIONS = {
    "Posição no corpus": "pos",
    "Contexto esquerdo": "left1",
    "Contexto direito":  "right1",
    "UCI":               "uci",
}


class KWICDialog(ctk.CTkToplevel):
    """
    Janela de Concordancer (KWIC) para corpus IRaMuTeQ.

    Args:
        parent:       Janela pai.
        corpus_text:  Texto bruto do corpus.
    """

    def __init__(self, parent, corpus_text: str) -> None:
        super().__init__(parent)
        self.title("Concordancer  (KWIC — Keyword-in-Context)")
        self.geometry("1060x700")
        self.minsize(800, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._corpus_text = corpus_text
        self._engine      = None
        self._result      = None
        self._sort_key    = "pos"
        self._loading     = False
        self._tab_kwic_name = "Concordâncias"
        self._tab_colloc_name = "Collocates"
        self._tab_uci_name = "Por UCI"

        self._create_widgets()
        self._center_on_parent(parent)
        self.after(80, self._preload_engine)

    def _center_on_parent(self, parent) -> None:
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        dw, dh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        # ── Barra de busca ────────────────────────────────────────────
        search_bar = ctk.CTkFrame(self, fg_color=get_themed_color("header_bg"),
                                  corner_radius=0, height=46)
        search_bar.pack(fill="x")
        search_bar.pack_propagate(False)

        self._query_entry = ctk.CTkEntry(
            search_bar, placeholder_text="Palavra-chave ou regex…",
            width=280, height=30, corner_radius=3,
            font=FONTS["heading"],
        )
        self._query_entry.pack(side="left", padx=(10, 4), pady=8)
        self._query_entry.bind("<Return>", lambda _: self._run_search())

        self._btn_search = ctk.CTkButton(
            search_bar, text="Buscar", height=30, width=90,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            corner_radius=3, border_width=0,
            command=self._run_search,
        )
        self._btn_search.pack(side="left", padx=4)

        ctk.CTkFrame(search_bar, width=1, height=30,
                     fg_color=get_themed_color("border")).pack(side="left", padx=8)

        # Opções
        self._case_var  = ctk.BooleanVar(value=False)
        self._regex_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(search_bar, text="Maiúsculas", variable=self._case_var,
                        font=FONTS["small"], checkbox_width=14, checkbox_height=14,
                        ).pack(side="left", padx=4)
        ctk.CTkCheckBox(search_bar, text="Regex", variable=self._regex_var,
                        font=FONTS["small"], checkbox_width=14, checkbox_height=14,
                        ).pack(side="left", padx=4)

        ctk.CTkFrame(search_bar, width=1, height=30,
                     fg_color=get_themed_color("border")).pack(side="left", padx=8)
        ctk.CTkLabel(search_bar, text="Contexto:", font=FONTS["small"]).pack(side="left")
        self._ctx_var = ctk.IntVar(value=5)
        ctk.CTkSlider(search_bar, from_=1, to=20, number_of_steps=19,
                      variable=self._ctx_var, width=80).pack(side="left", padx=(4, 2))
        self._ctx_lbl = ctk.CTkLabel(search_bar, text="5", font=FONTS["small"], width=20)
        self._ctx_lbl.pack(side="left")
        self._ctx_var.trace_add("write", lambda *_: self._ctx_lbl.configure(
            text=str(self._ctx_var.get())))

        # Status
        self._status_label = ctk.CTkLabel(
            search_bar, text="Carregando corpus…",
            font=FONTS["small"], text_color=COLORS["text_secondary"], anchor="e",
        )
        self._status_label.pack(side="right", padx=12)

        # ── Barra de progresso ────────────────────────────────────────
        self._progress = ctk.CTkProgressBar(self, height=3, corner_radius=0)
        self._progress.pack(fill="x")
        self._progress.set(0)

        # ── Área principal: concordâncias + detalhe ───────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # Tabs: Concordâncias | Collocates | Estatísticas UCI
        self._tabs = ctk.CTkTabview(main, corner_radius=4)
        self._tabs.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        self._tabs.add(self._tab_kwic_name)
        self._tabs.add(self._tab_colloc_name)
        self._tabs.add(self._tab_uci_name)
        self._style_tabs()

        self._build_tab_kwic(self._tabs.tab(self._tab_kwic_name))
        self._build_tab_collocates(self._tabs.tab(self._tab_colloc_name))
        self._build_tab_uci(self._tabs.tab(self._tab_uci_name))

        # ── Rodapé ───────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=get_themed_color("border")).pack(
            fill="x", side="bottom")
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=10, pady=6)

        def _exp_btn(text, cmd, width=150):
            return ctk.CTkButton(
                btn_row, text=text, height=26, width=width,
                fg_color=get_themed_color("button"),
                hover_color=get_themed_color("button_hover"),
                text_color=get_themed_color("text"),
                border_width=1, border_color=get_themed_color("border"),
                corner_radius=3, font=FONTS["small"],
                command=cmd,
            )

        _exp_btn("Exportar CSV", self._export_csv).pack(side="left", padx=(0, 4))
        _exp_btn("Exportar TXT alinhado", self._export_txt, 160).pack(side="left", padx=(0, 4))
        _exp_btn("Copiar linhas", self._copy_lines).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Fechar", height=26, width=80,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self.destroy,
        ).pack(side="right")

    def _style_tabs(self) -> None:
        """Padroniza contraste das abas e evita caracteres decorativos."""
        try:
            self._tabs.configure(
                segmented_button_fg_color=get_themed_color("surface"),
                segmented_button_selected_color=get_themed_color("primary"),
                segmented_button_selected_hover_color=get_themed_color("primary_hover"),
                segmented_button_unselected_color=get_themed_color("button"),
                segmented_button_unselected_hover_color=get_themed_color("button_hover"),
                segmented_button_selected_text_color=("#FFFFFF", "#FFFFFF"),
                segmented_button_unselected_text_color=get_themed_color("text"),
                command=lambda: self._refresh_tab_text_colors(),
            )
        except Exception:
            pass
        self._refresh_tab_text_colors()
        self.after_idle(self._refresh_tab_text_colors)

    def _refresh_tab_text_colors(self) -> None:
        """Garante texto branco na aba ativa do tabview."""
        try:
            segmented = getattr(self._tabs, "_segmented_button", None)
            buttons_dict = getattr(segmented, "_buttons_dict", {}) if segmented is not None else {}
            active = str(self._tabs.get() or "")
            default_text = get_themed_color("text")
            for name, button in buttons_dict.items():
                is_active = str(name) == active
                button.configure(
                    text_color=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                    text_color_disabled=("#FFFFFF", "#FFFFFF") if is_active else default_text,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Aba 1 — Concordâncias
    # ------------------------------------------------------------------

    def _build_tab_kwic(self, tab) -> None:
        # Ordenação
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(ctrl, text="Ordenar por:", font=FONTS["small"]).pack(side="left")
        self._sort_var = ctk.StringVar(value="Posição no corpus")
        sort_menu = ctk.CTkOptionMenu(
            ctrl,
            values=list(_SORT_OPTIONS.keys()),
            variable=self._sort_var,
            width=180, height=26,
            command=self._on_sort_change,
        )
        sort_menu.pack(side="left", padx=4)

        self._hit_count_label = ctk.CTkLabel(
            ctrl, text="", font=FONTS["small"],
            text_color=COLORS["text_secondary"], anchor="e",
        )
        self._hit_count_label.pack(side="right", padx=8)

        # Treeview
        tv_frame = tk.Frame(tab, bg=COLORS["background"])
        tv_frame.pack(fill="both", expand=True, padx=2, pady=2)

        style = ttk.Style()
        style.configure("KWIC.Treeview",
                        rowheight=20, font=("Consolas", 9),
                        background=COLORS["surface"],
                        fieldbackground=COLORS["surface"],
                        foreground=COLORS["text"])
        style.configure("KWIC.Treeview.Heading",
                        font=("Segoe UI", 10, "bold"))
        style.map("KWIC.Treeview",
                  background=[("selected", COLORS["selection"])])

        cols = ("#", "left", "kw", "right", "uci")
        self._kwic_tree = ttk.Treeview(
            tv_frame, style="KWIC.Treeview",
            columns=cols, show="headings", selectmode="browse",
        )
        self._kwic_tree.heading("#",     text="#",        anchor="e")
        self._kwic_tree.heading("left",  text="← Contexto esquerdo", anchor="e")
        self._kwic_tree.heading("kw",    text="PALAVRA",  anchor="center")
        self._kwic_tree.heading("right", text="Contexto direito →",  anchor="w")
        self._kwic_tree.heading("uci",   text="UCI",      anchor="w")
        self._kwic_tree.column("#",     width=40,  anchor="e",      stretch=False)
        self._kwic_tree.column("left",  width=300, anchor="e")
        self._kwic_tree.column("kw",    width=120, anchor="center", stretch=False)
        self._kwic_tree.column("right", width=300, anchor="w")
        self._kwic_tree.column("uci",   width=80,  anchor="w",      stretch=False)

        vsb = ttk.Scrollbar(tv_frame, orient="vertical",   command=self._kwic_tree.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=self._kwic_tree.xview)
        self._kwic_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._kwic_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        self._kwic_tree.bind("<<TreeviewSelect>>", self._on_line_select)

        # Painel de detalhe
        detail_frame = ctk.CTkFrame(tab, fg_color=get_themed_color("surface"),
                                     corner_radius=3, border_width=1,
                                     border_color=get_themed_color("border"),
                                     height=70)
        detail_frame.pack(fill="x", padx=2, pady=(4, 0))
        detail_frame.pack_propagate(False)
        ctk.CTkLabel(detail_frame, text="Contexto:", font=FONTS["small"],
                     text_color=COLORS["text_secondary"]).pack(anchor="nw", padx=6, pady=(4, 0))
        self._detail_label = ctk.CTkLabel(
            detail_frame, text="", font=FONTS["body"],
            wraplength=900, anchor="w", justify="left",
        )
        self._detail_label.pack(fill="x", padx=10, pady=(0, 4))

    # ------------------------------------------------------------------
    # Aba 2 — Collocates
    # ------------------------------------------------------------------

    def _build_tab_collocates(self, tab) -> None:
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=4)
        ctk.CTkLabel(ctrl, text="Janela de collocates:", font=FONTS["small"]).pack(side="left")
        self._coll_window_var = ctk.IntVar(value=3)
        ctk.CTkSlider(ctrl, from_=1, to=10, number_of_steps=9,
                      variable=self._coll_window_var, width=100).pack(side="left", padx=4)
        self._coll_w_lbl = ctk.CTkLabel(ctrl, text="3", font=FONTS["small"], width=20)
        self._coll_w_lbl.pack(side="left")
        self._coll_window_var.trace_add("write",
            lambda *_: self._coll_w_lbl.configure(text=str(self._coll_window_var.get())))

        ctk.CTkButton(ctrl, text="Calcular", height=26, width=90,
                      fg_color=get_themed_color("accent"),
                      hover_color=get_themed_color("primary_hover"),
                      text_color="#FFFFFF",
                      corner_radius=3, border_width=0, font=FONTS["small"],
                      command=self._compute_collocates,
                      ).pack(side="left", padx=8)

        tv_frame = tk.Frame(tab, bg=COLORS["background"])
        tv_frame.pack(fill="both", expand=True, padx=2, pady=2)

        self._coll_tree = ttk.Treeview(
            tv_frame, style="KWIC.Treeview",
            columns=("rank", "word", "freq_left", "freq_right", "total"),
            show="headings", selectmode="browse",
        )
        for col, label, w in [
            ("rank",       "#",          40),
            ("word",       "Collocate",  180),
            ("freq_left",  "Freq. Esq.", 90),
            ("freq_right", "Freq. Dir.", 90),
            ("total",      "Total",      80),
        ]:
            self._coll_tree.heading(col, text=label)
            self._coll_tree.column(col, width=w,
                                   anchor="center" if col != "word" else "w",
                                   stretch=col == "word")
        coll_vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self._coll_tree.yview)
        self._coll_tree.configure(yscrollcommand=coll_vsb.set)
        self._coll_tree.grid(row=0, column=0, sticky="nsew")
        coll_vsb.grid(row=0, column=1, sticky="ns")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Aba 3 — Por UCI
    # ------------------------------------------------------------------

    def _build_tab_uci(self, tab) -> None:
        tv_frame = tk.Frame(tab, bg=COLORS["background"])
        tv_frame.pack(fill="both", expand=True, padx=2, pady=2)

        self._uci_tree = ttk.Treeview(
            tv_frame, style="KWIC.Treeview",
            columns=("uci_id", "hits", "tokens", "rel_freq", "variables"),
            show="headings", selectmode="browse",
        )
        for col, label, w, anchor in [
            ("uci_id",    "UCI",          80, "w"),
            ("hits",      "Ocorrências",  90, "center"),
            ("tokens",    "Tokens UCI",   90, "center"),
            ("rel_freq",  "Freq/1k",      80, "center"),
            ("variables", "Variáveis",   300, "w"),
        ]:
            self._uci_tree.heading(col, text=label)
            self._uci_tree.column(col, width=w, anchor=anchor,
                                  stretch=(col == "variables"))
        uci_vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self._uci_tree.yview)
        self._uci_tree.configure(yscrollcommand=uci_vsb.set)
        self._uci_tree.grid(row=0, column=0, sticky="nsew")
        uci_vsb.grid(row=0, column=1, sticky="ns")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Pré-carregar engine
    # ------------------------------------------------------------------

    def _preload_engine(self) -> None:
        def worker():
            try:
                from ...analysis.kwic_engine import KWICEngine
                self._engine = KWICEngine(self._corpus_text)
                n_tok = len(self._engine._all_tokens)
                n_uci = len(self._engine._ucis)
                self._safe_after(lambda: self._status_label.configure(
                    text=f"{n_tok:,} tokens  ·  {n_uci} UCIs  ·  Pronto"
                ))
                self._safe_after(lambda: self._progress.set(1.0))
            except Exception as exc:
                log.exception("Erro KWICEngine")
                self._safe_after(lambda: self._status_label.configure(
                    text=f"Erro: {exc}", text_color=COLORS["danger"]
                ))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def _run_search(self) -> None:
        query = self._query_entry.get().strip()
        if not query:
            messagebox.showinfo("Busca vazia", "Digite uma palavra-chave.", parent=self)
            return
        if not self._engine:
            messagebox.showinfo("Aguarde", "Corpus ainda carregando.", parent=self)
            return
        if self._loading:
            return

        self._loading = True
        self._btn_search.configure(state="disabled")
        self._progress.set(0.2)
        self._status_label.configure(text="Buscando…")

        ctx   = max(1, int(self._ctx_var.get()))
        case  = self._case_var.get()
        regex = self._regex_var.get()

        def worker():
            try:
                result = self._engine.search(
                    query, context=ctx,
                    case_sensitive=case, use_regex=regex,
                )
                self._result = result
                self._sort_key = _SORT_OPTIONS.get(self._sort_var.get(), "pos")
                self._safe_after(lambda: self._populate_kwic(result))
                self._safe_after(lambda: self._populate_uci_tab(result))
            except ValueError as exc:
                self._safe_after(lambda: messagebox.showerror("Erro de regex",
                                 str(exc), parent=self))
            except Exception as exc:
                log.exception("Erro na busca KWIC")
                self._safe_after(lambda: self._status_label.configure(
                    text=f"Erro: {exc}", text_color=COLORS["danger"]
                ))
            finally:
                self._loading = False
                self._safe_after(lambda: (
                    self._btn_search.configure(state="normal"),
                    self._progress.set(1.0),
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_kwic(self, result) -> None:
        for item in self._kwic_tree.get_children():
            self._kwic_tree.delete(item)

        lines = result.sorted_by(self._sort_key)
        for i, ln in enumerate(lines, 1):
            self._kwic_tree.insert("", "end", values=(
                i,
                ln.left_str,
                ln.keyword,
                ln.right_str,
                ln.uci_id,
            ))

        freq = result.frequency
        disp = result.dispersion_d
        rel  = result.relative_freq
        self._hit_count_label.configure(
            text=f"{freq} ocorrências  ·  DispD={disp:.3f}  ·  {rel:.2f}/1k"
        )
        self._status_label.configure(
            text=f"'{result.query}' — {freq} hits em {result.ucis_with_hits}/{result.total_ucis} UCIs",
            text_color=COLORS["text_secondary"],
        )

    def _on_sort_change(self, _=None) -> None:
        if not self._result:
            return
        self._sort_key = _SORT_OPTIONS.get(self._sort_var.get(), "pos")
        self._populate_kwic(self._result)

    def _on_line_select(self, event) -> None:
        sel = self._kwic_tree.selection()
        if not sel or not self._result:
            return
        iid = sel[0]
        idx = self._kwic_tree.index(iid)
        lines = self._result.sorted_by(self._sort_key)
        if idx < len(lines):
            ln = lines[idx]
            vars_str = "  ·  ".join(f"{k}={v}" for k, v in sorted(ln.uci_vars.items()))
            self._detail_label.configure(
                text=f"{ln.sentence}   [{vars_str}]"
            )

    # ------------------------------------------------------------------
    # Collocates
    # ------------------------------------------------------------------

    def _compute_collocates(self) -> None:
        if not self._result:
            messagebox.showinfo("Faça uma busca primeiro",
                                "Execute uma busca antes de calcular collocates.", parent=self)
            return
        win = max(1, int(self._coll_window_var.get()))
        from collections import Counter
        left_c:  Counter = Counter()
        right_c: Counter = Counter()

        for ln in self._result.lines:
            for tok in ln.left_tokens[-win:]:
                left_c[tok.lower()] += 1
            for tok in ln.right_tokens[:win]:
                right_c[tok.lower()] += 1

        all_words = set(left_c) | set(right_c)
        rows = []
        for w in all_words:
            rows.append((w, left_c[w], right_c[w], left_c[w] + right_c[w]))
        rows.sort(key=lambda r: -r[3])

        for item in self._coll_tree.get_children():
            self._coll_tree.delete(item)
        for i, (word, fl, fr, total) in enumerate(rows, 1):
            self._coll_tree.insert("", "end", values=(i, word, fl, fr, total))

    # ------------------------------------------------------------------
    # Aba Por UCI
    # ------------------------------------------------------------------

    def _populate_uci_tab(self, result) -> None:
        for item in self._uci_tree.get_children():
            self._uci_tree.delete(item)

        if not self._engine:
            return

        from collections import Counter
        uci_hits: Counter = Counter()
        for ln in result.lines:
            uci_hits[ln.uci_index] += 1

        for uci in self._engine._ucis:
            hits = uci_hits.get(uci.index, 0)
            if hits == 0:
                continue
            tok_count = len(uci.tokens)
            rel = (hits / tok_count * 1000) if tok_count else 0.0
            vars_str = "  ·  ".join(f"{k}={v}" for k, v in sorted(uci.vars.items()))
            self._uci_tree.insert("", "end", values=(
                uci.uci_id, hits, tok_count, f"{rel:.2f}", vars_str
            ))

    # ------------------------------------------------------------------
    # Exportação
    # ------------------------------------------------------------------

    def _require_result(self) -> bool:
        if not self._result:
            messagebox.showinfo("Faça uma busca", "Execute uma busca antes de exportar.", parent=self)
            return False
        return True

    def _export_csv(self) -> None:
        if not self._require_result():
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar KWIC CSV",
            defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if path:
            from ...analysis.kwic_engine import KWICEngine
            KWICEngine.export_csv(self._result, path, sort_key=self._sort_key)
            messagebox.showinfo("Exportado", f"CSV salvo:\n{path}", parent=self)

    def _export_txt(self) -> None:
        if not self._require_result():
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar KWIC TXT",
            defaultextension=".txt", filetypes=[("TXT", "*.txt")]
        )
        if path:
            from ...analysis.kwic_engine import KWICEngine
            KWICEngine.export_txt(self._result, path, sort_key=self._sort_key)
            messagebox.showinfo("Exportado", f"TXT salvo:\n{path}", parent=self)

    def _copy_lines(self) -> None:
        if not self._require_result():
            return
        lines = self._result.sorted_by(self._sort_key)
        rows = ["Contexto Esq.\tPALAVRA\tContexto Dir.\tUCI"]
        for ln in lines:
            rows.append(f"{ln.left_str}\t{ln.keyword}\t{ln.right_str}\t{ln.uci_id}")
        self.clipboard_clear()
        self.clipboard_append("\n".join(rows))
        self._status_label.configure(text=f"{len(lines)} linhas copiadas para a área de transferência.")

    # ------------------------------------------------------------------
    def _safe_after(self, callback) -> None:
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except Exception:
            pass
