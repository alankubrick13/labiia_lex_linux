"""Dialog for Specificities analysis configuration."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from .analysis_dialog import BaseAnalysisDialog
from ..styles import FONTS, COLORS
from ..iconography import label_with_icon


class SpecificitiesDialog(BaseAnalysisDialog):
    """Parameters dialog for lexical specificities analysis."""

    ANALYSIS_TYPE = "specificities"

    INDEX_LABEL_TO_KEY = {
        "Chi²": "chi2",
        "Hipergeométrico": "hypergeo",
    }

    GRAM_LABEL_TO_KEY = {
        "Ativas + suplementares": 0,
        "Apenas ativas": 1,
        "Apenas suplementares": 2,
    }

    INDEX_KEY_TO_LABEL = {value: key for key, value in INDEX_LABEL_TO_KEY.items()}
    GRAM_KEY_TO_LABEL = {value: key for key, value in GRAM_LABEL_TO_KEY.items()}

    def __init__(
        self,
        parent,
        metadata_tokens: Optional[List[str]] = None,
        initial_params: Optional[Dict[str, Any]] = None,
    ):
        self._metadata_tokens = sorted(set(metadata_tokens or []))
        self.index_var = ctk.StringVar(
            value=self.INDEX_KEY_TO_LABEL.get(
                self._initial_str("index_type", "chi2"), "Chi²"
            )
        )
        self.gram_var = ctk.StringVar(
            value=self.GRAM_KEY_TO_LABEL.get(
                self._initial_int("gram_type", 0), "Ativas + suplementares"
            )
        )
        super().__init__(
            parent,
            "Análise de Especificidades",
            620,
            560,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        ctk.CTkLabel(
            self.params_frame,
            text=label_with_icon("keyness", "Especificidades Lexicais"),
            font=FONTS["title"],
        ).pack(pady=(0, 14))

        line1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        line1.pack(fill="x", pady=4)
        ctk.CTkLabel(line1, text="Índice:", font=FONTS["body"], width=170).pack(side="left")
        ctk.CTkOptionMenu(
            line1,
            values=list(self.INDEX_LABEL_TO_KEY.keys()),
            variable=self.index_var,
            width=200,
        ).pack(side="left", padx=8)
        self.create_help_icon(line1, "Métrica estatística para calcular a especificidade (Chi² ou Hipergeométrico).").pack(side="left", padx=(0, 5))

        line2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        line2.pack(fill="x", pady=4)
        ctk.CTkLabel(line2, text="Frequência mínima:", font=FONTS["body"], width=170).pack(side="left")
        self.min_freq_var = ctk.IntVar(
            value=self._initial_int("min_freq", 3, minimum=1)
        )
        ctk.CTkEntry(line2, textvariable=self.min_freq_var, width=100).pack(side="left", padx=8)
        self.create_help_icon(line2, "Frequência mínima para inclusão de termos na análise.").pack(side="left", padx=(0, 5))

        line3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        line3.pack(fill="x", pady=4)
        ctk.CTkLabel(line3, text="Tipo de forma:", font=FONTS["body"], width=170).pack(side="left")
        ctk.CTkOptionMenu(
            line3,
            values=list(self.GRAM_LABEL_TO_KEY.keys()),
            variable=self.gram_var,
            width=220,
        ).pack(side="left", padx=8)
        self.create_help_icon(line3, "Filtro de classes gramaticais (somente ativas, suplementares ou ambas).").pack(side="left", padx=(0, 5))

        self.run_afc_var = ctk.BooleanVar(value=self._initial_bool("run_afc", False))
        afc_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        afc_frame.pack(anchor="w", pady=(8, 8))
        ctk.CTkCheckBox(
            afc_frame,
            text="Gerar AFC da tabela lexical (quando backend R estiver disponível)",
            variable=self.run_afc_var,
        ).pack(side="left")
        self.create_help_icon(afc_frame, "Executa uma Análise Fatorial de Correspondência sobre a tabela de especificidades.").pack(side="left", padx=5)

        ctk.CTkLabel(
            self.params_frame,
            text="Metadados (seleção múltipla):",
            font=FONTS["heading"],
        ).pack(anchor="w", pady=(8, 4))

        list_frame = ctk.CTkFrame(self.params_frame)
        list_frame.pack(fill="both", expand=True, pady=4)

        self.metadata_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            height=10,
            font=FONTS["small"],
        )
        self.metadata_listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.metadata_listbox.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.metadata_listbox.configure(yscrollcommand=scrollbar.set)

        if self._metadata_tokens:
            for token in self._metadata_tokens:
                self.metadata_listbox.insert(tk.END, token)
            initial_tokens = self._initial_params.get("metadata_tokens", [])
            selected = set(initial_tokens) if isinstance(initial_tokens, list) else set()
            if selected:
                for idx, token in enumerate(self._metadata_tokens):
                    if token in selected:
                        self.metadata_listbox.selection_set(idx)
            if not self.metadata_listbox.curselection():
                self.metadata_listbox.selection_set(0, tk.END)
        else:
            self.metadata_listbox.insert(tk.END, "*sem_metadados_disponiveis")

        actions = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        actions.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            actions,
            text="Selecionar todos",
            width=140,
            fg_color=COLORS["primary"],
            command=lambda: self.metadata_listbox.selection_set(0, tk.END),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Limpar seleção",
            width=140,
            fg_color=COLORS["secondary"],
            command=lambda: self.metadata_listbox.selection_clear(0, tk.END),
        ).pack(side="left", padx=4)

    def _build_result(self) -> Dict[str, Any]:
        selected_indices = self.metadata_listbox.curselection()
        selected_tokens = [
            self.metadata_listbox.get(idx)
            for idx in selected_indices
        ]
        if not selected_tokens and self._metadata_tokens:
            selected_tokens = list(self._metadata_tokens)

        return {
            "analysis_type": "specificities",
            "index_type": self.INDEX_LABEL_TO_KEY.get(self.index_var.get(), "chi2"),
            "min_freq": int(self.min_freq_var.get()),
            "gram_type": self.GRAM_LABEL_TO_KEY.get(self.gram_var.get(), 0),
            "metadata_tokens": selected_tokens,
            "run_afc": bool(self.run_afc_var.get()),
            "backend": str(self._initial_params.get("backend", "python")),
            "allow_python_fallback": self._initial_bool("allow_python_fallback", True),
        }
