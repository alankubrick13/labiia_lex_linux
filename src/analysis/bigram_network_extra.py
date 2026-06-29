"""Extra bigram co-occurrence network analysis."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.corpus import Corpus
from ..utils.logger import get_logger
from ..utils.subprocess_utils import no_console_kwargs
from ._extras_common import build_uci_records, tokenize_text


@dataclass
class BigramNetworkExtraResult:
    """Result payload for bigram network analysis."""

    graph_path: Optional[Path]
    edges_path: Optional[Path]
    n_nodes: int
    n_edges: int


class BigramNetworkExtraAnalysisError(Exception):
    """Friendly error for bigram network extra analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class BigramNetworkExtraAnalysis:
    """Build and visualize a bigram co-occurrence network."""

    DEFAULT_PARAMS = {
        "min_bigram_freq": 2,
        "top_edges": 120,
        "width": 1200,
        "height": 800,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)

    def run(self, params: Optional[Dict[str, Any]] = None) -> BigramNetworkExtraResult:
        """Execute bigram network extraction and visualization."""
        import networkx as nx

        config = {**self.DEFAULT_PARAMS, **(params or {})}
        min_bigram_freq = max(1, int(config.get("min_bigram_freq", 2)))
        top_edges = max(20, int(config.get("top_edges", 120)))

        records = build_uci_records(self.corpus)
        if not records:
            raise BigramNetworkExtraAnalysisError(
                what="Corpus sem textos para rede de bigramas.",
                why="Nenhuma UCI foi encontrada no corpus carregado.",
                how="Importe um corpus válido e tente novamente.",
            )

        bigram_counter: Counter[Tuple[str, str]] = Counter()
        for record in records:
            tokens = tokenize_text(record.text, remove_stopwords=True)
            if len(tokens) < 2:
                continue
            for first, second in zip(tokens, tokens[1:]):
                bigram_counter[(first, second)] += 1

        filtered = [
            (first, second, int(freq))
            for (first, second), freq in bigram_counter.items()
            if int(freq) >= min_bigram_freq
        ]
        filtered.sort(key=lambda item: item[2], reverse=True)
        top_filtered = filtered[:top_edges]

        if not top_filtered:
            raise BigramNetworkExtraAnalysisError(
                what="Nenhum bigrama atingiu a frequência mínima.",
                why="Os pares de palavras ficaram abaixo do limiar configurado.",
                how="Reduza a frequência mínima ou use um corpus maior.",
            )

        graph = nx.Graph()
        for first, second, freq in top_filtered:
            graph.add_edge(first, second, weight=freq)

        edges_path = self.output_dir / "bigram_network_edges.csv"
        self._write_edges_csv(edges_path, top_filtered)
        graph_path = self.output_dir / "bigram_network.png"
        self._plot_network(graph_path, graph, config)

        return BigramNetworkExtraResult(
            graph_path=graph_path if graph_path.exists() else None,
            edges_path=edges_path if edges_path.exists() else None,
            n_nodes=graph.number_of_nodes(),
            n_edges=graph.number_of_edges(),
        )

    @staticmethod
    def _write_edges_csv(path: Path, rows: List[Tuple[str, str, int]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["word_1", "word_2", "frequency"])
            for first, second, freq in rows:
                writer.writerow([first, second, int(freq)])

    def _plot_network(self, path: Path, graph, params: Dict[str, Any]) -> None:
        """Generate network plot using R quanteda.textplots::textplot_network."""
        from .readable_network_plot import write_readable_network_plot

        if graph.number_of_nodes() <= 0:
            return
        write_readable_network_plot(
            graph,
            path,
            title="Rede de Coocorrência por Bigramas",
            max_labels=max(24, min(60, int(params.get("top_edges", 60) or 60))),
        )
        return

        import json
        import subprocess
        import tempfile

        if graph.number_of_nodes() <= 0:
            return

        # Export edges to CSV for R
        edges_csv = path.parent / "bigram_edges_for_r.csv"
        with open(edges_csv, "w", encoding="utf-8", newline="") as f:
            f.write("word_1;word_2;frequency\n")
            for u, v, data in graph.edges(data=True):
                freq = data.get("weight", 1)
                f.write(f"{u};{v};{freq}\n")

        # Prepare parameters for R
        r_params = {
            "edges_file": str(edges_csv),
            "output_file": str(path),
            "width": params.get("width", 1200),
            "height": params.get("height", 900),
            "top_words": params.get("top_edges", 30),
            "min_freq": 0.5,
            "edge_alpha": 0.4,
            "edge_color": "#3B82F6",
            "vertex_color": "#1E40AF",
            "vertex_size": 3,
            "title": "Rede de Coocorrência por Bigramas",
        }

        # Write params JSON
        params_file = path.parent / "bigram_params.json"
        with open(params_file, "w", encoding="utf-8") as f:
            json.dump(r_params, f, indent=2)

        # Find R script
        r_script = (
            Path(__file__).parent.parent
            / "visualization"
            / "r_integration"
            / "r_scripts"
            / "bigram_network.R"
        )

        if not r_script.exists():
            self._logger.warning(f"R script not found at {r_script}, falling back to matplotlib")
            self._plot_network_fallback(path, graph, params)
            return

        # Find Rscript executable via resolver multiplataforma
        from ..core.r_runtime import RRuntimeResolver

        rscript_exe = None
        try:
            rscript_exe = str(RRuntimeResolver().resolve().rscript_path)
        except Exception:
            self._logger.warning("Rscript not found, falling back to matplotlib")
            self._plot_network_fallback(path, graph, params)
            return

        # Run R script
        try:
            result = subprocess.run(
                [rscript_exe, str(r_script), str(params_file)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(path.parent),
                **no_console_kwargs(),
            )
            if result.returncode != 0:
                self._logger.warning(f"R script failed: {result.stderr}")
                self._plot_network_fallback(path, graph, params)
            else:
                self._logger.info("Bigram network generated with R quanteda")
        except Exception as e:
            self._logger.warning(f"R execution failed: {e}, falling back to matplotlib")
            self._plot_network_fallback(path, graph, params)

    def _plot_network_fallback(self, path: Path, graph, params: Dict[str, Any]) -> None:
        """Fallback matplotlib plotting if R is unavailable."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx

        if graph.number_of_nodes() <= 0:
            return

        n_nodes = graph.number_of_nodes()
        k_value = max(2.5, 3.5 + (n_nodes / 40))
        pos = nx.spring_layout(graph, k=k_value, iterations=300, seed=42, weight="weight", scale=2.0)

        node_strength = dict(graph.degree(weight="weight"))
        strengths = list(node_strength.values()) or [1.0]
        min_s, max_s = min(strengths), max(strengths)
        scale = (max_s - min_s) if (max_s - min_s) > 0 else 1.0

        node_sizes = [80.0 + ((node_strength.get(node, min_s) - min_s) / scale) * 400.0 for node in graph.nodes()]
        font_sizes = {node: 7 + int(((node_strength.get(node, min_s) - min_s) / scale) * 6) for node in graph.nodes()}
        edge_weights = [float(graph[u][v].get("weight", 1.0)) for u, v in graph.edges()]
        max_w = max(edge_weights) if edge_weights else 1.0
        widths = [0.4 + (weight / max_w) * 2.5 for weight in edge_weights]

        fig_width = max(14.0, float(params.get("width", 1200)) / 80.0)
        fig_height = max(10.0, float(params.get("height", 800)) / 80.0)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        nx.draw_networkx_edges(graph, pos, ax=ax, width=widths, edge_color="#9ca3af", alpha=0.5)
        nx.draw_networkx_nodes(graph, pos, ax=ax, node_size=node_sizes, node_color="#3b82f6", alpha=0.7, edgecolors="#1e40af", linewidths=0.5)

        label_pos = {node: (x, y + 0.08) for node, (x, y) in pos.items()}
        for node, (x, y) in label_pos.items():
            ax.text(x, y, node, fontsize=font_sizes.get(node, 8), ha="center", va="bottom", color="#1f2937", fontweight="medium",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75))

        ax.set_title("Rede de Coocorrência por Bigramas", fontsize=12, pad=10)
        ax.axis("off")
        ax.margins(0.15)
        fig.tight_layout()
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
