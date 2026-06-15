"""Dialog for configuring the NRC Emotion analysis (syuzhet via R)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import customtkinter as ctk

from ..styles import FONTS, get_themed_color
from ..iconography import label_with_icon
from .analysis_dialog import BaseAnalysisDialog


class EmotionsDialog(BaseAnalysisDialog):
    """Configuration dialog for the NRC Emotion analysis.

    Inherits from BaseAnalysisDialog which provides:
    - Scrollable params frame
    - 'Executar' / 'Cancelar' buttons
    - get_result() / _build_result() contract
    """

    ANALYSIS_TYPE = "emotions"

    def __init__(
        self,
        parent,
        initial_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            parent,
            "Análise de Emoções (NRC)",
            490,
            430,
            initial_params=initial_params,
        )

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _create_params_widgets(self) -> None:
        # --- Title row ------------------------------------------------
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 12))

        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("emotions", "Emoções — Léxico NRC"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)

        self.create_help_icon(
            title_frame,
            "Analisa o texto em 8 dimensões emocionais (Raiva, Antecipação, "
            "Nojo, Medo, Alegria, Tristeza, Surpresa, Confiança) usando o "
            "léxico NRC via pacote R syuzhet.",
        ).pack(side="left")

        # --- Output options -------------------------------------------
        ctk.CTkLabel(
            self.params_frame,
            text="Saídas geradas",
            font=FONTS.get("section", FONTS["body"]),
            text_color=get_themed_color("text_secondary"),
        ).pack(anchor="w", padx=12, pady=(4, 2))

        bar_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        bar_frame.pack(anchor="w", padx=12, pady=2)
        self.bar_chart_var = ctk.BooleanVar(
            value=self._initial_bool("bar_chart", True)
        )
        ctk.CTkCheckBox(
            bar_frame,
            text="Gráfico de barras (emoções totais)",
            variable=self.bar_chart_var,
        ).pack(side="left")
        self.create_help_icon(
            bar_frame,
            "Gera um gráfico de barras com a frequência de cada uma das "
            "8 emoções detectadas no corpus.",
        ).pack(side="left", padx=5)

        radar_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        radar_frame.pack(anchor="w", padx=12, pady=2)
        self.radar_chart_var = ctk.BooleanVar(
            value=self._initial_bool("radar_chart", True)
        )
        ctk.CTkCheckBox(
            radar_frame,
            text="Gráfico radar / teia de aranha",
            variable=self.radar_chart_var,
        ).pack(side="left")
        self.create_help_icon(
            radar_frame,
            "Gera um gráfico radar com o perfil emocional geral do corpus. "
            "Requer o pacote R 'fmsb' (instalado automaticamente se ausente).",
        ).pack(side="left", padx=5)

        # --- Image dimensions -----------------------------------------
        ctk.CTkLabel(
            self.params_frame,
            text="Dimensões dos gráficos (px)",
            font=FONTS.get("section", FONTS["body"]),
            text_color=get_themed_color("text_secondary"),
        ).pack(anchor="w", padx=12, pady=(10, 2))

        dim_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        dim_frame.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(dim_frame, text="Largura:", font=FONTS["body"], width=80).pack(
            side="left"
        )
        self.width_var = ctk.IntVar(
            value=self._initial_int("width", 1200, minimum=600, maximum=3000)
        )
        ctk.CTkEntry(dim_frame, textvariable=self.width_var, width=80).pack(
            side="left", padx=6
        )

        ctk.CTkLabel(dim_frame, text="Altura:", font=FONTS["body"], width=60).pack(
            side="left", padx=(12, 0)
        )
        self.height_var = ctk.IntVar(
            value=self._initial_int("height", 900, minimum=400, maximum=3000)
        )
        ctk.CTkEntry(dim_frame, textvariable=self.height_var, width=80).pack(
            side="left", padx=6
        )

        # --- Disclaimer -----------------------------------------------
        disclaimer_frame = ctk.CTkFrame(
            self.params_frame,
            fg_color=get_themed_color("surface"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=6,
        )
        disclaimer_frame.pack(fill="x", padx=8, pady=(14, 4))

        ctk.CTkLabel(
            disclaimer_frame,
            text=(
                "Limitações metodológicas\n"
                "• O NRC foi criado em inglês e traduzido automaticamente ao português;\n"
                "  podem ocorrer erros de mapeamento.\n"
                "• A análise ignora contexto (negação, ironia, expressões idiomáticas).\n"
                "• Os resultados refletem frequências léxicas brutas, não intenção real."
            ),
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
            justify="left",
            wraplength=420,
        ).pack(anchor="w", padx=10, pady=8)

        # --- Runtime note ---------------------------------------------
        ctk.CTkLabel(
            self.params_frame,
            text=(
                "Nota: A análise executa via R (syuzhet). "
                "O pacote será instalado automaticamente se necessário."
            ),
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
            wraplength=430,
        ).pack(pady=(8, 4))

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "emotions",
            "bar_chart":     bool(self.bar_chart_var.get()),
            "radar_chart":   bool(self.radar_chart_var.get()),
            "width":         int(self.width_var.get()),
            "height":        int(self.height_var.get()),
        }
