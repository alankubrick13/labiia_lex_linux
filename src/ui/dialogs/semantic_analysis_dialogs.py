"""
Dialogos base para a Suite Semantica ativa.

Inclui as janelas de configuracao para YAKE, LDA, Heatmap Associativo,
Mapa Tematico e CHD Tematico.

Estes dialogos apenas coletam parametros da UI e devolvem um `dict`,
sem nenhuma logica de negocio acoplada.
"""

from typing import Any, Dict, Optional

import customtkinter as ctk

from .analysis_dialog import BaseAnalysisDialog
from ..styles import FONTS, get_themed_color


# ---------------------------------------------------------------------------
# YAKE
# ---------------------------------------------------------------------------

class YAKEDialog(BaseAnalysisDialog):
    """Dialogo para extracao de palavras-chave (YAKE)."""
    ANALYSIS_TYPE = "yake"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Palavras-Chave (YAKE)",
            width=400,
            height=360,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(title_frame, text="Extração YAKE", font=FONTS['title']).pack(side="left")

        # Frequencia minima
        freq_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        freq_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(freq_frame, text="Frequência mínima:", font=FONTS['body']).pack(side="left")
        self.create_help_icon(freq_frame,
            "Número mínimo de vezes que uma frase deve aparecer no corpus para ser incluída no resultado.\n"
            "Valor 1 inclui todas as frases extraídas.\n"
            "Aumente para filtrar termos raros."
        ).pack(side="left", padx=(4, 0))
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 1, minimum=1))
        ctk.CTkEntry(freq_frame, textvariable=self.min_freq_var, width=60).pack(side="right")

        # Range de tokens
        range_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        range_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(range_frame, text="Tokens por frase:", font=FONTS['body']).pack(side="left")
        self.create_help_icon(range_frame,
            "Tamanho das frases-chave extraídas, em número de palavras.\n"
            "Ex: '1 a 4' extrai desde palavras únicas até frases de 4 palavras.\n"
            "Frases maiores capturam conceitos mais específicos."
        ).pack(side="left", padx=(4, 0))
        self.max_tok_var = ctk.IntVar(value=self._initial_int("max_tokens", 4, minimum=1))
        ctk.CTkEntry(range_frame, textvariable=self.max_tok_var, width=50).pack(side="right")
        ctk.CTkLabel(range_frame, text=" a ").pack(side="right")
        self.min_tok_var = ctk.IntVar(value=self._initial_int("min_tokens", 1, minimum=1))
        ctk.CTkEntry(range_frame, textvariable=self.min_tok_var, width=50).pack(side="right")

        # Top N
        top_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        top_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(top_frame, text="Ranking (Top N):", font=FONTS['body']).pack(side="left")
        self.create_help_icon(top_frame,
            "Quantidade máxima de palavras-chave a retornar no resultado final.\n"
            "O YAKE extrai internamente mais candidatos e seleciona os N mais relevantes.\n"
            "Valores entre 20 e 50 são adequados para a maioria dos corpus."
        ).pack(side="left", padx=(4, 0))
        self.top_n_var = ctk.IntVar(value=self._initial_int("top_n", 50, minimum=5))
        ctk.CTkEntry(top_frame, textvariable=self.top_n_var, width=60).pack(side="right")

        # Deduplicacao
        dedup_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        dedup_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(dedup_frame, text="Deduplicação (0–1):", font=FONTS['body']).pack(side="left")
        self.create_help_icon(dedup_frame,
            "Controla a remoção de frases similares no resultado.\n"
            "Valores menores (ex: 0.3) são mais agressivos: eliminam mais variantes.\n"
            "Valores maiores (ex: 0.9) são permissivos: mantêm frases parecidas.\n"
            "Recomendado: 0.7 para equilíbrio entre diversidade e precisão."
        ).pack(side="left", padx=(4, 0))
        self.dedup_var = ctk.DoubleVar(value=self._initial_float("dedup_threshold", 0.7))
        ctk.CTkEntry(dedup_frame, textvariable=self.dedup_var, width=60).pack(side="right")

    def _initial_float(self, key: str, default: float) -> float:
        """Obtem float de initial_params ou retorna default."""
        if self._initial_params and key in self._initial_params:
            try:
                return float(self._initial_params[key])
            except (ValueError, TypeError):
                pass
        return default

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": self.ANALYSIS_TYPE,
            "min_freq": self.min_freq_var.get(),
            "min_tokens": self.min_tok_var.get(),
            "max_tokens": self.max_tok_var.get(),
            "top_n": self.top_n_var.get(),
            "dedup_threshold": self.dedup_var.get(),
        }


