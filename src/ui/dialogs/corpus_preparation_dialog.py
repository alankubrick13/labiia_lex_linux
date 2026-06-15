"""Dialogo de preparacao NLP posterior a importacao inicial."""

from __future__ import annotations

from typing import Any, Dict, Optional

import customtkinter as ctk

from ..styles import FONTS, get_themed_color


class CorpusPreparationDialog(ctk.CTkToplevel):
    """Coleta opcoes pesadas de limpeza para aplicar depois da importacao."""

    def __init__(self, parent, initial_options: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.title("Preparar corpus")
        self.geometry("700x780")
        self.minsize(640, 700)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        options = dict(initial_options or {})
        self._result: Optional[Dict[str, Any]] = None
        self.lowercase_var = ctk.BooleanVar(value=bool(options.get("lowercase", False)))
        self.remove_numbers_var = ctk.BooleanVar(value=bool(options.get("remove_numbers", False)))
        self.remove_accents_var = ctk.BooleanVar(value=bool(options.get("remove_accents", False)))
        self.clean_web_data_var = ctk.BooleanVar(value=bool(options.get("clean_web_data", False)))
        self.detect_bigrams_var = ctk.BooleanVar(value=bool(options.get("detect_bigrams", False)))
        self.bigram_top_n_var = ctk.IntVar(value=int(options.get("bigram_top_n", 30) or 30))
        self.bigram_min_freq_var = ctk.IntVar(value=int(options.get("bigram_min_freq", 3) or 3))
        self.ngram_max_var = ctk.IntVar(value=min(3, max(2, int(options.get("ngram_max", 3) or 3))))
        self.min_is_norm_var = ctk.DoubleVar(value=float(options.get("min_is_norm", 0.35) or 0.35))
        self.detect_entities_var = ctk.BooleanVar(value=bool(options.get("detect_entities", False)))
        self.entity_top_n_var = ctk.IntVar(value=int(options.get("entity_top_n", 50) or 50))
        self.entity_min_freq_var = ctk.IntVar(value=int(options.get("entity_min_freq", 2) or 2))
        self.entity_max_tokens_var = ctk.IntVar(value=int(options.get("entity_max_tokens", 6) or 6))

        self._create_widgets()
        self._center_on_parent(parent)
        self.wait_window()

    def get_result(self) -> Optional[Dict[str, Any]]:
        return self._result

    def _create_widgets(self) -> None:
        self.configure(fg_color=get_themed_color("background"))
        container = ctk.CTkFrame(
            self,
            fg_color=get_themed_color("surface"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=16,
        )
        container.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            container,
            text="Preparar corpus",
            font=FONTS["title"],
            text_color=get_themed_color("text"),
        ).pack(anchor="w", padx=18, pady=(18, 4))
        ctk.CTkLabel(
            container,
            text=(
                "Esta etapa roda depois da importação inicial e pode demorar mais. "
                "Use quando quiser refinar a limpeza ou unir expressões compostas antes das análises."
            ),
            font=FONTS["body"],
            text_color=get_themed_color("text_secondary"),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        footer = ctk.CTkFrame(container, fg_color="transparent", height=56)
        footer.pack(fill="x", side="bottom", padx=18, pady=(8, 18))
        footer.pack_propagate(False)
        ctk.CTkButton(
            footer,
            text="Cancelar",
            command=self._cancel,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=10,
            width=120,
            height=40,
        ).pack(side="right", padx=(8, 0), pady=8)
        ctk.CTkButton(
            footer,
            text="Aplicar",
            command=self._confirm,
            fg_color=get_themed_color("primary"),
            hover_color=get_themed_color("primary_hover"),
            text_color=get_themed_color("text_inverse"),
            corner_radius=10,
            width=128,
            height=40,
        ).pack(side="right", pady=8)

        body = ctk.CTkScrollableFrame(container, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=(0, 0))

        options_frame = ctk.CTkFrame(body, fg_color="transparent")
        options_frame.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(
            options_frame,
            text="Limpeza opcional",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(anchor="w", pady=(0, 4))

        self._add_checkbox(options_frame, "Converter para minúsculas", self.lowercase_var)
        self._add_checkbox(options_frame, "Remover números", self.remove_numbers_var)
        self._add_checkbox(options_frame, "Remover acentos", self.remove_accents_var)
        self._add_checkbox(options_frame, "Limpar dados da internet (URLs, e-mails etc.)", self.clean_web_data_var)

        bigram_frame = ctk.CTkFrame(body, fg_color=get_themed_color("background"), corner_radius=12)
        bigram_frame.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(
            bigram_frame,
            text="Parâmetros de expressões compostas",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(anchor="w", padx=14, pady=(12, 6))
        self._add_checkbox(bigram_frame, "Detectar expressões compostas", self.detect_bigrams_var)

        row = ctk.CTkFrame(bigram_frame, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(4, 8))
        ctk.CTkLabel(row, text="Máximo de sugestões", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(row, textvariable=self.bigram_top_n_var, width=72).pack(side="left", padx=(8, 20))
        ctk.CTkLabel(row, text="Frequência mínima", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(row, textvariable=self.bigram_min_freq_var, width=72).pack(side="left", padx=(8, 0))

        row2 = ctk.CTkFrame(bigram_frame, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(row2, text="Tamanho máximo (2-3)", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(row2, textvariable=self.ngram_max_var, width=72).pack(side="left", padx=(8, 20))
        ctk.CTkLabel(row2, text="Score mínimo", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(row2, textvariable=self.min_is_norm_var, width=72).pack(side="left", padx=(8, 0))

        entity_frame = ctk.CTkFrame(body, fg_color=get_themed_color("background"), corner_radius=12)
        entity_frame.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(
            entity_frame,
            text="Entidades nomeadas",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(anchor="w", padx=14, pady=(12, 6))
        self._add_checkbox(entity_frame, "Detectar entidades nomeadas leves", self.detect_entities_var)

        entity_row = ctk.CTkFrame(entity_frame, fg_color="transparent")
        entity_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(entity_row, text="Máximo de sugestões", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(entity_row, textvariable=self.entity_top_n_var, width=72).pack(side="left", padx=(8, 20))
        ctk.CTkLabel(entity_row, text="Frequência mínima", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(entity_row, textvariable=self.entity_min_freq_var, width=72).pack(side="left", padx=(8, 20))
        ctk.CTkLabel(entity_row, text="Tamanho máximo", font=FONTS["body"]).pack(side="left")
        ctk.CTkEntry(entity_row, textvariable=self.entity_max_tokens_var, width=72).pack(side="left", padx=(8, 0))

        summary_frame = ctk.CTkFrame(body, fg_color="transparent")
        summary_frame.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(
            summary_frame,
            text="Resumo",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            summary_frame,
            text=(
                "A importação continua rápida. A detecção de expressões compostas acontece aqui, "
                "em uma segunda etapa opcional com seleção manual antes de aplicar. Entidades leves "
                "também podem ser sugeridas para preservar nomes próprios e instituições."
            ),
            font=FONTS["body"],
            text_color=get_themed_color("text_secondary"),
            wraplength=540,
            justify="left",
        ).pack(anchor="w")

    def _add_checkbox(self, parent, text: str, variable: ctk.BooleanVar) -> None:
        ctk.CTkCheckBox(
            parent,
            text=text,
            variable=variable,
            font=FONTS["body"],
            text_color=get_themed_color("text"),
        ).pack(anchor="w", pady=5)

    def _confirm(self) -> None:
        self._result = {
            "lowercase": bool(self.lowercase_var.get()),
            "remove_numbers": bool(self.remove_numbers_var.get()),
            "remove_accents": bool(self.remove_accents_var.get()),
            "clean_web_data": bool(self.clean_web_data_var.get()),
            "detect_bigrams": bool(self.detect_bigrams_var.get()),
            "bigram_top_n": max(1, int(self.bigram_top_n_var.get() or 30)),
            "bigram_min_freq": max(1, int(self.bigram_min_freq_var.get() or 3)),
            "ngram_max": min(3, max(2, int(self.ngram_max_var.get() or 3))),
            "min_is_norm": max(0.0, float(self.min_is_norm_var.get() or 0.35)),
            "selected_bigrams": [],
            "detect_entities": bool(self.detect_entities_var.get()),
            "entity_top_n": max(1, int(self.entity_top_n_var.get() or 50)),
            "entity_min_freq": max(1, int(self.entity_min_freq_var.get() or 2)),
            "entity_max_tokens": min(6, max(1, int(self.entity_max_tokens_var.get() or 6))),
            "selected_entities": [],
        }
        self.destroy()

    def _cancel(self) -> None:
        self._result = None
        self.destroy()

    def _center_on_parent(self, parent) -> None:
        try:
            self.update_idletasks()
            parent_x = int(parent.winfo_x())
            parent_y = int(parent.winfo_y())
            parent_w = int(parent.winfo_width())
            parent_h = int(parent.winfo_height())
            dialog_w = int(self.winfo_width())
            dialog_h = int(self.winfo_height())
            x = parent_x + max(0, (parent_w - dialog_w) // 2)
            y = parent_y + max(0, (parent_h - dialog_h) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
