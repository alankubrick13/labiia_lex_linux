"""Extra lexical sentiment analysis inspired by OpLexicon workflows."""

from __future__ import annotations

import csv
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.chart_theme import add_bar_labels, create_figure, save_figure, style_axes
from ..core.corpus import Corpus
from ..utils.logger import get_logger
from ..utils.paths import PathManager
from ._extras_common import build_uci_records, parse_date_from_metadata, tokenize_text


OPLEXICON_URL = "https://raw.githubusercontent.com/marlovss/OpLexicon/main/OpLexicon.csv"


@dataclass
class SentimentExtraResult:
    """Result payload for lexical sentiment extra analysis."""

    distribution_graph_path: Optional[Path]
    distribution_csv_path: Optional[Path]
    word_sentiment_csv_path: Optional[Path]
    timeline_graph_path: Optional[Path] = None
    timeline_csv_path: Optional[Path] = None
    total_matched_tokens: int = 0


class SentimentExtraAnalysisError(Exception):
    """Friendly error for sentiment extra analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class SentimentExtraAnalysis:
    """Lexicon-based sentiment analysis for Portuguese corpora."""

    DEFAULT_PARAMS = {
        "with_timeline": True,
        "top_words": 25,
        "width": 1100,
        "height": 700,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)

    def run(self, params: Optional[Dict[str, Any]] = None) -> SentimentExtraResult:
        """Execute lexical sentiment analysis and generate outputs."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        with_timeline = bool(config.get("with_timeline", True))
        top_words = max(10, int(config.get("top_words", 25)))

        records = build_uci_records(self.corpus)
        records = [record for record in records if record.text.strip()]
        if not records:
            raise SentimentExtraAnalysisError(
                what="Corpus sem conteúdo para análise de sentimentos.",
                why="Nenhuma UCI com texto foi encontrada.",
                how="Importe um corpus válido e tente novamente.",
            )

        lexicon = self._load_oplexicon()
        if not lexicon:
            raise SentimentExtraAnalysisError(
                what="Léxico de sentimentos indisponível.",
                why="Não foi possível carregar o OpLexicon nem fallback local.",
                how="Verifique conexão com internet e tente novamente.",
            )

        sentiment_counts: Counter[str] = Counter()
        word_sentiment_counts: Counter[Tuple[str, str]] = Counter()
        timeline_counts: Dict[Any, Counter[str]] = defaultdict(Counter)

        for record in records:
            tokens = tokenize_text(record.text, remove_stopwords=False)
            doc_date = parse_date_from_metadata(record)
            for token in tokens:
                sentiment = lexicon.get(token)
                if sentiment is None:
                    continue
                sentiment_counts[sentiment] += 1
                word_sentiment_counts[(token, sentiment)] += 1
                if doc_date is not None:
                    timeline_counts[doc_date][sentiment] += 1

        total_matched = int(sum(sentiment_counts.values()))
        if total_matched <= 0:
            raise SentimentExtraAnalysisError(
                what="Nenhum token do corpus casou com o léxico de sentimentos.",
                why="As palavras do corpus não estão presentes no dicionário usado.",
                how="Tente outro corpus ou complemente o léxico.",
            )

        distribution_csv = self.output_dir / "sentiment_distribution.csv"
        self._write_distribution_csv(distribution_csv, sentiment_counts)

        words_csv = self.output_dir / "sentiment_words.csv"
        self._write_words_csv(words_csv, word_sentiment_counts, top_words)

        distribution_graph = self.output_dir / "sentiment_distribution.png"
        self._plot_distribution(distribution_graph, sentiment_counts, config)

        timeline_graph: Optional[Path] = None
        timeline_csv: Optional[Path] = None
        if with_timeline and timeline_counts:
            timeline_csv = self.output_dir / "sentiment_timeline.csv"
            self._write_timeline_csv(timeline_csv, timeline_counts)
            timeline_graph = self.output_dir / "sentiment_timeline.png"
            self._plot_timeline(timeline_graph, timeline_counts, config)

        return SentimentExtraResult(
            distribution_graph_path=distribution_graph if distribution_graph.exists() else None,
            distribution_csv_path=distribution_csv if distribution_csv.exists() else None,
            word_sentiment_csv_path=words_csv if words_csv.exists() else None,
            timeline_graph_path=timeline_graph if timeline_graph and timeline_graph.exists() else None,
            timeline_csv_path=timeline_csv if timeline_csv and timeline_csv.exists() else None,
            total_matched_tokens=total_matched,
        )

    def _load_oplexicon(self) -> Dict[str, str]:
        cache_path = PathManager.resources_dir() / "oplexicon.csv"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if not cache_path.exists():
            try:
                urllib.request.urlretrieve(OPLEXICON_URL, cache_path)
            except Exception as exc:  # pragma: no cover - network dependent
                self._logger.warning("Falha ao baixar OpLexicon: %s", exc)

        if cache_path.exists():
            loaded = self._parse_oplexicon_file(cache_path)
            if loaded:
                return loaded

        # Fallback mínimo para manter funcionalidade offline.
        return {
            "bom": "Positivo",
            "boa": "Positivo",
            "ótimo": "Positivo",
            "excelente": "Positivo",
            "feliz": "Positivo",
            "sucesso": "Positivo",
            "ruim": "Negativa",
            "péssimo": "Negativa",
            "horrível": "Negativa",
            "horrivel": "Negativa",
            "triste": "Negativa",
            "problema": "Negativa",
            "normal": "Neutro",
            "regular": "Neutro",
        }

    @staticmethod
    def _parse_oplexicon_file(path: Path) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        with path.open("r", encoding="utf-8", errors="replace") as file:
            for raw_line in file:
                line = str(raw_line or "").strip()
                if not line or "," not in line:
                    continue
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 3:
                    continue
                word = parts[0].lower()
                sentiment_raw = parts[2].strip()
                if not word:
                    continue
                if sentiment_raw in {"1", "+1"}:
                    sentiment = "Positivo"
                elif sentiment_raw == "-1":
                    sentiment = "Negativa"
                else:
                    sentiment = "Neutro"
                mapping[word] = sentiment
        return mapping

    @staticmethod
    def _write_distribution_csv(path: Path, counts: Counter[str]) -> None:
        total = float(sum(counts.values())) or 1.0
        ordered = ["Positivo", "Negativa", "Neutro"]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["sentimento", "quantidade", "porcentagem"])
            for sentiment in ordered:
                value = int(counts.get(sentiment, 0))
                pct = (value / total) * 100.0
                writer.writerow([sentiment, value, f"{pct:.4f}"])

    @staticmethod
    def _write_words_csv(path: Path, counts: Counter[Tuple[str, str]], top_words: int) -> None:
        rows = sorted(
            ((word, sentiment, freq) for (word, sentiment), freq in counts.items()),
            key=lambda item: item[2],
            reverse=True,
        )[:top_words]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["palavra", "sentimento", "frequencia"])
            for word, sentiment, freq in rows:
                writer.writerow([word, sentiment, int(freq)])

    @staticmethod
    def _write_timeline_csv(path: Path, timeline_counts: Dict[Any, Counter[str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["data", "sentimento", "quantidade", "porcentagem"])
            for day in sorted(timeline_counts.keys()):
                counts = timeline_counts[day]
                total = float(sum(counts.values())) or 1.0
                for sentiment in ("Positivo", "Negativa", "Neutro"):
                    qty = int(counts.get(sentiment, 0))
                    pct = (qty / total) * 100.0
                    writer.writerow([str(day), sentiment, qty, f"{pct:.6f}"])

    @staticmethod
    def _plot_distribution(path: Path, counts: Counter[str], params: Dict[str, Any]) -> None:
        labels = ["Positivo", "Negativa", "Neutro"]
        values = [int(counts.get(label, 0)) for label in labels]
        colors = ["#00BA38", "#F8766D", "#9CA3AF"]

        fig, ax, _ = create_figure(
            width=max(8.0, float(params.get("width", 1100)) / 125.0),
            height=max(5.0, float(params.get("height", 700)) / 130.0),
        )
        bars = ax.bar(labels, values, color=colors, edgecolor="#FFFFFF", linewidth=1.2, alpha=0.92)
        add_bar_labels(ax, bars, values, total=float(sum(values)) or 1.0, fmt="{p:.1f}% ({v})", horizontal=False)
        ax.set_ylabel("Frequência")
        ax.set_title("Análise de Sentimentos (Polaridade Lexical)")
        style_axes(ax, grid_axis="y", spines=("bottom", "left"))
        save_figure(fig, path, dpi=160)

    @staticmethod
    def _plot_timeline(path: Path, timeline_counts: Dict[Any, Counter[str]], params: Dict[str, Any]) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        days = sorted(timeline_counts.keys())
        sentiments = ["Positivo", "Negativa", "Neutro"]
        series: Dict[str, List[float]] = {sentiment: [] for sentiment in sentiments}

        for day in days:
            counts = timeline_counts[day]
            total = float(sum(counts.values())) or 1.0
            for sentiment in sentiments:
                series[sentiment].append((float(counts.get(sentiment, 0)) / total) * 100.0)

        fig, ax, _ = create_figure(
            width=max(8.5, float(params.get("width", 1100)) / 125.0),
            height=max(5.0, float(params.get("height", 700)) / 130.0),
        )
        color_map = {"Positivo": "#00BA38", "Negativa": "#F8766D", "Neutro": "#6B7280"}
        for sentiment in sentiments:
            ax.plot(days, series[sentiment], marker="o", linewidth=1.7, markersize=3.8, color=color_map[sentiment], label=sentiment)

        ax.set_ylim(0.0, 100.0)
        ax.set_ylabel("Porcentagem por data")
        ax.set_title("Sentimentos ao Longo do Tempo")
        style_axes(ax, grid_axis="y", spines=("bottom", "left"))
        ax.legend(loc="best", fontsize=8)
        fig.autofmt_xdate()
        save_figure(fig, path, dpi=160)