# ---------------------------------------------------------------------------
# LDA
# ---------------------------------------------------------------------------

class LDADialog(BaseAnalysisDialog):
    """Dialogo para modelagem de topicos (LDA)."""
    ANALYSIS_TYPE = "lda"
    HELP_TEXTS = {
        "k": "Quantidade de tópicos que o modelo tentará encontrar. Use valores menores para leitura mais geral e valores maiores para separar temas próximos.",
        "method": "VEM costuma ser mais rápido. Gibbs pode ser mais estável em alguns corpus, mas normalmente demora mais.",
        "seed": "Número usado para repetir o mesmo sorteio interno do LDA. Mantendo a mesma seed, o resultado tende a ser reproduzível.",
        "min_freq": "Frequência mínima para uma forma entrar no vocabulário do LDA. Aumentar remove termos raros e deixa o modelo mais leve.",
        "max_features": "Limite máximo de formas usadas no modelo. Reduzir acelera a análise e evita vocabulário excessivamente disperso.",
        "n_iter": "Número de iterações do backend Python/fallback. Mais iterações podem refinar o modelo, mas aumentam o tempo.",
        "gibbs_burnin": "Rodadas iniciais descartadas no método Gibbs para estabilizar a amostragem antes de registrar resultados.",
        "gibbs_iter": "Total de iterações usadas pelo Gibbs. Valores maiores podem melhorar estabilidade, com custo de tempo.",
        "gibbs_thin": "Intervalo para guardar amostras no Gibbs. Ajuda a reduzir dependência entre amostras sucessivas.",
        "enable_k_tuning": "Roda modelos com diferentes valores de K e exporta sinais de qualidade. Não escolhe automaticamente por você.",
        "k_range": "Faixa de valores de K testados no tuning. Use uma faixa curta para evitar demora desnecessária.",
        "use_lemmas": "Usa lemas quando disponíveis, agrupando flexões da mesma palavra. Desmarque para trabalhar com formas exatamente como aparecem.",
        "enable_advanced_diagnostics": "Gera diagnósticos visuais extras sobre qualidade, tópicos pequenos, mistura de documentos e estabilidade.",
        "stability_n_seeds": "Quantidade de seeds usadas no teste de estabilidade. Mais seeds dão mais evidência, mas demoram mais.",
    }

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Modelagem de Tópicos (LDA)",
            width=460,
            height=520,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(title_frame, text="Modelagem de Tópicos (LDA)", font=FONTS['title']).pack(side="left")

        # K (número de tópicos)
        topic_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        topic_frame.pack(fill="x", pady=5)
        self._pack_label_with_help(topic_frame, "Número de Tópicos:", "k")
        initial_k = self._initial_int("k", self._initial_int("n_topics", 6, minimum=1), minimum=1)
        self.k_var = ctk.IntVar(value=initial_k)
        ctk.CTkEntry(topic_frame, textvariable=self.k_var, width=60).pack(side="right")

        # Método de inferência
        method_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        method_frame.pack(fill="x", pady=5)
        self._pack_label_with_help(method_frame, "Método:", "method")
        initial_method = str(self._initial_str("method", "VEM")).upper()
        if initial_method not in {"VEM", "GIBBS"}:
            initial_method = "VEM"
        self.method_var = ctk.StringVar(value=initial_method)
        selector = ctk.CTkSegmentedButton(
            method_frame,
            values=["VEM", "Gibbs"],
            variable=self.method_var,
            command=lambda _: self._update_gibbs_section_state(),
            width=180,
        )
        selector.pack(side="right")
        selector.set("Gibbs" if initial_method == "GIBBS" else "VEM")

        # Seed
        seed_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        seed_frame.pack(fill="x", pady=5)
        self._pack_label_with_help(seed_frame, "Seed:", "seed")
        self.seed_var = ctk.IntVar(value=self._initial_int("seed", 42, minimum=1))
        ctk.CTkEntry(seed_frame, textvariable=self.seed_var, width=80).pack(side="right")

        # Frequência mínima
        freq_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        freq_frame.pack(fill="x", pady=5)
        self._pack_label_with_help(freq_frame, "Frequência mínima:", "min_freq")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 2, minimum=1))
        ctk.CTkEntry(freq_frame, textvariable=self.min_freq_var, width=60).pack(side="right")

        # Max Features
        feat_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        feat_frame.pack(fill="x", pady=5)
        self._pack_label_with_help(feat_frame, "Máximo de formas (features):", "max_features")
        self.max_feat_var = ctk.IntVar(value=self._initial_int("max_features", 2000, minimum=10))
        ctk.CTkEntry(feat_frame, textvariable=self.max_feat_var, width=60).pack(side="right")

        # Iterações gerais (compat)
        iter_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        iter_frame.pack(fill="x", pady=5)
        self._pack_label_with_help(iter_frame, "Iterações:", "n_iter")
        self.n_iter_var = ctk.IntVar(value=self._initial_int("n_iter", 500, minimum=50))
        ctk.CTkEntry(iter_frame, textvariable=self.n_iter_var, width=80).pack(side="right")

        # Controles Gibbs
        self.gibbs_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        self.gibbs_frame.pack(fill="x", pady=(8, 5))

        burnin_row = ctk.CTkFrame(self.gibbs_frame, fg_color="transparent")
        burnin_row.pack(fill="x", pady=2)
        self._pack_label_with_help(burnin_row, "Gibbs burn-in:", "gibbs_burnin")
        self.gibbs_burnin_var = ctk.IntVar(value=self._initial_int("gibbs_burnin", 1000, minimum=0))
        ctk.CTkEntry(burnin_row, textvariable=self.gibbs_burnin_var, width=80).pack(side="right")

        gibbs_iter_row = ctk.CTkFrame(self.gibbs_frame, fg_color="transparent")
        gibbs_iter_row.pack(fill="x", pady=2)
        self._pack_label_with_help(gibbs_iter_row, "Gibbs iter:", "gibbs_iter")
        self.gibbs_iter_var = ctk.IntVar(value=self._initial_int("gibbs_iter", 1000, minimum=50))
        ctk.CTkEntry(gibbs_iter_row, textvariable=self.gibbs_iter_var, width=80).pack(side="right")

        gibbs_thin_row = ctk.CTkFrame(self.gibbs_frame, fg_color="transparent")
        gibbs_thin_row.pack(fill="x", pady=2)
        self._pack_label_with_help(gibbs_thin_row, "Gibbs thin:", "gibbs_thin")
        self.gibbs_thin_var = ctk.IntVar(value=self._initial_int("gibbs_thin", 100, minimum=1))
        ctk.CTkEntry(gibbs_thin_row, textvariable=self.gibbs_thin_var, width=80).pack(side="right")

        # Tuning de k
        tuning_row = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        tuning_row.pack(fill="x", pady=(8, 5))
        self.enable_k_tuning_var = ctk.BooleanVar(value=self._initial_bool("enable_k_tuning", False))
        ctk.CTkCheckBox(
            tuning_row,
            text="Executar tuning de k (perplexity)",
            variable=self.enable_k_tuning_var,
            font=FONTS["body"],
            command=self._update_tuning_section_state,
        ).pack(side="left")
        self.create_help_icon(tuning_row, self.HELP_TEXTS["enable_k_tuning"]).pack(side="left", padx=(6, 0))

        self.tuning_range_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        self.tuning_range_frame.pack(fill="x", pady=2)
        self._pack_label_with_help(self.tuning_range_frame, "Faixa k:", "k_range")
        self.k_min_var = ctk.IntVar(value=self._initial_int("k_min", 2, minimum=2))
        self.k_max_var = ctk.IntVar(value=self._initial_int("k_max", 12, minimum=2))
        ctk.CTkEntry(self.tuning_range_frame, textvariable=self.k_min_var, width=56).pack(side="right")
        ctk.CTkLabel(self.tuning_range_frame, text=" até ").pack(side="right")
        ctk.CTkEntry(self.tuning_range_frame, textvariable=self.k_max_var, width=56).pack(side="right")

        # Use Lemmas
        lemmas_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        lemmas_frame.pack(fill="x", pady=5)
        self.use_lemmas_var = ctk.BooleanVar(value=self._initial_bool("use_lemmas", True))
        ctk.CTkCheckBox(lemmas_frame, text="Usar lemas em vez de formas brutas", 
                        variable=self.use_lemmas_var, font=FONTS['body']).pack(side="left")
        self.create_help_icon(lemmas_frame, self.HELP_TEXTS["use_lemmas"]).pack(side="left", padx=(6, 0))

        diagnostics_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        diagnostics_frame.pack(fill="x", pady=(8, 5))
        self.enable_advanced_diagnostics_var = ctk.BooleanVar(
            value=self._initial_bool("enable_advanced_diagnostics", False)
        )
        ctk.CTkCheckBox(
            diagnostics_frame,
            text="Diagnóstico avançado (K e estabilidade)",
            variable=self.enable_advanced_diagnostics_var,
            font=FONTS["body"],
        ).pack(side="left")
        self.create_help_icon(diagnostics_frame, self.HELP_TEXTS["enable_advanced_diagnostics"]).pack(side="left", padx=(6, 0))
        self.stability_n_seeds_var = ctk.IntVar(value=self._initial_int("stability_n_seeds", 3, minimum=1))
        ctk.CTkEntry(diagnostics_frame, textvariable=self.stability_n_seeds_var, width=52).pack(side="right")
        ctk.CTkLabel(diagnostics_frame, text="Seeds:", font=FONTS["body"]).pack(side="right", padx=(0, 6))
        self.create_help_icon(diagnostics_frame, self.HELP_TEXTS["stability_n_seeds"]).pack(side="right", padx=(0, 6))

        self._update_gibbs_section_state()
        self._update_tuning_section_state()

    def _pack_label_with_help(self, parent, label: str, help_key: str) -> None:
        label_frame = ctk.CTkFrame(parent, fg_color="transparent")
        label_frame.pack(side="left")
        ctk.CTkLabel(label_frame, text=label, font=FONTS["body"]).pack(side="left")
        self.create_help_icon(label_frame, self.HELP_TEXTS[help_key]).pack(side="left", padx=(6, 0))

    def _initial_str(self, key: str, default: str) -> str:
        if self._initial_params and key in self._initial_params:
            try:
                value = str(self._initial_params[key]).strip()
                if value:
                    return value
            except Exception:
                pass
        return default

    def _update_gibbs_section_state(self) -> None:
        method = str(self.method_var.get() or "VEM").strip().upper()
        state = "normal" if method == "GIBBS" else "disabled"
        for child in self.gibbs_frame.winfo_children():
            for sub in child.winfo_children():
                if isinstance(sub, ctk.CTkEntry):
                    sub.configure(state=state)

    def _update_tuning_section_state(self) -> None:
        state = "normal" if bool(self.enable_k_tuning_var.get()) else "disabled"
        for child in self.tuning_range_frame.winfo_children():
            if isinstance(child, ctk.CTkEntry):
                child.configure(state=state)

    def _build_result(self) -> Dict[str, Any]:
        method = str(self.method_var.get() or "VEM").strip().upper()
        if method not in {"VEM", "GIBBS"}:
            method = "VEM"
        return {
            "analysis_type": self.ANALYSIS_TYPE,
            "k": self.k_var.get(),
            "n_topics": self.k_var.get(),  # compatibilidade com estado antigo
            "seed": self.seed_var.get(),
            "method": method,
            "min_freq": self.min_freq_var.get(),
            "max_features": self.max_feat_var.get(),
            "n_iter": self.n_iter_var.get(),
            "gibbs_burnin": self.gibbs_burnin_var.get(),
            "gibbs_iter": self.gibbs_iter_var.get(),
            "gibbs_thin": self.gibbs_thin_var.get(),
            "enable_k_tuning": self.enable_k_tuning_var.get(),
            "k_min": self.k_min_var.get(),
            "k_max": self.k_max_var.get(),
            "use_lemmas": self.use_lemmas_var.get(),
            "enable_advanced_diagnostics": self.enable_advanced_diagnostics_var.get(),
            "stability_n_seeds": self.stability_n_seeds_var.get(),
        }


