"""Dialog for selecting optional multiword expressions to merge."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
from tkinter import ttk

from ..styles import COLORS, get_themed_color
from ...importers.multiword_candidates import normalize_multiword_candidate


class MultiwordSelectionDialog(ctk.CTkToplevel):
    """Modal selector for 2- to 3-word expression candidates."""

    def __init__(
        self,
        parent,
        candidates: List[Dict[str, Any]],
        on_confirm: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        title: str = "Selecionar expressões compostas",
        min_freq: int = 2,
        min_is_norm: float = 0.35,
        header_text: str = "Expressões compostas",
        description_text: Optional[str] = None,
        apply_button_text: str = "Aplicar expressões",
        item_label_singular: str = "expressão",
        item_label_plural: str = "expressões",
    ):
        super().__init__(parent)
        self.title(title)
        self._set_initial_geometry(parent)
        self.minsize(980, 700)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._min_freq = max(1, int(min_freq or 2))
        self._min_is_norm = max(0.0, float(min_is_norm or 0.35))
        self._candidates = [
            normalize_multiword_candidate(item, min_freq=self._min_freq, min_is_norm=self._min_is_norm)
            for item in (candidates or [])
        ]
        self._on_confirm = on_confirm
        self._selected_bigrams: List[Dict[str, Any]] = []
        self._confirmed = False
        self._header_text = str(header_text or "Expressões compostas")
        self._description_text = str(
            description_text
            or (
                "Selecione as expressões que devem ficar unidas por underscore (_). "
                "A seleção só será aplicada depois da confirmação."
            )
        )
        self._apply_button_text = str(apply_button_text or "Aplicar expressões")
        self._item_label_singular = str(item_label_singular or "expressão")
        self._item_label_plural = str(item_label_plural or "expressões")

        self._create_widgets()
        self._center_on_parent(parent)
        self._load_candidates()

        self.wait_window()

    def _set_initial_geometry(self, parent) -> None:
        try:
            screen_w = max(1024, int(self.winfo_screenwidth()))
            screen_h = max(720, int(self.winfo_screenheight()))
        except Exception:
            self.geometry("1080x780")
            return

        target_w = min(1180, max(1020, int(screen_w * 0.66)))
        target_h = min(880, max(720, int(screen_h * 0.78)))
        target_w = min(target_w, screen_w - 48)
        target_h = min(target_h, screen_h - 72)
        self.geometry(f"{target_w}x{target_h}")

    def _center_on_parent(self, parent) -> None:
        try:
            self.update_idletasks()
            parent_x = int(parent.winfo_x())
            parent_y = int(parent.winfo_y())
            parent_w = int(parent.winfo_width())
            parent_h = int(parent.winfo_height())
            dialog_w = int(self.winfo_width())
            dialog_h = int(self.winfo_height())
            x = parent_x + (parent_w - dialog_w) // 2
            y = parent_y + (parent_h - dialog_h) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _create_widgets(self) -> None:
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header_frame,
            text=self._header_text,
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_frame,
            text=self._description_text,
            font=("Segoe UI", 13),
            text_color=COLORS.get("text_secondary", "gray"),
            wraplength=940,
        ).pack(anchor="w", pady=(5, 0))

        self.status_label = ctk.CTkLabel(
            header_frame,
            text="Carregando candidatos...",
            font=("Segoe UI", 13),
            text_color=COLORS.get("text_secondary", "gray"),
        )
        self.status_label.pack(anchor="w", pady=(8, 0))

        list_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, pady=10)

        style = ttk.Style()
        style.configure("Multiword.Treeview", font=("Segoe UI", 13), rowheight=30)
        style.configure("Multiword.Treeview.Heading", font=("Segoe UI", 13, "bold"))

        columns = ("selected", "expression", "replacement", "n_tokens", "frequency", "docs", "score")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=16,
            style="Multiword.Treeview",
        )
        self.tree.heading("selected", text="Sel.")
        self.tree.heading("expression", text="Expressão")
        self.tree.heading("replacement", text="Substituição")
        self.tree.heading("n_tokens", text="Tam.")
        self.tree.heading("frequency", text="Freq.")
        self.tree.heading("docs", text="Docs")
        self.tree.heading("score", text="Score")

        self.tree.column("selected", width=48, anchor="center")
        self.tree.column("expression", width=260, anchor="w")
        self.tree.column("replacement", width=240, anchor="w")
        self.tree.column("n_tokens", width=64, anchor="center")
        self.tree.column("frequency", width=70, anchor="center")
        self.tree.column("docs", width=70, anchor="center")
        self.tree.column("score", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<ButtonRelease-1>", self._on_item_click)
        self.tree.bind("<space>", self._toggle_selected_item)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_context)

        context_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        context_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            context_frame,
            text="Contextos",
            font=("Segoe UI", 13, "bold"),
            text_color=COLORS.get("text_secondary", "gray"),
        ).pack(anchor="w")
        self.context_box = ctk.CTkTextbox(context_frame, height=76, font=("Segoe UI", 12), wrap="word")
        self.context_box.pack(fill="x", pady=(4, 0))
        self.context_box.insert("1.0", "Selecione uma expressão para ver exemplos do corpus.")
        self.context_box.configure(state="disabled")

        action_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(
            action_frame,
            text="Marcar sugeridas",
            width=150,
            height=36,
            font=("Segoe UI", 13),
            command=self._select_suggested,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            action_frame,
            text="Selecionar todas",
            width=150,
            height=36,
            font=("Segoe UI", 13),
            command=self._select_all,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            action_frame,
            text="Desmarcar todas",
            width=150,
            height=36,
            font=("Segoe UI", 13),
            command=self._deselect_all,
            fg_color=COLORS.get("secondary", "gray"),
        ).pack(side="left")

        self.summary_label = ctk.CTkLabel(
            main_frame,
            text="Nenhuma expressão selecionada",
            font=("Segoe UI", 13, "bold"),
            text_color=COLORS.get("text_secondary", "gray"),
        )
        self.summary_label.pack(fill="x", pady=(5, 10))

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(
            btn_frame,
            text="Cancelar",
            width=96,
            height=30,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._cancel,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            btn_frame,
            text=self._apply_button_text,
            width=150,
            height=30,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._confirm,
        ).pack(side="right", padx=(0, 4))

    def _load_candidates(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, candidate in enumerate(self._candidates):
            selected = "Sim" if bool(candidate.get("selected_default", False)) else "Não"
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    selected,
                    str(candidate.get("expression", "")),
                    str(candidate.get("replacement", "")),
                    int(candidate.get("n_tokens", 0) or 0),
                    int(candidate.get("frequency", 0) or 0),
                    int(candidate.get("doc_count", 0) or 0),
                    f"{float(candidate.get('is_norm', 0.0) or 0.0):.2f}",
                ),
                tags=("selected",) if selected == "Sim" else ("unselected",),
            )

        self.tree.tag_configure("selected", background="#E8F5E9")
        self.tree.tag_configure("unselected", background="white")
        label = self._item_label_singular if len(self._candidates) == 1 else self._item_label_plural
        self.status_label.configure(text=f"{len(self._candidates)} {label} sugerida(s)")
        self._update_summary()

    def _on_item_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if item:
            self._toggle_item(item)
            self.tree.selection_set(item)

    def _toggle_selected_item(self, event=None) -> None:
        selection = self.tree.selection()
        if selection:
            self._toggle_item(selection[0])

    def _toggle_item(self, item_id: str) -> None:
        values = list(self.tree.item(item_id, "values"))
        values[0] = "Não" if values[0] == "Sim" else "Sim"
        self.tree.item(item_id, values=tuple(values), tags=("selected",) if values[0] == "Sim" else ("unselected",))
        self._update_summary()

    def _select_all(self) -> None:
        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, "values"))
            values[0] = "Sim"
            self.tree.item(item_id, values=tuple(values), tags=("selected",))
        self._update_summary()

    def _deselect_all(self) -> None:
        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, "values"))
            values[0] = "Não"
            self.tree.item(item_id, values=tuple(values), tags=("unselected",))
        self._update_summary()

    def _select_suggested(self) -> None:
        for idx, item_id in enumerate(self.tree.get_children()):
            candidate = self._candidates[idx]
            values = list(self.tree.item(item_id, "values"))
            values[0] = "Sim" if bool(candidate.get("selected_default", False)) else "Não"
            self.tree.item(item_id, values=tuple(values), tags=("selected",) if values[0] == "Sim" else ("unselected",))
        self._update_summary()

    def _update_summary(self) -> None:
        selected_count = sum(
            1 for item_id in self.tree.get_children() if self.tree.item(item_id, "values")[0] == "Sim"
        )
        if selected_count == 0:
            text = f"Nenhuma {self._item_label_singular} selecionada"
            color = COLORS.get("text_secondary", "gray")
        elif selected_count == 1:
            text = f"1 {self._item_label_singular} será aplicada"
            color = COLORS.get("success", "green")
        else:
            text = f"{selected_count} {self._item_label_plural} serão aplicadas"
            color = COLORS.get("success", "green")
        self.summary_label.configure(text=text, text_color=color)

    def _show_selected_context(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        try:
            idx = int(selection[0])
        except Exception:
            return
        if idx < 0 or idx >= len(self._candidates):
            return
        examples = self._candidates[idx].get("context_examples", [])
        lines: List[str] = []
        if isinstance(examples, list):
            for example in examples[:3]:
                if not isinstance(example, dict):
                    continue
                label = str(example.get("doc_label", "") or example.get("doc_id", "") or "Documento")
                context = str(example.get("context", "") or "").strip()
                if context:
                    lines.append(f"{label}: {context}")
        text = "\n".join(lines) if lines else f"Sem contexto disponível para esta {self._item_label_singular}."
        self.context_box.configure(state="normal")
        self.context_box.delete("1.0", "end")
        self.context_box.insert("1.0", text)
        self.context_box.configure(state="disabled")

    def _collect_selected(self) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        for idx, item_id in enumerate(self.tree.get_children()):
            values = self.tree.item(item_id, "values")
            if values[0] == "Sim" and idx < len(self._candidates):
                selected.append(dict(self._candidates[idx]))
        return selected

    def _confirm(self) -> None:
        self._selected_bigrams = self._collect_selected()
        self._confirmed = True
        if self._on_confirm:
            self._on_confirm(self._selected_bigrams)
        self.destroy()

    def _cancel(self) -> None:
        self._selected_bigrams = []
        self._confirmed = False
        self.destroy()

    def get_selected_bigrams(self) -> List[Dict[str, Any]]:
        return self._selected_bigrams

    def was_confirmed(self) -> bool:
        return self._confirmed
