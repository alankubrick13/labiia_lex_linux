"""Diagnostic artifacts for LDA topic models."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .topic_modeling import LDAModelResult, TopicTerms
from ..core.chart_theme import get_sequential_cmap, save_figure


def _topic_weights(topic: TopicTerms, *, top_n: int = 25) -> Dict[str, float]:
    return {str(term): float(weight) for term, weight in list(topic.terms)[:top_n]}


def _weighted_jaccard(left: Dict[str, float], right: Dict[str, float]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    numerator = sum(min(float(left.get(key, 0.0)), float(right.get(key, 0.0))) for key in keys)
    denominator = sum(max(float(left.get(key, 0.0)), float(right.get(key, 0.0))) for key in keys)
    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)


def topic_similarity_matrix(model_result: LDAModelResult) -> np.ndarray:
    """Return weighted-Jaccard similarity between topic top-term distributions."""

    topics = list(model_result.topic_terms or [])
    n_topics = int(model_result.n_topics or len(topics))
    matrix = np.eye(n_topics, dtype=float)
    weights = [_topic_weights(topic) for topic in topics]
    for i in range(n_topics):
        for j in range(i + 1, n_topics):
            sim = _weighted_jaccard(weights[i] if i < len(weights) else {}, weights[j] if j < len(weights) else {})
            matrix[i, j] = sim
            matrix[j, i] = sim
    return matrix


def mean_topic_probabilities(model_result: LDAModelResult) -> List[float]:
    n_topics = int(model_result.n_topics or 0)
    matrix = np.asarray(model_result.doc_topic_matrix, dtype=float)
    if n_topics <= 0:
        return []
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        return [0.0] * n_topics
    values = np.nan_to_num(np.mean(matrix, axis=0), nan=0.0, posinf=0.0, neginf=0.0)
    if values.shape[0] < n_topics:
        values = np.pad(values, (0, n_topics - values.shape[0]), mode="constant")
    return [float(max(0.0, min(1.0, value))) for value in values[:n_topics]]


def compute_topic_diagnostics(
    model_result: LDAModelResult,
    *,
    small_threshold: float = 0.05,
    similar_threshold: float = 0.75,
) -> List[Dict[str, Any]]:
    """Summarize topic size and nearest-topic similarity."""

    sizes = mean_topic_probabilities(model_result)
    sim = topic_similarity_matrix(model_result)
    rows: List[Dict[str, Any]] = []
    for topic_id, size in enumerate(sizes):
        other_scores = [(idx, float(sim[topic_id, idx])) for idx in range(sim.shape[1]) if idx != topic_id]
        nearest_id, nearest_sim = max(other_scores, key=lambda item: item[1]) if other_scores else (-1, 0.0)
        rows.append(
            {
                "topic_id": int(topic_id),
                "topic_label": (
                    str(model_result.topic_labels[topic_id])
                    if topic_id < len(model_result.topic_labels)
                    else f"T{topic_id + 1}"
                ),
                "mean_probability": float(size),
                "is_small_topic": bool(float(size) < float(small_threshold)),
                "most_similar_topic_id": int(nearest_id),
                "max_topic_similarity": float(nearest_sim),
                "is_similar_to_another": bool(float(nearest_sim) >= float(similar_threshold)),
            }
        )
    return rows


def compute_document_mixing(
    model_result: LDAModelResult,
    *,
    mixed_threshold: float = 0.15,
) -> List[Dict[str, Any]]:
    """Identify documents whose first and second topic probabilities are close."""

    rows: List[Dict[str, Any]] = []
    for row in model_result.doc_topic_rows:
        probs = [float(value) for value in row.topic_probabilities]
        ordered = sorted(probs, reverse=True)
        top_prob = ordered[0] if ordered else 0.0
        second_prob = ordered[1] if len(ordered) > 1 else 0.0
        dominant_topic = int(np.argmax(probs)) if probs else -1
        margin = float(top_prob - second_prob)
        entropy = 0.0
        for prob in probs:
            if prob > 0:
                entropy -= prob * math.log(prob)
        entropy_norm = float(entropy / math.log(len(probs))) if len(probs) > 1 else 0.0
        rows.append(
            {
                "doc_id": int(row.doc_id),
                "doc_label": str(row.doc_label),
                "dominant_topic": dominant_topic,
                "top_probability": top_prob,
                "second_probability": second_prob,
                "margin": margin,
                "entropy_norm": entropy_norm,
                "is_mixed": bool(margin < float(mixed_threshold)),
            }
        )
    return rows


def compute_stability_rows(
    base_model: LDAModelResult,
    comparison_models: Sequence[Tuple[int, LDAModelResult]],
) -> List[Dict[str, Any]]:
    """Compare topic top terms from repeated LDA runs against the base model."""

    base_topics = [_topic_weights(topic) for topic in base_model.topic_terms]
    rows: List[Dict[str, Any]] = []
    for seed, model in comparison_models:
        best_scores: List[float] = []
        compare_topics = [_topic_weights(topic) for topic in model.topic_terms]
        for base in base_topics:
            scores = [_weighted_jaccard(base, other) for other in compare_topics]
            best_scores.append(max(scores) if scores else 0.0)
        rows.append(
            {
                "seed": int(seed),
                "mean_similarity": float(np.mean(best_scores)) if best_scores else 0.0,
                "min_similarity": float(np.min(best_scores)) if best_scores else 0.0,
            }
        )
    return rows


def _write_dict_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def write_advanced_lda_diagnostics(
    model_result: LDAModelResult,
    *,
    output_dir: Path,
    k_quality_rows: Sequence[Dict[str, Any]],
    stability_rows: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, Path], Dict[str, Any]]:
    """Write advanced LDA diagnostic CSV/JSON/PNG artifacts."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    topic_rows = compute_topic_diagnostics(model_result)
    document_rows = compute_document_mixing(model_result)
    multiword_terms = sorted(
        {
            term
            for topic in model_result.topic_terms
            for term, _weight in topic.terms
            if "_" in str(term)
        }
    )

    paths = {
        "topic_diagnostics_csv": output_dir / "lda_topic_diagnostics.csv",
        "document_mixing_csv": output_dir / "lda_document_mixing.csv",
        "k_quality_csv": output_dir / "lda_k_quality.csv",
        "stability_csv": output_dir / "lda_stability.csv",
        "stability_summary_json": output_dir / "lda_stability_summary.json",
        "diagnostics_png": output_dir / "lda_diagnostics.png",
    }
    _write_dict_csv(paths["topic_diagnostics_csv"], topic_rows)
    _write_dict_csv(paths["document_mixing_csv"], document_rows)
    _write_dict_csv(paths["k_quality_csv"], list(k_quality_rows or []))
    _write_dict_csv(paths["stability_csv"], list(stability_rows or []))

    stability_mean = (
        float(np.mean([float(row.get("mean_similarity", 0.0) or 0.0) for row in stability_rows]))
        if stability_rows
        else 0.0
    )
    summary = {
        "stability_n_seeds": len(list(stability_rows or [])),
        "stability_mean_similarity": stability_mean,
        "unstable_topic_count": sum(1 for row in stability_rows if float(row.get("min_similarity", 0.0) or 0.0) < 0.5),
        "multiword_features_count": len(multiword_terms),
        "multiword_features": multiword_terms[:50],
    }
    paths["stability_summary_json"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_diagnostics_plot(paths["diagnostics_png"], topic_rows, document_rows, topic_similarity_matrix(model_result))
    return paths, summary


def _write_diagnostics_plot(
    path: Path,
    topic_rows: Sequence[Dict[str, Any]],
    document_rows: Sequence[Dict[str, Any]],
    similarity: np.ndarray,
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    labels = [f"T{int(row['topic_id']) + 1}" for row in topic_rows]
    sizes = [float(row["mean_probability"]) for row in topic_rows]
    axes[0].bar(labels, sizes, color="#4878CF")
    axes[0].set_title("Tamanho médio")
    axes[0].set_ylabel("P(tópico | documento)")

    im = axes[1].imshow(similarity, cmap=get_sequential_cmap(), vmin=0, vmax=1)
    axes[1].set_title("Similaridade entre tópicos")
    axes[1].set_xticks(range(len(labels)))
    axes[1].set_yticks(range(len(labels)))
    axes[1].set_xticklabels(labels)
    axes[1].set_yticklabels(labels)
    fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)

    margins = [float(row["margin"]) for row in document_rows]
    axes[2].hist(margins, bins=min(12, max(3, len(margins))), color="#6ACC64", edgecolor="#2D2D2D")
    axes[2].set_title("Mistura dos documentos")
    axes[2].set_xlabel("Margem tópico 1 - tópico 2")
    fig.tight_layout()
    save_figure(fig, path)