# ---------------------------------------------------------------------------
# Heatmap Associativo
# ---------------------------------------------------------------------------

class AssociativeHeatmapDialog(BaseAnalysisDialog):
    """Dialogo para matriz associativa."""
    ANALYSIS_TYPE = "associative_heatmap"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Heatmap Associativo",
            width=400,
            height=300,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(title_frame, text="Heatmap Associativo", font=FONTS['title']).pack(side="left")

        # Range Frequency
        freq_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        freq_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(freq_frame, text="Frequência mínima:", font=FONTS['body']).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 2, minimum=1))
        ctk.CTkEntry(freq_frame, textvariable=self.min_freq_var, width=60).pack(side="right")

        # Max Features
        feat_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        feat_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(feat_frame, text="Top features:", font=FONTS['body']).pack(side="left")
        self.max_feat_var = ctk.IntVar(value=self._initial_int("max_features", 200, minimum=10))
        ctk.CTkEntry(feat_frame, textvariable=self.max_feat_var, width=60).pack(side="right")

        # Top N Pairs
        top_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        top_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(top_frame, text="Top pares a exportar:", font=FONTS['body']).pack(side="left")
        self.top_pairs_var = ctk.IntVar(value=self._initial_int("top_n_pairs", 100, minimum=5))
        ctk.CTkEntry(top_frame, textvariable=self.top_pairs_var, width=60).pack(side="right")

        # Alpha (Smoothing)
        alpha_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        alpha_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(alpha_frame, text="PPMI Alpha (smoothing):", font=FONTS['body']).pack(side="left")
        self.alpha_var = ctk.DoubleVar(value=self._initial_float("alpha", 0.75, minimum=0.1, maximum=1.0))
        ctk.CTkEntry(alpha_frame, textvariable=self.alpha_var, width=60).pack(side="right")

        # Lemmas
        lemmas_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        lemmas_frame.pack(fill="x", pady=5)
        self.use_lemmas_var = ctk.BooleanVar(value=self._initial_bool("use_lemmas", True))
        ctk.CTkCheckBox(lemmas_frame, text="Usar lemas em vez de formas brutas", 
                        variable=self.use_lemmas_var, font=FONTS['body']).pack(side="left")

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": self.ANALYSIS_TYPE,
            "min_freq": self.min_freq_var.get(),
            "max_features": self.max_feat_var.get(),
            "top_n_pairs": self.top_pairs_var.get(),
            "alpha": self.alpha_var.get(),
            "use_lemmas": self.use_lemmas_var.get(),
        }


