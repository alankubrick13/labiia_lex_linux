"""Textual network analysis engine with strict Gephi-compatible layout backend."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
from scipy import sparse

from ..core.text_processor import TextProcessor, TextProcessorError
from .community_detection import detect_louvain_partition
from .layout_backends import (
    GephiJavaBackendError,
    GephiJavaBackendResult,
    run_layout as run_gephi_java_layout,
)

log = logging.getLogger(__name__)


@dataclass
class NetworkTextAnalysisResult:
    """Full output payload for textual network analysis."""

    n_nodes: int = 0
    n_edges: int = 0
    graph_type: str = "undirected"

    average_degree: float = 0.0
    density: float = 0.0
    diameter: int = 0
    modularity_score: float = 0.0
    n_communities: int = 0

    nodes_table: List[Dict[str, Any]] = field(default_factory=list)
    edges_table: List[Dict[str, Any]] = field(default_factory=list)

    graph_image_path: Optional[Path] = None
    graph_svg_path: Optional[Path] = None
    nodes_csv_path: Optional[Path] = None
    edges_csv_path: Optional[Path] = None
    gexf_path: Optional[Path] = None
    net_path: Optional[Path] = None
    report_data: Optional[Dict[str, Any]] = None

    layout_algorithm: str = "forceatlas2"
    layout_params: Dict[str, Any] = field(default_factory=dict)
    layout_backend_used: str = "unknown"
    diagnostics_path: Optional[Path] = None


class NetworkTextAnalysisError(Exception):
    """Friendly exception for textual network analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(
            f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        )


