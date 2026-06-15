"""Extra word dispersion (x-ray style) analysis."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.corpus import Corpus
from ..utils.logger import get_logger
from ._extras_common import build_uci_records, tokenize_text


@dataclass
class XRayExtraResult:
    """Result payload for x-ray extra analysis."""

    graph_path: Optional[Path]
    points_path: Optional[Path]
    patterns: List[str]
    n_points: int


class XRayExtraAnalysisError(Exception):
    """Friendly error for x-ray extra analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class XRayExtraAnalysis:
    """Build dispersion plot for term occurrences across UCI order."""

    DEFAULT_PARAMS = {
        "patterns": "",
        "max_docs": 200,
        "width": 1200,
        "height": 760,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)

    def run(self, params: Optional[Dict[str, Any]] = None) -> XRayExtraResult:
        """Execute x-ray dispersion analysis."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        max_docs = max(20, int(config.get("max_docs", 200)))

        records = build_uci_records(self.corpus)
        records = [record for record in records if record.text.strip()]
        if not records:
            raise XRayExtraAnalysisError(
                what="Corpus sem conteúdo para dispersão x-ray.",
                why="Nenhuma UCI com texto foi encontrada.",
                how="Importe um corpus válido e tente novamente.",
            )
        records = records[:max_docs]

        patterns = self._normalize_patterns(str(config.get("patterns", "") or ""))
        if not patterns:
            patterns = self._infer_default_patterns(records)
        if not patterns:
            raise XRayExtraAnalysisError(
                what="Não foi possível definir termos para x-ray.",
                why="O corpus não possui tokens suficientes após limpeza.",
                how="Informe termos manualmente no diálogo de x-ray.",
            )

        points: List[Tuple[int, float, str, str]] = []
        for doc_rank, record in enumerate(records, start=1):
            tokens = tokenize_text(record.text, remove_stopwords=False)
            total = len(tokens)
            if total == 0:
                continue
            for idx, token in enumerate(tokens, start=1):
                for pattern in patterns:
                    if self._match_pattern(token, pattern):
                        points.append(
                            (
                                doc_rank,
                                float(idx) / float(total),
                                pattern,
                                token,
                            )
                        )
                        break

        if not points:
            raise XRayExtraAnalysisError(
                what="Nenhuma ocorrência encontrada para os termos informados.",
                why=f"Os padrões {', '.join(patterns)} não apareceram nas UCIs selecionadas.",
                how="Use termos mais frequentes ou padrões com sufixo *.",
            )

        points_path = self.output_dir / "xray_points.csv"
        self._write_points_csv(points_path, points)
        graph_path = self.output_dir / "xray_dispersion.png"
        self._plot_dispersion(graph_path, points, patterns, config)

        return XRayExtraResult(
            graph_path=graph_path if graph_path.exists() else None,
            points_path=points_path if points_path.exists() else None,
            patterns=patterns,
            n_points=len(points),
        )

    @staticmethod
    def _normalize_patterns(raw: str) -> List[str]:
        parts = [part.strip().lower() for part in raw.replace(";", ",").split(",")]
        return [part for part in parts if part]

    @staticmethod
    def _match_pattern(token: str, pattern: str) -> bool:
        if pattern.endswith("*") and len(pattern) > 1:
            return token.startswith(pattern[:-1])
        return token == pattern

    @staticmethod
    def _infer_default_patterns(records) -> List[str]:
        counter: Counter[str] = Counter()
        for record in records:
            counter.update(tokenize_text(record.text, remove_stopwords=True))
        return [word for word, _freq in counter.most_common(2)]

    @staticmethod
    def _write_points_csv(path: Path, points: List[Tuple[int, float, str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["doc_rank", "relative_position", "pattern", "token"])
            for doc_rank, rel_pos, pattern, token in points:
                writer.writerow([doc_rank, f"{rel_pos:.6f}", pattern, token])

    def _plot_dispersion(
        self,
        path: Path,
        points: List[Tuple[int, float, str, str]],
        patterns: List[str],
        params: Dict[str, Any],
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        by_pattern: Dict[str, List[Tuple[float, int]]] = {pattern: [] for pattern in patterns}
        for doc_rank, rel_pos, pattern, _token in points:
            by_pattern.setdefault(pattern, []).append((rel_pos, doc_rank))

        fig, ax = plt.subplots(
            figsize=(max(8.0, float(params.get("width", 1200)) / 120.0), max(5.5, float(params.get("height", 760)) / 120.0))
        )
        cmap = plt.get_cmap("tab10", max(1, len(patterns)))
        for idx, pattern in enumerate(patterns):
            coords = by_pattern.get(pattern, [])
            if not coords:
                continue
            xs = [x for x, _y in coords]
            ys = [y for _x, y in coords]
            ax.scatter(xs, ys, s=16, alpha=0.72, label=pattern, color=cmap(idx))

        ax.set_xlim(0.0, 1.0)
        ax.set_xlabel("Posição relativa no documento")
        ax.set_ylabel("Ordem dos documentos (UCI)")
        ax.set_title("Dispersão de Palavras (X-Ray)")
        ax.invert_yaxis()
        ax.grid(linestyle="--", linewidth=0.5, alpha=0.35)
        ax.legend(title="Termos", loc="upper right", fontsize=8)
        fig.tight_layout()
        fig.savefig(path, dpi=180)
        plt.close(fig)
