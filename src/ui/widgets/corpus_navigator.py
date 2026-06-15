"""
Navigator visual para explorar corpus e segmentos.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from typing import Dict, Optional, List, Tuple

import customtkinter as ctk

from ...core.corpus import Corpus
from ..styles import FONTS, COLORS, get_themed_color
from ..iconography import label_with_icon


class CorpusNavigator(ctk.CTkToplevel):
    """Janela de navegacao pelo corpus com busca e filtros."""

    _CLASS_COLORS = [
        "#FFE8E8",
        "#E8F4FF",
        "#E8FFE8",
        "#FFF4DD",
        "#F1E8FF",
        "#FFEEDD",
        "#E0FFF8",
        "#FCEBFF",
    ]

    def __init__(
        self,
        parent,
        corpus: Corpus,
        cluster_assignments: Optional[Dict[int, int]] = None,
    ):
        super().__init__(parent)
        self.title("Navigator do Corpus")
        self.geometry("1100x700")
        self.transient(parent)
        self.grab_set()

        self._corpus = corpus
        self._assignments = cluster_assignments or {}
        self._uci_indices: List[int] = []
        self._last_segments: List[Tuple[int, str]] = []

        self._create_widgets()
        self._populate_metadata_filter()
        self._refresh_uci_list()
        self.wait_visibility()
        self.focus_set()

    def _create_widgets(self) -> None:
        """Cria interface principal."""
        root = ctk.CTkFrame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        top = ctk.CTkFrame(root, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(top, text="Buscar:", font=FONTS["body"]).pack(side="left", padx=(0, 4))
        self.search_entry = ctk.CTkEntry(top, width=280, placeholder_text="Digite palavra ou trecho...")
        self.search_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(top, text=label_with_icon("search", "Buscar"), width=86, command=self._apply_search).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(top, text="Filtro por metadado:", font=FONTS["body"]).pack(side="left", padx=(0, 4))
        self.meta_filter_var = ctk.StringVar(value="(todas)")
        self.meta_filter_menu = ctk.CTkOptionMenu(
            top,
            variable=self.meta_filter_var,
            values=["(todas)"],
            width=220,
            command=lambda _value: self._refresh_uci_list(),
        )
        self.meta_filter_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(top, text=label_with_icon("export", "Exportar Seleção"), width=170, command=self._export_selected).pack(side="right")

        body = ctk.CTkFrame(root)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        ctk.CTkLabel(left, text="Documentos (UCIs)", font=FONTS["heading"]).pack(anchor="w", padx=8, pady=(8, 4))

        self.uci_listbox = tk.Listbox(left, width=40, height=35, exportselection=False)
        self.uci_listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        list_scroll = ttk.Scrollbar(left, orient="vertical", command=self.uci_listbox.yview)
        list_scroll.pack(side="left", fill="y", padx=(0, 8), pady=8)
        self.uci_listbox.configure(yscrollcommand=list_scroll.set)
        self.uci_listbox.bind("<<ListboxSelect>>", self._on_select_uci)

        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(right, text="Conteúdo", font=FONTS["heading"]).pack(anchor="w", padx=8, pady=(8, 4))

        text_container = ctk.CTkFrame(right)
        text_container.pack(fill="both", expand=True, padx=8, pady=8)

        mode_idx = 0 if ctk.get_appearance_mode() == "Light" else 1
        
        self.text_widget = tk.Text(
            text_container,
            wrap="word",
            font=FONTS["mono"],
            background=get_themed_color("surface")[mode_idx],
            foreground=get_themed_color("text")[mode_idx],
            insertbackground=get_themed_color("text")[mode_idx],
        )
        self.text_widget.pack(side="left", fill="both", expand=True)
        text_scroll = ttk.Scrollbar(text_container, orient="vertical", command=self.text_widget.yview)
        text_scroll.pack(side="right", fill="y")
        self.text_widget.configure(yscrollcommand=text_scroll.set)
        self.text_widget.tag_configure("meta", foreground=get_themed_color("primary")[mode_idx])
        self.text_widget.tag_configure("search", background="#FFF2CC", foreground=get_themed_color("text")[mode_idx])
        for idx, color in enumerate(self._CLASS_COLORS, start=1):
            self.text_widget.tag_configure(f"class_{idx}", background=color, foreground="#111111")

    def _populate_metadata_filter(self) -> None:
        """Carrega tokens de metadados no filtro."""
        tokens = set()
        for uci in self._corpus.ucis:
            for token in getattr(uci, "etoiles", [])[1:]:
                if token and token != "****":
                    tokens.add(token)
        values = ["(todas)"] + sorted(tokens)
        self.meta_filter_menu.configure(values=values)
        if self.meta_filter_var.get() not in values:
            self.meta_filter_var.set("(todas)")

    def _refresh_uci_list(self) -> None:
        """Atualiza lista de UCIs com filtro atual."""
        self.uci_listbox.delete(0, tk.END)
        self._uci_indices = []
        selected_token = self.meta_filter_var.get()

        for idx, uci in enumerate(self._corpus.ucis):
            etoiles = getattr(uci, "etoiles", [])
            if selected_token != "(todas)" and selected_token not in etoiles:
                continue
            label = f"{idx + 1:03d} | {' '.join(etoiles[:5]) if etoiles else '**** *uci'}"
            self.uci_listbox.insert(tk.END, label)
            self._uci_indices.append(idx)

        if self._uci_indices:
            self.uci_listbox.selection_set(0)
            self._on_select_uci()
        else:
            self.text_widget.delete("1.0", tk.END)
            self.text_widget.insert("1.0", "Nenhuma UCI corresponde ao filtro atual.")

    def _on_select_uci(self, _event=None) -> None:
        """Renderiza UCI selecionada no painel de texto."""
        selection = self.uci_listbox.curselection()
        if not selection:
            return
        pos = selection[0]
        if pos >= len(self._uci_indices):
            return
        uci_idx = self._uci_indices[pos]
        uci = self._corpus.ucis[uci_idx]

        self.text_widget.delete("1.0", tk.END)
        meta_line = " ".join(getattr(uci, "etoiles", []) or [f"**** *uci_{uci_idx + 1}"])
        self.text_widget.insert(tk.END, f"{meta_line}\n\n", ("meta",))

        uce_ids = [uce.ident for uce in uci.uces]
        self._last_segments = list(self._corpus.getconcorde(uce_ids))
        for uce_id, segment in self._last_segments:
            class_id = int(self._assignments.get(int(uce_id), 0))
            header = f"[UCE {uce_id}]"
            if class_id > 0:
                header += f" [Classe {class_id}]"
            header += " "

            tag_name = f"class_{((class_id - 1) % len(self._CLASS_COLORS)) + 1}" if class_id > 0 else None
            start_index = self.text_widget.index(tk.END)
            self.text_widget.insert(tk.END, header + str(segment).strip() + "\n\n")
            end_index = self.text_widget.index(tk.END)
            if tag_name:
                self.text_widget.tag_add(tag_name, start_index, end_index)

        self._apply_search()

    def _apply_search(self) -> None:
        """Aplica destaque de busca no texto visivel."""
        self.text_widget.tag_remove("search", "1.0", tk.END)
        query = self.search_entry.get().strip().lower()
        if not query:
            return

        content = self.text_widget.get("1.0", tk.END)
        idx = "1.0"
        while True:
            idx = self.text_widget.search(query, idx, stopindex=tk.END, nocase=True)
            if not idx:
                break
            end = f"{idx}+{len(query)}c"
            self.text_widget.tag_add("search", idx, end)
            idx = end

    def _export_selected(self) -> None:
        """Exporta trecho selecionado no painel direito."""
        try:
            selected = self.text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = self.text_widget.get("1.0", tk.END).strip()

        if not selected:
            return

        path = filedialog.asksaveasfilename(
            title="Exportar Segmento",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(selected, encoding="utf-8")
