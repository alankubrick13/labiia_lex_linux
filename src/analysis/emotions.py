"""Emotion analysis module using the NRC Lexicon (via R / syuzhet).

Architecture follows the Pattern B (R-orchestration) used by
WordCloudAnalysis: Python prepares the corpus text file, generates an R
script via RScriptGenerator, executes it with RExecutor, then reads the
generated PNG and CSV paths back into a result object.
"""

from __future__ import annotations

import csv
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.corpus import Corpus
from ..core.r_script_generator import RScriptGenerator
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class EmotionsResult:
    """Result payload for the NRC emotion analysis."""

    bar_graph_path: Optional[Path]
    """Bar chart PNG produced by R."""

    radar_graph_path: Optional[Path]
    """Radar / spider chart PNG produced by R."""

    polarity_graph_path: Optional[Path]
    """Polarity bar chart PNG produced by R."""

    stats_csv_path: Optional[Path]
    """CSV with per-emotion counts and percentages (10 rows: 8 emotions + pos/neg)."""

    words_csv_path: Optional[Path]
    """CSV with token-level emotion assignments (one row per token-emotion match)."""

    words_summary_csv_path: Optional[Path]
    """CSV with grouped word lists per emotion/sentiment for direct auditing."""

    totals: Dict[str, int] = field(default_factory=dict)
    """Aggregated emotion counts read back from stats_csv for quick display."""


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class EmotionsAnalysisError(Exception):
    """Friendly error for emotion analysis. Follows the What/Why/How pattern."""

    def __init__(self, what: str, why: str, how: str) -> None:
        self.what = what
        self.why = why
        self.how = how
        super().__init__(
            f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        )


# ---------------------------------------------------------------------------
# Analysis class
# ---------------------------------------------------------------------------

