"""Dialogs for matrix analyses (CSV/XLSX)."""

from __future__ import annotations

import customtkinter as ctk
from typing import Any, Dict, List, Optional

from .analysis_dialog import (
    BaseAnalysisDialog,
    SIMILARITY_LAYOUT_OPTIONS,
    SIMILARITY_COMMUNITY_OPTIONS,
)
from ..styles import FONTS, COLORS, get_themed_color
from ..iconography import label_with_icon


class MatrixFrequencyDialog(BaseAnalysisDialog):
    """Dialog for matrix frequency analysis."""

    ANALYSIS_TYPE = "matrix_frequency"

    def __init__(
        self,
        parent,
        columns: List[str],
        initial_params: Optional[Dict[str, Any]] = None,
    ):
        self._columns = list(columns or [])
        super().__init__(
            parent,
            "Frequências (Matriz)",
            520,
            420,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        ctk.CTkLabel(
            self.params_frame,
            text=label_with_icon("matrix", "Frequências em Matriz"),
            font=FONTS["title"],
        ).pack(pady=(0, 14))

        ctk.CTkLabel(
            self.params_frame,
            text="Colunas (separadas por vírgula):",
            font=FONTS["body"],
            anchor="w",
        ).pack(fill="x")

        default_columns = self._initial_params.get("columns")
        if isinstance(default_columns, list) and default_columns:
            default_value = ", ".join(str(col) for col in default_columns)
        else:
            default_value = ", ".join(self._columns)

        self.columns_box = ctk.CTkTextbox(self.params_frame, height=90, font=FONTS["body"])
        self.columns_box.pack(fill="x", pady=(4, 12))
        self.columns_box.insert("1.0", default_value)

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Top N categorias:", font=FONTS["body"], width=180).pack(side="left")
        self.top_n_var = ctk.IntVar(value=self._initial_int("top_n", 50, minimum=5, maximum=300))
        ctk.CTkSlider(
            row1,
            from_=5,
            to=300,
            number_of_steps=59,
            variable=self.top_n_var,
            width=180,
        ).pack(side="left", padx=8)
        self.top_n_label = ctk.CTkLabel(row1, text=str(self.top_n_var.get()), width=40)
        self.top_n_label.pack(side="left")
        self.top_n_var.trace_add("write", lambda *_: self.top_n_label.configure(text=str(self.top_n_var.get())))
        self.create_help_icon(row1, "Número máximo de categorias para exibir no gráfico.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Formato do gráfico:", font=FONTS["body"], width=180).pack(side="left")
        self.typegraph_var = ctk.StringVar(value=self._initial_str("typegraph", "png", allowed=["png", "svg"]))
        ctk.CTkOptionMenu(
            row2,
            values=["png", "svg"],
            variable=self.typegraph_var,
            width=120,
        ).pack(side="left", padx=8)
        self.create_help_icon(row2, "Formato do arquivo de imagem gerado.").pack(side="left", padx=(0, 5))

        ctk.CTkLabel(
            self.params_frame,
            text="Nota: deixe vazio para usar todas as colunas.",
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
        ).pack(anchor="w", pady=(10, 0))

    def _build_result(self) -> Dict[str, Any]:
        raw = self.columns_box.get("1.0", "end").strip()
        selected = [item.strip() for item in raw.split(",") if item.strip()]
        if not selected:
            selected = list(self._columns)
        return {
            "analysis_type": "matrix_frequency",
            "columns": selected,
            "top_n": int(self.top_n_var.get()),
            "typegraph": self.typegraph_var.get(),
        }


class MatrixChi2Dialog(BaseAnalysisDialog):
    """Dialog for matrix Chi-square analysis."""

    ANALYSIS_TYPE = "matrix_chi2"

    def __init__(
        self,
        parent,
        columns: List[str],
        initial_params: Optional[Dict[str, Any]] = None,
    ):
        self._columns = list(columns or [])
        super().__init__(
            parent,
            "Qui-Quadrado (Matriz)",
            500,
            320,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        ctk.CTkLabel(
            self.params_frame,
            text=label_with_icon("chi2", "Qui-Quadrado em Matriz"),
            font=FONTS["title"],
        ).pack(pady=(0, 14))

        default_row = self._initial_str("row_var", self._columns[0] if self._columns else "")
        default_col = self._initial_str(
            "col_var",
            self._columns[1] if len(self._columns) > 1 else (self._columns[0] if self._columns else ""),
        )

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Variável de linha:", font=FONTS["body"], width=180).pack(side="left")
        self.row_var = ctk.StringVar(value=default_row)
        ctk.CTkOptionMenu(
            row1,
            values=self._columns if self._columns else [""],
            variable=self.row_var,
            width=220,
        ).pack(side="left", padx=8)
        self.create_help_icon(row1, "Variável categórica para as linhas da tabela de contingência.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Variável de coluna:", font=FONTS["body"], width=180).pack(side="left")
        self.col_var = ctk.StringVar(value=default_col)
        ctk.CTkOptionMenu(
            row2,
            values=self._columns if self._columns else [""],
            variable=self.col_var,
            width=220,
        ).pack(side="left", padx=8)
        self.create_help_icon(row2, "Variável categórica para as colunas da tabela de contingência.").pack(side="left", padx=(0, 5))

        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Formato do gráfico:", font=FONTS["body"], width=180).pack(side="left")
        self.typegraph_var = ctk.StringVar(value=self._initial_str("typegraph", "png", allowed=["png", "svg"]))
        ctk.CTkOptionMenu(row3, values=["png", "svg"], variable=self.typegraph_var, width=120).pack(side="left", padx=8)
        self.create_help_icon(row3, "Formato do arquivo de imagem do gráfico.").pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        row_var = str(self.row_var.get()).strip()
        col_var = str(self.col_var.get()).strip()
        if row_var == col_var and len(self._columns) > 1:
            for candidate in self._columns:
                if candidate != row_var:
                    col_var = candidate
                    break
        return {
            "analysis_type": "matrix_chi2",
            "row_var": row_var,
            "col_var": col_var,
            "typegraph": self.typegraph_var.get(),
        }


class MatrixAFCDialog(BaseAnalysisDialog):
    """Dialog for matrix AFC analysis."""

    ANALYSIS_TYPE = "matrix_afc"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "AFC (Matriz)",
            460,
            280,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        ctk.CTkLabel(
            self.params_frame,
            text=label_with_icon("afc", "AFC em Matriz"),
            font=FONTS["title"],
        ).pack(pady=(0, 14))

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Número de dimensões:", font=FONTS["body"], width=180).pack(side="left")
        self.n_dim_var = ctk.IntVar(value=self._initial_int("n_dim", 2, minimum=2, maximum=5))
        ctk.CTkOptionMenu(
            row1,
            values=["2", "3", "4", "5"],
            variable=self.n_dim_var,
            width=100,
            command=lambda value: self.n_dim_var.set(int(value)),
        ).pack(side="left", padx=8)
        self.create_help_icon(row1, "Número de fatores/eixos para reter na análise.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Formato do gráfico:", font=FONTS["body"], width=180).pack(side="left")
        self.typegraph_var = ctk.StringVar(value=self._initial_str("typegraph", "png", allowed=["png", "svg"]))
        ctk.CTkOptionMenu(row2, values=["png", "svg"], variable=self.typegraph_var, width=120).pack(side="left", padx=8)
        self.create_help_icon(row2, "Formato do arquivo de imagem do gráfico.").pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "matrix_afc",
            "n_dim": int(self.n_dim_var.get()),
            "typegraph": self.typegraph_var.get(),
        }


class MatrixCHDDialog(BaseAnalysisDialog):
    """Dialog for matrix CHD analysis."""

    ANALYSIS_TYPE = "matrix_chd"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "CHD (Matriz)",
            500,
            360,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        ctk.CTkLabel(
            self.params_frame,
            text=label_with_icon("dendrogram", "CHD em Matriz"),
            font=FONTS["title"],
        ).pack(pady=(0, 14))

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Número de classes:", font=FONTS["body"], width=180).pack(side="left")
        self.n_classes_var = ctk.IntVar(value=self._initial_int("nb_classes", 5, minimum=2, maximum=20))
        ctk.CTkSlider(
            row1,
            from_=2,
            to=20,
            number_of_steps=18,
            variable=self.n_classes_var,
            width=180,
        ).pack(side="left", padx=8)
        self.n_classes_label = ctk.CTkLabel(row1, text=str(self.n_classes_var.get()), width=40)
        self.n_classes_label.pack(side="left")
        self.n_classes_var.trace_add("write", lambda *_: self.n_classes_label.configure(text=str(self.n_classes_var.get())))
        self.create_help_icon(row1, "Número desejado de classes finais no dendrograma.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Método de clustering:", font=FONTS["body"], width=180).pack(side="left")
        self.method_var = ctk.StringVar(
            value=self._initial_str("method", "ward.D2", allowed=["ward.D2", "ward.D", "average", "complete"])
        )
        ctk.CTkOptionMenu(
            row2,
            values=["ward.D2", "ward.D", "average", "complete"],
            variable=self.method_var,
            width=160,
        ).pack(side="left", padx=8)
        self.create_help_icon(row2, "Algoritmo de aglomeração para o clustering hierárquico.").pack(side="left", padx=(0, 5))

        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Formato do gráfico:", font=FONTS["body"], width=180).pack(side="left")
        self.typegraph_var = ctk.StringVar(value=self._initial_str("typegraph", "png", allowed=["png", "svg"]))
        ctk.CTkOptionMenu(row3, values=["png", "svg"], variable=self.typegraph_var, width=120).pack(side="left", padx=8)
        self.create_help_icon(row3, "Formato do arquivo de imagem do gráfico.").pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "matrix_chd",
            "nb_classes": int(self.n_classes_var.get()),
            "method": self.method_var.get(),
            "typegraph": self.typegraph_var.get(),
        }