# ---------------------------------------------------------------------------
# Mapa Tematico
# ---------------------------------------------------------------------------

class ThematicMapDialog(BaseAnalysisDialog):
    """Dialogo para rede de expressoes, comunidades e mapa estrategico."""
    ANALYSIS_TYPE = "thematic_map"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Mapa Temático Estratégico",
            width=430,
            height=390,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(title_frame, text="Mapa Temático Estratégico", font=FONTS['title']).pack(side="left")

        freq_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        freq_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(freq_frame, text="Frequência mínima:", font=FONTS['body']).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 2, minimum=1))
        ctk.CTkEntry(freq_frame, textvariable=self.min_freq_var, width=60).pack(side="right")

        cooc_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        cooc_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(cooc_frame, text="Coocorrência mínima:", font=FONTS['body']).pack(side="left")
        self.min_cooc_var = ctk.IntVar(value=self._initial_int("min_cooc", 2, minimum=1))
        ctk.CTkEntry(cooc_frame, textvariable=self.min_cooc_var, width=60).pack(side="right")

        edge_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        edge_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(edge_frame, text="Máximo de arestas:", font=FONTS['body']).pack(side="left")
        self.top_edges_var = ctk.IntVar(value=self._initial_int("top_edges", 160, minimum=10))
        ctk.CTkEntry(edge_frame, textvariable=self.top_edges_var, width=60).pack(side="right")

        nodes_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        nodes_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(nodes_frame, text="Máximo de nós:", font=FONTS['body']).pack(side="left")
        self.max_nodes_var = ctk.IntVar(value=self._initial_int("max_nodes", 120, minimum=10))
        ctk.CTkEntry(nodes_frame, textvariable=self.max_nodes_var, width=60).pack(side="right")

        feat_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        feat_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(feat_frame, text="Vocabulário máximo:", font=FONTS['body']).pack(side="left")
        self.max_feat_var = ctk.IntVar(value=self._initial_int("max_features", 300, minimum=20))
        ctk.CTkEntry(feat_frame, textvariable=self.max_feat_var, width=60).pack(side="right")

        lemmas_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        lemmas_frame.pack(fill="x", pady=5)
        self.use_lemmas_var = ctk.BooleanVar(value=self._initial_bool("use_lemmas", True))
        ctk.CTkCheckBox(lemmas_frame, text="Usar lemas em vez de formas brutas",
                        variable=self.use_lemmas_var, font=FONTS['body']).pack(side="left")

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": self.ANALYSIS_TYPE,
            "min_freq": self.min_freq_var.get(),
            "min_cooc": self.min_cooc_var.get(),
            "top_edges": self.top_edges_var.get(),
            "max_nodes": self.max_nodes_var.get(),
            "max_features": self.max_feat_var.get(),
            "use_lemmas": self.use_lemmas_var.get(),
        }


