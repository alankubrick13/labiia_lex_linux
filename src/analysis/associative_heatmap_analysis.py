"""
Analise de Heatmap Associativo.

Calcula associações lexicais auditáveis e gera visualização principal
baseada em correlação entre tópicos, evitando confundir o usuário com
matriz termo-termo na área de gráfico.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from src.core.chart_theme import (
    ggplot_hue,
    get_sequential_cmap,
    apply_theme,
    heatmap_text_color,
    save_figure,
)
from src.core.corpus import Corpus
from src.analysis.semantic_contracts import (
    BaseSemanticParams,
    BaseSemanticResult,
    SemanticAnalysisError,
)
from src.analysis.semantic_text_base import SemanticTextBundle
from src.analysis.association_metrics import (
    AssociationPair,
    build_cooccurrence_matrix,
    compute_ppmi,
    rank_association_pairs,
)
from src.analysis.topic_modeling import LDAModelResult, train_lda
from src.analysis.semantic_graph_exports import write_summary_json

log = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class AssociativeHeatmapParams(BaseSemanticParams):
    """Parametros da analise de Heatmap Associativo."""
    min_freq: int = 2
    max_features: int = 200
    top_n_pairs: int = 100
    alpha: float = 0.75
    use_lemmas: bool = True
    n_topics: int = 6


@dataclass(slots=True, kw_only=True)
class AssociativeHeatmapResult(BaseSemanticResult):
    """Resultado da Analise Associativa."""
    association_matrix_csv_path: Path
    top_pairs_csv_path: Path
    heatmap_image_path: Path
    ranked_pairs: List[AssociationPair]

    def primary_image_path(self) -> Optional[Path]:
        return self.heatmap_image_path

    def primary_table_path(self) -> Optional[Path]:
        return self.top_pairs_csv_path


class AssociativeHeatmapAnalysis:
    """Orquestrador do Heatmap Associativo."""

    def run(self, corpus: Corpus, output_dir: Path, params: AssociativeHeatmapParams) -> AssociativeHeatmapResult:
        """Executa a analise de associacao e gera Heatmaps com hierarquia."""

        # 1. Extrair bundle no nivel de segmento (UCE) para coocorrencia mais fina
        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=params.min_freq,
            use_lemmas=params.use_lemmas,
            max_features=params.max_features,
        )

        dt_bundle = bundle.uce_term_matrix
        if dt_bundle is None or dt_bundle.matrix.shape[1] < 2:
            raise SemanticAnalysisError(
                "Vocabulario insuficiente.",
                "O Heatmap necessita de pelo menos 2 formas validas para coocorrencia.",
                "Reduza a frequencia minima ou adicione textos ao corpus."
            )

        # 2. Computar metricas esparsas
        cooc = build_cooccurrence_matrix(dt_bundle.matrix)
        ppmi = compute_ppmi(cooc, alpha=params.alpha)

        vocab = dt_bundle.vocabulary
        
        # Ranqueamento dos top pares
        top_pairs = rank_association_pairs(
            cooc=cooc,
            ppmi=ppmi,
            vocabulary=vocab,
            top_n=params.top_n_pairs,
            min_cooc=1,
        )

        # 3. Gerar CSV da Matriz Completa
        matrix_csv = output_dir / "association_matrix.csv"
        self._write_matrix_csv(ppmi, vocab, matrix_csv)

        # 4. Gerar CSV dos Principais Pares
        pairs_csv = output_dir / "top_pairs.csv"
        self._write_pairs_csv(top_pairs, pairs_csv)

        # 5. Imagem do Heatmap — tópicos LDA. Não degradar para termo-termo:
        # esse fallback muda a interpretação do gráfico principal.
        heatmap_png = output_dir / "heatmap.png"
        try:
            lda_result = train_lda(
                dtm=dt_bundle.matrix,
                vocabulary=dt_bundle.vocabulary,
                doc_ids=list(range(dt_bundle.matrix.shape[0])),
                doc_labels=[str(i) for i in range(dt_bundle.matrix.shape[0])],
                n_topics=params.n_topics,
                n_iter=200,
                random_state=params.random_state,
            )
            self._write_topic_heatmap(lda_result, heatmap_png)
        except SemanticAnalysisError:
            raise
        except Exception as exc:
            raise SemanticAnalysisError(
                "Falha no Heatmap Associativo de tópicos.",
                f"O modelo LDA interno falhou antes de gerar o mapa tópico-tópico: {exc}",
                "Verifique as dependências semânticas Python e reduza min_freq se o corpus for pequeno.",
            ) from exc

        # 6. JSON Summary
        summary_json = output_dir / "associative_summary.json"
        write_summary_json({
            "analysis_type": "associative_heatmap",
            "heatmap_mode": "topic_correlation",
            "n_topics": int(lda_result.n_topics),
            "n_terms": len(vocab),
            "n_pairs": len(top_pairs),
            "max_ppmi": float(ppmi.max()) if ppmi.nnz > 0 else 0.0,
        }, summary_json)

        return AssociativeHeatmapResult(
            analysis_type="associative_heatmap",
            output_dir=output_dir,
            association_matrix_csv_path=matrix_csv,
            top_pairs_csv_path=pairs_csv,
            heatmap_image_path=heatmap_png,
            ranked_pairs=top_pairs,
        )

    def _write_matrix_csv(self, ppmi_sparse, vocab: List[str], path: Path) -> None:
        """Salva a matriz densa PPMI reduzida em CSV."""
        # A matriz toda pode ser grande, limite aos top N por precaucao
        n_features = len(vocab)
        if n_features > 500:
            log.warning("Truncando exportacao de matriz PPMI para as top 500 features mais densas.")
            # Pegar as que tem mais variancia ou soma
            sums = np.array(ppmi_sparse.sum(axis=0)).flatten()
            top_k_indices = np.argsort(sums)[::-1][:500]
            vocab = [vocab[i] for i in top_k_indices]
            ppmi_dense = ppmi_sparse[top_k_indices, :][:, top_k_indices].toarray()
        else:
            ppmi_dense = ppmi_sparse.toarray()

        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Term"] + vocab)
            for i, term in enumerate(vocab):
                row_vals = [f"{val:.4f}" for val in ppmi_dense[i]]
                writer.writerow([term] + row_vals)

    def _write_pairs_csv(self, pairs: List[AssociationPair], path: Path) -> None:
        """Grava relatorio de ligacoes P(T1, T2)."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Term_A", "Term_B", "Co-occurrence", "PPMI"])
            for p in pairs:
                writer.writerow([p.term_a, p.term_b, p.cooccurrence, f"{p.ppmi:.4f}"])

    def _write_topic_heatmap(self, lda_result: LDAModelResult, path: Path) -> None:
        """Heatmap de correlacao de Pearson entre topicos LDA (matplotlib puro)."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        doc_topic = lda_result.doc_topic_matrix
        n_topics = lda_result.n_topics

        if n_topics < 2 or doc_topic.shape[0] < 2:
            apply_theme()
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.text(0.5, 0.5, "Corpus insuficiente para heatmap de topicos",
                    ha="center", va="center")
            save_figure(fig, path)
            return

        corr = np.corrcoef(doc_topic.T)
        corr = np.nan_to_num(corr, nan=0.0)

        short_labels = [f"T{i + 1}" for i in range(n_topics)]
        legend_lines = [f"T{i + 1}: {lda_result.topic_labels[i]}" for i in range(n_topics)]
        topic_colors = ggplot_hue(n_topics)
        cmap = get_sequential_cmap()

        apply_theme()
        fig_w = max(10, n_topics * 1.5 + 5)
        fig_h = max(8, n_topics * 1.5)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))

        im = ax.imshow(corr, cmap=cmap, vmin=-1, vmax=1, aspect="auto")

        ax.set_xticks(range(n_topics))
        ax.set_yticks(range(n_topics))
        ax.set_xticklabels(short_labels, fontsize=14, fontweight="bold", color="#2D2D2D")
        ax.set_yticklabels(short_labels, fontsize=14, fontweight="bold", color="#2D2D2D")
        ax.tick_params(length=0)

        for i in range(n_topics):
            for j in range(n_topics):
                tc = heatmap_text_color(corr[i, j], -1, 1)
                ax.text(j, i, f"{corr[i, j]:.2f}", ha="center", va="center",
                        color=tc, fontsize=12, fontweight="semibold")

        ax.set_title("Heatmap Associativo de Tópicos", fontsize=15,
                     fontweight="semibold", color="#2D2D2D", pad=15)

        # Remover spines para visual limpo
        for spine in ax.spines.values():
            spine.set_visible(False)

        fig.subplots_adjust(right=0.60, top=0.95)

        # Legenda de tópicos com swatches coloridos — ampliada para legibilidade
        import textwrap as _tw
        wrapped_lines = [_tw.fill(ln, width=38) for ln in legend_lines]
        handles = [
            mpatches.Patch(color=topic_colors[i], label=ln)
            for i, ln in enumerate(wrapped_lines)
        ]
        leg = fig.legend(
            handles=handles,
            loc="upper left",
            title="Tópicos",
            fontsize=13,
            title_fontsize=14,
            frameon=True,
            framealpha=0.95,
            edgecolor="#4878CF",
            facecolor="#F5F9FF",
            borderpad=1.0,
            labelspacing=0.9,
            handlelength=1.8,
            handleheight=1.4,
            bbox_to_anchor=(0.62, 0.92),
        )
        leg.get_title().set_fontweight("bold")
        leg.get_title().set_color("#1a3a5c")
        leg.get_frame().set_linewidth(1.4)

        # Colorbar horizontal abaixo da legenda
        cbar_ax = fig.add_axes([0.66, 0.08, 0.24, 0.035])
        cbar = fig.colorbar(im, cax=cbar_ax, orientation="horizontal")
        cbar.set_label("Correlação", fontsize=11)
        cbar.ax.tick_params(labelsize=10)

        save_figure(fig, path)

    def _write_clustered_heatmap(self, ppmi_sparse, vocab: List[str], path: Path) -> None:
        """Renderiza mapa de calor com dendrograma adjacente limitando a top 40 termos para legibilidade."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        sums = np.array(ppmi_sparse.sum(axis=0)).flatten()
        max_plot_terms = min(40, len(vocab))
        
        # Filtra top termos para graficos
        top_k_indices = np.argsort(sums)[::-1][:max_plot_terms]
        plot_vocab = [vocab[i] for i in top_k_indices]
        plot_mat = ppmi_sparse[top_k_indices, :][:, top_k_indices].toarray()

        if plot_mat.sum() == 0:
            # Matriz nula (sem ppmi significante), gera placeholder
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.text(0.5, 0.5, "Nenhuma associação forte o suficiente", ha="center")
            fig.savefig(path, bbox_inches="tight", dpi=100)
            plt.close(fig)
            return

        # Tentativa de clustering hierarquico (Seaborn sns.clustermap)
        try:
            import seaborn as sns
            import pandas as pd
            apply_theme()

            df = pd.DataFrame(plot_mat, index=plot_vocab, columns=plot_vocab)
            # Para matrizes simetricas, clustering = average
            g = sns.clustermap(
                df,
                method="average",
                metric="euclidean",
                cmap=get_sequential_cmap(),
                figsize=(10, 10),
                linewidths=0.5,
                linecolor="#E5E5E5",
                cbar_pos=(0.02, 0.8, 0.05, 0.18),
                annot=False,
                xticklabels=True,
                yticklabels=True
            )
            g.ax_heatmap.set_title("Heatmap Associativo (PPMI)", pad=50,
                                   fontsize=13, fontweight="semibold", color="#2D2D2D")
            g.savefig(path, bbox_inches="tight", dpi=120)
            plt.close(g.fig)

        except ImportError:
            # Fallback Matplotlib
            apply_theme()
            fig, ax = plt.subplots(figsize=(10, 10))
            im = ax.imshow(plot_mat, cmap=get_sequential_cmap(), vmin=0, aspect="auto")
            ax.set_xticks(np.arange(len(plot_vocab)))
            ax.set_yticks(np.arange(len(plot_vocab)))
            ax.set_xticklabels(plot_vocab, rotation=90)
            ax.set_yticklabels(plot_vocab)
            ax.set_title("Heatmap Associativo (PPMI Sem Clustering)")
            fig.colorbar(im, ax=ax)
            save_figure(fig, path)
