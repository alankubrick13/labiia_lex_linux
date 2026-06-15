"""Extra 1D document scaling inspired by Wordfish workflows."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.corpus import Corpus
from ..utils.logger import get_logger
from ._extras_common import build_uci_records, most_common_variable, tokenize_text


@dataclass
class WordfishExtraResult:
    """Result payload for 1D scaling analysis."""

    graph_path: Optional[Path]
    scores_path: Optional[Path]
    n_documents: int
    n_terms: int


class WordfishExtraAnalysisError(Exception):
    """Friendly error for wordfish-style extra analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class WordfishExtraAnalysis:
    """Approximate Wordfish-like 1D scaling from UCI term matrix."""

    DEFAULT_PARAMS = {
        "group_variable": "",
        "min_freq": 3,
        "max_features": 1200,
        "width": 1200,
        "height": 640,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)

    def run(self, params: Optional[Dict[str, Any]] = None) -> WordfishExtraResult:
        """Execute 1D scaling and export scatter/CSV."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        min_freq = max(1, int(config.get("min_freq", 3)))
        max_features = max(100, int(config.get("max_features", 1200)))

        records = build_uci_records(self.corpus)
        records = [record for record in records if record.text.strip()]
        if len(records) < 2:
            raise WordfishExtraAnalysisError(
                what="Documentos insuficientes para escalonamento 1D.",
                why="A análise requer pelo menos 2 UCIs com texto.",
                how="Importe um corpus maior e tente novamente.",
            )

        group_variable = str(config.get("group_variable", "") or "").strip().lower()
        if not group_variable:
            group_variable = most_common_variable(records) or ""

        doc_counts: List[Counter[str]] = []
        total_counter: Counter[str] = Counter()
        for record in records:
            tokens = tokenize_text(record.text, remove_stopwords=True)
            counter = Counter(tokens)
            doc_counts.append(counter)
            total_counter.update(counter)

        selected_terms = [
            term
            for term, freq in total_counter.most_common(max_features * 2)
            if int(freq) >= min_freq
        ][:max_features]
        if len(selected_terms) < 2:
            raise WordfishExtraAnalysisError(
                what="Vocabulário insuficiente para escalonamento 1D.",
                why="Poucos termos ficaram acima da frequência mínima.",
                how="Reduza a frequência mínima e tente novamente.",
            )

        term_to_idx = {term: idx for idx, term in enumerate(selected_terms)}
        matrix = np.zeros((len(records), len(selected_terms)), dtype=np.float64)
        for doc_idx, counts in enumerate(doc_counts):
            for term, freq in counts.items():
                term_idx = term_to_idx.get(term)
                if term_idx is None:
                    continue
                matrix[doc_idx, term_idx] = float(freq)

        # Log transform + centering improves stability for sparse-like text counts.
        matrix = np.log1p(matrix)
        matrix -= matrix.mean(axis=0, keepdims=True)

        if not np.any(matrix):
            raise WordfishExtraAnalysisError(
                what="Matriz degenerada para escalonamento 1D.",
                why="Após transformação, não restou variação nos documentos.",
                how="Use um corpus com maior diversidade lexical.",
            )

        try:
            u, s, _vt = np.linalg.svd(matrix, full_matrices=False)
        except np.linalg.LinAlgError as exc:
            raise WordfishExtraAnalysisError(
                what="Falha numérica ao calcular escalonamento 1D.",
                why=str(exc),
                how="Tente reduzir o corpus ou ajustar os parâmetros.",
            ) from exc

        if len(s) == 0:
            raise WordfishExtraAnalysisError(
                what="SVD sem componentes para escalonamento 1D.",
                why="A decomposição não retornou dimensão útil.",
                how="Revise o corpus e tente novamente.",
            )

        scores = u[:, 0] * s[0]
        scores = scores.astype(float)

        scores_path = self.output_dir / "wordfish_scores.csv"
        self._write_scores_csv(scores_path, records, scores, group_variable)
        graph_path = self.output_dir / "wordfish_scale1d.png"
        self._plot_scale(graph_path, records, scores, group_variable, config)

        return WordfishExtraResult(
            graph_path=graph_path if graph_path.exists() else None,
            scores_path=scores_path if scores_path.exists() else None,
            n_documents=len(records),
            n_terms=len(selected_terms),
        )

    @staticmethod
    def _write_scores_csv(
        path: Path,
        records,
        scores: np.ndarray,
        group_variable: str,
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["uci_id", "uci_index", "group", "score"])
            for idx, record in enumerate(records):
                group = record.metadata.get(group_variable, "(sem grupo)") if group_variable else "(sem grupo)"
                writer.writerow([record.uci_id, record.uci_index, group, f"{float(scores[idx]):.8f}"])

    def _plot_scale(
        self,
        path: Path,
        records,
        scores: np.ndarray,
        group_variable: str,
        params: Dict[str, Any],
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        groups = [
            (record.metadata.get(group_variable, "(sem grupo)") if group_variable else "(sem grupo)")
            for record in records
        ]
        unique_groups = sorted(set(groups))
        cmap = plt.get_cmap("tab10", max(1, len(unique_groups)))
        color_map = {group: cmap(idx) for idx, group in enumerate(unique_groups)}
        colors = [color_map[group] for group in groups]

        rng = np.random.default_rng(seed=42)
        y = rng.normal(0.0, 0.03, size=len(scores))

        fig, ax = plt.subplots(
            figsize=(max(8.0, float(params.get("width", 1200)) / 120.0), max(4.5, float(params.get("height", 640)) / 120.0))
        )
        ax.scatter(scores, y, c=colors, s=58, alpha=0.85, edgecolors="white", linewidths=0.6)
        ax.axvline(0.0, color="black", linewidth=1)
        ax.set_yticks([])
        ax.set_xlabel("Posição 1D (aproximação Wordfish)")
        title = "Escalonamento 1D de Documentos"
        if group_variable:
            title += f" por {group_variable}"
        ax.set_title(title)

        if len(scores) <= 40:
            for idx, score in enumerate(scores):
                ax.text(float(score), float(y[idx]) + 0.01, str(records[idx].uci_id), fontsize=7, alpha=0.75)

        handles = [
            plt.Line2D([0], [0], marker="o", color="w", label=group, markerfacecolor=color_map[group], markersize=8)
            for group in unique_groups
        ]
        if handles:
            ax.legend(handles=handles, title="Grupo", loc="best", fontsize=8)

        ax.grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.4)
        fig.tight_layout()
        fig.savefig(path, dpi=180)
        plt.close(fig)
