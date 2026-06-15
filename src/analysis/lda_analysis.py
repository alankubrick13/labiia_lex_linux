"""
Analise LDA (Modelagem de Topicos).

Implementacao robusta:
- backend principal R/topicmodels (VEM/Gibbs)
- fallback Python (lda-project) para compatibilidade
- saidas auditaveis beta/gamma e tuning de k
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from src.core.chart_theme import (
    add_bar_labels,
    create_figure,
    draw_legend_panel,
    get_sequential_cmap,
    ggplot_hue,
    heatmap_text_color,
    save_figure,
    style_axes,
)

from src.analysis.semantic_contracts import (
    ArtifactManifest,
    BaseSemanticParams,
    BaseSemanticResult,
    SemanticAnalysisError,
)
from src.analysis.semantic_text_base import SemanticTextBundle
from src.analysis.topic_modeling import (
    LDAModelResult,
    train_lda_classic,
)
from src.analysis.lda_diagnostics import compute_stability_rows, write_advanced_lda_diagnostics
from src.analysis.extractive_summary import (
    rank_representative_sentences,
    sentences_from_bundle,
    topic_targets_from_model,
    write_representative_sentences_csv,
)
from src.core.corpus import Corpus
from src.analysis.semantic_graph_exports import write_summary_json

matplotlib.use("Agg")


@dataclass(slots=True, kw_only=True)
class LDAParams(BaseSemanticParams):
    """Parâmetros da análise LDA clássica."""

    # Compatibilidade: n_topics antigo continua aceito; k é a chave canônica.
    k: int = 6
    n_topics: Optional[int] = None
    seed: Optional[int] = None
    method: str = "VEM"  # VEM | Gibbs

    min_freq: int = 2
    max_features: int = 2000
    n_iter: int = 500
    use_lemmas: bool = True

    # Controles do Gibbs (aplicados apenas quando method == Gibbs)
    gibbs_burnin: int = 1000
    gibbs_iter: int = 1000
    gibbs_thin: int = 100

    # Tuning de k
    enable_k_tuning: bool = False
    k_min: int = 2
    k_max: int = 20
    enable_advanced_diagnostics: bool = False
    stability_n_seeds: int = 3
    diagnostic_k_min: Optional[int] = None
    diagnostic_k_max: Optional[int] = None

    def __post_init__(self) -> None:
        if self.n_topics is not None:
            self.k = int(self.n_topics)
        self.k = int(self.k)
        self.n_topics = self.k
        if self.seed is not None:
            self.random_state = int(self.seed)
        else:
            self.seed = int(self.random_state)
        self.method = str(self.method or "VEM").strip().upper()
        if self.method not in {"VEM", "GIBBS"}:
            self.method = "VEM"
        self.min_freq = max(1, int(self.min_freq))
        self.max_features = max(10, int(self.max_features))
        self.n_iter = max(50, int(self.n_iter))
        self.gibbs_burnin = max(0, int(self.gibbs_burnin))
        self.gibbs_iter = max(50, int(self.gibbs_iter))
        self.gibbs_thin = max(1, int(self.gibbs_thin))
        self.enable_k_tuning = bool(self.enable_k_tuning)
        self.enable_advanced_diagnostics = bool(self.enable_advanced_diagnostics)
        self.stability_n_seeds = max(1, int(self.stability_n_seeds))
        self.k_min = max(2, int(self.k_min))
        self.k_max = max(self.k_min, int(self.k_max))
        if self.diagnostic_k_min is not None:
            self.diagnostic_k_min = max(2, int(self.diagnostic_k_min))
        if self.diagnostic_k_max is not None:
            self.diagnostic_k_max = max(2, int(self.diagnostic_k_max))


@dataclass(slots=True, kw_only=True)
class LDAResult(BaseSemanticResult):
    """Resultado da análise LDA."""

    model_result: LDAModelResult
    topics_csv_path: Path
    doc_topic_csv_path: Path
    terms_beta_csv_path: Path
    documents_gamma_csv_path: Path
    distribution_image_path: Path
    top_terms_image_path: Path
    heatmap_image_path: Path
    timeline_image_path: Optional[Path] = None
    tuning_csv_path: Optional[Path] = None
    tuning_image_path: Optional[Path] = None
    diagnostics_image_path: Optional[Path] = None
    topic_diagnostics_csv_path: Optional[Path] = None
    document_mixing_csv_path: Optional[Path] = None
    k_quality_csv_path: Optional[Path] = None
    stability_csv_path: Optional[Path] = None
    stability_summary_json_path: Optional[Path] = None
    representative_sentences_csv_path: Optional[Path] = None
    summary_json_path: Optional[Path] = None
    method: str = "VEM"
    k_requested: int = 0
    k_effective: int = 0
    seed: int = 42
    backend: str = "r_topicmodels"
    tuning_available: bool = False

    def primary_image_path(self) -> Optional[Path]:
        return self.distribution_image_path

    def primary_table_path(self) -> Optional[Path]:
        return self.terms_beta_csv_path

    def artifact_manifest(self) -> ArtifactManifest:
        secondary_images: List[Path] = [self.top_terms_image_path, self.heatmap_image_path]
        if self.timeline_image_path is not None and self.timeline_image_path.exists():
            secondary_images.append(self.timeline_image_path)
        if self.tuning_image_path is not None and self.tuning_image_path.exists():
            secondary_images.append(self.tuning_image_path)
        if self.diagnostics_image_path is not None and self.diagnostics_image_path.exists():
            secondary_images.append(self.diagnostics_image_path)

        secondary_tables: List[Path] = [self.documents_gamma_csv_path, self.doc_topic_csv_path, self.topics_csv_path]
        if self.tuning_csv_path is not None and self.tuning_csv_path.exists():
            secondary_tables.append(self.tuning_csv_path)
        for extra_table in (
            self.topic_diagnostics_csv_path,
            self.document_mixing_csv_path,
            self.k_quality_csv_path,
            self.stability_csv_path,
            self.representative_sentences_csv_path,
        ):
            if extra_table is not None and extra_table.exists():
                secondary_tables.append(extra_table)

        extra_files: List[Path] = []
        if self.summary_json_path is not None and self.summary_json_path.exists():
            extra_files.append(self.summary_json_path)
        if self.stability_summary_json_path is not None and self.stability_summary_json_path.exists():
            extra_files.append(self.stability_summary_json_path)

        return ArtifactManifest(
            primary_image=self.primary_image_path(),
            primary_table=self.primary_table_path(),
            summary_json=self.summary_json_path,
            secondary_images=secondary_images,
            secondary_tables=secondary_tables,
            extra_files=extra_files,
        )

    def to_history_metadata(self) -> Dict[str, object]:
        meta = super().to_history_metadata()
        graph_gallery: Dict[str, str] = {
            "Distribuição de Tópicos": str(self.distribution_image_path),
            "Top Termos por Tópico": str(self.top_terms_image_path),
            "Heatmap Doc-Tópico": str(self.heatmap_image_path),
        }
        if self.tuning_image_path is not None and self.tuning_image_path.exists():
            graph_gallery["Tuning de k"] = str(self.tuning_image_path)
        if self.timeline_image_path is not None and self.timeline_image_path.exists():
            graph_gallery["Linha do Tempo"] = str(self.timeline_image_path)
        if self.diagnostics_image_path is not None and self.diagnostics_image_path.exists():
            graph_gallery["Diagnóstico Avançado"] = str(self.diagnostics_image_path)

        table_gallery: Dict[str, str] = {
            "Termos por Tópico (beta)": str(self.terms_beta_csv_path),
            "Prevalência Doc-Tópico (gamma)": str(self.documents_gamma_csv_path),
            "Distribuição Doc-Tópico": str(self.doc_topic_csv_path),
            "Termos por Tópico (compat)": str(self.topics_csv_path),
        }
        if self.tuning_csv_path is not None and self.tuning_csv_path.exists():
            table_gallery["Tuning de k"] = str(self.tuning_csv_path)
        if self.topic_diagnostics_csv_path is not None and self.topic_diagnostics_csv_path.exists():
            table_gallery["Diagnóstico de Tópicos"] = str(self.topic_diagnostics_csv_path)
        if self.document_mixing_csv_path is not None and self.document_mixing_csv_path.exists():
            table_gallery["Documentos Misturados"] = str(self.document_mixing_csv_path)
        if self.k_quality_csv_path is not None and self.k_quality_csv_path.exists():
            table_gallery["Qualidade por K"] = str(self.k_quality_csv_path)
        if self.stability_csv_path is not None and self.stability_csv_path.exists():
            table_gallery["Estabilidade por Seed"] = str(self.stability_csv_path)
        if self.representative_sentences_csv_path is not None and self.representative_sentences_csv_path.exists():
            table_gallery["Frases Representativas"] = str(self.representative_sentences_csv_path)

        meta.update(
            {
                "method": self.method,
                "seed": self.seed,
                "k_requested": self.k_requested,
                "k_effective": self.k_effective,
                "backend": self.backend,
                "perplexity": self.model_result.perplexity,
                "tuning_available": self.tuning_available,
                "terms_beta_csv_path": str(self.terms_beta_csv_path),
                "documents_gamma_csv_path": str(self.documents_gamma_csv_path),
                "graph_gallery": graph_gallery,
                "table_gallery": table_gallery,
            }
        )
        if self.tuning_csv_path is not None:
            meta["tuning_csv_path"] = str(self.tuning_csv_path)
        if self.tuning_image_path is not None:
            meta["tuning_plot_path"] = str(self.tuning_image_path)
        if self.diagnostics_image_path is not None:
            meta["diagnostics_image_path"] = str(self.diagnostics_image_path)
        if self.representative_sentences_csv_path is not None:
            meta["representative_sentences_csv_path"] = str(self.representative_sentences_csv_path)
        return meta


class LDAAnalysis:
    """Orquestrador da análise de tópicos (LDA)."""

    def run(self, corpus: Corpus, output_dir: Path, params: LDAParams) -> LDAResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if params.k < 1:
            raise SemanticAnalysisError(
                "Número de tópicos inválido.",
                "O LDA requer pelo menos 1 tópico.",
                "Aumente o valor de k.",
            )

        bundle = SemanticTextBundle.from_corpus(
            corpus,
            min_freq=params.min_freq,
            use_lemmas=params.use_lemmas,
            max_features=params.max_features,
        )
        dt_bundle = bundle.doc_term_matrix
        if dt_bundle is None or dt_bundle.matrix.shape[0] < 2:
            raise SemanticAnalysisError(
                "Documentos insuficientes.",
                "Modelagem de tópicos requer pelo menos 2 documentos (UCIs).",
                "Use um corpus maior.",
            )

        doc_labels = [bundle.doc_id_to_label.get(did, f"Doc_{did}") for did in dt_bundle.row_ids]

        diag_k_min = params.diagnostic_k_min if params.diagnostic_k_min is not None else max(2, params.k - 2)
        diag_k_max = params.diagnostic_k_max if params.diagnostic_k_max is not None else max(diag_k_min, params.k + 2)

        model_result = train_lda_classic(
            dtm=dt_bundle.matrix,
            vocabulary=dt_bundle.vocabulary,
            doc_ids=dt_bundle.row_ids,
            doc_labels=doc_labels,
            output_dir=output_dir,
            k=params.k,
            method=params.method,
            seed=int(params.seed or params.random_state),
            gibbs_burnin=params.gibbs_burnin,
            gibbs_iter=params.gibbs_iter if params.method == "GIBBS" else params.n_iter,
            gibbs_thin=params.gibbs_thin,
            n_top_terms=15,
            enable_tuning=bool(params.enable_k_tuning or params.enable_advanced_diagnostics),
            k_min=diag_k_min if params.enable_advanced_diagnostics else params.k_min,
            k_max=diag_k_max if params.enable_advanced_diagnostics else params.k_max,
            fallback_to_python=True,
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        topics_csv = output_dir / "lda_topics.csv"
        self._write_topics_csv(model_result, topics_csv)

        doc_topic_csv = output_dir / "lda_doc_topic.csv"
        self._write_doc_topic_csv(model_result, doc_topic_csv)

        terms_beta_csv = output_dir / "lda_terms_beta.csv"
        self._write_terms_beta_csv(model_result, terms_beta_csv)

        documents_gamma_csv = output_dir / "lda_documents_gamma.csv"
        self._write_documents_gamma_csv(model_result, documents_gamma_csv)

        dist_png = output_dir / "lda_distribution.png"
        self._write_distribution_plot(model_result, dist_png)

        top_terms_png = output_dir / "lda_top_terms.png"
        self._write_top_terms_plot(model_result, top_terms_png, top_n=10)

        heatmap_png = output_dir / "lda_doc_topic_heatmap.png"
        self._write_heatmap(model_result, heatmap_png)

        timeline_png = None
        if bundle.has_temporal_data():
            dates_by_doc = {doc.doc_id: doc.date for doc in bundle.documents if doc.date}
            timeline_png = output_dir / "lda_topic_timeline.png"
            self._write_timeline(model_result, dates_by_doc, timeline_png)
            if not timeline_png.exists():
                timeline_png = None

        tuning_csv = output_dir / "lda_tuning.csv"
        tuning_png = None
        if tuning_csv.exists():
            tuning_png = output_dir / "lda_tuning_plot.png"
            self._write_tuning_plot(tuning_csv, tuning_png)
            if not tuning_png.exists():
                tuning_png = None

        representative_sentences_csv = output_dir / "lda_representative_sentences.csv"
        representative_sentences = rank_representative_sentences(
            sentences_from_bundle(bundle, use_lemmas=params.use_lemmas),
            targets=topic_targets_from_model(model_result),
            per_target=3,
        )
        write_representative_sentences_csv(representative_sentences_csv, representative_sentences)

        summary_json = output_dir / "lda_summary.json"
        tuning_rows = self._read_tuning_rows(tuning_csv) if tuning_csv.exists() else []
        advanced_paths: Dict[str, Path] = {}
        advanced_payload: Dict[str, object] = {
            "multiword_features_count": self._count_multiword_features(model_result),
            "multiword_features": self._collect_multiword_features(model_result),
        }
        if params.enable_advanced_diagnostics:
            stability_rows = self._run_stability_diagnostics(
                dt_bundle=dt_bundle,
                doc_labels=doc_labels,
                params=params,
                output_dir=output_dir,
                base_model=model_result,
            )
            if not tuning_rows:
                tuning_rows = [{"k": int(model_result.n_topics), "perplexity": model_result.perplexity}]
            advanced_paths, advanced_payload = write_advanced_lda_diagnostics(
                model_result,
                output_dir=output_dir,
                k_quality_rows=tuning_rows,
                stability_rows=stability_rows,
            )
        diagnostics = dict(getattr(model_result, "diagnostics", {}) or {})
        diagnostics.update(
            {
                "n_topics_requested": int(params.k),
                "n_topics_rendered": int(model_result.n_topics),
                "topic_mass": self._mean_topic_probabilities(model_result),
                "empty_topics": [
                    idx
                    for idx, val in enumerate(self._mean_topic_probabilities(model_result))
                    if float(val) <= 1e-12
                ],
                "advanced_diagnostics_available": bool(params.enable_advanced_diagnostics),
                "multiword_features_count": int(advanced_payload.get("multiword_features_count", 0) or 0),
            }
        )
        write_summary_json(
            {
                "analysis_type": "lda",
                "backend": getattr(model_result, "backend", "python_lda_gibbs"),
                "method": getattr(model_result, "method", params.method),
                "seed": int(params.seed or params.random_state),
                "k_requested": int(params.k),
                "k_effective": int(model_result.n_topics),
                "n_topics": int(model_result.n_topics),
                "perplexity": model_result.perplexity,
                "n_docs": int(dt_bundle.matrix.shape[0]),
                "n_terms": int(dt_bundle.matrix.shape[1]),
                "tuning_available": bool(tuning_rows),
                "advanced_diagnostics_available": bool(params.enable_advanced_diagnostics),
                "multiword_features_count": int(advanced_payload.get("multiword_features_count", 0) or 0),
                "multiword_features": list(advanced_payload.get("multiword_features", []) or []),
                "representative_sentences_count": len(representative_sentences),
                "representative_sentences": representative_sentences[:30],
                "tuning_rows": tuning_rows,
                "diagnostics": diagnostics,
            },
            summary_json,
        )

        return LDAResult(
            analysis_type="lda",
            output_dir=output_dir,
            model_result=model_result,
            topics_csv_path=topics_csv,
            doc_topic_csv_path=doc_topic_csv,
            terms_beta_csv_path=terms_beta_csv,
            documents_gamma_csv_path=documents_gamma_csv,
            distribution_image_path=dist_png,
            top_terms_image_path=top_terms_png,
            heatmap_image_path=heatmap_png,
            timeline_image_path=timeline_png,
            tuning_csv_path=tuning_csv if tuning_csv.exists() else None,
            tuning_image_path=tuning_png,
            diagnostics_image_path=advanced_paths.get("diagnostics_png"),
            topic_diagnostics_csv_path=advanced_paths.get("topic_diagnostics_csv"),
            document_mixing_csv_path=advanced_paths.get("document_mixing_csv"),
            k_quality_csv_path=advanced_paths.get("k_quality_csv"),
            stability_csv_path=advanced_paths.get("stability_csv"),
            stability_summary_json_path=advanced_paths.get("stability_summary_json"),
            representative_sentences_csv_path=representative_sentences_csv,
            summary_json_path=summary_json,
            method=getattr(model_result, "method", params.method),
            k_requested=int(params.k),
            k_effective=int(model_result.n_topics),
            seed=int(params.seed or params.random_state),
            backend=getattr(model_result, "backend", "python_lda_gibbs"),
            tuning_available=bool(tuning_rows),
        )

    def _run_stability_diagnostics(
        self,
        *,
        dt_bundle,
        doc_labels: List[str],
        params: LDAParams,
        output_dir: Path,
        base_model: LDAModelResult,
    ) -> List[Dict[str, object]]:
        base_seed = int(params.seed or params.random_state)
        seeds = [base_seed + idx for idx in range(max(1, int(params.stability_n_seeds)))]
        rows: List[Dict[str, object]] = [{"seed": seeds[0], "mean_similarity": 1.0, "min_similarity": 1.0}]
        comparison_models = []
        for seed in seeds[1:]:
            model = train_lda_classic(
                dtm=dt_bundle.matrix,
                vocabulary=dt_bundle.vocabulary,
                doc_ids=dt_bundle.row_ids,
                doc_labels=doc_labels,
                output_dir=Path(output_dir) / f"lda_stability_seed_{seed}",
                k=params.k,
                method=params.method,
                seed=int(seed),
                gibbs_burnin=params.gibbs_burnin,
                gibbs_iter=params.gibbs_iter if params.method == "GIBBS" else params.n_iter,
                gibbs_thin=params.gibbs_thin,
                n_top_terms=15,
                enable_tuning=False,
                k_min=params.k_min,
                k_max=params.k_max,
                fallback_to_python=True,
            )
            comparison_models.append((seed, model))
        rows.extend(compute_stability_rows(base_model, comparison_models))
        return rows

    @staticmethod
    def _collect_multiword_features(model_result: LDAModelResult) -> List[str]:
        return sorted(
            {
                str(term)
                for topic in model_result.topic_terms
                for term, _weight in topic.terms
                if "_" in str(term)
            }
        )[:50]

    @classmethod
    def _count_multiword_features(cls, model_result: LDAModelResult) -> int:
        return len(cls._collect_multiword_features(model_result))

    def _write_topics_csv(self, model_result: LDAModelResult, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Topic_ID", "Topic_Label", "Term", "Weight"])
            for tt in model_result.topic_terms:
                for term, weight in tt.terms:
                    writer.writerow([tt.topic_id, tt.label, term, f"{float(weight):.10f}"])

    def _write_terms_beta_csv(self, model_result: LDAModelResult, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["topic_id", "topic_label", "term", "beta", "rank"])
            for tt in model_result.topic_terms:
                for rank, (term, weight) in enumerate(tt.terms, start=1):
                    writer.writerow([tt.topic_id, tt.label, term, f"{float(weight):.12f}", rank])

    def _write_doc_topic_csv(self, model_result: LDAModelResult, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            header = ["Doc_ID", "Label", "Dominant_Topic"] + [f"T{i}" for i in range(model_result.n_topics)]
            writer.writerow(header)
            for row in model_result.doc_topic_rows:
                probs = list(row.topic_probabilities)
                dom = int(np.argmax(probs)) if probs else -1
                str_probs = [f"{float(p):.10f}" for p in probs]
                writer.writerow([row.doc_id, row.doc_label, dom] + str_probs)

    def _write_documents_gamma_csv(self, model_result: LDAModelResult, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["doc_id", "doc_label", "topic_id", "gamma"])
            for row in model_result.doc_topic_rows:
                for topic_id, gamma in enumerate(row.topic_probabilities):
                    writer.writerow([row.doc_id, row.doc_label, topic_id, f"{float(gamma):.12f}"])

    def _write_distribution_plot(self, model_result: LDAModelResult, path: Path) -> None:
        raw_labels = model_result.topic_labels
        topics = list(range(model_result.n_topics))
        means = self._mean_topic_probabilities(model_result)
        values = [means[t] for t in topics]
        total = sum(values) or 1.0
        n_shown = len(topics)

        colors = ggplot_hue(n_shown)
        display_labels = [f"T{i + 1}" for i in range(n_shown)]
        legend_entries = [(f"T{i + 1}", raw_labels[t] if t < len(raw_labels) else f"T{i+1}") for i, t in enumerate(topics)]

        fig_h = max(4.0, min(10.0, 0.55 * n_shown + 1.5))
        fig, ax, ax_leg = create_figure(
            width=8.0,
            height=fig_h,
            with_legend_panel=True,
            legend_entries=legend_entries,
        )

        bars = ax.barh(display_labels, values, color=colors, height=0.6)
        ax.invert_yaxis()
        ax.tick_params(axis="y", labelsize=12, labelcolor="#2D2D2D")
        for label in ax.get_yticklabels():
            label.set_fontweight("bold")
        ax.set_xlabel("Probabilidade Média P(Tópico | Documento)")
        ax.set_title("Distribuição de Tópicos")
        style_axes(ax, grid_axis="x", spines=("bottom", "left"))
        add_bar_labels(ax, bars, values, total, fmt="{v:.3f} ({p:.1f}%)")
        draw_legend_panel(ax_leg, legend_entries, colors)
        save_figure(fig, path)

    @staticmethod
    def _mean_topic_probabilities(model_result: LDAModelResult) -> List[float]:
        n_topics = int(getattr(model_result, "n_topics", 0) or 0)
        if n_topics <= 0:
            return []
        matrix = np.asarray(getattr(model_result, "doc_topic_matrix", np.empty((0, n_topics))), dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return [0.0] * n_topics
        means = np.mean(matrix, axis=0)
        means = np.nan_to_num(means, nan=0.0, posinf=0.0, neginf=0.0)
        if means.shape[0] < n_topics:
            means = np.pad(means, (0, n_topics - means.shape[0]), mode="constant")
        means = means[:n_topics]
        return [float(max(0.0, min(1.0, value))) for value in means]

    def _write_top_terms_plot(self, model_result: LDAModelResult, path: Path, top_n: int = 10) -> None:
        n_topics = int(model_result.n_topics)
        if n_topics <= 0:
            return
        cols = min(3, n_topics)
        rows = int(np.ceil(n_topics / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(4.4 * cols, 3.2 * rows))
        if not isinstance(axes, np.ndarray):
            axes = np.array([axes])
        axes_flat = axes.flatten()

        for i in range(n_topics):
            ax = axes_flat[i]
            topic_terms = []
            if i < len(model_result.topic_terms):
                topic_terms = model_result.topic_terms[i].terms[:top_n]
            if not topic_terms:
                ax.text(0.5, 0.5, "Sem termos", ha="center", va="center")
                ax.set_axis_off()
                continue
            words = [term for term, _ in topic_terms][::-1]
            weights = [float(w) for _, w in topic_terms][::-1]
            ax.barh(words, weights, color=ggplot_hue(n_topics)[i])
            ax.set_title(f"T{i + 1}", fontsize=11, fontweight="bold")
            ax.tick_params(axis="y", labelsize=8)
            ax.tick_params(axis="x", labelsize=8)
            style_axes(ax, grid_axis="x", spines=("bottom", "left"))
            if i % cols == 0:
                ax.set_ylabel("Termos")
            ax.set_xlabel("beta")

        for j in range(n_topics, len(axes_flat)):
            axes_flat[j].set_axis_off()

        fig.suptitle("Top Termos por Tópico", fontsize=14, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        save_figure(fig, path)

    def _write_heatmap(self, model_result: LDAModelResult, path: Path) -> None:
        mat = model_result.doc_topic_matrix
        if mat.shape[0] > 40:
            mat = mat[:40]
            doc_labels = [r.doc_label for r in model_result.doc_topic_rows[:40]]
            title_suffix = " (Top 40 Documentos)"
        else:
            doc_labels = [r.doc_label for r in model_result.doc_topic_rows]
            title_suffix = ""

        n_topics = model_result.n_topics
        n_docs = len(doc_labels)
        raw_labels = model_result.topic_labels
        x_labels = [f"T{i + 1}" for i in range(n_topics)]
        legend_entries = [(f"T{i + 1}", raw_labels[i] if i < len(raw_labels) else f"T{i+1}") for i in range(n_topics)]
        colors = ggplot_hue(n_topics)

        fig_h = max(9, map_height(n_docs) + 3)
        fig, ax, ax_leg = create_figure(
            width=max(10, 6 + n_topics * 1.0),
            height=fig_h,
            with_legend_panel=True,
            legend_entries=legend_entries,
            legend_gap=0.18,
        )

        vmin, vmax = float(np.min(mat)), float(np.max(mat))
        im = ax.imshow(mat, cmap=get_sequential_cmap(), aspect="auto", vmin=vmin, vmax=vmax)

        ax.set_xticks(np.arange(n_topics))
        ax.set_xticklabels(x_labels, fontsize=12, fontweight="bold", rotation=0)
        ax.set_yticks(np.arange(n_docs))
        ax.set_yticklabels([lbl[:28] for lbl in doc_labels], fontsize=8)
        ax.tick_params(length=0)
        ax.set_title(f"Heatmap Doc-Tópico{title_suffix}")
        style_axes(ax, grid_axis="none", spines=())

        for i in range(n_docs):
            for j in range(n_topics):
                val = mat[i, j]
                tc = heatmap_text_color(val, vmin, vmax)
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8, color=tc)

        cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cbar.set_label("P(Tópico | Doc)", fontsize=9)
        cbar.ax.tick_params(labelsize=8)
        draw_legend_panel(ax_leg, legend_entries, colors)
        save_figure(fig, path)

    def _write_timeline(self, model_result: LDAModelResult, dates_by_doc: dict, path: Path) -> None:
        date_sums: dict = defaultdict(lambda: np.zeros(model_result.n_topics))
        date_counts: dict = defaultdict(int)
        for row in model_result.doc_topic_rows:
            date_val = dates_by_doc.get(row.doc_id)
            if not date_val:
                continue
            probs = np.array(row.topic_probabilities)
            date_sums[date_val] += probs
            date_counts[date_val] += 1
        if not date_sums:
            return
        sorted_dates = sorted(list(date_sums.keys()))
        t_matrix = np.array([date_sums[d] / date_counts[d] for d in sorted_dates])
        colors = ggplot_hue(model_result.n_topics)
        fig, ax, _ = create_figure(width=10, height=6)
        for t in range(model_result.n_topics):
            ax.plot(
                sorted_dates,
                t_matrix[:, t],
                marker="o",
                linewidth=1.5,
                markersize=4,
                color=colors[t],
                label=f"T{t + 1}",
            )
        ax.set_title("Evolução Média dos Tópicos no Tempo")
        ax.set_xlabel("Data")
        ax.set_ylabel("Probabilidade Média P(T|D)")
        style_axes(ax, grid_axis="y")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        ax.legend(framealpha=0.9, edgecolor="#DDDDDD", fontsize=9)
        fig.subplots_adjust(top=0.93, bottom=0.18)
        save_figure(fig, path)

    def _write_tuning_plot(self, tuning_csv_path: Path, plot_path: Path) -> None:
        rows = self._read_tuning_rows(tuning_csv_path)
        if not rows:
            return
        ks: List[int] = []
        perplexity: List[float] = []
        metric_names: List[str] = []
        for row in rows:
            k_val = row.get("k")
            p_val = row.get("perplexity")
            if isinstance(k_val, (int, float)) and isinstance(p_val, (int, float)):
                ks.append(int(k_val))
                perplexity.append(float(p_val))
            for key, value in row.items():
                if key in {"k", "perplexity"}:
                    continue
                if isinstance(value, (int, float)):
                    if key not in metric_names:
                        metric_names.append(key)

        if not ks:
            return

        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        ax.plot(ks, perplexity, marker="o", linewidth=2.0, color="#1f77b4", label="Perplexity")
        ax.set_title("Tuning de k (LDA)")
        ax.set_xlabel("k")
        ax.set_ylabel("Perplexity")
        ax.grid(True, alpha=0.25)

        if metric_names:
            ax2 = ax.twinx()
            palette = ggplot_hue(max(3, len(metric_names) + 1))
            for idx, metric in enumerate(metric_names):
                values = []
                for row in rows:
                    raw = row.get(metric)
                    values.append(float(raw) if isinstance(raw, (int, float)) else np.nan)
                ax2.plot(ks, values, linestyle="--", alpha=0.55, color=palette[idx + 1], label=metric)
            ax2.set_ylabel("Métricas complementares")
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=8)
        else:
            ax.legend(loc="best")

        fig.tight_layout()
        save_figure(fig, plot_path)

    @staticmethod
    def _read_tuning_rows(path: Path) -> List[Dict[str, object]]:
        if not path.exists():
            return []
        rows: List[Dict[str, object]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                parsed: Dict[str, object] = {}
                for key, value in row.items():
                    k = str(key or "").strip()
                    raw = str(value or "").strip()
                    if not k:
                        continue
                    if raw == "":
                        parsed[k] = None
                        continue
                    if k == "k":
                        try:
                            parsed[k] = int(float(raw))
                            continue
                        except Exception:
                            parsed[k] = raw
                            continue
                    try:
                        parsed[k] = float(raw)
                    except Exception:
                        parsed[k] = raw
                if parsed:
                    rows.append(parsed)
        return rows


def map_height(n_items: int) -> float:
    return max(4.0, min(12.0, 0.4 * n_items))
