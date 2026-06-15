"""
KeynessDialog — comparação de corpora com backend exclusivo em R (quanteda).
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from ..styles import COLORS, FONTS, get_themed_color
from ...analysis.keyness_r import KeynessRAnalysis, KeynessRAnalysisError, KeynessRResult
from ...utils.logger import get_logger
from ...utils.paths import PathManager


log = get_logger(__name__)

_TABLE_SORTS = {
    "Keyness (|estat|)": "statistic",
    "p-valor": "p_value",
    "Freq. em A": "freq_a",
    "Freq. em B": "freq_b",
    "Norm/M em A": "norm_a",
    "Norm/M em B": "norm_b",
}

_R_MEASURES = {
    "Log-Likelihood (lr)": "lr",
    "Qui-quadrado (chi2)": "chi2",
}

_COLOR_A = "#4E79A7"
_COLOR_B = "#E15759"
_COLOR_A_BORDER = "#A9C4E5"
_COLOR_B_BORDER = "#E8B0B0"
_COLOR_A_HEADER_BG = "#EAF2FA"
_COLOR_B_HEADER_BG = "#FDECEC"
_COLOR_A_ROW_BG = "#EDF4FB"
_COLOR_B_ROW_BG = "#FDEFF0"


class KeynessDialog(ctk.CTkToplevel):
    """Diálogo de keyness com execução obrigatória em R/quanteda."""

    def __init__(
        self,
        parent,
        corpus_text_a: Optional[str] = None,
        corpus_name_a: str = "Corpus A (atual)",
    ) -> None:
        super().__init__(parent)
        self.title("Análise de Keyness  (R / quanteda)")
        self.geometry("1080x740")
        self.minsize(860, 560)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._text_a = corpus_text_a or ""
        self._text_b = ""
        self._name_a = corpus_name_a
        self._name_b = "Corpus B (Referência)"
        self._result: Optional[KeynessRResult] = None
        self._running = False
        self._sort_key = "statistic"
        self._output_dir = PathManager.user_data_dir() / "keyness_r"
        self._analysis = KeynessRAnalysis(self._output_dir)
        self._tab_corpora = "1 Corpora"
        self._tab_keywords = "2 Keywords"
        self._tab_summary = "3 Resumo"

        self._create_widgets()
        self._center_on_parent(parent)
        if self._text_a:
            self.after(50, lambda: self._name_a_var.set(corpus_name_a))

    def _center_on_parent(self, parent) -> None:
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        dw, dh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _create_widgets(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=get_themed_color("header_bg"), corner_radius=0, height=38)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Keyness (R/quanteda) — Comparação de Corpora", font=FONTS["heading"]).pack(
            side="left", padx=12
        )
        self._hdr_status = ctk.CTkLabel(
            hdr,
            text="Backend exclusivo em R",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="e",
        )
        self._hdr_status.pack(side="right", padx=12)

        self._progress = ctk.CTkProgressBar(self, height=3, corner_radius=0)
        self._progress.pack(fill="x")
        self._progress.set(0)

        self._tabs = ctk.CTkTabview(self, corner_radius=4)
        self._tabs.pack(fill="both", expand=True, padx=6, pady=4)
        self._tabs.add(self._tab_corpora)
        self._tabs.add(self._tab_keywords)
        self._tabs.add(self._tab_summary)

        self._build_tab_corpora(self._tabs.tab(self._tab_corpora))
        self._build_tab_keywords(self._tabs.tab(self._tab_keywords))
        self._build_tab_summary(self._tabs.tab(self._tab_summary))
        self._style_tabs()

        ctk.CTkFrame(self, height=1, fg_color=get_themed_color("border")).pack(fill="x", side="bottom")
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=10, pady=6)

        self._btn_run = ctk.CTkButton(
            btn_row,
            text="▶  Calcular Keyness (R)",
            height=28,
            width=190,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            border_width=0,
            corner_radius=3,
            command=self._run_analysis,
        )
        self._btn_run.pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="Exportar CSV",
            height=28,
            width=150,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            font=FONTS["small"],
            command=self._export_csv,
        ).pack(side="left", padx=(8, 4))
        ctk.CTkButton(
            btn_row,
            text="Copiar tabela",
            height=28,
            width=150,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            font=FONTS["small"],
            command=self._copy_table,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row,
            text="Fechar",
            height=28,
            width=80,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            font=FONTS["small"],
            command=self.destroy,
        ).pack(side="right")

    def _style_tabs(self) -> None:
        """Padroniza estilo das abas e garante contraste legível."""
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
    # Tab 1
    # ------------------------------------------------------------------
    def _build_tab_corpora(self, tab) -> None:
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        frame_a = ctk.CTkFrame(
            tab,
            fg_color=get_themed_color("surface"),
            corner_radius=4,
            border_width=1,
            border_color=_COLOR_A_BORDER,
        )
        frame_a.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 4), pady=4)

        hdr_a = ctk.CTkFrame(frame_a, fg_color=_COLOR_A_HEADER_BG, corner_radius=3)
        hdr_a.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(hdr_a, text="Corpus A — Foco", font=FONTS["heading"]).pack(side="left", padx=8, pady=4)

        name_row_a = ctk.CTkFrame(frame_a, fg_color="transparent")
        name_row_a.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(name_row_a, text="Nome:", font=FONTS["small"]).pack(side="left")
        self._name_a_var = ctk.StringVar(value=self._name_a)
        ctk.CTkEntry(name_row_a, textvariable=self._name_a_var, height=26, corner_radius=3, width=200).pack(
            side="left", padx=4
        )

        self._text_a_box = ctk.CTkTextbox(
            frame_a,
            height=250,
            font=("Consolas", 8),
            fg_color=get_themed_color("surface"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
        )
        self._text_a_box.pack(fill="both", expand=True, padx=8, pady=4)
        if self._text_a:
            self._text_a_box.insert("1.0", self._text_a[:12000])
            if len(self._text_a) > 12000:
                self._text_a_box.insert("end", "\n\n[... texto truncado no preview ...]")

        btn_row_a = ctk.CTkFrame(frame_a, fg_color="transparent")
        btn_row_a.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkButton(
            btn_row_a,
            text="Carregar arquivo",
            height=26,
            width=160,
            font=FONTS["small"],
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=lambda: self._load_file("a"),
        ).pack(side="left")
        self._lbl_a_info = ctk.CTkLabel(btn_row_a, text="", font=FONTS["small"], text_color=COLORS["text_secondary"])
        self._lbl_a_info.pack(side="left", padx=8)
        if self._text_a:
            self._update_corpus_info("a", self._text_a)

        frame_b = ctk.CTkFrame(
            tab,
            fg_color=get_themed_color("surface"),
            corner_radius=4,
            border_width=1,
            border_color=_COLOR_B_BORDER,
        )
        frame_b.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(4, 0), pady=4)

        hdr_b = ctk.CTkFrame(frame_b, fg_color=_COLOR_B_HEADER_BG, corner_radius=3)
        hdr_b.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(hdr_b, text="Corpus B — Referência", font=FONTS["heading"]).pack(side="left", padx=8, pady=4)

        name_row_b = ctk.CTkFrame(frame_b, fg_color="transparent")
        name_row_b.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(name_row_b, text="Nome:", font=FONTS["small"]).pack(side="left")
        self._name_b_var = ctk.StringVar(value=self._name_b)
        ctk.CTkEntry(name_row_b, textvariable=self._name_b_var, height=26, corner_radius=3, width=200).pack(
            side="left", padx=4
        )

        self._text_b_box = ctk.CTkTextbox(
            frame_b,
            height=250,
            font=("Consolas", 8),
            fg_color=get_themed_color("surface"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
        )
        self._text_b_box.pack(fill="both", expand=True, padx=8, pady=4)
        self._text_b_box.insert("1.0", "Cole aqui o texto do corpus B\nou use o botão 'Carregar arquivo'…")

        btn_row_b = ctk.CTkFrame(frame_b, fg_color="transparent")
        btn_row_b.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkButton(
            btn_row_b,
            text="Carregar arquivo",
            height=26,
            width=160,
            font=FONTS["small"],
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=lambda: self._load_file("b"),
        ).pack(side="left")
        self._lbl_b_info = ctk.CTkLabel(btn_row_b, text="", font=FONTS["small"], text_color=COLORS["text_secondary"])
        self._lbl_b_info.pack(side="left", padx=8)

        params = ctk.CTkFrame(tab, fg_color="transparent")
        params.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        ctk.CTkLabel(params, text="Freq. mínima:", font=FONTS["small"]).pack(side="left")
        self._min_freq_var = ctk.IntVar(value=3)
        ctk.CTkSlider(params, from_=1, to=30, number_of_steps=29, variable=self._min_freq_var, width=100).pack(
            side="left", padx=(4, 2)
        )
        self._min_freq_lbl = ctk.CTkLabel(params, text="3", font=FONTS["small"], width=24)
        self._min_freq_lbl.pack(side="left", padx=(0, 10))
        self._min_freq_var.trace_add(
            "write",
            lambda *_: self._min_freq_lbl.configure(text=str(self._min_freq_var.get())),
        )

        self._stopwords_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            params,
            text="Remover stopwords PT",
            variable=self._stopwords_var,
            font=FONTS["small"],
            checkbox_width=14,
            checkbox_height=14,
        ).pack(side="left", padx=8)

        ctk.CTkLabel(params, text="Métrica R:", font=FONTS["small"]).pack(side="left", padx=(10, 4))
        self._measure_var = ctk.StringVar(value="Log-Likelihood (lr)")
        ctk.CTkOptionMenu(
            params,
            values=list(_R_MEASURES.keys()),
            variable=self._measure_var,
            width=170,
            height=26,
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(params, text="Top no gráfico:", font=FONTS["small"]).pack(side="left")
        self._topn_var = ctk.IntVar(value=30)
        ctk.CTkSlider(params, from_=10, to=120, number_of_steps=22, variable=self._topn_var, width=90).pack(
            side="left", padx=(4, 2)
        )
        self._topn_lbl = ctk.CTkLabel(params, text="30", font=FONTS["small"], width=26)
        self._topn_lbl.pack(side="left")
        self._topn_var.trace_add("write", lambda *_: self._topn_lbl.configure(text=str(self._topn_var.get())))

    # ------------------------------------------------------------------
    # Tab 2
    # ------------------------------------------------------------------
    def _build_tab_keywords(self, tab) -> None:
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=(4, 2))

        ctk.CTkLabel(ctrl, text="Ordenar por:", font=FONTS["small"]).pack(side="left")
        self._table_metric_var = ctk.StringVar(value="Keyness (|estat|)")
        ctk.CTkOptionMenu(
            ctrl,
            values=list(_TABLE_SORTS.keys()),
            variable=self._table_metric_var,
            width=170,
            height=26,
            command=self._on_metric_change,
        ).pack(side="left", padx=4)

        ctk.CTkLabel(ctrl, text="Limite visual:", font=FONTS["small"]).pack(side="left", padx=(14, 0))
        self._show_n_var = ctk.IntVar(value=80)
        ctk.CTkSlider(
            ctrl,
            from_=20,
            to=300,
            number_of_steps=28,
            variable=self._show_n_var,
            width=90,
            command=lambda _: self._redraw_if_done(),
        ).pack(side="left", padx=4)
        self._show_n_lbl = ctk.CTkLabel(ctrl, text="80", font=FONTS["small"], width=30)
        self._show_n_lbl.pack(side="left")
        self._show_n_var.trace_add("write", lambda *_: self._show_n_lbl.configure(text=str(self._show_n_var.get())))

        for color, label in [(_COLOR_A, "Chave em A"), (_COLOR_B, "Chave em B")]:
            ctk.CTkLabel(ctrl, text=label, font=FONTS["small"], text_color=color).pack(side="right", padx=8)

        tv_frame = tk.Frame(tab, bg=COLORS["background"])
        tv_frame.pack(fill="both", expand=True, padx=2, pady=2)

        style = ttk.Style()
        style.configure(
            "KNR.Treeview",
            rowheight=20,
            font=("Segoe UI", 10),
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.configure("KNR.Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.map("KNR.Treeview", background=[("selected", COLORS["selection"])], foreground=[("selected", "#FFFFFF")])

        cols = ("rank", "word", "dir", "freq_a", "freq_b", "norm_a", "norm_b", "stat", "p")
        self._kn_tree = ttk.Treeview(tv_frame, style="KNR.Treeview", columns=cols, show="headings", selectmode="browse")
        for col, label, width, anchor in [
            ("rank", "#", 42, "center"),
            ("word", "Termo", 190, "w"),
            ("dir", "Chave em", 90, "center"),
            ("freq_a", "Freq A", 80, "center"),
            ("freq_b", "Freq B", 80, "center"),
            ("norm_a", "Norm/M A", 95, "center"),
            ("norm_b", "Norm/M B", 95, "center"),
            ("stat", "Keyness", 90, "center"),
            ("p", "p-valor", 90, "center"),
        ]:
            self._kn_tree.heading(col, text=label, command=lambda c=col: self._sort_by_col(c))
            self._kn_tree.column(col, width=width, anchor=anchor, stretch=(col == "word"))

        vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=self._kn_tree.yview)
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=self._kn_tree.xview)
        self._kn_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._kn_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        self._kn_tree.tag_configure("kw_a", background=_COLOR_A_ROW_BG)
        self._kn_tree.tag_configure("kw_b", background=_COLOR_B_ROW_BG)

        self._kn_status = ctk.CTkLabel(
            tab,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self._kn_status.pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------------
    # Tab 3
    # ------------------------------------------------------------------
    def _build_tab_summary(self, tab) -> None:
        self._summary_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._summary_frame.pack(fill="both", expand=True)
        self._summary_label = ctk.CTkLabel(
            self._summary_frame,
            text="Execute a análise para ver o resumo comparativo.",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
        )
        self._summary_label.pack(fill="x", padx=10, pady=10)

    # ------------------------------------------------------------------
    # File IO helpers
    # ------------------------------------------------------------------
    def _load_file(self, which: str) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=f"Carregar Corpus {'A' if which == 'a' else 'B'}",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            if which == "a":
                self._text_a = text
                self._text_a_box.delete("1.0", "end")
                self._text_a_box.insert("1.0", text[:12000])
                self._name_a_var.set(Path(path).stem)
                self._update_corpus_info("a", text)
            else:
                self._text_b = text
                self._text_b_box.delete("1.0", "end")
                self._text_b_box.insert("1.0", text[:12000])
                self._name_b_var.set(Path(path).stem)
                self._update_corpus_info("b", text)
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)

    def _update_corpus_info(self, which: str, text: str) -> None:
        import re as _re

        words = _re.findall(r"\b\w+\b", str(text or ""))
        info = f"{len(words):,} tokens  ·  {len(set(words)):,} formas"
        if which == "a":
            self._lbl_a_info.configure(text=info)
        else:
            self._lbl_b_info.configure(text=info)

    def _get_text_a(self) -> str:
        box_text = self._text_a_box.get("1.0", "end").strip()
        return box_text if box_text else self._text_a

    def _get_text_b(self) -> str:
        box_text = self._text_b_box.get("1.0", "end").strip()
        return box_text if box_text else self._text_b

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _run_analysis(self) -> None:
        if self._running:
            return

        text_a = self._get_text_a()
        text_b = self._get_text_b()
        if not text_a.strip():
            messagebox.showinfo("Corpus A vazio", "Defina o Corpus A antes de calcular.", parent=self)
            return
        if not text_b.strip() or "Cole aqui" in text_b:
            messagebox.showinfo("Corpus B vazio", "Defina o Corpus B antes de calcular.", parent=self)
            return

        name_a = self._name_a_var.get().strip() or "Corpus A"
        name_b = self._name_b_var.get().strip() or "Corpus B"
        min_f = max(1, int(self._min_freq_var.get()))
        top_n = max(5, int(self._topn_var.get()))
        measure = _R_MEASURES.get(self._measure_var.get(), "lr")
        remove_sw = bool(self._stopwords_var.get())

        self._running = True
        self._btn_run.configure(state="disabled")
        self._progress.set(0.2)
        self._hdr_status.configure(text="Executando keyness em R...")

        def worker() -> None:
            try:
                result = self._analysis.run(
                    text_a=text_a,
                    text_b=text_b,
                    name_a=name_a,
                    name_b=name_b,
                    params={
                        "min_freq": min_f,
                        "top_n": top_n,
                        "measure": measure,
                        "remove_stopwords": remove_sw,
                        "stopwords_lang": "pt",
                    },
                )
                self._result = result
                self._sort_key = "statistic"
                self._safe_after(lambda: self._populate_keywords(result, self._sort_key))
                self._safe_after(lambda: self._populate_summary(result))
                self._safe_after(lambda: self._tabs.set(self._tab_keywords))
            except KeynessRAnalysisError as exc:
                log.warning("Erro de Keyness (R): %s", exc)
                self._safe_after(lambda: messagebox.showerror("Keyness (R)", str(exc), parent=self))
            except Exception as exc:
                log.exception("Erro inesperado no Keyness (R)")
                self._safe_after(lambda: messagebox.showerror("Erro", str(exc), parent=self))
            finally:
                self._running = False
                self._safe_after(
                    lambda: (
                        self._btn_run.configure(state="normal"),
                        self._progress.set(1.0),
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _populate_keywords(self, result: KeynessRResult, metric: str) -> None:
        for item in self._kn_tree.get_children():
            self._kn_tree.delete(item)

        show_n = max(20, int(self._show_n_var.get()))
        rows = result.sorted_by(metric)[:show_n]
        for idx, row in enumerate(rows, start=1):
            tag = "kw_a" if str(row.direction).upper() == "A" else "kw_b"
            p_str = "NA" if math.isnan(float(row.p_value)) else f"{float(row.p_value):.3g}"
            self._kn_tree.insert(
                "",
                "end",
                tags=(tag,),
                values=(
                    idx,
                    row.word,
                    row.direction,
                    row.freq_a,
                    row.freq_b,
                    f"{row.norm_a:.1f}",
                    f"{row.norm_b:.1f}",
                    f"{row.statistic:.3f}",
                    p_str,
                ),
            )

        self._kn_status.configure(
            text=(
                f"{len(result.rows)} termos avaliados  ·  "
                f"{len(result.key_in_a)} em A  ·  {len(result.key_in_b)} em B  ·  "
                f"mostrando {len(rows)}"
            )
        )
        self._hdr_status.configure(
            text=(
                f"A: {result.total_a:,}t  ·  B: {result.total_b:,}t  ·  "
                f"medida R: {result.measure}"
            ),
            text_color=COLORS["text_secondary"],
        )

    def _populate_summary(self, result: KeynessRResult) -> None:
        top_a = [row for row in result.sorted_by("statistic") if row.direction == "A"][:10]
        top_b = [row for row in result.sorted_by("statistic") if row.direction == "B"][:10]
        lines = [
            f"{'═' * 68}",
            f"  Keyness (R/quanteda)  ·  medida: {result.measure}",
            f"{'─' * 68}",
            f"  Corpus A: {result.name_a}  ·  tokens: {result.total_a:,}",
            f"  Corpus B: {result.name_b}  ·  tokens: {result.total_b:,}",
            f"  Freq. mínima: {result.min_freq}  ·  Top no gráfico: {result.top_n}",
            f"{'═' * 68}",
            "",
            "  Top termos-chave em A:",
        ]
        for row in top_a:
            p_str = "NA" if math.isnan(float(row.p_value)) else f"{float(row.p_value):.2e}"
            lines.append(
                f"    {row.word:20s}  key={row.statistic:>8.3f}  "
                f"freqA={row.freq_a:>5}  freqB={row.freq_b:>5}  p={p_str}"
            )
        lines.append("")
        lines.append("  Top termos-chave em B:")
        for row in top_b:
            p_str = "NA" if math.isnan(float(row.p_value)) else f"{float(row.p_value):.2e}"
            lines.append(
                f"    {row.word:20s}  key={row.statistic:>8.3f}  "
                f"freqA={row.freq_a:>5}  freqB={row.freq_b:>5}  p={p_str}"
            )
        lines.append(f"{'═' * 68}")
        self._summary_label.configure(text="\n".join(lines), font=("Consolas", 9))

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def _on_metric_change(self, _=None) -> None:
        if not self._result:
            return
        self._sort_key = _TABLE_SORTS.get(self._table_metric_var.get(), "statistic")
        self._populate_keywords(self._result, self._sort_key)

    def _sort_by_col(self, col: str) -> None:
        if not self._result:
            return
        col_to_metric = {
            "stat": "statistic",
            "p": "p_value",
            "freq_a": "freq_a",
            "freq_b": "freq_b",
            "norm_a": "norm_a",
            "norm_b": "norm_b",
        }
        if col in col_to_metric:
            self._sort_key = col_to_metric[col]
            self._populate_keywords(self._result, self._sort_key)

    def _redraw_if_done(self) -> None:
        if self._result:
            self._populate_keywords(self._result, self._sort_key)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _export_csv(self) -> None:
        if not self._result:
            messagebox.showinfo("Calcule primeiro", "Execute a análise antes de exportar.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar Keyness CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        KeynessRAnalysis.export_csv(self._result, Path(path), metric=self._sort_key)
        messagebox.showinfo("Exportado", f"CSV salvo em:\n{path}", parent=self)

    def _copy_table(self) -> None:
        if not self._result:
            return
        rows = self._result.sorted_by(self._sort_key)
        lines = ["Termo\tDireção\tKeyness\tp-valor\tFreq A\tFreq B\tNorm/M A\tNorm/M B"]
        for row in rows:
            p_str = "NA" if math.isnan(float(row.p_value)) else f"{float(row.p_value):.6g}"
            lines.append(
                f"{row.word}\t{row.direction}\t{row.statistic:.6f}\t{p_str}\t"
                f"{row.freq_a}\t{row.freq_b}\t{row.norm_a:.3f}\t{row.norm_b:.3f}"
            )
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._hdr_status.configure(text=f"{len(rows)} linhas copiadas.", text_color=COLORS["text_secondary"])

    # ------------------------------------------------------------------
    def _safe_after(self, callback) -> None:
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except Exception:
            pass
