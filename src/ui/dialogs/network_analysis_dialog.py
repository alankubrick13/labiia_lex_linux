"""Dialog for textual network analysis configuration."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import customtkinter as ctk

from ..styles import COLORS, FONTS, get_themed_color
from ..iconography import create_help_button
from ..tk_helpers import cleanup_widget_menus


class NetworkAnalysisDialog(ctk.CTkToplevel):
    """Configuration dialog for textual network analysis."""

    _LAYOUT_LABELS = {
        "forceatlas2": "ForceAtlas2 (Gephi Java)",
    }
    _LAYOUT_VALUES = {v: k for k, v in _LAYOUT_LABELS.items()}
    _FORMAT_LABELS = {"png": "PNG", "svg": "SVG", "both": "Ambos"}
    _FORMAT_VALUES = {v: k for k, v in _FORMAT_LABELS.items()}
    _METRICS = ["weighted_degree", "degree", "betweenness", "closeness"]

    def __init__(
        self,
        parent,
        on_run: Optional[Callable[[Dict[str, Any]], None]] = None,
        initial_params: Optional[Dict[str, Any]] = None,
        default_params: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.title("Analise de Redes Textuais")
        self.geometry("620x760")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.on_run = on_run
        self._initial_params = dict(initial_params or {})
        self._default_params = dict(default_params or {})
        self._result: Optional[Dict[str, Any]] = None
        self._is_destroying = False

        self._build_ui()
        self._center_on_parent(parent)

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

    def create_help_icon(self, parent, text: str):
        """Create a standard help icon with tooltip."""
        return create_help_button(parent, text, size=18)

    def _build_ui(self) -> None:
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=16, pady=16)

        title = ctk.CTkLabel(main, text="Rede Textual (Gephi-like)", font=FONTS["title"])
        title.pack(anchor="w", pady=(4, 8))

        buttons = ctk.CTkFrame(main, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", pady=(10, 2))
        ctk.CTkButton(
            buttons,
            text="Restaurar padrao",
            width=160,
            fg_color=COLORS["button"],
            hover_color=COLORS["button_hover"],
            command=self._on_reset_defaults,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            buttons,
            text="Cancelar",
            width=110,
            fg_color=COLORS["secondary"],
            command=self._on_cancel,
        ).pack(side="right", padx=6)
        ctk.CTkButton(
            buttons,
            text="Executar",
            width=120,
            fg_color=COLORS["success"],
            command=self._on_run_click,
        ).pack(side="right", padx=6)

        scroll = ctk.CTkScrollableFrame(main)
        scroll.pack(side="top", fill="both", expand=True)

        self._build_network_section(scroll)
        self._build_layout_section(scroll)
        self._build_visual_section(scroll)
        self._build_gephi_section(scroll)
        self._build_export_section(scroll)

    def _section_title(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=FONTS["heading"]).pack(anchor="w", pady=(10, 6))

    def _slider_row(
        self,
        parent,
        label: str,
        *,
        from_: float,
        to: float,
        steps: int,
        initial: float,
        formatter: str = "{:.0f}",
        help_text: Optional[str] = None,
    ):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=3)
        ctk.CTkLabel(frame, text=label, font=FONTS["body"]).pack(side="left")

        if help_text:
            self.create_help_icon(frame, help_text).pack(side="right", padx=(5, 0))

        value_label = ctk.CTkLabel(frame, text=formatter.format(initial), font=FONTS["small"], width=56)
        value_label.pack(side="right")
        slider = ctk.CTkSlider(frame, from_=from_, to=to, number_of_steps=steps)
        slider.set(initial)
        slider.pack(side="right", fill="x", expand=True, padx=(10, 8))

        def _update_label(raw_value: float) -> None:
            try:
                value_label.configure(text=formatter.format(float(raw_value)))
            except Exception:
                value_label.configure(text=str(raw_value))

        slider.configure(command=_update_label)
        _update_label(initial)
        return slider

    def _build_network_section(self, parent) -> None:
        self._section_title(parent, "Construcao da Rede")

        self.auto_tune_var = ctk.BooleanVar(value=self._initial_bool("auto_tune", True))
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(anchor="w", pady=(2, 6))
        ctk.CTkCheckBox(
            frame,
            text="Selecao automatica (recomendado)",
            variable=self.auto_tune_var,
        ).pack(side="left")
        self.create_help_icon(
            frame,
            "Ajusta automaticamente frequencia e coocorrencia para gerar uma rede mais legivel.",
        ).pack(side="left", padx=5)

        self.min_freq_slider = self._slider_row(
            parent,
            "Frequencia minima",
            from_=1,
            to=30,
            steps=29,
            initial=self._initial_int("min_freq", 3, minimum=1, maximum=30),
            help_text="Frequencia minima para um termo entrar na rede.",
        )
        self.min_cooc_slider = self._slider_row(
            parent,
            "Coocorrencia minima",
            from_=1,
            to=30,
            steps=29,
            initial=self._initial_int("min_cooc", 2, minimum=1, maximum=30),
            help_text="Numero minimo de coocorrencias para manter uma aresta.",
        )
        self.max_nodes_slider = self._slider_row(
            parent,
            "Maximo de nos",
            from_=50,
            to=1000,
            steps=19,
            initial=self._initial_int("max_nodes", 300, minimum=50, maximum=1000),
            help_text="Limite de palavras (nos) no grafo final.",
        )
        self.edge_threshold_slider = self._slider_row(
            parent,
            "Limiar de peso de aresta",
            from_=0,
            to=30,
            steps=30,
            initial=self._initial_int("edge_threshold", 0, minimum=0, maximum=30),
            help_text="Remove arestas com peso abaixo deste valor.",
        )

        self.arbremax_var = ctk.BooleanVar(value=self._initial_bool("arbremax", False))
        frame_mst = ctk.CTkFrame(parent, fg_color="transparent")
        frame_mst.pack(anchor="w", pady=(4, 2))
        ctk.CTkCheckBox(
            frame_mst,
            text="Arvore de cobertura maxima (MST)",
            variable=self.arbremax_var,
        ).pack(side="left")
        self.create_help_icon(
            frame_mst,
            "Mantem apenas as arestas essenciais para conectar a rede.",
        ).pack(side="left", padx=5)

    def _build_layout_section(self, parent) -> None:
        self._section_title(parent, "Layout")

        layout_value = self._initial_str("layout", "forceatlas2", allowed=list(self._LAYOUT_LABELS.keys()))
        self.layout_var = ctk.StringVar(value=self._LAYOUT_LABELS.get(layout_value, "ForceAtlas2 (Gephi Java)"))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Algoritmo", font=FONTS["body"]).pack(side="left")
        self.create_help_icon(row, "ForceAtlas2 via backend Java do Gephi Toolkit.").pack(side="right", padx=(5, 0))
        ctk.CTkOptionMenu(
            row,
            variable=self.layout_var,
            values=list(self._LAYOUT_VALUES.keys()),
            width=240,
        ).pack(side="right")

        self.resolution_slider = self._slider_row(
            parent,
            "Resolucao Louvain",
            from_=0.1,
            to=3.0,
            steps=29,
            initial=self._initial_float("community_resolution", 1.0, minimum=0.1, maximum=3.0),
            formatter="{:.1f}",
            help_text="Controla granularidade das comunidades.",
        )

    def _build_visual_section(self, parent) -> None:
        self._section_title(parent, "Visualizacao")

        node_metric = self._initial_str("node_size_metric", "weighted_degree", allowed=self._METRICS)
        label_metric = self._initial_str("label_size_metric", node_metric, allowed=self._METRICS)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Tamanho de no", font=FONTS["body"]).pack(side="left")
        self.node_size_metric_var = ctk.StringVar(value=node_metric)
        ctk.CTkOptionMenu(row, variable=self.node_size_metric_var, values=self._METRICS, width=220).pack(side="right")
        self.create_help_icon(row, "Define qual métrica matemática será usada para calcular o tamanho dos nós (os círculos).").pack(side="right", padx=(5, 10))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Tamanho de rotulo", font=FONTS["body"]).pack(side="left")
        self.label_size_metric_var = ctk.StringVar(value=label_metric)
        ctk.CTkOptionMenu(row, variable=self.label_size_metric_var, values=self._METRICS, width=220).pack(side="right")
        self.create_help_icon(row, "Define qual métrica matemática será usada para calcular o tamanho do texto (rótulo) de cada nó.").pack(side="right", padx=(5, 10))

        self.show_halos_var = ctk.BooleanVar(value=self._initial_bool("show_halos", False))
        ctk.CTkCheckBox(parent, text="Mostrar halos de comunidade", variable=self.show_halos_var).pack(anchor="w", pady=2)

        self.show_edges_var = ctk.BooleanVar(value=self._initial_bool("show_edges", True))
        ctk.CTkCheckBox(parent, text="Mostrar arestas", variable=self.show_edges_var).pack(anchor="w", pady=2)

        self.edge_use_community_color_var = ctk.BooleanVar(value=self._initial_bool("edge_use_community_color", True))
        ctk.CTkCheckBox(
            parent,
            text="Colorir arestas por comunidade",
            variable=self.edge_use_community_color_var,
        ).pack(anchor="w", pady=2)

        self.normalize_centralities_var = ctk.BooleanVar(value=self._initial_bool("normalize_centralities", False))
        ctk.CTkCheckBox(
            parent,
            text="Normalizar centralidades",
            variable=self.normalize_centralities_var,
        ).pack(anchor="w", pady=2)

        self.curved_edges_var = ctk.BooleanVar(value=self._initial_bool("curved_edges", True))
        ctk.CTkCheckBox(
            parent,
            text="Arestas curvas (estilo Gephi)",
            variable=self.curved_edges_var,
        ).pack(anchor="w", pady=2)

        self.edge_alpha_slider = self._slider_row(
            parent,
            "Transparencia de arestas",
            from_=0.0,
            to=0.5,
            steps=25,
            initial=self._initial_float("edge_alpha", 0.26, minimum=0.0, maximum=0.5),
            formatter="{:.2f}",
            help_text="Define o grau de opacidade das linhas que conectam as palavras. Valores menores as deixam mais transparentes.",
        )

    def _build_gephi_section(self, parent) -> None:
        self._section_title(parent, "Parametros do Layout (Gephi)")

        self.iterations_slider = self._slider_row(
            parent,
            "Iteracoes ForceAtlas2",
            from_=100,
            to=5000,
            steps=49,
            initial=self._initial_int("fa2_iterations", 3000, minimum=100, maximum=5000),
            help_text="Mais iteracoes melhoram o layout, mas aumentam o tempo.",
        )
        self.gravity_slider = self._slider_row(
            parent,
            "Gravidade",
            from_=0.1,
            to=10.0,
            steps=99,
            initial=self._initial_float("fa2_gravity", 0.8, minimum=0.1, maximum=10.0),
            formatter="{:.1f}",
            help_text="Controla a força com que os nós são atraídos para o centro do grafo. Evita que partes se dispersem muito.",
        )
        self.scaling_slider = self._slider_row(
            parent,
            "Escala (espalhamento)",
            from_=1.0,
            to=150.0,
            steps=149,
            initial=self._initial_float("fa2_scaling", 50.0, minimum=1.0, maximum=150.0),
            formatter="{:.1f}",
            help_text="Controla a taxa de repulsão entre os nós, causando aumento ou diminuição no nível de espalhamento.",
        )

        self._section_title(parent, "Ajuste de Rotulos (Noverlap)")

        frame_noverlap = ctk.CTkFrame(parent, fg_color="transparent")
        frame_noverlap.pack(anchor="w", pady=2)
        self.noverlap_var = ctk.BooleanVar(value=self._initial_bool("noverlap_enabled", True))
        ctk.CTkCheckBox(frame_noverlap, text="Ativar Noverlap", variable=self.noverlap_var).pack(side="left")
        self.create_help_icon(frame_noverlap, "Evita que os nós fiquem sobrepostos impedindo a visualização.").pack(side="left", padx=(5, 0))

        frame_lbl_adj = ctk.CTkFrame(parent, fg_color="transparent")
        frame_lbl_adj.pack(anchor="w", pady=2)
        self.label_adjust_var = ctk.BooleanVar(value=self._initial_bool("label_adjust", True))
        ctk.CTkCheckBox(frame_lbl_adj, text="Ajustar rotulos automaticamente", variable=self.label_adjust_var).pack(side="left")
        self.create_help_icon(frame_lbl_adj, "Evita que os textos (rótulos) dos nós fiquem uns sobre os outros.").pack(side="left", padx=(5, 0))

        self.label_adjust_speed_slider = self._slider_row(
            parent,
            "Velocidade Noverlap",
            from_=0.1,
            to=8.0,
            steps=79,
            initial=self._initial_float("label_adjust_speed", 3.0, minimum=0.1, maximum=8.0),
            formatter="{:.1f}",
            help_text="Quão rápido os nós e rótulos se movem para não se sobreporem. Um valor maior reduz a precisão.",
        )
        self.label_adjust_iter_slider = self._slider_row(
            parent,
            "Iteracoes Noverlap",
            from_=10,
            to=500,
            steps=49,
            initial=self._initial_int("label_adjust_iterations", 50, minimum=10, maximum=500),
            help_text="O número máximo de vezes que o algoritmo vai buscar uma posição ideal que não fique sobreposta. Mais interações demandam tempo.",
        )

    def _build_export_section(self, parent) -> None:
        self._section_title(parent, "Exportacao")

        fmt_value = self._initial_str("typegraph", "png", allowed=list(self._FORMAT_LABELS.keys()))
        fmt_label = self._FORMAT_LABELS.get(fmt_value, "PNG")
        self.format_var = ctk.StringVar(value=fmt_label)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Formato", font=FONTS["body"]).pack(side="left")
        ctk.CTkOptionMenu(
            row,
            variable=self.format_var,
            values=list(self._FORMAT_VALUES.keys()),
            width=220,
        ).pack(side="right")

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="Largura", font=FONTS["body"]).pack(side="left")
        self.width_entry = ctk.CTkEntry(row, width=100)
        self.width_entry.insert(0, str(self._initial_int("width", 3200, minimum=400, maximum=5000)))
        self.width_entry.pack(side="left", padx=(8, 14))
        ctk.CTkLabel(row, text="Altura", font=FONTS["body"]).pack(side="left")
        self.height_entry = ctk.CTkEntry(row, width=100)
        self.height_entry.insert(0, str(self._initial_int("height", 2200, minimum=300, maximum=5000)))
        self.height_entry.pack(side="left", padx=(8, 0))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text="DPI", font=FONTS["body"]).pack(side="left")
        dpi = self._initial_int("dpi", 240, minimum=72, maximum=600)
        self.dpi_var = ctk.StringVar(value=str(dpi if dpi in {150, 200, 240, 300} else 240))
        ctk.CTkOptionMenu(row, variable=self.dpi_var, values=["150", "200", "240", "300"], width=220).pack(side="right")

        self.export_gexf_var = ctk.BooleanVar(value=self._initial_bool("export_gexf", True))
        ctk.CTkCheckBox(parent, text="Exportar GEXF (Gephi)", variable=self.export_gexf_var).pack(anchor="w", pady=2)
        self.export_net_var = ctk.BooleanVar(value=self._initial_bool("export_net", False))
        ctk.CTkCheckBox(parent, text="Exportar NET (Pajek/Gephi)", variable=self.export_net_var).pack(anchor="w", pady=2)
        self.export_csv_var = ctk.BooleanVar(value=self._initial_bool("export_csv", True))
        ctk.CTkCheckBox(parent, text="Exportar CSV (nos e arestas)", variable=self.export_csv_var).pack(anchor="w", pady=2)

    def _initial_int(
        self,
        key: str,
        default: int,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> int:
        raw = self._initial_params.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = int(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _initial_float(
        self,
        key: str,
        default: float,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        raw = self._initial_params.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _initial_bool(self, key: str, default: bool) -> bool:
        value = self._initial_params.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim"}
        return bool(value)

    def _initial_str(self, key: str, default: str, allowed: Optional[list] = None) -> str:
        value = str(self._initial_params.get(key, default) or default)
        if allowed and value not in allowed:
            return default
        return value

    def _default_int(
        self,
        key: str,
        default: int,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> int:
        raw = self._default_params.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = int(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _default_float(
        self,
        key: str,
        default: float,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        raw = self._default_params.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _default_bool(self, key: str, default: bool) -> bool:
        value = self._default_params.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim"}
        return bool(value)

    def _default_str(self, key: str, default: str, allowed: Optional[list] = None) -> str:
        value = str(self._default_params.get(key, default) or default)
        if allowed and value not in allowed:
            return default
        return value

    def _safe_entry_int(self, entry: ctk.CTkEntry, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(entry.get().strip())
        except Exception:
            value = int(default)
        return max(minimum, min(maximum, value))

    def _collect_params(self) -> Dict[str, Any]:
        layout = self._LAYOUT_VALUES.get(self.layout_var.get(), "forceatlas2")
        typegraph = self._FORMAT_VALUES.get(self.format_var.get(), "png")
        width = self._safe_entry_int(self.width_entry, 3200, 400, 5000)
        height = self._safe_entry_int(self.height_entry, 2200, 300, 5000)
        dpi = int(self.dpi_var.get())

        label_speed = round(float(self.label_adjust_speed_slider.get()), 2)
        label_iters = int(round(self.label_adjust_iter_slider.get()))

        return {
            "analysis_type": "network_text",
            "auto_tune": bool(self.auto_tune_var.get()),
            "min_freq": int(round(self.min_freq_slider.get())),
            "min_cooc": int(round(self.min_cooc_slider.get())),
            "max_nodes": int(round(self.max_nodes_slider.get())),
            "edge_threshold": int(round(self.edge_threshold_slider.get())),
            "arbremax": bool(self.arbremax_var.get()),
            "layout": layout,
            "layout_backend": "gephi_java",
            "strict_layout_backend": True,
            "community_resolution": round(float(self.resolution_slider.get()), 1),
            "node_size_metric": str(self.node_size_metric_var.get()),
            "label_size_metric": str(self.label_size_metric_var.get()),
            "show_halos": bool(self.show_halos_var.get()),
            "show_edges": bool(self.show_edges_var.get()),
            "edge_use_community_color": bool(self.edge_use_community_color_var.get()),
            "show_nodes": False,
            "normalize_centralities": bool(self.normalize_centralities_var.get()),
            "edge_alpha": round(float(self.edge_alpha_slider.get()), 2),
            "curved_edges": bool(self.curved_edges_var.get()),
            "typegraph": typegraph,
            "width": width,
            "height": height,
            "dpi": dpi,
            "export_gexf": bool(self.export_gexf_var.get()),
            "export_net": bool(self.export_net_var.get()),
            "export_csv": bool(self.export_csv_var.get()),
            "active_only": True,
            "stopword_policy": "aggressive_pt",
            "strict_stopword_filter": True,
            "fa2_iterations": int(round(self.iterations_slider.get())),
            "fa2_gravity": round(float(self.gravity_slider.get()), 1),
            "fa2_scaling": round(float(self.scaling_slider.get()), 1),
            "noverlap_enabled": bool(self.noverlap_var.get()),
            "noverlap_speed": label_speed,
            "noverlap_iterations": label_iters,
            "label_adjust": bool(self.label_adjust_var.get()),
            "label_adjust_speed": label_speed,
            "label_adjust_iterations": label_iters,
        }

    def _on_reset_defaults(self) -> None:
        """Restore controls to software defaults."""
        self.auto_tune_var.set(self._default_bool("auto_tune", True))
        self.min_freq_slider.set(self._default_int("min_freq", 3, minimum=1, maximum=30))
        self.min_cooc_slider.set(self._default_int("min_cooc", 2, minimum=1, maximum=30))
        self.max_nodes_slider.set(self._default_int("max_nodes", 300, minimum=50, maximum=1000))
        self.edge_threshold_slider.set(self._default_int("edge_threshold", 0, minimum=0, maximum=30))
        self.arbremax_var.set(self._default_bool("arbremax", False))

        layout_value = self._default_str("layout", "forceatlas2", allowed=list(self._LAYOUT_LABELS.keys()))
        self.layout_var.set(self._LAYOUT_LABELS.get(layout_value, "ForceAtlas2 (Gephi Java)"))
        self.resolution_slider.set(self._default_float("community_resolution", 1.0, minimum=0.1, maximum=3.0))

        node_metric = self._default_str("node_size_metric", "weighted_degree", allowed=self._METRICS)
        label_metric = self._default_str("label_size_metric", node_metric, allowed=self._METRICS)
        self.node_size_metric_var.set(node_metric)
        self.label_size_metric_var.set(label_metric)
        self.show_halos_var.set(self._default_bool("show_halos", False))
        self.show_edges_var.set(self._default_bool("show_edges", True))
        self.edge_use_community_color_var.set(self._default_bool("edge_use_community_color", True))
        self.normalize_centralities_var.set(self._default_bool("normalize_centralities", False))
        self.curved_edges_var.set(self._default_bool("curved_edges", False))
        self.edge_alpha_slider.set(self._default_float("edge_alpha", 0.26, minimum=0.0, maximum=0.5))

        self.iterations_slider.set(self._default_int("fa2_iterations", 3000, minimum=100, maximum=5000))
        self.gravity_slider.set(self._default_float("fa2_gravity", 0.8, minimum=0.1, maximum=10.0))
        self.scaling_slider.set(self._default_float("fa2_scaling", 50.0, minimum=1.0, maximum=150.0))
        self.noverlap_var.set(self._default_bool("noverlap_enabled", True))
        self.label_adjust_var.set(self._default_bool("label_adjust", True))
        self.label_adjust_speed_slider.set(self._default_float("label_adjust_speed", 3.0, minimum=0.1, maximum=8.0))
        self.label_adjust_iter_slider.set(self._default_int("label_adjust_iterations", 50, minimum=10, maximum=500))

        typegraph_value = self._default_str("typegraph", "png", allowed=list(self._FORMAT_LABELS.keys()))
        self.format_var.set(self._FORMAT_LABELS.get(typegraph_value, "PNG"))

        self.width_entry.delete(0, "end")
        self.width_entry.insert(0, str(self._default_int("width", 3200, minimum=400, maximum=5000)))
        self.height_entry.delete(0, "end")
        self.height_entry.insert(0, str(self._default_int("height", 2200, minimum=300, maximum=5000)))
        dpi = self._default_int("dpi", 240, minimum=72, maximum=600)
        self.dpi_var.set(str(dpi if dpi in {150, 200, 240, 300} else 240))

        self.export_gexf_var.set(self._default_bool("export_gexf", True))
        self.export_net_var.set(self._default_bool("export_net", False))
        self.export_csv_var.set(self._default_bool("export_csv", True))

    def _on_run_click(self) -> None:
        params = self._collect_params()
        self._result = params
        self.destroy()
        if self.on_run:
            self.on_run(params)

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    def destroy(self):
        """Destroy dialog and cleanup CTkOptionMenu dropdown menus."""
        if self._is_destroying:
            return
        self._is_destroying = True
        try:
            cleanup_widget_menus(self)
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            super().destroy()
        finally:
            self._is_destroying = False

    def get_result(self) -> Optional[Dict[str, Any]]:
        """Wait for dialog close and return selected parameters."""
        self.wait_window()
        return self._result