class MatrixSimilarityDialog(BaseAnalysisDialog):
    """Dialog for matrix similarity analysis."""

    ANALYSIS_TYPE = "matrix_similarity"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Similitude (Matriz)",
            520,
            430,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        ctk.CTkLabel(
            self.params_frame,
            text=label_with_icon("similarity", "Similitude em Matriz"),
            font=FONTS["title"],
        ).pack(pady=(0, 14))

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Layout:", font=FONTS["body"], width=180).pack(side="left")
        self.layout_var = ctk.StringVar(
            value=self._initial_str("layout", "frutch", allowed=SIMILARITY_LAYOUT_OPTIONS)
        )
        ctk.CTkOptionMenu(
            row1,
            values=SIMILARITY_LAYOUT_OPTIONS,
            variable=self.layout_var,
            width=160,
        ).pack(side="left", padx=8)
        self.create_help_icon(row1, "Algoritmo de disposição dos nós no grafo.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Aresta mínima:", font=FONTS["body"], width=180).pack(side="left")
        self.min_edge_var = ctk.IntVar(value=self._initial_int("min_edge", 0, minimum=0, maximum=20))
        ctk.CTkSlider(
            row2,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.min_edge_var,
            width=180,
        ).pack(side="left", padx=8)
        self.min_edge_label = ctk.CTkLabel(row2, text=str(self.min_edge_var.get()), width=40)
        self.min_edge_label.pack(side="left")
        self.min_edge_var.trace_add("write", lambda *_: self.min_edge_label.configure(text=str(self.min_edge_var.get())))
        self.create_help_icon(row2, "Valor mínimo para exibir uma conexão entre nós.").pack(side="left", padx=(0, 5))

        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        self.detect_communities_var = ctk.BooleanVar(value=self._initial_bool("detect_communities", False))
        chk_comm = ctk.CTkCheckBox(
            row3,
            text="Detectar comunidades",
            variable=self.detect_communities_var,
        )
        chk_comm.pack(side="left", padx=8)
        self.create_help_icon(row3, "Identificar e colorir agrupamentos (comunidades) no grafo.").pack(side="left", padx=5)

        row4 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=5)
        ctk.CTkLabel(row4, text="Método comunidade:", font=FONTS["body"], width=180).pack(side="left")
        self.community_method_var = ctk.StringVar(
            value=self._initial_str(
                "community_method",
                "edge_betweenness",
                allowed=SIMILARITY_COMMUNITY_OPTIONS + ["louvain"],
            )
        )
        ctk.CTkOptionMenu(
            row4,
            values=SIMILARITY_COMMUNITY_OPTIONS,
            variable=self.community_method_var,
            width=160,
        ).pack(side="left", padx=8)
        self.create_help_icon(row4, "Algoritmo para detecção de comunidades.").pack(side="left", padx=(0, 5))

        row5 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row5.pack(fill="x", pady=5)
        ctk.CTkLabel(row5, text="Formato do gráfico:", font=FONTS["body"], width=180).pack(side="left")
        self.typegraph_var = ctk.StringVar(value=self._initial_str("typegraph", "png", allowed=["png", "svg"]))
        ctk.CTkOptionMenu(row5, values=["png", "svg"], variable=self.typegraph_var, width=120).pack(side="left", padx=8)
        self.create_help_icon(row5, "Formato do arquivo de imagem do gráfico.").pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "matrix_similarity",
            "layout": self.layout_var.get(),
            "min_edge": int(self.min_edge_var.get()),
            "detect_communities": self.detect_communities_var.get(),
            "community_method": self.community_method_var.get(),
            "typegraph": self.typegraph_var.get(),
        }