# ---------------------------------------------------------------------------
# CHD Tematico
# ---------------------------------------------------------------------------

class ThematicCHDDialog(BaseAnalysisDialog):
    """Dialogo para CHD com topicos."""
    ANALYSIS_TYPE = "thematic_chd"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "CHD Temático",
            width=400,
            height=300,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(title_frame, text="CHD Temático", font=FONTS['title']).pack(side="left")

        topic_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        topic_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(topic_frame, text="Número de Tópicos (K):", font=FONTS['body']).pack(side="left")
        self.topics_var = ctk.IntVar(value=self._initial_int("n_topics", 5, minimum=2))
        ctk.CTkEntry(topic_frame, textvariable=self.topics_var, width=60).pack(side="right")

        freq_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        freq_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(freq_frame, text="Frequência mínima das palavras:", font=FONTS['body']).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 2, minimum=1))
        ctk.CTkEntry(freq_frame, textvariable=self.min_freq_var, width=60).pack(side="right")

        feat_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        feat_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(feat_frame, text="Vocabulário máximo (0=ilimitado):", font=FONTS['body']).pack(side="left")
        self.max_feat_var = ctk.IntVar(value=self._initial_int("max_features", 2000, minimum=0))
        ctk.CTkEntry(feat_frame, textvariable=self.max_feat_var, width=60).pack(side="right")

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": self.ANALYSIS_TYPE,
            "n_topics": self.topics_var.get(),
            "min_freq": self.min_freq_var.get(),
            "max_features": self.max_feat_var.get(),
        }