class EmotionsAnalysis:
    """Runs NRC emotion analysis via syuzhet in R.

    Usage::

        analysis = EmotionsAnalysis(corpus, output_dir)
        result   = analysis.run(params)
    """

    EMOTION_COLS: List[str] = [
        "anger", "anticipation", "disgust", "fear",
        "joy", "sadness", "surprise", "trust",
    ]

    DEFAULT_PARAMS: Dict[str, Any] = {
        "width":  1200,
        "height":  900,
    }
    MIN_PLOT_WIDTH = 900
    MIN_PLOT_HEIGHT = 650

    _REQUIRED_PACKAGES: List[str] = ["syuzhet"]

    def __init__(
        self,
        corpus: Corpus,
        output_dir: Path,
        r_executor: Optional[RExecutor] = None,
    ) -> None:
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.script_generator = RScriptGenerator()
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, params: Optional[Dict[str, Any]] = None) -> EmotionsResult:
        """Execute emotion analysis and return paths to generated artefacts.

        Args:
            params: Optional overrides for DEFAULT_PARAMS.

        Returns:
            EmotionsResult with paths to bar chart, radar chart, and CSVs.

        Raises:
            EmotionsAnalysisError: on any failure during processing.
        """
        config = {**self.DEFAULT_PARAMS, **(params or {})}

        self._ensure_packages()

        # --- 1. Extract plain text from corpus into a temp file ----------
        corpus_text = self._build_corpus_text()
        if not corpus_text.strip():
            raise EmotionsAnalysisError(
                what="Corpus sem conteúdo de texto.",
                why="Nenhuma UCI com texto foi encontrada no corpus.",
                how="Importe um corpus válido com conteúdo textual e tente novamente.",
            )

        corpus_txt_path = self.output_dir / "emotions_corpus_input.txt"
        corpus_txt_path.write_text(corpus_text, encoding="utf-8")

        # --- 2. Define output paths -------------------------------------
        bar_out   = self.output_dir / "emotions_bar.png"
        radar_out = self.output_dir / "emotions_radar.png"
        polarity_out = self.output_dir / "emotions_polarity.png"
        stats_out = self.output_dir / "emotions_stats.csv"
        words_out = self.output_dir / "emotions_words.csv"
        words_summary_out = self.output_dir / "emotions_words_summary.csv"

        # --- 3. Generate & execute R script -----------------------------
        plot_width, plot_height = self._safe_plot_dimensions(config)
        script_params: Dict[str, Any] = {
            "pathout":     str(self.output_dir),
            "corpus_file": str(corpus_txt_path),
            "bar_out":     str(bar_out),
            "radar_out":   str(radar_out),
            "polarity_out": str(polarity_out),
            "stats_out":   str(stats_out),
            "words_out":   str(words_out),
            "words_summary_out": str(words_summary_out),
            "width":       plot_width,
            "height":      plot_height,
        }

        script_path = self.script_generator.generate_and_save(
            "emotions",
            script_params,
            self.output_dir / "emotions_script.R",
        )

        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )
        except RNotFoundError as exc:
            raise EmotionsAnalysisError(
                what="R não foi encontrado no sistema.",
                why=str(exc),
                how="Instale o R (versão 4.0+) e verifique se o Rscript está disponível no PATH.",
            ) from exc
        except RTimeoutError as exc:
            raise EmotionsAnalysisError(
                what="Tempo limite excedido na análise de emoções.",
                why=str(exc),
                how="Tente com um corpus menor ou aumente o timeout nas configurações.",
            ) from exc
        except RExecutionError as exc:
            why = str(exc)
            how = (
                "Verifique se o pacote 'syuzhet' está instalado no R. "
                "No R, execute: install.packages('syuzhet')"
            )
            if "figure margins too large" in why.lower():
                how = (
                    "O LabiiaLex ajusta automaticamente o tamanho mínimo dos gráficos; "
                    "se o erro persistir, limpe parâmetros antigos da análise de emoções "
                    "ou aumente largura/altura do gráfico."
                )
            raise EmotionsAnalysisError(
                what="Falha na execução do script de emoções.",
                why=why,
                how=how,
            ) from exc
        except Exception as exc:
            raise EmotionsAnalysisError(
                what="Erro inesperado na análise de emoções.",
                why=str(exc),
                how="Verifique os dados e tente novamente.",
            ) from exc

        # --- 4. Parse stats CSV for quick access ------------------------
        totals = self._parse_stats_csv(stats_out)

        return EmotionsResult(
            bar_graph_path=bar_out   if bar_out.exists()   else None,
            radar_graph_path=radar_out if radar_out.exists() else None,
            polarity_graph_path=polarity_out if polarity_out.exists() else None,
            stats_csv_path=stats_out if stats_out.exists() else None,
            words_csv_path=words_out if words_out.exists() else None,
            words_summary_csv_path=words_summary_out if words_summary_out.exists() else None,
            totals=totals,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _safe_plot_dimensions(cls, params: Dict[str, Any]) -> tuple[int, int]:
        """Clamp chart dimensions so R base plots have enough margin space."""
        def _coerce(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(default)

        width = _coerce((params or {}).get("width"), cls.DEFAULT_PARAMS["width"])
        height = _coerce((params or {}).get("height"), cls.DEFAULT_PARAMS["height"])
        return max(cls.MIN_PLOT_WIDTH, width), max(cls.MIN_PLOT_HEIGHT, height)

    def _build_corpus_text(self) -> str:
        """Extract all text from the corpus UCIs into a single string.

        Uses corpus.get_uces() which correctly reads text from SQLite or the
        in-memory _uce_texts dict — the ``Uce`` dataclass itself does NOT store
        text content as an attribute.
        """
        parts: List[str] = []
        try:
            for _uce_id, text in self.corpus.get_uces():
                t = (text or "").strip()
                if t:
                    parts.append(t)
        except Exception as exc:
            self._logger.warning("Erro ao extrair texto do corpus: %s", exc)
        return " ".join(parts)

    def _ensure_packages(self) -> None:
        """Check that syuzhet is available; attempt install if missing."""
        try:
            status = self.r_executor.check_packages(self._REQUIRED_PACKAGES)
        except Exception:
            # If the check itself fails (e.g. R not found) let the main
            # execute() call surface a friendlier error.
            return

        missing = [p for p, ok in status.items() if not ok]
        if not missing:
            return

        self._logger.info("Instalando pacotes R ausentes: %s", missing)
        pkgs_r = ", ".join(f'"{p}"' for p in missing)
        install_code = (
            "options(timeout = 120)\n"
            ".lexi_type <- if (.Platform$OS.type == 'windows') 'binary' else 'source'\n"
            f"for (pkg in c({pkgs_r})) {{\n"
            "    if (!requireNamespace(pkg, quietly = TRUE)) {\n"
            "        install.packages(pkg,\n"
            "            repos = 'https://cloud.r-project.org',\n"
            "            type = .lexi_type,\n"
            "            dependencies = c('Depends', 'Imports', 'LinkingTo'),\n"
            "            quiet = TRUE)\n"
            "    }\n"
            "}\n"
            f"still <- c({pkgs_r})[!sapply(c({pkgs_r}), requireNamespace, quietly = TRUE)]\n"
            "if (length(still) > 0) stop(paste('Pacotes nao instalados:', paste(still, collapse=', ')))\n"
            "cat('OK\\n')\n"
        )
        tmp = Path(tempfile.mktemp(suffix=".R"))
        try:
            tmp.write_text(install_code, encoding="utf-8")
            self.r_executor.execute(str(tmp), timeout=300)
        except (RExecutionError, RTimeoutError) as exc:
            raise EmotionsAnalysisError(
                what=f"Pacotes R necessários não disponíveis: {', '.join(missing)}.",
                why="Instalação automática falhou ou excedeu 5 minutos.",
                how="Execute manualmente no R: install.packages('syuzhet')",
            ) from exc
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _parse_stats_csv(stats_path: Path) -> Dict[str, int]:
        """Read the CSV written by R and return {emotion: count}."""
        totals: Dict[str, int] = {}
        if not stats_path.exists():
            return totals
        try:
            with stats_path.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    name = str(row.get("emocao") or "").strip()
                    raw  = str(row.get("contagem") or "0").strip()
                    try:
                        totals[name] = int(float(raw))
                    except (ValueError, TypeError):
                        totals[name] = 0
        except Exception:
            pass
        return totals
