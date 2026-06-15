"""
Analise CHD Tematico (Classificacao Hierarquica Descendente Tematica).

Combina o agrupamento lexico rigido do CHD/ALCESTE com a
flexibilidade dos topicos do LDA, rotulando automaticamente
as classes extraidas com relacoes tematicas.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from src.core.chart_theme import (
    ggplot_hue,
    get_sequential_cmap,
    apply_theme,
    style_axes,
    heatmap_text_color,
    save_figure,
)

from src.core.corpus import Corpus
from src.analysis.semantic_contracts import (
    BaseSemanticParams,
    BaseSemanticResult,
    SemanticAnalysisError,
)
from src.analysis.chd_reinert import CHDAnalysis, CHDResult
from src.analysis.topic_modeling import train_lda
from src.analysis.semantic_graph_exports import write_summary_json

matplotlib.use("Agg")
log = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class ThematicCHDParams(BaseSemanticParams):
    """Parametros da analise CHD Tematica."""
    n_topics: int = 5
    min_freq: int = 2
    max_features: int = 2000
    chd_params: Optional[Dict[str, Any]] = None


@dataclass(slots=True, kw_only=True)
class ThematicCHDResult(BaseSemanticResult):
    """Resultado da extracao CHD Tematico."""
    chd_result: CHDResult
    class_topic_heatmap_path: Path
    class_topic_mix_csv_path: Path
    class_labels_json_path: Path

    def primary_image_path(self) -> Optional[Path]:
        return self.class_topic_heatmap_path

    def primary_table_path(self) -> Optional[Path]:
        return self.class_topic_mix_csv_path


class ThematicCHDAnalysis:
    """Orquestrador do cruzamento de CHD e LDA."""

    def run(self, corpus: Corpus, output_dir: Path, params: ThematicCHDParams) -> ThematicCHDResult:
        
        # 1. Executar CHD Base
        chd_args = params.chd_params or {}
        chd_analysis = CHDAnalysis(corpus, output_dir)
        try:
            chd_res = chd_analysis.run(chd_args)
        except Exception as e:
            raise SemanticAnalysisError(
                "Falha na base CHD.",
                f"O modulo CHD falhou ao extrair as classes: {e}",
                "Verifique se o IRaMuTeQ esta configurado ou mude os limites do corpus."
            )
            
        if not chd_res.class_text_paths:
            raise SemanticAnalysisError(
                "Falha na integracao CHD/LDA.",
                "O CHD retornou sucesso mas nao alocou os textos (UCEs) nas classes.",
                "Certifique-se de que o CHD esta extraindo os segmentos tipicos corretamente."
            )

        # 2. Resgatar Textos Agrupados por Classe
        all_texts = []
        all_cids = []
        
        for cid, path in chd_res.class_text_paths.items():
            if not path.exists():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for ln in lines:
                text = ln.strip()
                if text:
                    all_texts.append(text)
                    all_cids.append(cid)

        if len(all_texts) < params.n_topics:
            raise SemanticAnalysisError(
                "Insuficiencia de textos nas classes.",
                "O numero de segmentos recuperados pelo CHD e muito pequeno para modelagem de topicos.",
                "Diminua o numero de topicos procurados ou o tamanho minimo das classes."
            )

        # 3. Treinar LDA nas UCEs agrupadas
        try:
            from sklearn.feature_extraction.text import CountVectorizer
            vectorizer = CountVectorizer(
                min_df=params.min_freq,
                max_features=params.max_features if params.max_features > 0 else None
            )
            dtm = vectorizer.fit_transform(all_texts)
            vocabulary = vectorizer.get_feature_names_out().tolist()
            doc_ids = list(range(len(all_texts)))
            doc_labels = [f"UCE_{i}" for i in doc_ids]

            lda_model = train_lda(
                dtm=dtm,
                vocabulary=vocabulary,
                doc_ids=doc_ids,
                doc_labels=doc_labels,
                n_topics=params.n_topics,
            )
        except Exception as e:
            raise SemanticAnalysisError(
                "Falha na Modelagem de Topicos (LDA).",
                f"O modelo LDA falhou ao processar os textos das classes: {e}",
                "Use min_freq menor ou max_features maior."
            )

        # 4. Agregar a distribuicao de Topicos por Classe
        # doc_topic e matriz N_docs x K_topics
        doc_topic = lda_model.doc_topic_matrix
        
        unique_classes = sorted(list(set(all_cids)))
        class_topic_mix = np.zeros((len(unique_classes), params.n_topics))
        
        for i, cid in enumerate(unique_classes):
            # Encontrar docs que pertencem a essa classe
            indices = [idx for idx, c in enumerate(all_cids) if c == cid]
            if not indices:
                continue
            # Media das probabilidades de topico para os textos dessa classe
            class_avg = doc_topic[indices, :].mean(axis=0)
            class_topic_mix[i, :] = class_avg

        # 5. Nomear as Classes dinamicamente com base no Topico Dominante
        class_labels: Dict[str, Dict[str, Any]] = {}
        top_terms_by_topic = lda_model.topic_terms
        
        for i, cid in enumerate(unique_classes):
            dominant_topic_idx = int(np.argmax(class_topic_mix[i, :]))
            # Pega as 3 principais palavras do topico
            topic_obj = lda_model.topic_terms[dominant_topic_idx]
            top_words = [t[0] for t in topic_obj.terms[:3]]
            label = " - ".join(top_words).title() if top_words else f"Tema {dominant_topic_idx+1}"
            
            class_labels[str(cid)] = {
                "theme": label,
                "top_words": top_words,
                "dominant_topic": dominant_topic_idx,
                "topic_intensity": float(class_topic_mix[i, dominant_topic_idx])
            }

        # 6. Gerar Matriz CSV
        mix_csv = output_dir / "class_topic_mix.csv"
        self._write_mix_csv(class_topic_mix, unique_classes, params.n_topics, mix_csv)

        # 7. Gerar Labels JSON
        labels_json = output_dir / "class_labels.json"
        with open(labels_json, "w", encoding="utf-8") as f:
            json.dump(class_labels, f, indent=4, ensure_ascii=False)

        # 8. Plotar Heatmap
        heatmap_png = output_dir / "thematic_chd_class_topic_heatmap.png"
        topic_labels = [
            ", ".join(t[0] for t in lda_model.topic_terms[i].terms[:5])
            for i in range(params.n_topics)
        ]
        self._write_heatmap(class_topic_mix, unique_classes, params.n_topics, class_labels, topic_labels, heatmap_png)

        # 9. Resumo da analise
        write_summary_json({
            "analysis_type": "thematic_chd",
            "n_classes": len(unique_classes),
            "n_topics": params.n_topics,
        }, output_dir / "thematic_diagnostics.json")

        return ThematicCHDResult(
            analysis_type="thematic_chd",
            output_dir=output_dir,
            chd_result=chd_res,
            class_topic_heatmap_path=heatmap_png,
            class_topic_mix_csv_path=mix_csv,
            class_labels_json_path=labels_json,
        )

    def _write_mix_csv(self, mix_matrix: np.ndarray, classes: List[int], n_topics: int, path: Path) -> None:
        """Salva a mistura Classes x Topicos."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            header = ["Classe\\Topico"] + [f"Topico_{i+1}" for i in range(n_topics)]
            writer.writerow(header)
            
            for i, cid in enumerate(classes):
                row = [f"Classe {cid}"] + [f"{v:.4f}" for v in mix_matrix[i, :]]
                writer.writerow(row)

    def _write_heatmap(
        self,
        mix: np.ndarray,
        classes: List[int],
        n_topics: int,
        labels: Dict[str, Any],
        topic_labels: List[str],
        path: Path,
    ) -> None:
        """Renderiza mapa de calor da distribuicao de topicos nas classes."""
        import textwrap
        import matplotlib.patches as mpatches
        apply_theme()

        n_classes = len(classes)
        cell_w = max(2.2, 12.0 / max(n_topics, 1))
        cell_h = max(1.6, 10.0 / max(n_classes, 1))
        # Largura extra à direita para acomodar a legenda lateral
        fig_w = max(20, n_topics * cell_w + 9)
        fig_h = max(10, n_classes * cell_h + 4)

        fig = plt.figure(figsize=(fig_w, fig_h), facecolor="#FFFFFF")

        # Heatmap ocupa parte esquerda; legenda fica à direita via fig.legend
        ax = fig.add_axes([0.22, 0.10, 0.50, 0.80])

        cmap = get_sequential_cmap()
        vmin, vmax = 0.0, 1.0
        im = ax.imshow(mix, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax)

        ax.set_yticks(np.arange(n_classes))
        ax.set_xticks(np.arange(n_topics))

        y_labels = []
        for c in classes:
            theme = labels[str(c)]["theme"]
            wrapped = textwrap.fill(theme, width=24)
            y_labels.append(f"Classe {c}\n{wrapped}")

        x_labels = [f"T{i + 1}" for i in range(n_topics)]
        ax.set_yticklabels(y_labels, fontsize=11, va="center", linespacing=1.3,
                           color="#444444")
        ax.set_xticklabels(x_labels, rotation=0, fontsize=13, fontweight="bold",
                           color="#2D2D2D")
        ax.tick_params(axis="y", length=0, pad=8)
        ax.tick_params(axis="x", length=0, pad=6)
        style_axes(ax, grid_axis="none", spines=())

        for i in range(n_classes):
            for j in range(n_topics):
                val = mix[i, j]
                tc = heatmap_text_color(val, vmin, vmax)
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        color=tc, fontsize=11, fontweight="bold")

        ax.set_title("Identidade Temática — CHD + LDA",
                     fontsize=16, fontweight="bold", pad=18, color="#2D2D2D")

        cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cbar.set_label("Probabilidade média do tópico", fontsize=10, color="#4D4D4D")
        cbar.ax.tick_params(labelsize=9)

        # Legenda à direita — itens em linha única (sem quebra), formato parecido
        # com o Heatmap Associativo. Há espaço horizontal de sobra à direita.
        topic_colors = ggplot_hue(n_topics)
        legend_lines = [f"T{i + 1}: {lbl}" for i, lbl in enumerate(topic_labels)]
        handles = [
            mpatches.Patch(color=topic_colors[i % len(topic_colors)], label=ln)
            for i, ln in enumerate(legend_lines)
        ]
        leg = fig.legend(
            handles=handles,
            loc="upper left",
            title="Tópicos LDA",
            fontsize=13,
            title_fontsize=14,
            frameon=True,
            framealpha=0.95,
            edgecolor="#4878CF",
            facecolor="#F5F9FF",
            borderpad=1.0,
            labelspacing=0.8,
            handlelength=1.8,
            handleheight=1.4,
            bbox_to_anchor=(0.76, 0.90),
        )
        leg.get_title().set_fontweight("bold")
        leg.get_title().set_color("#1a3a5c")
        leg.get_frame().set_linewidth(1.4)

        save_figure(fig, path, dpi=130)
