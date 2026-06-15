"""Extra trigram co-occurrence network analysis.

Produces:
- A directed trigram network graph (PNG)
- A trigram edges CSV (word_1;word_2;word_3;frequency)
- A combined bigram+trigram CSV (ngram_type;word_1;word_2;word_3;frequency)
"""

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
class TrigramNetworkExtraResult:
    """Result payload for trigram network analysis."""

    graph_path: Optional[Path]
    edges_path: Optional[Path]
    combined_path: Optional[Path]
    n_nodes: int
    n_edges: int


class TrigramNetworkExtraAnalysisError(Exception):
    """Friendly error for trigram network extra analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = (
            f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        )
        super().__init__(message)


class TrigramNetworkExtraAnalysis:
    """Build and visualize a trigram co-occurrence network."""

    DEFAULT_PARAMS: Dict[str, Any] = {
        "min_trigram_freq": 2,
        "top_edges": 120,
        "width": 1200,
        "height": 800,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, params: Optional[Dict[str, Any]] = None) -> TrigramNetworkExtraResult:
        """Execute trigram network extraction and visualization."""
        import networkx as nx

        config = {**self.DEFAULT_PARAMS, **(params or {})}
        min_trigram_freq = max(1, int(config.get("min_trigram_freq", 2)))
        top_edges = max(20, int(config.get("top_edges", 120)))

        records = build_uci_records(self.corpus)
        if not records:
            raise TrigramNetworkExtraAnalysisError(
                what="Corpus sem textos para rede de trigramas.",
                why="Nenhuma UCI foi encontrada no corpus carregado.",
                how="Importe um corpus válido e tente novamente.",
            )

        # --- Extrair trigramas -------------------------------------------
        trigram_counter: Counter[Tuple[str, str, str]] = Counter()
        bigram_counter: Counter[Tuple[str, str]] = Counter()

        for record in records:
            tokens = tokenize_text(record.text, remove_stopwords=True)
            # bigramas (para exportação conjunta)
            if len(tokens) >= 2:
                for w1, w2 in zip(tokens, tokens[1:]):
                    bigram_counter[(w1, w2)] += 1
            # trigramas
            if len(tokens) >= 3:
                for w1, w2, w3 in zip(tokens, tokens[1:], tokens[2:]):
                    trigram_counter[(w1, w2, w3)] += 1

        filtered: List[Tuple[str, str, str, int]] = [
            (w1, w2, w3, int(freq))
            for (w1, w2, w3), freq in trigram_counter.items()
            if int(freq) >= min_trigram_freq
        ]
        filtered.sort(key=lambda item: item[3], reverse=True)
        top_filtered = filtered[:top_edges]

        if not top_filtered:
            raise TrigramNetworkExtraAnalysisError(
                what="Nenhum trigrama atingiu a frequência mínima.",
                why="As sequências de três palavras ficaram abaixo do limiar configurado.",
                how="Reduza a frequência mínima ou use um corpus maior.",
            )

        # --- Grafo: nós = palavras, arestas = par vizinho dentro do trigrama --
        graph = nx.Graph()
        for w1, w2, w3, freq in top_filtered:
            # Adiciona as duas arestas que compõem o trigrama
            if graph.has_edge(w1, w2):
                graph[w1][w2]["weight"] += freq
            else:
                graph.add_edge(w1, w2, weight=freq)
            if graph.has_edge(w2, w3):
                graph[w2][w3]["weight"] += freq
            else:
                graph.add_edge(w2, w3, weight=freq)

        # --- Exportar artefatos -------------------------------------------
        edges_path = self.output_dir / "trigram_network_edges.csv"
        self._write_trigram_edges_csv(edges_path, top_filtered)

        combined_path = self.output_dir / "ngram_combined_edges.csv"
        self._write_combined_csv(combined_path, bigram_counter, top_filtered)

        graph_path = self.output_dir / "trigram_network.png"
        self._plot_network(graph_path, graph, config)

        return TrigramNetworkExtraResult(
            graph_path=graph_path if graph_path.exists() else None,
            edges_path=edges_path if edges_path.exists() else None,
            combined_path=combined_path if combined_path.exists() else None,
            n_nodes=graph.number_of_nodes(),
            n_edges=graph.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # CSV helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_trigram_edges_csv(
        path: Path, rows: List[Tuple[str, str, str, int]]
    ) -> None:
        """Escreve CSV exclusivo de trigramas (word_1;word_2;word_3;frequency)."""
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["word_1", "word_2", "word_3", "frequency"])
            for w1, w2, w3, freq in rows:
                writer.writerow([w1, w2, w3, freq])

    @staticmethod
    def _write_combined_csv(
        path: Path,
        bigram_counter: Counter,
        trigram_rows: List[Tuple[str, str, str, int]],
    ) -> None:
        """Escreve CSV conjunto com bigramas e trigramas.

        Colunas: ngram_type;word_1;word_2;word_3;frequency
        Para bigramas, word_3 fica em branco.
        """
        bigram_rows = sorted(
            ((w1, w2, int(f)) for (w1, w2), f in bigram_counter.items()),
            key=lambda x: x[2],
            reverse=True,
        )
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["ngram_type", "word_1", "word_2", "word_3", "frequency"])
            for w1, w2, freq in bigram_rows:
                writer.writerow(["bigram", w1, w2, "", freq])
            for w1, w2, w3, freq in trigram_rows:
                writer.writerow(["trigram", w1, w2, w3, freq])

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------

    def _plot_network(self, path: Path, graph, params: Dict[str, Any]) -> None:
        """Gera gráfico de rede usando R (se disponível) ou matplotlib."""
        from .readable_network_plot import write_readable_network_plot

        if graph.number_of_nodes() <= 0:
            return
        write_readable_network_plot(
            graph,
            path,
            title="Rede de Coocorrência por Trigramas",
            max_labels=max(24, min(60, int(params.get("top_edges", 60) or 60))),
        )
        return

        import json
        import subprocess

        if graph.number_of_nodes() <= 0:
            return

        # Exportar arestas para R (formato compatível com bigram_network.R)
        edges_csv = path.parent / "trigram_edges_for_r.csv"
        with edges_csv.open("w", encoding="utf-8", newline="") as fh:
            fh.write("word_1;word_2;frequency\n")
            for u, v, data in graph.edges(data=True):
                fh.write(f"{u};{v};{data.get('weight', 1)}\n")

        r_params = {
            "edges_file": str(edges_csv),
            "output_file": str(path),
            "width": params.get("width", 1200),
            "height": params.get("height", 900),
            "top_words": params.get("top_edges", 30),
            "min_freq": 0.5,
            "edge_alpha": 0.4,
            "edge_color": "#6D28D9",
            "vertex_color": "#4C1D95",
            "vertex_size": 3,
            "title": "Rede de Coocorrência por Trigramas",
        }

        params_file = path.parent / "trigram_params.json"
        with params_file.open("w", encoding="utf-8") as fh:
            json.dump(r_params, fh, indent=2)

        # Tenta reutilizar o script R de bigramas (aceita qualquer CSV word_1;word_2;freq)
        r_script = (
            Path(__file__).parent.parent
            / "visualization"
            / "r_integration"
            / "r_scripts"
            / "bigram_network.R"
        )

        if not r_script.exists():
            self._logger.warning("R script não encontrado, usando matplotlib.")
            self._plot_network_fallback(path, graph, params)
            return

        rscript_paths = [
            "Rscript",
            r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe",
            r"C:\Program Files\R\R-4.4.0\bin\Rscript.exe",
            r"C:\Program Files\R\R-4.3.0\bin\Rscript.exe",
        ]
        rscript_exe = None
        for rpath in rscript_paths:
            try:
                res = subprocess.run(
                    [rpath, "--version"],
                    capture_output=True,
                    timeout=5,
                    **no_console_kwargs(),
                )
                if res.returncode == 0:
                    rscript_exe = rpath
                    break
            except Exception:
                continue

        if rscript_exe is None:
            self._logger.warning("Rscript não encontrado, usando matplotlib.")
            self._plot_network_fallback(path, graph, params)
            return

        try:
            res = subprocess.run(
                [rscript_exe, str(r_script), str(params_file)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(path.parent),
                **no_console_kwargs(),
            )
            if res.returncode != 0:
                self._logger.warning(f"R script falhou: {res.stderr}")
                self._plot_network_fallback(path, graph, params)
            else:
                self._logger.info("Rede de trigramas gerada com R.")
        except Exception as exc:
            self._logger.warning(f"Erro ao executar R: {exc}, usando matplotlib.")
            self._plot_network_fallback(path, graph, params)

    def _plot_network_fallback(self, path: Path, graph, params: Dict[str, Any]) -> None:
        """Fallback matplotlib quando R não está disponível."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx

        if graph.number_of_nodes() <= 0:
            return

        n_nodes = graph.number_of_nodes()
        k_value = max(2.5, 3.5 + (n_nodes / 40))
        pos = nx.spring_layout(
            graph, k=k_value, iterations=300, seed=42, weight="weight", scale=2.0
        )

        node_strength = dict(graph.degree(weight="weight"))
        strengths = list(node_strength.values()) or [1.0]
        min_s, max_s = min(strengths), max(strengths)
        scale = (max_s - min_s) if (max_s - min_s) > 0 else 1.0

        node_sizes = [
            80.0 + ((node_strength.get(n, min_s) - min_s) / scale) * 400.0
            for n in graph.nodes()
        ]
        font_sizes = {
            n: 7 + int(((node_strength.get(n, min_s) - min_s) / scale) * 6)
            for n in graph.nodes()
        }
        edge_weights = [float(graph[u][v].get("weight", 1.0)) for u, v in graph.edges()]
        max_w = max(edge_weights) if edge_weights else 1.0
        widths = [0.4 + (w / max_w) * 2.5 for w in edge_weights]

        fig_width = max(14.0, float(params.get("width", 1200)) / 80.0)
        fig_height = max(10.0, float(params.get("height", 800)) / 80.0)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        nx.draw_networkx_edges(
            graph, pos, ax=ax, width=widths, edge_color="#c4b5fd", alpha=0.5
        )
        nx.draw_networkx_nodes(
            graph, pos, ax=ax,
            node_size=node_sizes,
            node_color="#7c3aed",
            alpha=0.7,
            edgecolors="#4c1d95",
            linewidths=0.5,
        )
        label_pos = {n: (x, y + 0.08) for n, (x, y) in pos.items()}
        for n, (x, y) in label_pos.items():
            ax.text(
                x, y, n,
                fontsize=font_sizes.get(n, 8),
                ha="center", va="bottom",
                color="#1f2937", fontweight="medium",
                bbox=dict(
                    boxstyle="round,pad=0.15",
                    facecolor="white",
                    edgecolor="none",
                    alpha=0.75,
                ),
            )

        ax.set_title("Rede de Coocorrência por Trigramas", fontsize=12, pad=10)
        ax.axis("off")
        ax.margins(0.15)
        fig.tight_layout()
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
