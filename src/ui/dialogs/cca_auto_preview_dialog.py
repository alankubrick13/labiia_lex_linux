"""Preview dialog for automatic CCA concept suggestions."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from ..styles import COLORS, FONTS, get_current_colors, get_themed_color


class CCAAutoPreviewDialog(ctk.CTkToplevel):
    """Shows auto-generated CCA concepts and lets the user choose what to apply."""

    def __init__(
        self,
        parent,
        suggestions: List[Any],
        unassigned_words: Optional[List[str]] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Sugestões Automáticas de Conceitos (CCA)")
        self.geometry("980x620")
        self.minsize(840, 520)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._suggestions = list(suggestions or [])
        self._unassigned_words = list(unassigned_words or [])
        self._diagnostics = diagnostics or {}
        self._result: Optional[List[Any]] = None
        self._row_to_suggestion: Dict[str, Any] = {}
        self._native_colors: Dict[str, str] = get_current_colors()

        self._create_widgets()
        self._center_on_parent(parent)
        self._populate_rows()

    def _native_color(self, key: str, fallback_key: str = "text") -> str:
        return str(
            self._native_colors.get(
                key,
                COLORS.get(fallback_key, "#242424"),
            )
        )

    def _center_on_parent(self, parent) -> None:
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        dw, dh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

    def _create_widgets(self) -> None:
        header = ctk.CTkFrame(self, fg_color=get_themed_color("header_bg"), corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header,
            text="Prévia de Conceitos Automáticos",
            font=FONTS["heading"],
        ).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            header,
            text=(
                f"Sugestões: {len(self._suggestions)}  ·  "
                f"Não atribuídas: {len(self._unassigned_words)}"
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        ).pack(side="right", padx=12, pady=8)

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(
            info_frame,
            text=(
                "Selecione as sugestões que deseja aplicar. "
                "Conceitos manuais existentes não serão sobrescritos.\n"
                "As sugestões são aplicadas ao CCA atual (não alteram o corpus global dos demais testes)."
            ),
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x")

        if self._diagnostics:
            passes = list(self._diagnostics.get("passes", []) or [])
            if passes:
                first_metrics = (
                    passes[0]
                    .get("community_metrics", {})
                    if isinstance(passes[0], dict)
                    else {}
                )
                diag_text = (
                    f"Passes: {len(passes)}  ·  "
                    f"Adaptativo: {'sim' if bool(self._diagnostics.get('adaptive_relaxation_used', False)) else 'não'}  ·  "
                    f"Modularidade (passo 1): {float(first_metrics.get('modularity', 0.0) or 0.0):.4f}  ·  "
                    f"Limiar inicial: {float(self._diagnostics.get('confidence_threshold', 0.0) or 0.0):.2f}"
                )
            else:
                diag_text = (
                    f"Modularidade: {float(self._diagnostics.get('modularity', 0.0) or 0.0):.4f}  ·  "
                    f"Comunidades: {int(self._diagnostics.get('communities_detected', 0) or 0)}  ·  "
                    f"Limiar: {float(self._diagnostics.get('confidence_threshold', 0.0) or 0.0):.2f}"
                )
            ctk.CTkLabel(
                info_frame,
                text=diag_text,
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                anchor="w",
            ).pack(fill="x", pady=(2, 0))

            semantic_diag = dict(self._diagnostics.get("semantic_resources", {}) or {})
            pair_count = int(self._diagnostics.get("external_pairs_loaded", 0) or 0)
            lemma_count = int(semantic_diag.get("lemma_entries_loaded", 0) or 0)
            if pair_count > 0 or lemma_count > 0:
                ctk.CTkLabel(
                    info_frame,
                    text=(
                        f"Recursos externos: {pair_count} pares semânticos"
                        f"  ·  {lemma_count} entradas de lema"
                    ),
                    font=FONTS["small"],
                    text_color=COLORS["text_secondary"],
                    anchor="w",
                ).pack(fill="x", pady=(2, 0))

        tree_frame = tk.Frame(self, bg=self._native_color("background", "background"))
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(4, 6))

        style = ttk.Style()
        style.configure(
            "CCA.AutoPreview.Treeview",
            rowheight=22,
            font=("Segoe UI", 10),
            background=self._native_color("surface", "surface"),
            fieldbackground=self._native_color("surface", "surface"),
            foreground=self._native_color("text", "text"),
            bordercolor=self._native_color("border", "border"),
            lightcolor=self._native_color("border", "border"),
            darkcolor=self._native_color("border", "border"),
        )
        style.configure(
            "CCA.AutoPreview.Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background=self._native_color("header_bg", "header_bg"),
            foreground=self._native_color("text", "text"),
            relief="flat",
        )
        style.map(
            "CCA.AutoPreview.Treeview",
            background=[("selected", self._native_color("primary", "primary"))],
            foreground=[("selected", "#FFFFFF")],
        )

        self._tree = ttk.Treeview(
            tree_frame,
            style="CCA.AutoPreview.Treeview",
            columns=("concept", "size", "confidence", "words"),
            show="headings",
            selectmode="extended",
        )
        self._tree.heading("concept", text="Conceito sugerido")
        self._tree.heading("size", text="# palavras")
        self._tree.heading("confidence", text="Confiança média")
        self._tree.heading("words", text="Palavras")

        self._tree.column("concept", width=210, anchor="w")
        self._tree.column("size", width=90, anchor="center", stretch=False)
        self._tree.column("confidence", width=130, anchor="center", stretch=False)
        self._tree.column("words", width=500, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            footer,
            text="Selecionar tudo",
            width=120,
            height=28,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._select_all,
        ).pack(side="left")
        ctk.CTkButton(
            footer,
            text="Limpar seleção",
            width=120,
            height=28,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._clear_selection,
        ).pack(side="left", padx=(6, 0))

        ctk.CTkButton(
            footer,
            text="Cancelar",
            width=100,
            height=28,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._cancel,
        ).pack(side="right")
        ctk.CTkButton(
            footer,
            text="Aplicar no CCA",
            width=170,
            height=28,
            fg_color=get_themed_color("accent"),
            hover_color=get_themed_color("primary_hover"),
            text_color="#FFFFFF",
            border_width=0,
            corner_radius=3,
            command=self._confirm,
        ).pack(side="right", padx=(0, 6))

    def _populate_rows(self) -> None:
        self._row_to_suggestion.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

        for suggestion in self._suggestions:
            words = list(getattr(suggestion, "words", []) or [])
            concept_name = str(getattr(suggestion, "name", "") or "").strip() or "conceito"
            mean_confidence = float(getattr(suggestion, "mean_confidence", 0.0) or 0.0)
            size = int(getattr(suggestion, "size", len(words)) or len(words))
            iid = self._tree.insert(
                "",
                "end",
                values=(
                    concept_name,
                    str(size),
                    f"{mean_confidence:.2f}",
                    ", ".join(words),
                ),
                tags=("row_even",) if len(self._row_to_suggestion) % 2 == 0 else ("row_odd",),
            )
            self._row_to_suggestion[iid] = suggestion

        self._tree.tag_configure(
            "row_even",
            background=self._native_color("surface", "surface"),
            foreground=self._native_color("text", "text"),
        )
        self._tree.tag_configure(
            "row_odd",
            background=self._native_color("secondary", "secondary"),
            foreground=self._native_color("text", "text"),
        )
        self._select_all()

    def _select_all(self) -> None:
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children)
            self._tree.focus(children[0])
            self._tree.see(children[0])

    def _clear_selection(self) -> None:
        children = self._tree.get_children()
        if children:
            self._tree.selection_remove(children)

    def _confirm(self) -> None:
        selected_ids = list(self._tree.selection())
        if not selected_ids:
            return
        self._result = [self._row_to_suggestion[iid] for iid in selected_ids if iid in self._row_to_suggestion]
        self.destroy()

    def _cancel(self) -> None:
        self._result = None
        self.destroy()

    def get_result(self) -> Optional[List[Any]]:
        self.wait_window()
        return self._result
