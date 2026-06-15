"""
Analise YAKE (Yet Another Keyword Extractor).

Conecta o pipeline de processamento de texto (SemanticTextBundle) com
o servico de extracao YAKE (keyphrase_yake) e gera os artefatos visuais.
"""

from __future__ import annotations

import csv
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import matplotlib
import matplotlib.pyplot as plt

from src.core.chart_theme import (
    ggplot_hue,
    create_figure,
    style_axes,
    add_bar_labels,
    save_figure,
)

from src.core.corpus import Corpus
from src.analysis.semantic_contracts import (
    BaseSemanticParams,
    BaseSemanticResult,
    KeyphraseCandidate,
    SemanticAnalysisError,
)
from src.analysis.semantic_text_base import SemanticTextBundle
from src.analysis.keyphrase_yake import extract_ranked_keyphrases
from src.analysis.semantic_graph_exports import write_summary_json

matplotlib.use("Agg")


@dataclass(slots=True, kw_only=True)
class YAKEParams(BaseSemanticParams):
    """Parametros da analise YAKE."""
    min_freq: int = 1
    min_tokens: int = 1
    max_tokens: int = 3
    top_n: int = 50
    dedup_threshold: float = 0.7


@dataclass(slots=True, kw_only=True)
class YAKEResult(BaseSemanticResult):
    """Resultado da analise YAKE."""
    keyphrases: List[KeyphraseCandidate]
    keyphrases_csv_path: Path
    ranking_image_path: Path

    def primary_image_path(self) -> Optional[Path]:
        return self.ranking_image_path

    def primary_table_path(self) -> Optional[Path]:
        return self.keyphrases_csv_path


class YAKEAnalysis:
    """Orquestrador da analise de Palavras-Chave (YAKE)."""

    def run(self, corpus: Corpus, output_dir: Path, params: YAKEParams) -> YAKEResult:
        """Executa a analise ponta a ponta e gera artefatos."""

        if params.min_freq < 1:
            raise SemanticAnalysisError(
                "Frequência mínima inválida.",
                "O YAKE requer que a frequência mínima das palavras seja maior ou igual a 1.",
                "Ajuste a frequência mínima nos parâmetros de entrada."
            )

        # 1. Carregar textos
        bundle = SemanticTextBundle.from_corpus(corpus, min_freq=1)
        texts = [seg.text for seg in bundle.segments]

        if not texts:
            raise SemanticAnalysisError(
                "Corpus vazio ou inválido.",
                "Não foi possível extrair textos válidos do corpus.",
                "Verifique se o corpus não está vazio."
            )

        # 2. Executar pipeline YAKE
        ranked = extract_ranked_keyphrases(
            texts,
            min_tokens=params.min_tokens,
            max_tokens=params.max_tokens,
            min_freq=params.min_freq,
            top_n=params.top_n,
            dedup_threshold=params.dedup_threshold,
        )

        # 3. Exportar artefatos
        csv_path = output_dir / "yake_keyphrases.csv"
        self._write_csv(ranked, csv_path)

        png_path = output_dir / "yake_ranking.png"
        self._write_plot(ranked, png_path)

        json_path = output_dir / "yake_summary.json"
        write_summary_json({
            "analysis_type": "yake",
            "n_keyphrases": len(ranked),
            "min_freq": params.min_freq,
            "top_n": params.top_n,
            "dedup_threshold": params.dedup_threshold,
        }, json_path)

        return YAKEResult(
            analysis_type="yake",
            output_dir=output_dir,
            keyphrases=ranked,
            keyphrases_csv_path=csv_path,
            ranking_image_path=png_path,
        )

    def _write_csv(self, keyphrases: List[KeyphraseCandidate], path: Path) -> None:
        """Grava a tabela de keyphrases em CSV."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Phrase", "RawYAKE", "Relevance", "Frequency", "DocCount"])
            for kp in keyphrases:
                writer.writerow([
                    kp.phrase,
                    "" if kp.raw_yake_score is None else f"{kp.raw_yake_score:.6f}",
                    f"{kp.score:.3f}",
                    kp.frequency,
                    kp.doc_count,
                ])

    def _write_plot(self, keyphrases: List[KeyphraseCandidate], path: Path) -> None:
        """Pinta um grafico de barras horizontais do top N com tema ggplot2."""
        plot_data = keyphrases[:15]
        if not plot_data:
            fig, ax, _ = create_figure(width=6, height=4)
            ax.text(0.5, 0.5, "Nenhuma palavra-chave encontrada",
                    ha="center", va="center", transform=ax.transAxes)
            save_figure(fig, path)
            return

        plot_data = plot_data[::-1]
        labels = [textwrap.fill(kp.phrase, width=32) for kp in plot_data]
        scores = [max(0.0, float(kp.score)) for kp in plot_data]

        max_label_chars = max((len(l) for l in labels), default=10)
        fig_width = max(8, min(16, 6 + max_label_chars * 0.12))
        n = len(labels)
        colors = ggplot_hue(n)

        fig, ax, _ = create_figure(width=fig_width, height=_map_height(n))
        bars = ax.barh(labels, scores, color=colors, height=0.7)
        ax.set_xlim(left=0)
        ax.set_xlabel("YAKE Relevância")
        ax.set_title("Ranking de Palavras-Chave (YAKE)")
        style_axes(ax, grid_axis="x", spines=("bottom", "left"))
        add_bar_labels(ax, bars, scores, sum(scores) or 1,
                       fmt="{v:.3f}", horizontal=True)
        fig.subplots_adjust(top=0.95, left=0.32)
        save_figure(fig, path)


def _map_height(n_items: int) -> float:
    """Ajusta altura do plot conforme numero de itens (min=4.0, max=10.0)."""
    h = 0.4 * n_items
    return max(4.0, min(10.0, h))
