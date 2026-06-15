"""
RollingWindowDialog - Diálogo de Rolling Window Analysis.
==========================================================
Inspirado no Lexos Rolling Window.

Fluxo:
  ① Usuário digita termos-alvo (um por linha)
  ② Configura: janela (tokens), passo, métrica
  ③ Executa → gráfico matplotlib embutido
  ④ Exportar: PNG · SVG · CSV
"""

import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from ..styles import COLORS, FONTS, SIZES, get_themed_color
from ..iconography import create_help_button, label_with_icon
from ...utils.logger import get_logger

log = get_logger(__name__)

# Paleta de cores para os termos
_TERM_COLORS = [
    "#4E79A7", "#E15759", "#59A14F", "#F28E2B",
    "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7",
    "#9C755F", "#BAB0AC",
]

_METRIC_LABELS = {
    "raw_count": "Contagem bruta",
    "ratio":     "Proporção (frequência relativa)",
    "presence":  "Presença (0/1)",
}


class RollingWindowDialog(ctk.CTkToplevel):
    """
    Diálogo de Rolling Window Analysis com gráfico embutido.

    Args:
        parent:       Janela pai.
        corpus_text:  Texto do corpus.
        output_dir:   Pasta padrão para exportação.
    """

    def __init__(
        self,
        parent,
        corpus_text: str,
        output_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Rolling Window Analysis  (Lexos-inspired)")
        self.geometry("1000x700")
        self.minsize(760, 520)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._corpus_text = corpus_text
        self._output_dir  = output_dir or Path.home() / "labiia_lex_RW"
        self._result      = None
        self._fig         = None         # matplotlib Figure
        self._analyzer    = None
        self._running     = False

        self._create_widgets()
        self._center_on_parent(parent)
        # pré-carregar analyzer em background
        self.after(100, self._preload_analyzer)

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
        # ── Painel lateral de configuração ──────────────────────────────
        left = ctk.CTkFrame(self, fg_color=get_themed_color("sidebar_bg"),
                            width=240, corner_radius=0)
        left.pack(side="left", fill="y", padx=0, pady=0)
        left.pack_propagate(False)

        # Linha divisória direita
        ctk.CTkFrame(self, width=1, fg_color=get_themed_color("border"),
                     corner_radius=0).pack(side="left", fill="y")

        # Termos
        terms_title_row = ctk.CTkFrame(left, fg_color="transparent")
        terms_title_row.pack(fill="x", padx=10, pady=(12, 2))
        ctk.CTkLabel(terms_title_row, text="Termos a rastrear:", font=FONTS["heading"],
                     anchor="w").pack(side="left")
        self._create_help_icon(
            terms_title_row,
            "Liste um termo por linha. O gráfico mostra a evolução de cada termo ao longo do corpus.",
        ).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(left,
                     text="(um por linha, separados por Enter)",
                     font=FONTS["small"],
                     text_color=COLORS["text_secondary"],
                     anchor="w").pack(fill="x", padx=10)

        self._terms_text = ctk.CTkTextbox(left, height=120, font=FONTS["mono"]
                                          if "mono" in FONTS else FONTS["body"],
                                          corner_radius=3)
        self._terms_text.pack(fill="x", padx=10, pady=(4, 8))
        self._terms_text.insert("1.0", "democracia\nliberdade")

        # Separador
        ctk.CTkFrame(left, height=1, fg_color=get_themed_color("border")).pack(
            fill="x", padx=8, pady=4)

        # Janela
        win_title_row = ctk.CTkFrame(left, fg_color="transparent")
        win_title_row.pack(fill="x", padx=10)
        ctk.CTkLabel(win_title_row, text="Tamanho da janela (tokens):",
                     font=FONTS["small"], anchor="w").pack(side="left")
        self._create_help_icon(
            win_title_row,
            "Quantidade de tokens por janela. Janela maior suaviza variações locais.",
        ).pack(side="left", padx=(6, 0))
        win_row = ctk.CTkFrame(left, fg_color="transparent")
        win_row.pack(fill="x", padx=10, pady=(2, 6))
        self._window_var = ctk.IntVar(value=100)
        ctk.CTkSlider(win_row, from_=10, to=500, number_of_steps=49,
                      variable=self._window_var, width=150).pack(side="left")
        self._window_lbl = ctk.CTkLabel(win_row, text="100",
                                        font=FONTS["small"], width=36)
        self._window_lbl.pack(side="left", padx=(4, 0))
        self._window_var.trace_add("write",
            lambda *_: self._window_lbl.configure(text=str(self._window_var.get())))

        # Passo
        step_title_row = ctk.CTkFrame(left, fg_color="transparent")
        step_title_row.pack(fill="x", padx=10)
        ctk.CTkLabel(step_title_row, text="Passo (tokens):",
                     font=FONTS["small"], anchor="w").pack(side="left")
        self._create_help_icon(
            step_title_row,
            "Distância entre janelas consecutivas. Passo menor aumenta a resolução do gráfico.",
        ).pack(side="left", padx=(6, 0))
        step_row = ctk.CTkFrame(left, fg_color="transparent")
        step_row.pack(fill="x", padx=10, pady=(2, 6))
        self._step_var = ctk.IntVar(value=10)
        ctk.CTkSlider(step_row, from_=1, to=100, number_of_steps=99,
                      variable=self._step_var, width=150).pack(side="left")
        self._step_lbl = ctk.CTkLabel(step_row, text="10",
                                      font=FONTS["small"], width=36)
        self._step_lbl.pack(side="left", padx=(4, 0))
        self._step_var.trace_add("write",
            lambda *_: self._step_lbl.configure(text=str(self._step_var.get())))

        # Métrica
        metric_title_row = ctk.CTkFrame(left, fg_color="transparent")
        metric_title_row.pack(fill="x", padx=10)
        ctk.CTkLabel(metric_title_row, text="Métrica:", font=FONTS["small"],
                     anchor="w").pack(side="left")
        self._create_help_icon(
            metric_title_row,
            "Contagem bruta: total de ocorrências; Proporção: frequência relativa; Presença: 0/1 por janela.",
        ).pack(side="left", padx=(6, 0))
        self._metric_var = ctk.StringVar(value="ratio")
        for key, label in _METRIC_LABELS.items():
            ctk.CTkRadioButton(
                left, text=label, variable=self._metric_var, value=key,
                font=FONTS["small"],
            ).pack(anchor="w", padx=14, pady=1)

        # Marcadores de UCI
        ctk.CTkFrame(left, height=1, fg_color=get_themed_color("border")).pack(
            fill="x", padx=8, pady=8)
        self._show_boundaries_var = ctk.BooleanVar(value=True)
        boundaries_row = ctk.CTkFrame(left, fg_color="transparent")
        boundaries_row.pack(fill="x", padx=10)
        ctk.CTkCheckBox(boundaries_row, text="Marcar fronteiras de UCI",
                        variable=self._show_boundaries_var, font=FONTS["small"],
                        checkbox_width=16, checkbox_height=16,
                        command=self._redraw_if_done).pack(side="left")
        self._create_help_icon(
            boundaries_row,
            "Desenha linhas verticais indicando limites entre documentos (UCIs) no eixo x.",
        ).pack(side="left", padx=(6, 0))

        # Suavização (média móvel sobre os pontos)
        smooth_title_row = ctk.CTkFrame(left, fg_color="transparent")
        smooth_title_row.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(smooth_title_row, text="Suavização (pontos):",
                     font=FONTS["small"], anchor="w").pack(side="left")
        self._create_help_icon(
            smooth_title_row,
            "Aplica média móvel sobre a curva. Valores maiores deixam o traçado mais suave.",
        ).pack(side="left", padx=(6, 0))
        smooth_row = ctk.CTkFrame(left, fg_color="transparent")
        smooth_row.pack(fill="x", padx=10, pady=(2, 6))
        self._smooth_var = ctk.IntVar(value=1)
        ctk.CTkSlider(smooth_row, from_=1, to=20, number_of_steps=19,
                      variable=self._smooth_var, width=150,
                      command=lambda _: self._redraw_if_done()).pack(side="left")
        self._smooth_lbl = ctk.CTkLabel(smooth_row, text="1",
                                        font=FONTS["small"], width=36)
        self._smooth_lbl.pack(side="left", padx=(4, 0))
        self._smooth_var.trace_add("write",
            lambda *_: self._smooth_lbl.configure(text=str(self._smooth_var.get())))

        # Botão executar
        ctk.CTkFrame(left, height=1, fg_color=get_themed_color("border")).pack(
            fill="x", padx=8, pady=8)
        self._btn_run = ctk.CTkButton(
            left, text="▶  Executar", height=30,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            border_width=0, corner_radius=3,
            command=self._run,
        )
        self._btn_run.pack(fill="x", padx=10, pady=(0, 4))

        # Status
        self._status_label = ctk.CTkLabel(
            left, text="", font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            wraplength=210, anchor="w", justify="left",
        )
        self._status_label.pack(fill="x", padx=10)

        # ── Área do gráfico ──────────────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color=get_themed_color("surface"),
                             corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        # Frame para o canvas matplotlib
        self._chart_frame = tk.Frame(right, bg=COLORS["surface"])
        self._chart_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Placeholder antes do gráfico
        self._placeholder = ctk.CTkLabel(
            self._chart_frame,
            text=(
                "Configure os termos e parâmetros no painel\n"
                "à esquerda e clique em ▶ Executar."
            ),
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Barra de progresso
        self._progress = ctk.CTkProgressBar(right, height=3, corner_radius=0)
        self._progress.pack(fill="x", side="bottom")
        self._progress.set(0)

        # Botões de exportação
        export_row = ctk.CTkFrame(right, fg_color="transparent")
        export_row.pack(fill="x", side="bottom", padx=6, pady=4)

        def _exp_btn(text, cmd, width=130):
            return ctk.CTkButton(
                export_row, text=text, height=26, width=width,
                fg_color=get_themed_color("button"),
                hover_color=get_themed_color("button_hover"),
                text_color=get_themed_color("text"),
                border_width=1, border_color=get_themed_color("border"),
                corner_radius=3, font=FONTS["small"],
                command=cmd,
            )

        _exp_btn(label_with_icon("save", "Exportar PNG"), self._export_png).pack(side="left", padx=(0, 4))
        _exp_btn(label_with_icon("save", "Exportar SVG"), self._export_svg).pack(side="left", padx=(0, 4))
        _exp_btn(label_with_icon("export", "Exportar CSV"), self._export_csv).pack(side="left")

        ctk.CTkButton(
            export_row, text="Fechar", height=26, width=80,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3, font=FONTS["small"],
            command=self.destroy,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Pré-carregar analyzer
    # ------------------------------------------------------------------

    def _preload_analyzer(self) -> None:
        def worker():
            try:
                from ...analysis.rolling_window import RollingWindowAnalyzer
                self._analyzer = RollingWindowAnalyzer(self._corpus_text)
                n = len(self._analyzer._tokens)
                self._safe_after(lambda: self._status_label.configure(
                    text=f"Corpus: {n:,} tokens prontos."
                ))
            except Exception as exc:
                log.exception("Erro ao pré-carregar RollingWindow")
                self._safe_after(lambda: self._status_label.configure(
                    text=f"Erro: {exc}", text_color=COLORS["danger"]
                ))
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Executar análise
    # ------------------------------------------------------------------

    def _parse_terms(self):
        raw = self._terms_text.get("1.0", "end").strip()
        terms = [t.strip() for t in raw.splitlines() if t.strip()]
        return list(dict.fromkeys(terms))  # deduplicate preserving order

    def _run(self) -> None:
        if self._running:
            return
        terms = self._parse_terms()
        if not terms:
            messagebox.showinfo("Termos vazios",
                                "Digite ao menos um termo no campo à esquerda.",
                                parent=self)
            return
        if not self._analyzer:
            messagebox.showinfo("Aguarde", "O corpus ainda está carregando.", parent=self)
            return

        self._running = True
        self._btn_run.configure(state="disabled")
        self._progress.set(0.15)
        self._status_label.configure(text="Calculando...", text_color=COLORS["text_secondary"])

        window  = max(1, int(self._window_var.get()))
        step    = max(1, int(self._step_var.get()))
        metric  = self._metric_var.get()

        def worker():
            try:
                result = self._analyzer.run(
                    terms=terms,
                    window_size=window,
                    step=step,
                    metric=metric,
                )
                self._result = result
                self._safe_after(lambda: self._draw_chart(result))
            except Exception as exc:
                log.exception("Erro na Rolling Window")
                self._safe_after(lambda: self._status_label.configure(
                    text=f"Erro: {exc}", text_color=COLORS["danger"]
                ))
            finally:
                self._safe_after(lambda: (
                    self._progress.set(1.0),
                    self._btn_run.configure(state="normal"),
                ))
                self._running = False

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Gráfico matplotlib
    # ------------------------------------------------------------------

    def _draw_chart(self, result) -> None:
        """Renderiza o gráfico matplotlib no frame interno."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import numpy as np
        except ImportError as exc:
            self._status_label.configure(
                text=f"matplotlib não encontrado: {exc}",
                text_color=COLORS["danger"],
            )
            return

        # Destruir canvas anterior
        for widget in self._chart_frame.winfo_children():
            widget.destroy()

        smooth = max(1, int(self._smooth_var.get()))
        bg     = COLORS["surface"]
        text_c = COLORS["text"]

        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=96)
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        for i, series in enumerate(result.series):
            color = _TERM_COLORS[i % len(_TERM_COLORS)]
            x = series.positions
            y = series.values

            # Suavização por média móvel simples
            if smooth > 1 and len(y) >= smooth:
                kernel = np.ones(smooth) / smooth
                y_smooth = list(np.convolve(y, kernel, mode="same"))
            else:
                y_smooth = y

            ax.plot(x, y_smooth, label=series.term, color=color,
                    linewidth=1.8, alpha=0.9)
            ax.fill_between(x, y_smooth, alpha=0.08, color=color)

        # Marcar fronteiras de UCI
        if self._show_boundaries_var.get():
            for boundary in result.segment_boundaries:
                if 0 < boundary < result.total_tokens:
                    ax.axvline(x=boundary, color=COLORS["border"],
                               linewidth=0.8, linestyle="--", alpha=0.6)

        # Estilo
        metric_label = _METRIC_LABELS.get(result.metric, result.metric)
        ax.set_xlabel("Posição no corpus (tokens)", color=text_c, fontsize=9)
        ax.set_ylabel(metric_label, color=text_c, fontsize=9)
        ax.set_title(
            f"Rolling Window  ·  janela={result.window_size} tokens  ·  passo={result.step}",
            color=text_c, fontsize=10, pad=8,
        )
        ax.tick_params(colors=text_c, labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(COLORS["border"])
        ax.legend(fontsize=9, facecolor=bg, edgecolor=COLORS["border"],
                  labelcolor=text_c)
        ax.grid(True, color=COLORS["border"], alpha=0.5, linewidth=0.5)
        fig.tight_layout(pad=1.2)

        # Embed
        canvas = FigureCanvasTkAgg(fig, master=self._chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        self._fig = fig
        n_points = len(result.series[0].positions) if result.series else 0
        self._status_label.configure(
            text=(
                f"{len(result.series)} termo(s)  ·  {result.total_tokens:,} tokens  "
                f"·  {n_points} pontos por série"
            ),
            text_color=COLORS["text_secondary"],
        )
        self._progress.set(1.0)

    def _redraw_if_done(self) -> None:
        if self._result:
            self._draw_chart(self._result)

    # ------------------------------------------------------------------
    # Exportação
    # ------------------------------------------------------------------

    def _require_result(self) -> bool:
        if not self._result:
            messagebox.showinfo("Execute a análise",
                                "Execute o Rolling Window antes de exportar.",
                                parent=self)
            return False
        return True

    def _export_png(self) -> None:
        if not self._require_result() or not self._fig:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar gráfico PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("Todos", "*.*")],
        )
        if path:
            self._fig.savefig(path, dpi=150, bbox_inches="tight")
            messagebox.showinfo("Exportado", f"PNG salvo em:\n{path}", parent=self)

    def _export_svg(self) -> None:
        if not self._require_result() or not self._fig:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar gráfico SVG",
            defaultextension=".svg",
            filetypes=[("SVG", "*.svg"), ("Todos", "*.*")],
        )
        if path:
            self._fig.savefig(path, format="svg", bbox_inches="tight")
            messagebox.showinfo("Exportado", f"SVG salvo em:\n{path}", parent=self)

    def _export_csv(self) -> None:
        if not self._require_result():
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar séries CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if path:
            from ...analysis.rolling_window import RollingWindowAnalyzer
            RollingWindowAnalyzer.export_csv(self._result, path)
            messagebox.showinfo("Exportado", f"CSV salvo em:\n{path}", parent=self)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _safe_after(self, callback) -> None:
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except Exception:
            pass
