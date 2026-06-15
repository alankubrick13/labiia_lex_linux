"""Dialogo para selecao interativa de palavras na analise de similitude."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from ...core.corpus import Corpus
from ..styles import FONTS, COLORS, get_themed_color
from ..iconography import label_with_icon


class WordSelectorDialog(ctk.CTkToplevel):
    """Permite selecionar palavras ativas para a analise de similitude."""

    def __init__(
        self,
        parent,
        corpus: Corpus,
        max_words: int = 50,
        min_freq: int = 3,
        use_lemmas: bool = False,
        chi2_scores: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Selecionar Palavras - Similitude")
        self.geometry("820x550")
        self.minsize(700, 480)
        self.transient(parent)
        self.grab_set()

        self._result: Optional[List[str]] = None
        self._use_lemmas = bool(use_lemmas)
        self._chi2_scores = chi2_scores or {}
        self._words: List[Tuple[str, int, float]] = self._collect_words(corpus)
        self._selected_words: set[str] = set()
        self._selection_dirty = False

        self.min_freq_var = ctk.IntVar(value=max(1, int(min_freq or 3)))
        self.max_words_var = ctk.IntVar(value=max(10, min(300, int(max_words or 50))))
        self.top_n_var = ctk.IntVar(value=min(50, self.max_words_var.get()))

        self._item_to_word: Dict[str, str] = {}

        self._create_widgets()
        self._center_on_parent(parent)
        self._refresh_rows()

    def _center_on_parent(self, parent) -> None:
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

    def _create_widgets(self) -> None:
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            main,
            text=label_with_icon("search", "Seleção de Palavras"),
            font=FONTS["title"],
        ).pack(anchor="w", pady=(0, 10))

        controls = ctk.CTkFrame(main, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(controls, text="Freq. mínima:", font=FONTS["body"]).pack(side="left", padx=(0, 6))
        ctk.CTkEntry(controls, textvariable=self.min_freq_var, width=70).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(controls, text="Máx. palavras:", font=FONTS["body"]).pack(side="left", padx=(4, 6))
        ctk.CTkSlider(
            controls,
            from_=10,
            to=300,
            number_of_steps=29,
            variable=self.max_words_var,
            width=180,
            command=lambda _=None: self._refresh_rows(),
        ).pack(side="left", padx=(0, 6))
        self.max_words_label = ctk.CTkLabel(
            controls,
            text=str(self.max_words_var.get()),
            width=40,
        )
        self.max_words_label.pack(side="left", padx=(0, 8))
        self.max_words_var.trace_add(
            "write",
            lambda *_: self.max_words_label.configure(text=str(self.max_words_var.get())),
        )

        ctk.CTkButton(
            controls,
            text="Aplicar Filtro",
            width=110,
            command=self._refresh_rows,
        ).pack(side="left", padx=(4, 8))

        bulk = ctk.CTkFrame(main, fg_color="transparent")
        bulk.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(bulk, text="Top N:", font=FONTS["body"]).pack(side="left", padx=(0, 6))
        ctk.CTkEntry(bulk, textvariable=self.top_n_var, width=70).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            bulk,
            text="Selecionar top N",
            width=140,
            command=self._select_top_n,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            bulk,
            text="Desselecionar todas",
            width=150,
            command=self._deselect_all,
            fg_color=COLORS["secondary"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            bulk,
            text="Inverter seleção",
            width=130,
            command=self._invert_selection,
        ).pack(side="left")

        tree_frame = ctk.CTkFrame(main)
        tree_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("selected", "word", "freq", "chi2"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("selected", text="Sel.")
        self.tree.heading("word", text="Palavra")
        self.tree.heading("freq", text="Frequência")
        self.tree.heading("chi2", text="Chi²")
        self.tree.column("selected", width=60, anchor="center")
        self.tree.column("word", width=280, anchor="w")
        self.tree.column("freq", width=120, anchor="center")
        self.tree.column("chi2", width=120, anchor="center")

        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        y_scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        self.tree.bind("<Double-1>", self._toggle_selected_from_click)

        self.info_label = ctk.CTkLabel(
            main,
            text="0 palavra(s) selecionada(s). Nenhuma seleção = vocabulário elegível completo.",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.info_label.pack(fill="x", pady=(0, 8))

        footer = ctk.CTkFrame(main, fg_color="transparent")
        footer.pack(fill="x")
        ctk.CTkButton(
            footer,
            text="Cancelar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._cancel,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            footer,
            text="Usar Seleção", width=110, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._confirm,
        ).pack(side="right", padx=(0, 4))

    def _collect_words(self, corpus: Corpus) -> List[Tuple[str, int, float]]:
        """Retorna palavras ativas com frequencia e chi2 opcional."""
        items: List[Tuple[str, int, float]] = []
        if self._use_lemmas:
            for lem in corpus.lems.values():
                if getattr(lem, "act", 1) != 1:
                    continue
                token = str(getattr(lem, "lem", "") or "").strip()
                if not token:
                    continue
                freq = int(getattr(lem, "freq", 0))
                chi2 = float(self._chi2_scores.get(token, 0.0))
                items.append((token, freq, chi2))
        else:
            for word in corpus.formes.values():
                if getattr(word, "act", 1) != 1:
                    continue
                freq = int(getattr(word, "freq", 0))
                chi2 = float(self._chi2_scores.get(word.forme, 0.0))
                items.append((word.forme, freq, chi2))
        items.sort(key=lambda item: item[1], reverse=True)
        return items

    def _filtered_words(self) -> List[Tuple[str, int, float]]:
        min_freq = max(1, int(self.min_freq_var.get() or 1))
        limit = max(10, int(self.max_words_var.get() or 50))
        filtered = [item for item in self._words if item[1] >= min_freq]
        return filtered[:limit]

    def _refresh_rows(self) -> None:
        if not self._selection_dirty:
            self._selected_words = {word for word, _, _ in self._filtered_words()}
        self._item_to_word.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        for word, freq, chi2 in self._filtered_words():
            selected = "Sim" if word in self._selected_words else ""
            item_id = self.tree.insert(
                "",
                "end",
                values=(selected, word, str(freq), f"{chi2:.3f}" if chi2 else "-"),
            )
            self._item_to_word[item_id] = word

        self._update_info()

    def _toggle_selected_from_click(self, _event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item_id = selection[0]
        word = self._item_to_word.get(item_id)
        if not word:
            return
        if word in self._selected_words:
            self._selected_words.remove(word)
        else:
            self._selected_words.add(word)
        self._selection_dirty = True
        self._refresh_rows()

    def _select_top_n(self) -> None:
        n = max(1, int(self.top_n_var.get() or 1))
        for word, _, _ in self._filtered_words()[:n]:
            self._selected_words.add(word)
        self._selection_dirty = True
        self._refresh_rows()

    def _deselect_all(self) -> None:
        self._selected_words.clear()
        self._selection_dirty = True
        self._refresh_rows()

    def _invert_selection(self) -> None:
        visible = [word for word, _, _ in self._filtered_words()]
        visible_set = set(visible)
        selected_visible = self._selected_words.intersection(visible_set)
        self._selected_words.difference_update(selected_visible)
        self._selected_words.update(visible_set.difference(selected_visible))
        self._selection_dirty = True
        self._refresh_rows()

    def _update_info(self) -> None:
        selected_total = len(self._selected_words)
        visible_total = len(self._filtered_words())
        mode_text = (
            "Seleção manual ativa."
            if self._selection_dirty
            else "Seleção inicial = palavras visíveis no filtro atual."
        )
        self.info_label.configure(
            text=(
                f"{selected_total} palavra(s) selecionada(s). "
                f"{visible_total} visíveis no filtro atual. "
                f"{mode_text} Nenhuma seleção manual = vocabulário elegível completo."
            )
        )

    def _confirm(self) -> None:
        self._result = sorted(self._selected_words)
        self.destroy()

    def _cancel(self) -> None:
        self._result = None
        self.destroy()

    def get_result(self) -> Optional[List[str]]:
        self.wait_window()
        return self._result
