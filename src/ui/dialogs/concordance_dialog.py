"""Interactive concordance (KWIC) dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, List
import csv

import customtkinter as ctk

from ...analysis.concordancer import (
    Concordancer,
    ConcordanceContext,
    ConcordancerError,
)
from ..styles import FONTS, COLORS, get_themed_color
from ..iconography import create_help_button
from ..widgets.tooltip import CTkTooltip


class ConcordanceDialog(ctk.CTkToplevel):
    """Dialog for KWIC word/regex search with full UCE preview."""

    def __init__(self, parent, corpus):
        super().__init__(parent)
        self.title("Concordância (KWIC)")
        self.geometry("1080x600")
        self.minsize(850, 500)
        self.transient(parent)
        self.grab_set()

        self._concordancer = Concordancer(corpus)
        self._contexts: List[ConcordanceContext] = []
        self._result_index_by_item: Dict[str, int] = {}

        self._create_widgets()
        self._center_on_parent(parent)
        self.query_entry.focus_set()

    def _center_on_parent(self, parent):
        """Center the dialog over parent window."""
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        dialog_w = self.winfo_width()
        dialog_h = self.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.geometry(f"+{x}+{y}")

    def _create_help_icon(self, parent, text: str) -> ctk.CTkButton:
        """Cria ícone de ajuda padronizado com tooltip."""
        return create_help_button(parent, text, size=18)

    def _create_widgets(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=12, pady=12)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            header,
            text="Concordância (KWIC)",
            font=FONTS["title"],
        ).pack(side="left")
        self._create_help_icon(
            header,
            "A concordância permite pesquisar uma palavra ou padrão e exibir o contexto (texto à esquerda e à direita) ao redor dela (Keyword in Context)."
        ).pack(side="left", padx=(8, 0))

        controls = ctk.CTkFrame(main)
        controls.pack(fill="x", pady=(0, 8))

        lbl_search = ctk.CTkLabel(controls, text="Busca:", font=FONTS["body"])
        lbl_search.pack(side="left", padx=(10, 6))

        self.query_entry = ctk.CTkEntry(controls, width=300, placeholder_text="Palavra ou regex")
        self.query_entry.pack(side="left", padx=(0, 10), pady=10)
        self.query_entry.bind("<Return>", lambda _e: self._run_search())

        self.regex_var = ctk.BooleanVar(value=False)
        chk_regex = ctk.CTkCheckBox(
            controls,
            text="Regex",
            variable=self.regex_var,
        )
        chk_regex.pack(side="left", padx=(0, 4))
        self._create_help_icon(
            controls,
            "Habilita a busca por Extressões Regulares (Regex) para pesquisa avançada."
        ).pack(side="left", padx=(0, 10))

        lbl_context = ctk.CTkLabel(controls, text="Contexto:", font=FONTS["body"])
        lbl_context.pack(side="left", padx=(0, 6))
        CTkTooltip(lbl_context, message="Número de caracteres para exibir à esquerda e direita do termo.")

        self.context_var = ctk.IntVar(value=50)
        self.context_entry = ctk.CTkEntry(controls, textvariable=self.context_var, width=80)
        self.context_entry.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            controls,
            text="Executar",
            width=120,
            fg_color=get_themed_color("primary"),
            hover_color=get_themed_color("primary_hover"),
            text_color=("#FFFFFF", "#FFFFFF"),
            border_width=0,
            command=self._run_search,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Exportar CSV",
            width=120,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            command=self._export_results_csv,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            controls,
            text="Fechar",
            width=100,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            command=self.destroy,
        ).pack(side="right", padx=10)

        self.status_label = ctk.CTkLabel(
            main,
            text="Digite um termo e clique em Executar.",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 6))

        results = ctk.CTkFrame(main)
        results.pack(fill="both", expand=True)

        left_panel = ctk.CTkFrame(results)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right_panel = ctk.CTkFrame(results, width=360)
        right_panel.pack(side="right", fill="both", padx=(6, 0))
        right_panel.pack_propagate(False)

        self.tree = ttk.Treeview(
            left_panel,
            columns=("left", "keyword", "right", "metadata", "uce"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("left", text="Contexto esquerdo")
        self.tree.heading("keyword", text="Termo")
        self.tree.heading("right", text="Contexto direito")
        self.tree.heading("metadata", text="Metadados")
        self.tree.heading("uce", text="UCE")

        self.tree.column("left", width=220, anchor="w")
        self.tree.column("keyword", width=110, anchor="center")
        self.tree.column("right", width=220, anchor="w")
        self.tree.column("metadata", width=180, anchor="w")
        self.tree.column("uce", width=60, anchor="center")

        y_scroll = ttk.Scrollbar(left_panel, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        y_scroll.pack(side="right", fill="y", pady=8, padx=(0, 8))

        self.tree.bind("<<TreeviewSelect>>", self._on_select_context)

        ctk.CTkLabel(
            right_panel,
            text="UCE completa",
            font=FONTS["heading"],
        ).pack(anchor="w", padx=10, pady=(10, 4))

        self.full_uce_box = ctk.CTkTextbox(right_panel, font=FONTS["body"], wrap="word")
        self.full_uce_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.full_uce_box.insert("1.0", "Selecione uma ocorrência para visualizar o segmento completo.")
        self.full_uce_box.configure(state="disabled")

        ctk.CTkLabel(
            right_panel,
            text="Distribuição por metadados",
            font=FONTS["heading"],
        ).pack(anchor="w", padx=10, pady=(0, 4))

        self.distribution_box = ctk.CTkTextbox(right_panel, height=140, font=FONTS["mono"])
        self.distribution_box.pack(fill="x", padx=10, pady=(0, 10))
        self.distribution_box.insert("1.0", "Sem dados.")
        self.distribution_box.configure(state="disabled")

    def _run_search(self):
        query = self.query_entry.get().strip()
        if not query:
            self.status_label.configure(text="Informe um termo para buscar.")
            return

        try:
            context_size = int(self.context_entry.get().strip() or "50")
        except ValueError:
            messagebox.showerror(
                "Erro de contexto",
                (
                    "O que aconteceu: Valor de contexto invalido.\n"
                    "Por que aconteceu: O campo contexto aceita apenas numeros inteiros.\n"
                    "Como resolver: Informe um numero inteiro (ex.: 50) e tente novamente."
                ),
            )
            return

        try:
            if self.regex_var.get():
                result = self._concordancer.search_regex(query, context_size=context_size)
            else:
                result = self._concordancer.search(query, context_size=context_size)
        except ConcordancerError as exc:
            messagebox.showerror("Erro na concordância", str(exc))
            return
        except Exception as exc:
            messagebox.showerror(
                "Erro na concordância",
                (
                    "O que aconteceu: Falha na busca de concordancia.\n"
                    f"Por que aconteceu: {exc}\n"
                    "Como resolver: Revise o termo de busca e tente novamente."
                ),
            )
            return

        self._contexts = result.contexts
        self._render_contexts()
        self._render_distribution(query)
        self.status_label.configure(
            text=f"{result.occurrences} ocorrência(s) encontrada(s) para '{result.query}'."
        )

    def _render_contexts(self):
        self._result_index_by_item = {}
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, ctx in enumerate(self._contexts):
            metadata_str = " ".join(
                f"*{key}_{value}".rstrip("_")
                for key, value in ctx.metadata.items()
            ) or "-"
            item_id = self.tree.insert(
                "",
                "end",
                values=(ctx.left, ctx.keyword, ctx.right, metadata_str, ctx.uce_id),
            )
            self._result_index_by_item[item_id] = idx

        self._set_full_uce_text(
            "Selecione uma ocorrência para visualizar o segmento completo."
        )
        if not self._contexts:
            self._set_full_uce_text("Nenhuma ocorrência encontrada para o termo informado.")

    def _render_distribution(self, query: str):
        self.distribution_box.configure(state="normal")
        self.distribution_box.delete("1.0", "end")

        if self.regex_var.get():
            self.distribution_box.insert(
                "1.0",
                "Distribuição por metadados disponível apenas para busca por palavra.",
            )
            self.distribution_box.configure(state="disabled")
            return

        dist = self._concordancer.get_word_distribution(query)
        if not dist:
            self.distribution_box.insert("1.0", "Sem distribuição disponível.")
            self.distribution_box.configure(state="disabled")
            return

        lines = [f"{token}: {count}" for token, count in list(dist.items())[:30]]
        self.distribution_box.insert("1.0", "\n".join(lines))
        self.distribution_box.configure(state="disabled")

    def _on_select_context(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        idx = self._result_index_by_item.get(selection[0])
        if idx is None or idx >= len(self._contexts):
            return

        ctx = self._contexts[idx]
        metadata_str = " ".join(
            f"*{key}_{value}".rstrip("_")
            for key, value in ctx.metadata.items()
        ) or "-"
        detail = (
            f"UCI: {ctx.uci_id} | UCE: {ctx.uce_id}\n"
            f"Metadados: {metadata_str}\n\n"
            f"{ctx.full_text}"
        )
        self._set_full_uce_text(detail)

    def _set_full_uce_text(self, text: str):
        self.full_uce_box.configure(state="normal")
        self.full_uce_box.delete("1.0", "end")
        self.full_uce_box.insert("1.0", text)
        self.full_uce_box.configure(state="disabled")

    def _export_results_csv(self):
        """Export current KWIC results to CSV."""
        if not self._contexts:
            messagebox.showinfo(
                "Exportação KWIC",
                "Não há resultados para exportar. Execute uma busca primeiro.",
            )
            return

        output_path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar concordância (KWIC)",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos os arquivos", "*.*")],
            initialfile="kwic_resultados.csv",
        )
        if not output_path:
            return

        try:
            with open(output_path, "w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(
                    [
                        "uci_id",
                        "uce_id",
                        "termo",
                        "contexto_esquerdo",
                        "contexto_direito",
                        "metadados",
                        "uce_completa",
                    ]
                )
                for ctx in self._contexts:
                    metadata_str = " ".join(
                        f"*{key}_{value}".rstrip("_")
                        for key, value in ctx.metadata.items()
                    ) or "-"
                    writer.writerow(
                        [
                            ctx.uci_id,
                            ctx.uce_id,
                            ctx.keyword,
                            ctx.left,
                            ctx.right,
                            metadata_str,
                            ctx.full_text,
                        ]
                    )
            messagebox.showinfo(
                "Exportação KWIC",
                f"Resultado exportado com sucesso:\n{output_path}",
            )
        except Exception as exc:
            messagebox.showerror(
                "Erro na exportação",
                (
                    "O que aconteceu: Não foi possível exportar o KWIC.\n"
                    f"Por que aconteceu: {exc}\n"
                    "Como resolver: Verifique permissões da pasta e tente novamente."
                ),
            )