class NetworkTextAnalysis:
    """
    Textual network analysis engine.

    Pipeline:
    1. Build graph from co-occurrence matrix
    2. Apply graph filters
    3. Compute centrality metrics
    4. Detect communities (Louvain)
    5. Compute layout (strict backend policy)
    6. Render and export outputs
    """

    DEFAULT_PARAMS = {
        "min_freq": 3,
        "window_size": 5,
        "min_cooc": 2,
        "max_nodes": 450,
        "auto_tune": True,
        "layout": "forceatlas2",
        "layout_backend": "gephi_java",
        "strict_layout_backend": True,
        "community_resolution": 1.0,
        "node_size_metric": "weighted_degree",
        "label_size_metric": "weighted_degree",
        "use_edge_weights": True,
        "arbremax": False,
        "edge_threshold": 0,
        "edge_weight_quantile": 0.0,
        "candidate_min_cooc": 1.0,
        "normalize_centralities": False,
        "width": 3200,
        "height": 2200,
        "dpi": 240,
        "view_trim_quantile": 0.05,
        "view_pad_ratio_initial": 0.06,
        "view_pad_ratio_final": 0.03,
        "typegraph": "png",
        "background": "white",
        "show_edges": True,
        "show_halos": True,
        "show_nodes": False,
        "curved_edges": False,
        "edge_alpha": 0.26,
        "edge_min_alpha": 0.13,
        "edge_color": "#778391",
        "edge_intercommunity_color": "#66727F",
        "edge_use_community_color": True,
        "edge_min_width": 0.34,
        "edge_max_width": 1.40,
        "auto_reconnect_components": True,
        "auto_reconnect_max_bridges": 16,
        "peripheral_enrichment": True,
        "peripheral_min_degree": 2,
        "peripheral_quantile": 0.55,
        "peripheral_boost_max_added": 180,
        "font_family": "sans-serif",
        "node_min_size": 10,
        "node_max_size": 120,
        "label_min_size": 5.5,
        "label_max_size": 19.0,
        "label_size_boost": 3.0,
        "label_size_gamma": 1.2,
        "label_color": "#1B1F23",
        "export_gexf": True,
        "export_csv": True,
        "export_net": False,
        "label_adjust": True,
        "label_threshold": 0.08,
        "label_density": 0.7,
        "label_max_count": 200,
        "label_hide_overlap": True,
        "label_min_keep": 8,
        "label_overlap_target": 0.16,
        "label_anchor_lines": True,
        "label_anchor_line_alpha": 0.38,
        "label_anchor_line_width": 0.62,
        "render_quality_auto": True,
        "render_quality_passes": 2,
        "active_only": True,
        "stopword_policy": "aggressive_pt",
        "strict_stopword_filter": True,
        # ForceAtlas2 — Layout compacto estilo Gephi
        # scaling baixo = nos ficam proximos; gravity alto = puxa para centro
        "fa2_scaling": 8.0,
        "fa2_gravity": 1.5,
        "fa2_iterations": 6000,
        "fa2_edge_weight_influence": 0.5,
        "fa2_jitter_tolerance": 1.0,
        "fa2_barnes_hut_theta": 1.2,
        "fa2_barnes_hut_optimize": True,
        "fa2_strong_gravity_mode": True,
        "layout_timeout_sec": 360,
        # Noverlap — Espacamento minimo, so evitar sobreposicao
        "noverlap_enabled": True,
        "noverlap_speed": 3.0,
        "noverlap_ratio": 1.1,
        "noverlap_margin": 3.0,
        "noverlap_iterations": 100,
        # Label Adjust - Previne sobreposicao de labels
        "gephi_fidelity": True,
        "gephi_quality": False,
        "gephi_node_reflow": False,
        "label_reposition_on_overlap": True,
        "label_adjust_speed": 0.9,
        "label_adjust_margin": 3.0,
        "label_adjust_iterations": 1000,
        "seed": 42,
    }

    def __init__(self, corpus, output_dir, r_executor=None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.r_executor = r_executor
        self.graph: Optional[nx.Graph] = None
        self.positions: Optional[Dict[Any, Tuple[float, float]]] = None

        self._layout_backend_used: str = "unknown"
        self._layout_diagnostics: Dict[str, Any] = {}
        self._layout_diag_path: Optional[Path] = None
        self._top_terms_before_filter: List[Tuple[str, int]] = []
        self._top_terms_after_filter: List[Tuple[str, int]] = []
        self._network_diagnostics_path: Optional[Path] = None
        self._auto_tuning_notes: Dict[str, Any] = {}
        self._candidate_graph: Optional[nx.Graph] = None

    def run(self, params: Optional[Dict[str, Any]] = None) -> NetworkTextAnalysisResult:
        """Execute full textual network analysis pipeline."""
        p = {**self.DEFAULT_PARAMS, **(params or {})}
        p = self._apply_auto_selection(p)

        self._build_graph(p)
        self._filter_graph(p)

        if self.graph is None or self.graph.number_of_nodes() <= 0:
            raise NetworkTextAnalysisError(
                what="A rede textual ficou vazia apos os filtros.",
                why="Nao houve termos/arestas suficientes para formar um grafo valido.",
                how="Reduza min_freq/min_cooc, diminua edge_threshold ou desative arbremax.",
            )

        metrics = self._compute_metrics(p)
        communities = self._detect_communities(p)
        self.positions = self._compute_layout(p)
        nodes_table = self._build_nodes_table(metrics, communities)
        edges_table = self._build_edges_table()
        image_path, svg_path = self._render(p, nodes_table)
        nodes_csv, edges_csv, gexf_path, net_path = self._export(
            p,
            nodes_table,
            edges_table,
        )
        diagnostics_path = self._write_network_diagnostics(metrics, communities, p)

        density = nx.density(self.graph) if self.graph.number_of_nodes() > 1 else 0.0
        result = NetworkTextAnalysisResult(
            n_nodes=self.graph.number_of_nodes(),
            n_edges=self.graph.number_of_edges(),
            average_degree=float(metrics.get("average_degree", 0.0)),
            density=float(density),
            diameter=int(metrics.get("diameter", 0) or 0),
            modularity_score=float(communities.get("modularity", 0.0) or 0.0),
            n_communities=int(communities.get("n_communities", 0) or 0),
            nodes_table=nodes_table,
            edges_table=edges_table,
            graph_image_path=image_path,
            graph_svg_path=svg_path,
            nodes_csv_path=nodes_csv,
            edges_csv_path=edges_csv,
            gexf_path=gexf_path,
            net_path=net_path,
            layout_algorithm="forceatlas2",
            layout_params=dict(p),
            layout_backend_used=self._layout_backend_used,
            diagnostics_path=diagnostics_path,
            report_data=self._build_report_data(metrics, communities, p, diagnostics_path),
        )
        return result

    def _build_graph(self, params: Dict[str, Any]) -> None:
        """Build NetworkX graph from corpus co-occurrence matrix."""
        tp = TextProcessor(self.corpus)
        min_freq = max(1, int(params.get("min_freq", 3)))
        window_size = max(1, int(params.get("window_size", 5)))
        active_only = bool(params.get("active_only", True))
        stopword_policy = str(params.get("stopword_policy", "aggressive_pt"))
        strict_stopword_filter = bool(params.get("strict_stopword_filter", True))

        self._top_terms_before_filter = tp.get_word_frequencies(
            use_lemmas=False,
            active_only=False,
            exclude_stopwords=False,
        )[:40]

        try:
            cooc_matrix = tp.build_cooccurrence_matrix(
                window_size=window_size,
                min_freq=min_freq,
                active_only=active_only,
                stopword_policy=stopword_policy,
                strict_stopword_filter=strict_stopword_filter,
                prefer_portuguese_br=True,
            )
        except TextProcessorError as exc:
            # Robust fallback for legacy corpora where lexicon is not attached.
            if (
                strict_stopword_filter
                and self._is_missing_lexicon_stopword_error(exc)
            ):
                log.warning(
                    "Strict stopword filter failed due missing lexicon; "
                    "retrying with strict_stopword_filter=False."
                )
                params["strict_stopword_filter"] = False
                self._auto_tuning_notes["stopword_fallback"] = {
                    "applied": True,
                    "reason": "lexicon_missing_for_strict_stopword_filter",
                    "stopword_policy": str(stopword_policy),
                    "strict_stopword_filter_requested": True,
                    "strict_stopword_filter_effective": False,
                }
                try:
                    cooc_matrix = tp.build_cooccurrence_matrix(
                        window_size=window_size,
                        min_freq=min_freq,
                        active_only=active_only,
                        stopword_policy=stopword_policy,
                        strict_stopword_filter=False,
                        prefer_portuguese_br=True,
                    )
                except TextProcessorError as retry_exc:
                    raise NetworkTextAnalysisError(
                        what="Nao foi possivel construir a matriz de coocorrencia.",
                        why=str(retry_exc),
                        how="Verifique o corpus e a configuracao de stopwords/frequencia minima.",
                    ) from retry_exc
            else:
                raise NetworkTextAnalysisError(
                    what="Nao foi possivel construir a matriz de coocorrencia.",
                    why=str(exc),
                    how="Verifique o corpus e a configuracao de stopwords/frequencia minima.",
                ) from exc

        self._top_terms_after_filter = sorted(
            [
                (
                    token,
                    int(getattr(self.corpus.formes.get(token), "freq", 0)),
                )
                for token in tp.vocabulary
            ],
            key=lambda item: (-item[1], item[0]),
        )[:40]

        vocabulary = list(tp.vocabulary)
        if cooc_matrix.shape[0] == 0 or not vocabulary:
            self.graph = nx.Graph()
            self._candidate_graph = nx.Graph()
            return

        graph = nx.Graph()
        candidate_graph = nx.Graph()
        upper = sparse.triu(cooc_matrix).tocoo()
        min_cooc = float(params.get("min_cooc", 1))
        candidate_min_cooc = float(params.get("candidate_min_cooc", 1.0) or 1.0)
        candidate_min_cooc = max(1.0, min(candidate_min_cooc, min_cooc))
        for i, j, value in zip(upper.row, upper.col, upper.data):
            if i == j:
                continue
            weight = float(value)
            if i >= len(vocabulary) or j >= len(vocabulary):
                continue
            u = vocabulary[int(i)]
            v = vocabulary[int(j)]
            if weight >= candidate_min_cooc:
                candidate_graph.add_edge(u, v, weight=weight)
            if weight >= min_cooc:
                graph.add_edge(u, v, weight=weight)

        freq = np.asarray(cooc_matrix.sum(axis=1)).flatten()
        for idx, word in enumerate(vocabulary):
            if word in graph:
                graph.nodes[word]["frequency"] = int(freq[idx]) if idx < len(freq) else 0
            if word in candidate_graph:
                candidate_graph.nodes[word]["frequency"] = int(freq[idx]) if idx < len(freq) else 0

        max_nodes = max(10, int(params.get("max_nodes", 500)))
        if graph.number_of_nodes() > max_nodes:
            ranked = sorted(
                graph.nodes(),
                key=lambda node: float(graph.degree(node, weight="weight")),
                reverse=True,
            )
            keep = set(ranked[:max_nodes])
            remove = [node for node in graph.nodes() if node not in keep]
            graph.remove_nodes_from(remove)
            candidate_graph.remove_nodes_from(
                [node for node in candidate_graph.nodes() if node not in keep]
            )

        isolates = list(nx.isolates(graph))
        if isolates:
            graph.remove_nodes_from(isolates)
        candidate_graph.remove_nodes_from(
            [node for node in candidate_graph.nodes() if node not in graph]
        )

        self.graph = graph
        self._candidate_graph = candidate_graph
        log.info(
            "Text network built: %d nodes, %d edges",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )

    @staticmethod
    def _is_missing_lexicon_stopword_error(exc: TextProcessorError) -> bool:
        text = str(exc).strip().lower()
        return (
            "lexico nao esta carregado" in text
            and "strict_stopword_filter=true" in text
        )

    def _filter_graph(self, params: Dict[str, Any]) -> None:
        """Apply graph filters: edge threshold and optional maximum spanning tree."""
        if self.graph is None:
            return

        graph = self.graph
        raw_graph = (
            self._candidate_graph.copy()
            if self._candidate_graph is not None
            else graph.copy()
        )
        if raw_graph.number_of_nodes() > 0:
            raw_graph = raw_graph.subgraph(graph.nodes()).copy()
        edge_threshold = float(params.get("edge_threshold", 0) or 0)
        if edge_threshold > 0:
            weak_edges = [
                (u, v)
                for u, v, data in graph.edges(data=True)
                if float(data.get("weight", 0) or 0) <= edge_threshold
            ]
            if weak_edges:
                graph.remove_edges_from(weak_edges)
                graph.remove_nodes_from(list(nx.isolates(graph)))

        if bool(params.get("auto_tune", True)):
            self._auto_balance_graph(graph=graph, params=params)
            self._reinforce_peripheral_connectivity(
                graph=graph,
                raw_graph=raw_graph,
                params=params,
            )
            self._auto_reconnect_components(
                graph=graph,
                raw_graph=raw_graph,
                params=params,
            )

        if bool(params.get("arbremax", False)) and graph.number_of_edges() > 0:
            graph = nx.maximum_spanning_tree(graph, weight="weight")

        self.graph = graph
        if bool(params.get("render_quality_auto", True)):
            self._apply_render_quality_plan(params)
        log.info(
            "Text network filtered: %d nodes, %d edges",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )

    def _apply_auto_selection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-select robust defaults based on corpus scale."""
        tuned = dict(params)
        gephi_mode = bool(tuned.get("gephi_fidelity", False) or tuned.get("gephi_quality", False))
        
        if not bool(tuned.get("auto_tune", True)):
            self._auto_tuning_notes = {"enabled": False}
            if gephi_mode:
                tuned["auto_reconnect_components"] = False
                tuned["peripheral_enrichment"] = False
                tuned["show_halos"] = False
                tuned["label_anchor_lines"] = False
                tuned["label_hide_overlap"] = True
                tuned["label_overlap_target"] = 0.08
                tuned["label_bbox_expand_x"] = 1.12
                tuned["label_bbox_expand_y"] = 1.18
                tuned["label_min_keep"] = 6
                tuned["render_quality_passes"] = 3
                tuned["show_nodes"] = False
                tuned["edge_alpha"] = 0.28
                tuned["edge_min_alpha"] = 0.10
                tuned["edge_min_width"] = 0.20
                tuned["edge_max_width"] = 0.80
                tuned["edge_curve_ratio"] = 0.2
                tuned["edge_threshold"] = 0
                tuned["edge_weight_quantile"] = 0.0
                tuned["label_density"] = 0.85
                tuned["label_max_count"] = 300
                tuned["label_max_size"] = 32.0
                tuned["label_min_size"] = 4.5
                tuned["label_size_gamma"] = 1.5
                tuned["label_size_boost"] = 0.0
                tuned["view_trim_quantile"] = min(
                    float(tuned.get("view_trim_quantile", 0.01) or 0.01),
                    0.01,
                )
                tuned["gephi_node_reflow"] = False
                tuned["label_reposition_on_overlap"] = False
                tuned["noverlap_enabled"] = False
            return tuned

        total_tokens = int(
            sum(int(getattr(word, "freq", 0) or 0) for word in getattr(self.corpus, "formes", {}).values())
        )
        vocab_size = int(len(getattr(self.corpus, "formes", {})))
        n_uces = int(sum(1 for _uce_id, _text in self.corpus.get_uces()))

        if total_tokens <= 1500:
            profile = {
                "name": "very_small",
                "min_freq": 1,
                "min_cooc": 1,
                "edge_threshold": 0,
                "max_nodes": 450,
                "edge_alpha": 0.35,
                "label_density": 0.9,
                "label_max_count": 250,
                "label_max_size": 28.0,
                "show_halos": True,
                "label_overlap_target": 0.25,
                "render_quality_passes": 1,
                "fa2_scaling": 5.0,
                "fa2_gravity": 2.0,
                "noverlap_ratio": 1.0,
                "noverlap_iterations": 60,
                "peripheral_min_degree": 3,
                "peripheral_quantile": 0.7,
            }
        elif total_tokens <= 8000:
            profile = {
                "name": "small",
                "min_freq": 2,
                "min_cooc": 2,
                "edge_threshold": 1,
                "max_nodes": 450,
                "edge_alpha": 0.30,
                "label_density": 0.8,
                "label_max_count": 230,
                "label_max_size": 24.0,
                "show_halos": True,
                "label_overlap_target": 0.22,
                "render_quality_passes": 1,
                "fa2_scaling": 6.0,
                "fa2_gravity": 1.8,
                "noverlap_ratio": 1.05,
                "noverlap_iterations": 80,
                "peripheral_min_degree": 3,
                "peripheral_quantile": 0.65,
            }
        elif total_tokens <= 30000:
            profile = {
                "name": "medium",
                "min_freq": 3,
                "min_cooc": 3,
                "edge_threshold": 1,
                "max_nodes": 450,
                "edge_alpha": 0.25,
                "label_density": 0.7,
                "label_max_count": 210,
                "label_max_size": 20.0,
                "show_halos": False,
                "label_overlap_target": 0.20,
                "render_quality_passes": 3,
                "fa2_scaling": 8.0,
                "fa2_gravity": 1.5,
                "noverlap_ratio": 1.1,
                "noverlap_iterations": 100,
                "peripheral_min_degree": 2,
                "peripheral_quantile": 0.58,
            }
        elif total_tokens <= 90000:
            profile = {
                "name": "large",
                "min_freq": 4,
                "min_cooc": 4,
                "edge_threshold": 2,
                "max_nodes": 450,
                "edge_alpha": 0.26,
                "label_density": 0.6,
                "label_max_count": 190,
                "label_max_size": 18.0,
                "show_halos": False,
                "label_overlap_target": 0.18,
                "render_quality_passes": 3,
                "fa2_scaling": 10.0,
                "fa2_gravity": 1.3,
                "noverlap_ratio": 1.15,
                "noverlap_iterations": 120,
                "peripheral_min_degree": 2,
                "peripheral_quantile": 0.56,
            }
        else:
            profile = {
                "name": "xlarge",
                "min_freq": 5,
                "min_cooc": 5,
                "edge_threshold": 3,
                "max_nodes": 450,
                "edge_alpha": 0.25,
                "label_density": 0.55,
                "label_max_count": 170,
                "label_max_size": 16.0,
                "show_halos": False,
                "label_overlap_target": 0.16,
                "render_quality_passes": 3,
                "fa2_scaling": 12.0,
                "fa2_gravity": 1.2,
                "noverlap_ratio": 1.2,
                "noverlap_iterations": 140,
                "peripheral_min_degree": 2,
                "peripheral_quantile": 0.54,
            }

        # Auto mode takes control of graph-size parameters to avoid stale manual values.
        previous_values = {
            "min_freq": tuned.get("min_freq"),
            "min_cooc": tuned.get("min_cooc"),
            "edge_threshold": tuned.get("edge_threshold"),
            "max_nodes": tuned.get("max_nodes"),
            "edge_alpha": tuned.get("edge_alpha"),
            "label_density": tuned.get("label_density"),
            "arbremax": tuned.get("arbremax"),
        }
        tuned["min_freq"] = int(profile["min_freq"])
        tuned["min_cooc"] = int(profile["min_cooc"])
        tuned["edge_threshold"] = int(profile["edge_threshold"])
        tuned["max_nodes"] = int(profile["max_nodes"])
        tuned["edge_alpha"] = float(profile["edge_alpha"])
        tuned["label_density"] = float(profile["label_density"])
        tuned["label_max_count"] = int(profile["label_max_count"])
        tuned["label_max_size"] = float(profile["label_max_size"])
        tuned["label_min_keep"] = min(max(6, int(profile["label_max_count"] * 0.10)), 12)
        tuned["label_size_gamma"] = 1.28
        tuned["label_overlap_target"] = float(profile["label_overlap_target"])
        tuned["render_quality_passes"] = int(profile["render_quality_passes"])
        tuned["edge_min_alpha"] = max(0.13, float(tuned["edge_alpha"]) * 0.52)
        tuned["edge_min_width"] = 0.34
        tuned["edge_max_width"] = 1.42
        tuned["show_halos"] = bool(profile["show_halos"])
        tuned["show_nodes"] = False
        tuned["edge_color"] = "#778391"
        tuned["edge_intercommunity_color"] = "#66727F"
        tuned["edge_use_community_color"] = True
        tuned["auto_reconnect_components"] = True
        tuned["peripheral_enrichment"] = True
        tuned["peripheral_min_degree"] = int(profile["peripheral_min_degree"])
        tuned["peripheral_quantile"] = float(profile["peripheral_quantile"])
        tuned["label_anchor_lines"] = True
        if profile["name"] in {"very_small", "small"}:
            tuned["auto_reconnect_max_bridges"] = 10
            tuned["peripheral_boost_max_added"] = 120
        elif profile["name"] == "medium":
            tuned["auto_reconnect_max_bridges"] = 14
            tuned["peripheral_boost_max_added"] = 180
        else:
            tuned["auto_reconnect_max_bridges"] = 18
            tuned["peripheral_boost_max_added"] = 240
        tuned["fa2_scaling"] = float(profile["fa2_scaling"])
        tuned["fa2_gravity"] = float(profile["fa2_gravity"])
        tuned["noverlap_ratio"] = float(profile["noverlap_ratio"])
        tuned["noverlap_iterations"] = int(profile["noverlap_iterations"])
        tuned["edge_weight_quantile"] = float(tuned.get("edge_weight_quantile", 0.0) or 0.0)
        tuned["arbremax"] = False

        if gephi_mode:
            # Gephi overwrites to guarantee aesthetics
            tuned["auto_reconnect_components"] = False
            tuned["peripheral_enrichment"] = False
            tuned["show_halos"] = False
            tuned["label_anchor_lines"] = False
            tuned["label_hide_overlap"] = True
            tuned["label_overlap_target"] = 0.08
            tuned["label_bbox_expand_x"] = 1.12
            tuned["label_bbox_expand_y"] = 1.18
            tuned["label_min_keep"] = 6
            tuned["render_quality_passes"] = 3
            # Em Gephi visual de texto puro, os nós (bolhas) são geralmente ocultos
            tuned["show_nodes"] = False
            # Arestas Gephi: semi-transparentes mas visiveis, criando textura de fibras
            tuned["edge_alpha"] = 0.28
            tuned["edge_min_alpha"] = 0.10
            tuned["edge_min_width"] = 0.20
            tuned["edge_max_width"] = 0.80
            tuned["edge_curve_ratio"] = 0.2
            # Expansão da rede (elliptical compression in renderer handles compaction)
            tuned["network_expansion"] = 1.0
            # Em Gephi, a gente sempre ve a aresta sem cortes bruscos
            tuned["edge_threshold"] = 0
            tuned["edge_weight_quantile"] = 0.0
            
            # Critical FIX: Sizes must be smaller so abstract Noverlap isn't pushing craters
            tuned["node_min_size"] = 1.0
            tuned["node_max_size"] = 10.0
            # Texts are scaled directly and mapped properly
            tuned["label_density"] = 0.85
            tuned["label_max_count"] = 300
            tuned["label_max_size"] = 32.0
            tuned["label_min_size"] = 4.5
            tuned["label_size_gamma"] = 1.5
            tuned["label_size_boost"] = 0.0
            tuned["view_trim_quantile"] = min(
                float(tuned.get("view_trim_quantile", 0.01) or 0.01),
                0.01,
            )
            tuned["gephi_node_reflow"] = False
            tuned["label_reposition_on_overlap"] = False
            
            # Critical: Disable Noverlap in Java runner because it uses default sizes=1.0.
            # We'll run exact visual Noverlap + LabelAdjust in Python.
            tuned["noverlap_enabled"] = False
            
        self._auto_tuning_notes = {
            "enabled": True,
            "phase": "pre_graph",
            "profile": profile["name"],
            "gephi_fidelity": bool(tuned.get("gephi_fidelity", False)),
            "gephi_quality": bool(tuned.get("gephi_quality", False)),
            "gephi_mode": gephi_mode,
            "corpus": {
                "total_tokens": total_tokens,
                "vocab_size": vocab_size,
                "n_uces": n_uces,
            },
            "selected": {
                "min_freq": int(tuned["min_freq"]),
                "min_cooc": int(tuned["min_cooc"]),
                "edge_threshold": int(tuned["edge_threshold"]),
                "max_nodes": int(tuned["max_nodes"]),
                "edge_alpha": float(tuned["edge_alpha"]),
                "label_density": float(tuned["label_density"]),
                "label_max_count": int(tuned["label_max_count"]),
                "label_max_size": float(tuned["label_max_size"]),
                "label_min_keep": int(tuned["label_min_keep"]),
                "label_size_gamma": float(tuned["label_size_gamma"]),
                "label_overlap_target": float(tuned["label_overlap_target"]),
                "render_quality_passes": int(tuned["render_quality_passes"]),
                "show_halos": bool(tuned["show_halos"]),
                "edge_min_alpha": float(tuned["edge_min_alpha"]),
                "edge_min_width": float(tuned["edge_min_width"]),
                "edge_max_width": float(tuned["edge_max_width"]),
                "auto_reconnect_components": bool(tuned["auto_reconnect_components"]),
                "auto_reconnect_max_bridges": int(tuned["auto_reconnect_max_bridges"]),
                "peripheral_enrichment": bool(tuned["peripheral_enrichment"]),
                "peripheral_min_degree": int(tuned["peripheral_min_degree"]),
                "peripheral_quantile": float(tuned["peripheral_quantile"]),
                "peripheral_boost_max_added": int(tuned["peripheral_boost_max_added"]),
                "label_anchor_lines": bool(tuned["label_anchor_lines"]),
                "fa2_scaling": float(tuned["fa2_scaling"]),
                "fa2_gravity": float(tuned["fa2_gravity"]),
                "noverlap_ratio": float(tuned["noverlap_ratio"]),
                "noverlap_iterations": int(tuned["noverlap_iterations"]),
                "arbremax": bool(tuned["arbremax"]),
                "gephi_node_reflow": bool(tuned.get("gephi_node_reflow", False)),
                "label_reposition_on_overlap": bool(tuned.get("label_reposition_on_overlap", True)),
            },
            "previous_user_values": previous_values,
        }
        return tuned

    def _auto_balance_graph(self, graph: nx.Graph, params: Dict[str, Any]) -> None:
        """Reduce edge clutter targeting Gephi-like visual density."""
        if graph.number_of_nodes() < 6 or graph.number_of_edges() < 10:
            return
        if bool(params.get("arbremax", False)):
            return

        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()
        avg_degree = (2.0 * edge_count) / max(node_count, 1)
        if node_count <= 70:
            target_avg_degree = 11.0
        elif node_count <= 120:
            target_avg_degree = 12.0
        elif node_count <= 220:
            target_avg_degree = 13.0
        else:
            target_avg_degree = 14.0
        target_edges = max(node_count * 2, int(round((target_avg_degree * node_count) / 2.0)))

        if edge_count <= target_edges:
            self._auto_tuning_notes["post_graph"] = {
                "action": "none",
                "node_count": node_count,
                "edge_count": edge_count,
                "avg_degree": round(avg_degree, 3),
                "target_edges": target_edges,
            }
            return

        ranked_edges = sorted(
            graph.edges(data=True),
            key=lambda item: float(item[2].get("weight", 1.0) or 1.0),
            reverse=True,
        )
        mandatory_set = set()

        # Preserve one strongest edge per node to avoid peripheral "floating" labels.
        for node in graph.nodes():
            incident = list(graph.edges(node, data=True))
            if not incident:
                continue
            best_u, best_v, _best_data = max(
                incident,
                key=lambda item: float(item[2].get("weight", 1.0) or 1.0),
            )
            mandatory_set.add(frozenset((best_u, best_v)))

        # Preserve spanning structure inside each connected component.
        for component_nodes in nx.connected_components(graph):
            if len(component_nodes) <= 2:
                continue
            subgraph = graph.subgraph(component_nodes)
            tree = nx.maximum_spanning_tree(subgraph, weight="weight")
            for u, v in tree.edges():
                mandatory_set.add(frozenset((u, v)))

        keep_set = set(mandatory_set)
        keep_target = max(len(mandatory_set), min(target_edges, len(ranked_edges)))
        for u, v, _data in ranked_edges:
            if len(keep_set) >= keep_target:
                break
            keep_set.add(frozenset((u, v)))

        to_remove = []
        for u, v, _data in graph.edges(data=True):
            if frozenset((u, v)) not in keep_set:
                to_remove.append((u, v))

        if to_remove:
            graph.remove_edges_from(to_remove)
            graph.remove_nodes_from(list(nx.isolates(graph)))

        self._auto_tuning_notes["post_graph"] = {
            "action": "edge_prune",
            "edge_count_before": edge_count,
            "edge_count_after": graph.number_of_edges(),
            "node_count_before": node_count,
            "node_count_after": graph.number_of_nodes(),
            "target_edges": target_edges,
            "mandatory_edges_preserved": len(mandatory_set),
            "avg_degree_before": round(avg_degree, 3),
            "avg_degree_after": round(
                (2.0 * graph.number_of_edges()) / max(graph.number_of_nodes(), 1),
                3,
            ),
        }

    def _reinforce_peripheral_connectivity(
        self,
        graph: nx.Graph,
        raw_graph: nx.Graph,
        params: Dict[str, Any],
    ) -> None:
        """Increase connectivity for peripheral nodes without inflating the dense core."""
        if not bool(params.get("peripheral_enrichment", True)):
            return
        if graph.number_of_nodes() < 10 or graph.number_of_edges() <= 0:
            return

        min_degree = max(1, min(4, int(params.get("peripheral_min_degree", 2) or 2)))
        quantile = max(0.2, min(0.9, float(params.get("peripheral_quantile", 0.55) or 0.55)))

        raw_strength = {
            node: float(raw_graph.degree(node, weight="weight"))
            for node in graph.nodes()
            if node in raw_graph
        }
        if not raw_strength:
            return

        threshold = float(np.quantile(np.array(list(raw_strength.values()), dtype=float), quantile))
        peripheral_nodes = [node for node, strength in raw_strength.items() if strength <= threshold]
        if not peripheral_nodes:
            self._auto_tuning_notes["peripheral_reinforcement"] = {
                "action": "none",
                "reason": "no_peripheral_nodes",
                "min_degree": min_degree,
                "quantile": quantile,
            }
            return

        max_added = max(
            4,
            int(params.get("peripheral_boost_max_added", 180) or 180),
        )
        max_added = min(max_added, max(4, graph.number_of_edges()))

        added = 0
        touched_nodes = 0
        for node in sorted(peripheral_nodes, key=lambda n: raw_strength.get(n, 0.0)):
            if node not in graph:
                continue
            need = max(0, min_degree - int(graph.degree(node)))
            if need <= 0:
                continue

            candidates: List[Tuple[float, Any]] = []
            for neighbor, edge_data in raw_graph[node].items():
                if neighbor not in graph or graph.has_edge(node, neighbor):
                    continue
                weight = float(edge_data.get("weight", 1.0) or 1.0)
                candidates.append((weight, neighbor))
            if not candidates:
                continue

            candidates.sort(key=lambda item: item[0], reverse=True)
            local_added = 0
            for weight, neighbor in candidates:
                if added >= max_added or local_added >= need:
                    break
                graph.add_edge(node, neighbor, weight=float(weight), peripheral_boost=1)
                added += 1
                local_added += 1
            if local_added > 0:
                touched_nodes += 1
            if added >= max_added:
                break

        self._auto_tuning_notes["peripheral_reinforcement"] = {
            "action": "edges_added" if added > 0 else "none_added",
            "peripheral_nodes": int(len(peripheral_nodes)),
            "peripheral_nodes_touched": int(touched_nodes),
            "min_degree_target": int(min_degree),
            "quantile": round(float(quantile), 4),
            "strength_threshold": round(float(threshold), 6),
            "edges_added": int(added),
            "max_added": int(max_added),
        }

    def _auto_reconnect_components(
        self,
        graph: nx.Graph,
        raw_graph: nx.Graph,
        params: Dict[str, Any],
    ) -> None:
        """Reconnect fragmented components using strongest original cross-component bridges."""
        if not bool(params.get("auto_reconnect_components", True)):
            return
        if graph.number_of_nodes() < 6 or graph.number_of_edges() <= 0:
            return

        components = list(nx.connected_components(graph))
        n_components = len(components)
        if n_components <= 1:
            self._auto_tuning_notes["component_reconnect"] = {
                "action": "none",
                "components_before": 1,
                "components_after": 1,
            }
            return

        node_to_comp: Dict[Any, int] = {}
        for idx, nodes in enumerate(components):
            for node in nodes:
                node_to_comp[node] = idx

        best_between: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for u, v, data in raw_graph.edges(data=True):
            cu = node_to_comp.get(u)
            cv = node_to_comp.get(v)
            if cu is None or cv is None or cu == cv:
                continue
            key = (cu, cv) if cu < cv else (cv, cu)
            weight = float(data.get("weight", 1.0) or 1.0)
            previous = best_between.get(key)
            if previous is None or weight > float(previous["weight"]):
                best_between[key] = {
                    "u": u,
                    "v": v,
                    "weight": weight,
                }

        if not best_between:
            self._auto_tuning_notes["component_reconnect"] = {
                "action": "no_candidates",
                "components_before": n_components,
                "components_after": n_components,
            }
            return

        comp_graph = nx.Graph()
        for (ca, cb), edge_data in best_between.items():
            comp_graph.add_edge(
                ca,
                cb,
                weight=float(edge_data["weight"]),
                u=edge_data["u"],
                v=edge_data["v"],
            )

        if comp_graph.number_of_edges() <= 0:
            self._auto_tuning_notes["component_reconnect"] = {
                "action": "no_candidates",
                "components_before": n_components,
                "components_after": n_components,
            }
            return

        max_bridges = max(1, int(params.get("auto_reconnect_max_bridges", 16) or 16))
        bridge_tree = nx.maximum_spanning_tree(comp_graph, weight="weight")
        candidate_bridges = sorted(
            bridge_tree.edges(data=True),
            key=lambda item: float(item[2].get("weight", 1.0) or 1.0),
            reverse=True,
        )

        added = 0
        for _ca, _cb, edge_data in candidate_bridges:
            if added >= max_bridges:
                break
            u = edge_data.get("u")
            v = edge_data.get("v")
            if u is None or v is None or graph.has_edge(u, v):
                continue
            graph.add_edge(u, v, weight=float(edge_data.get("weight", 1.0) or 1.0), auto_bridge=1)
            added += 1

        components_after = nx.number_connected_components(graph)
        self._auto_tuning_notes["component_reconnect"] = {
            "action": "bridges_added" if added > 0 else "none_added",
            "components_before": n_components,
            "components_after": int(components_after),
            "bridges_added": int(added),
            "bridge_candidates": int(len(candidate_bridges)),
        }

    def _apply_render_quality_plan(self, params: Dict[str, Any]) -> None:
        """Tune render visibility/readability based on final graph metrics."""
        if self.graph is None or self.graph.number_of_nodes() <= 0:
            return
        graph = self.graph
        n_nodes = graph.number_of_nodes()
        n_edges = graph.number_of_edges()
        density = nx.density(graph) if n_nodes > 1 else 0.0
        avg_degree = (2.0 * n_edges) / max(n_nodes, 1)
        # Gephi fidelity mode already has carefully tuned parameters from
        # _apply_auto_selection. Do NOT overwrite them, but keep diagnostics keys.
        if bool(params.get("gephi_fidelity", False) or params.get("gephi_quality", False)):
            self._auto_tuning_notes["render_plan"] = {
                "mode": "gephi_mode_passthrough",
                "n_nodes": n_nodes,
                "n_edges": n_edges,
                "density": round(float(density), 6),
                "avg_degree": round(float(avg_degree), 4),
                "selected": {
                    "render_quality_passes": int(params.get("render_quality_passes", 0)),
                    "label_density": float(params.get("label_density", 0.0)),
                    "label_max_count": int(params.get("label_max_count", 0)),
                    "label_max_size": float(params.get("label_max_size", 0.0)),
                    "edge_alpha": float(params.get("edge_alpha", 0.0)),
                    "show_halos": bool(params.get("show_halos", False)),
                },
            }
            return

        if n_nodes >= 220:
            params["label_density"] = min(float(params.get("label_density", 0.42)), 0.34)
            params["label_max_count"] = min(int(params.get("label_max_count", 96)), 80)
            params["label_max_size"] = min(float(params.get("label_max_size", 19.0)), 11.6)
            params["label_min_keep"] = min(int(params.get("label_min_keep", 8)), 8)
            params["label_size_gamma"] = max(float(params.get("label_size_gamma", 1.2)), 1.42)
            params["label_overlap_target"] = min(float(params.get("label_overlap_target", 0.16)), 0.16)
            params["render_quality_passes"] = max(int(params.get("render_quality_passes", 2)), 3)
        elif n_nodes >= 150:
            params["label_density"] = min(float(params.get("label_density", 0.42)), 0.38)
            params["label_max_count"] = min(int(params.get("label_max_count", 96)), 86)
            params["label_max_size"] = min(float(params.get("label_max_size", 19.0)), 12.2)
            params["label_min_keep"] = min(int(params.get("label_min_keep", 8)), 8)
            params["label_size_gamma"] = max(float(params.get("label_size_gamma", 1.2)), 1.36)
            params["label_overlap_target"] = min(float(params.get("label_overlap_target", 0.14)), 0.14)
            params["render_quality_passes"] = max(int(params.get("render_quality_passes", 2)), 3)
        elif n_nodes >= 100:
            params["label_density"] = min(float(params.get("label_density", 0.42)), 0.40)
            params["label_max_count"] = min(int(params.get("label_max_count", 96)), 88)
            params["label_max_size"] = min(float(params.get("label_max_size", 19.0)), 13.4)
            params["label_size_gamma"] = max(float(params.get("label_size_gamma", 1.2)), 1.30)
            params["label_overlap_target"] = min(float(params.get("label_overlap_target", 0.16)), 0.16)
            params["render_quality_passes"] = max(int(params.get("render_quality_passes", 2)), 2)
        else:
            params["label_overlap_target"] = min(float(params.get("label_overlap_target", 0.14)), 0.18)
            params["render_quality_passes"] = max(int(params.get("render_quality_passes", 1)), 1)

        alpha_base = float(params.get("edge_alpha", 0.14))
        if density <= 0.035:
            alpha_base = max(alpha_base, 0.30)
        elif density <= 0.07:
            alpha_base = max(alpha_base, 0.28)
        else:
            alpha_base = max(alpha_base, 0.25)
        params["edge_alpha"] = min(alpha_base, 0.38)
        params["edge_min_alpha"] = max(float(params.get("edge_min_alpha", 0.13)), 0.13)
        params["edge_min_width"] = max(float(params.get("edge_min_width", 0.34)), 0.34)
        params["edge_max_width"] = max(float(params.get("edge_max_width", 1.40)), 1.42)
        params["edge_use_community_color"] = bool(params.get("edge_use_community_color", True))
        params["candidate_min_cooc"] = min(
            float(params.get("candidate_min_cooc", 1.0)),
            float(params.get("min_cooc", 1)),
        )
        params["auto_reconnect_components"] = bool(params.get("auto_reconnect_components", True))
        params["peripheral_enrichment"] = bool(params.get("peripheral_enrichment", True))
        if n_nodes >= 200:
            params["auto_reconnect_max_bridges"] = max(int(params.get("auto_reconnect_max_bridges", 16)), 18)
            params["peripheral_min_degree"] = max(int(params.get("peripheral_min_degree", 2)), 2)
            params["peripheral_quantile"] = max(float(params.get("peripheral_quantile", 0.55)), 0.56)
        elif n_nodes >= 120:
            params["auto_reconnect_max_bridges"] = max(int(params.get("auto_reconnect_max_bridges", 14)), 14)
            params["peripheral_min_degree"] = max(int(params.get("peripheral_min_degree", 2)), 2)
            params["peripheral_quantile"] = max(float(params.get("peripheral_quantile", 0.55)), 0.58)
        else:
            params["auto_reconnect_max_bridges"] = max(int(params.get("auto_reconnect_max_bridges", 10)), 10)
            params["peripheral_min_degree"] = max(int(params.get("peripheral_min_degree", 2)), 3)
            params["peripheral_quantile"] = max(float(params.get("peripheral_quantile", 0.55)), 0.65)
        params["peripheral_boost_max_added"] = max(
            int(params.get("peripheral_boost_max_added", 180)),
            120 if n_nodes < 120 else 180,
        )
        params["label_anchor_lines"] = bool(params.get("label_anchor_lines", True))
        params["show_nodes"] = False
        params["show_halos"] = bool(params.get("show_halos", False)) and n_nodes <= 110

        self._auto_tuning_notes["render_plan"] = {
            "n_nodes": n_nodes,
            "n_edges": n_edges,
            "density": round(float(density), 6),
            "avg_degree": round(float(avg_degree), 4),
            "selected": {
                "edge_alpha": float(params.get("edge_alpha", 0.0)),
                "edge_min_alpha": float(params.get("edge_min_alpha", 0.0)),
                "edge_min_width": float(params.get("edge_min_width", 0.0)),
                "edge_max_width": float(params.get("edge_max_width", 0.0)),
                "edge_use_community_color": bool(params.get("edge_use_community_color", True)),
                "auto_reconnect_components": bool(params.get("auto_reconnect_components", True)),
                "auto_reconnect_max_bridges": int(params.get("auto_reconnect_max_bridges", 0)),
                "peripheral_enrichment": bool(params.get("peripheral_enrichment", True)),
                "peripheral_min_degree": int(params.get("peripheral_min_degree", 0)),
                "peripheral_quantile": float(params.get("peripheral_quantile", 0.0)),
                "peripheral_boost_max_added": int(params.get("peripheral_boost_max_added", 0)),
                "label_anchor_lines": bool(params.get("label_anchor_lines", True)),
                "label_density": float(params.get("label_density", 0.0)),
                "label_max_count": int(params.get("label_max_count", 0)),
                "label_max_size": float(params.get("label_max_size", 0.0)),
                "label_min_keep": int(params.get("label_min_keep", 0)),
                "label_size_gamma": float(params.get("label_size_gamma", 0.0)),
                "label_overlap_target": float(params.get("label_overlap_target", 0.0)),
                "render_quality_passes": int(params.get("render_quality_passes", 0)),
                "show_halos": bool(params.get("show_halos", False)),
            },
        }

    def _compute_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compute network metrics."""
        if self.graph is None:
            return self._empty_metrics()

        graph = self.graph
        if graph.number_of_nodes() == 0:
            return self._empty_metrics()

        use_weights = bool(params.get("use_edge_weights", True))
        weight_key: Optional[str] = "weight" if use_weights else None
        normalize = bool(params.get("normalize_centralities", False))

        degree = dict(graph.degree())
        weighted_degree = dict(graph.degree(weight="weight"))
        average_degree = (sum(degree.values()) / max(len(degree), 1)) if degree else 0.0

        try:
            betweenness = nx.betweenness_centrality(
                graph, weight=weight_key, normalized=normalize
            )
        except Exception:
            betweenness = {node: 0.0 for node in graph.nodes()}

        try:
            closeness = nx.closeness_centrality(graph, distance=weight_key)
        except Exception:
            closeness = {node: 0.0 for node in graph.nodes()}

        try:
            eigenvector = nx.eigenvector_centrality_numpy(graph, weight=weight_key)
        except Exception:
            eigenvector = {node: 0.0 for node in graph.nodes()}

        diameter = 0
        try:
            if graph.number_of_nodes() > 1:
                if nx.is_connected(graph):
                    diameter = int(nx.diameter(graph))
                else:
                    largest_cc = max(nx.connected_components(graph), key=len)
                    subgraph = graph.subgraph(largest_cc)
                    if subgraph.number_of_nodes() > 1:
                        diameter = int(nx.diameter(subgraph))
        except Exception:
            diameter = 0

        return {
            "degree": degree,
            "weighted_degree": weighted_degree,
            "betweenness": betweenness,
            "closeness": closeness,
            "eigenvector": eigenvector,
            "average_degree": average_degree,
            "diameter": diameter,
        }

    @staticmethod
    def _empty_metrics() -> Dict[str, Any]:
        return {
            "degree": {},
            "weighted_degree": {},
            "betweenness": {},
            "closeness": {},
            "eigenvector": {},
            "average_degree": 0.0,
            "diameter": 0,
        }

    def _detect_communities(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Detect communities with shared Louvain helper + robust fallback."""
        if self.graph is None or self.graph.number_of_nodes() == 0:
            return {"partition": {}, "modularity": 0.0, "n_communities": 0}

        resolution = float(params.get("community_resolution", 1.0) or 1.0)
        payload = detect_louvain_partition(
            self.graph,
            resolution=resolution,
            seed=int(params.get("seed", 42) or 42),
        )

        n_communities = int(payload.get("n_communities", 0) or 0)
        modularity = float(payload.get("modularity", 0.0) or 0.0)
        if n_communities > 0:
            log.info(
                "Communities detected: %d (modularity=%.4f, resolution=%.2f)",
                n_communities,
                modularity,
                resolution,
            )
        return payload

    def _compute_layout(self, params: Dict[str, Any]) -> Dict[Any, Tuple[float, float]]:
        """Compute node positions using explicit backend selection."""
        if self.graph is None or self.graph.number_of_nodes() == 0:
            return {}

        backend = str(params.get("layout_backend", "gephi_java") or "gephi_java").strip().lower()
        strict = bool(params.get("strict_layout_backend", True))

        if backend != "gephi_java":
            message = f"Backend de layout '{backend}' nao suportado no pipeline principal."
            if strict:
                raise NetworkTextAnalysisError(
                    what="Nao foi possivel calcular o layout da rede textual.",
                    why=message,
                    how="Use layout_backend='gephi_java' ou desative strict_layout_backend.",
                )
            log.warning("%s Fallback para spring layout por modo nao estrito.", message)
            self._layout_backend_used = "spring_fallback"
            self._layout_diagnostics = {"backend": "spring_fallback", "reason": message}
            self._layout_diag_path = None
            return self._layout_spring(self.graph, params)

        try:
            backend_result: GephiJavaBackendResult = run_gephi_java_layout(
                graph=self.graph,
                params=params,
                output_dir=self.output_dir,
            )
            self._layout_backend_used = "gephi_java"
            self._layout_diagnostics = dict(backend_result.diagnostics or {})
            self._layout_diag_path = backend_result.diagnostics_path
            return backend_result.positions
        except GephiJavaBackendError as exc:
            if strict:
                raise NetworkTextAnalysisError(
                    what="Nao foi possivel calcular o layout ForceAtlas2 via Gephi Java.",
                    why=str(exc),
                    how=(
                        "Verifique se resources/gephi_runner/gephi-runner.jar e Java "
                        "estao disponiveis; depois execute novamente."
                    ),
                ) from exc
            log.warning("Gephi backend falhou; usando fallback spring: %s", exc)
            self._layout_backend_used = "spring_fallback"
            self._layout_diagnostics = {"backend": "spring_fallback", "reason": str(exc)}
            self._layout_diag_path = None
            return self._layout_spring(self.graph, params)

    def _layout_spring(
        self, graph: nx.Graph, params: Dict[str, Any]
    ) -> Dict[Any, Tuple[float, float]]:
        """Spring layout fallback for non-strict mode only."""
        iterations = max(50, int(params.get("spring_iterations", 200)))
        return nx.spring_layout(
            graph,
            k=None,
            iterations=iterations,
            weight="weight",
            seed=int(params.get("seed", 42) or 42),
            scale=1.0,
        )

    def _build_nodes_table(
        self, metrics: Dict[str, Any], communities: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Build node-level table with all metrics."""
        if self.graph is None:
            return []

        partition = communities.get("partition", {}) or {}
        positions = self.positions or {}
        rows: List[Dict[str, Any]] = []

        for node in self.graph.nodes():
            x, y = positions.get(node, (0.0, 0.0))
            rows.append(
                {
                    "id": node,
                    "label": node,
                    "degree": int(metrics.get("degree", {}).get(node, 0)),
                    "weighted_degree": round(
                        float(metrics.get("weighted_degree", {}).get(node, 0.0)), 2
                    ),
                    "betweenness": round(
                        float(metrics.get("betweenness", {}).get(node, 0.0)), 6
                    ),
                    "closeness": round(
                        float(metrics.get("closeness", {}).get(node, 0.0)), 6
                    ),
                    "eigenvector": round(
                        float(metrics.get("eigenvector", {}).get(node, 0.0)), 6
                    ),
                    "community": int(partition.get(node, 0) or 0),
                    "frequency": int(self.graph.nodes[node].get("frequency", 0) or 0),
                    "x": round(float(x), 4),
                    "y": round(float(y), 4),
                }
            )

        rows.sort(key=lambda row: row["weighted_degree"], reverse=True)
        return rows

    def _build_edges_table(self) -> List[Dict[str, Any]]:
        """Build edge-level table."""
        if self.graph is None:
            return []

        rows = [
            {
                "source": source,
                "target": target,
                "weight": round(float(data.get("weight", 1.0)), 2),
            }
            for source, target, data in self.graph.edges(data=True)
        ]
        rows.sort(key=lambda row: row["weight"], reverse=True)
        return rows

    def _render(
        self,
        params: Dict[str, Any],
        nodes_table: List[Dict[str, Any]],
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Render graph using network_text_renderer."""
        if self.graph is None or self.positions is None:
            return None, None

        from .network_text_renderer import render_network

        output_path = self.output_dir / "network_text"
        image_path, svg_path = render_network(
            graph=self.graph,
            positions=self.positions,
            nodes_table=nodes_table,
            output_path=output_path,
            params=params,
        )
        render_feedback = params.get("_render_quality")
        if isinstance(render_feedback, dict):
            self._auto_tuning_notes["render_feedback"] = render_feedback
        else:
            self._auto_tuning_notes["render_feedback"] = {"available": False}
        return image_path, svg_path

    def _export(
        self,
        params: Dict[str, Any],
        nodes_table: List[Dict[str, Any]],
        edges_table: List[Dict[str, Any]],
    ) -> Tuple[Optional[Path], Optional[Path], Optional[Path], Optional[Path]]:
        """Export CSV, GEXF and optional NET (Pajek/Gephi) artifacts."""
        nodes_csv: Optional[Path] = None
        edges_csv: Optional[Path] = None
        gexf_path: Optional[Path] = None
        net_path: Optional[Path] = None

        if bool(params.get("export_csv", True)):
            nodes_csv = self.output_dir / "network_nodes.csv"
            with nodes_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "id",
                        "label",
                        "degree",
                        "weighted_degree",
                        "betweenness",
                        "closeness",
                        "eigenvector",
                        "community",
                        "frequency",
                        "x",
                        "y",
                    ],
                    delimiter=";",
                )
                writer.writeheader()
                writer.writerows(nodes_table)

            edges_csv = self.output_dir / "network_edges.csv"
            with edges_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["source", "target", "weight"],
                    delimiter=";",
                )
                writer.writeheader()
                writer.writerows(edges_table)

        if bool(params.get("export_gexf", True)):
            gexf_path = self.output_dir / "network.gexf"
            self._export_gexf(gexf_path, nodes_table)
        if bool(params.get("export_net", False)):
            net_path = self.output_dir / "network.net"
            self._export_net(net_path)

        return (
            nodes_csv if nodes_csv and nodes_csv.exists() else None,
            edges_csv if edges_csv and edges_csv.exists() else None,
            gexf_path if gexf_path and gexf_path.exists() else None,
            net_path if net_path and net_path.exists() else None,
        )

    def _export_gexf(self, path: Path, nodes_table: List[Dict[str, Any]]) -> None:
        """Export graph as GEXF with metrics and coordinates."""
        if self.graph is None:
            return

        graph = self.graph.copy()
        node_lookup = {row["id"]: row for row in nodes_table}
        positions = self.positions or {}

        for node in graph.nodes():
            info = node_lookup.get(node, {})
            graph.nodes[node]["degree"] = int(info.get("degree", 0))
            graph.nodes[node]["weighted_degree"] = float(
                info.get("weighted_degree", 0.0)
            )
            graph.nodes[node]["betweenness"] = float(info.get("betweenness", 0.0))
            graph.nodes[node]["closeness"] = float(info.get("closeness", 0.0))
            graph.nodes[node]["modularity_class"] = int(info.get("community", 0))
            x, y = positions.get(node, (0.0, 0.0))
            graph.nodes[node]["viz"] = {
                "position": {
                    "x": float(x) * 1000.0,
                    "y": float(y) * 1000.0,
                    "z": 0.0,
                }
            }

        nx.write_gexf(graph, str(path), encoding="utf-8", prettyprint=True)
        log.info("GEXF exported: %s", path)

    def _export_net(self, path: Path) -> None:
        """Export graph as Pajek NET (.net), compatible with Gephi import."""
        if self.graph is None:
            return

        graph = self.graph
        positions = self.positions or {}
        nodes = sorted(graph.nodes(), key=lambda item: str(item))
        node_index = {node: idx for idx, node in enumerate(nodes, start=1)}

        lines: List[str] = [f"*Vertices {len(nodes)}"]
        for node in nodes:
            idx = node_index[node]
            x, y = positions.get(node, (0.0, 0.0))
            label = str(node).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(
                f'{idx} "{label}" {float(x):.6f} {float(y):.6f} 0.0'
            )

        lines.append("*Edges")
        for source, target, data in graph.edges(data=True):
            weight = float(data.get("weight", 1.0) or 1.0)
            lines.append(
                f"{node_index[source]} {node_index[target]} {weight:.6f}"
            )

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("NET exported: %s", path)

    def _write_network_diagnostics(
        self,
        metrics: Dict[str, Any],
        communities: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Optional[Path]:
        """Persist machine-readable diagnostics for one run."""
        if self.graph is None:
            return None

        degree_values = list(metrics.get("degree", {}).values())
        weighted_values = list(metrics.get("weighted_degree", {}).values())
        density = nx.density(self.graph) if self.graph.number_of_nodes() > 1 else 0.0

        diagnostics = {
            "backend_used": self._layout_backend_used,
            "layout_backend_requested": str(params.get("layout_backend", "gephi_java")),
            "strict_layout_backend": bool(params.get("strict_layout_backend", True)),
            "auto_tune": bool(params.get("auto_tune", True)),
            "auto_tuning": self._auto_tuning_notes,
            "selected_params": {
                "min_freq": int(params.get("min_freq", 0) or 0),
                "min_cooc": int(params.get("min_cooc", 0) or 0),
                "max_nodes": int(params.get("max_nodes", 0) or 0),
                "stopword_policy": str(params.get("stopword_policy", "")),
                "strict_stopword_filter": bool(params.get("strict_stopword_filter", False)),
                "edge_threshold": float(params.get("edge_threshold", 0) or 0),
                "edge_weight_quantile": float(params.get("edge_weight_quantile", 0.0) or 0.0),
                "candidate_min_cooc": float(params.get("candidate_min_cooc", 0.0) or 0.0),
                "label_density": float(params.get("label_density", 0.0) or 0.0),
                "label_max_count": int(params.get("label_max_count", 0) or 0),
                "label_max_size": float(params.get("label_max_size", 0.0) or 0.0),
                "label_size_boost": float(params.get("label_size_boost", 0.0) or 0.0),
                "label_min_keep": int(params.get("label_min_keep", 0) or 0),
                "label_size_gamma": float(params.get("label_size_gamma", 0.0) or 0.0),
                "label_overlap_target": float(params.get("label_overlap_target", 0.0) or 0.0),
                "render_quality_passes": int(params.get("render_quality_passes", 0) or 0),
                "edge_alpha": float(params.get("edge_alpha", 0.0) or 0.0),
                "edge_min_alpha": float(params.get("edge_min_alpha", 0.0) or 0.0),
                "edge_min_width": float(params.get("edge_min_width", 0.0) or 0.0),
                "edge_max_width": float(params.get("edge_max_width", 0.0) or 0.0),
                "view_trim_quantile": float(params.get("view_trim_quantile", 0.0) or 0.0),
                "view_pad_ratio_initial": float(params.get("view_pad_ratio_initial", 0.0) or 0.0),
                "view_pad_ratio_final": float(params.get("view_pad_ratio_final", 0.0) or 0.0),
                "edge_use_community_color": bool(params.get("edge_use_community_color", True)),
                "auto_reconnect_components": bool(params.get("auto_reconnect_components", True)),
                "auto_reconnect_max_bridges": int(params.get("auto_reconnect_max_bridges", 0) or 0),
                "peripheral_enrichment": bool(params.get("peripheral_enrichment", True)),
                "peripheral_min_degree": int(params.get("peripheral_min_degree", 0) or 0),
                "peripheral_quantile": float(params.get("peripheral_quantile", 0.0) or 0.0),
                "peripheral_boost_max_added": int(params.get("peripheral_boost_max_added", 0) or 0),
                "label_anchor_lines": bool(params.get("label_anchor_lines", True)),
                "show_halos": bool(params.get("show_halos", True)),
                "show_nodes": bool(params.get("show_nodes", False)),
                "arbremax": bool(params.get("arbremax", False)),
            },
            "layout_diagnostics_path": str(self._layout_diag_path) if self._layout_diag_path else "",
            "layout_diagnostics": self._layout_diagnostics,
            "top_terms_before_filter": self._top_terms_before_filter,
            "top_terms_after_filter": self._top_terms_after_filter,
            "network": {
                "n_nodes": self.graph.number_of_nodes(),
                "n_edges": self.graph.number_of_edges(),
                "density": round(float(density), 8),
                "n_components": int(nx.number_connected_components(self.graph)),
                "largest_component_ratio": round(
                    float(
                        max((len(c) for c in nx.connected_components(self.graph)), default=0)
                    )
                    / max(self.graph.number_of_nodes(), 1),
                    8,
                ),
                "average_degree": round(float(metrics.get("average_degree", 0.0)), 8),
                "diameter": int(metrics.get("diameter", 0) or 0),
                "modularity": round(float(communities.get("modularity", 0.0) or 0.0), 8),
                "n_communities": int(communities.get("n_communities", 0) or 0),
                "degree_distribution": {
                    "min": int(min(degree_values)) if degree_values else 0,
                    "max": int(max(degree_values)) if degree_values else 0,
                    "mean": float(np.mean(degree_values)) if degree_values else 0.0,
                    "median": float(np.median(degree_values)) if degree_values else 0.0,
                },
                "weighted_degree_distribution": {
                    "min": float(min(weighted_values)) if weighted_values else 0.0,
                    "max": float(max(weighted_values)) if weighted_values else 0.0,
                    "mean": float(np.mean(weighted_values)) if weighted_values else 0.0,
                    "median": float(np.median(weighted_values)) if weighted_values else 0.0,
                },
            },
        }

        path = self.output_dir / "network_diagnostics.json"
        path.write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._network_diagnostics_path = path
        return path

    def _build_report_data(
        self,
        metrics: Dict[str, Any],
        communities: Dict[str, Any],
        params: Dict[str, Any],
        diagnostics_path: Optional[Path],
    ) -> Dict[str, Any]:
        """Build structured summary for HTML report and statistics panel."""
        if self.graph is None:
            return {}

        from collections import Counter

        top_degree = sorted(
            metrics.get("degree", {}).items(), key=lambda item: -item[1]
        )[:10]
        top_betweenness = sorted(
            metrics.get("betweenness", {}).items(),
            key=lambda item: -float(item[1]),
        )[:10]
        top_closeness = sorted(
            metrics.get("closeness", {}).items(),
            key=lambda item: -float(item[1]),
        )[:10]

        partition = communities.get("partition", {}) or {}
        comm_dist = Counter(partition.values())
        density = nx.density(self.graph) if self.graph.number_of_nodes() > 1 else 0.0

        return {
            "n_nodes": self.graph.number_of_nodes(),
            "n_edges": self.graph.number_of_edges(),
            "average_degree": round(float(metrics.get("average_degree", 0.0)), 3),
            "density": round(float(density), 6),
            "diameter": int(metrics.get("diameter", 0) or 0),
            "modularity": round(float(communities.get("modularity", 0.0) or 0.0), 4),
            "n_communities": int(communities.get("n_communities", 0) or 0),
            "community_resolution": float(
                params.get("community_resolution", 1.0) or 1.0
            ),
            "layout": "forceatlas2",
            "layout_backend": self._layout_backend_used,
            "auto_tune": bool(params.get("auto_tune", True)),
            "auto_tuning": self._auto_tuning_notes,
            "diagnostics_path": str(diagnostics_path) if diagnostics_path else "",
            "top_degree": top_degree,
            "top_betweenness": top_betweenness,
            "top_closeness": top_closeness,
            "community_distribution": dict(comm_dist),
            "top_terms_before_filter": self._top_terms_before_filter[:15],
            "top_terms_after_filter": self._top_terms_after_filter[:15],
        }
