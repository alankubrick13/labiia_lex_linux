"""
Rolling Window Analysis
========================
Inspirado no Lexos "Rolling Window Analysis".

Desliza uma janela de tamanho fixo (em tokens ou UCEs) sobre o corpus
e conta a ocorrência de termos-alvo em cada posição, gerando gráficos
de linha que revelam como a presença dos termos evolui ao longo do texto.

Métricas disponíveis:
  - raw_count   : contagem bruta por janela
  - ratio       : proporção sobre total de tokens na janela
  - average_ratio: média deslizante da proporção (mais suave)
  - presence    : 0/1 — a janela contém o termo?

Nenhum código foi copiado do Lexos (GPL-3); reimplementação a partir
da documentação pública do método.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

@dataclass
class WindowSeries:
    """Série temporal de uma janela deslizante para um termo."""
    term:        str
    positions:   List[int]        # índice central de cada janela (em tokens)
    values:      List[float]      # métrica em cada posição
    metric:      str              # raw_count | ratio | presence
    window_size: int
    step:        int


@dataclass
class RollingWindowResult:
    """Resultado completo da análise Rolling Window."""
    series:       List[WindowSeries]
    total_tokens: int
    window_size:  int
    step:         int
    metric:       str
    segment_boundaries: List[int]   # posições (em tokens) de início de cada UCI

    def to_dict(self):
        return {
            "window_size": self.window_size,
            "step": self.step,
            "metric": self.metric,
            "total_tokens": self.total_tokens,
            "segment_boundaries": self.segment_boundaries,
            "series": [
                {
                    "term": s.term,
                    "positions": s.positions,
                    "values": s.values,
                }
                for s in self.series
            ],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RollingWindowAnalyzer:
    """
    Engine de Rolling Window Analysis.

    Uso::
        analyzer = RollingWindowAnalyzer(corpus_text)
        result = analyzer.run(
            terms=["democracia", "liberdade"],
            window_size=100,
            step=10,
            metric="ratio",
        )
    """

    _COMMAND_LINE = re.compile(r"^\s*\*{4}", re.MULTILINE)
    _WORD_RE = re.compile(
        r"\b[a-zA-ZàáâãäéêëíîïóôõöúûüçñÀÁÂÃÄÉÊËÍÎÏÓÔÕÖÚÛÜÇÑ][a-zA-ZàáâãäéêëíîïóôõöúûüçñÀÁÂÃÄÉÊËÍÎÏÓÔÕÖÚÛÜÇÑ_-]*\b"
    )
    METRICS = ("raw_count", "ratio", "presence")

    def __init__(self, raw_text: str, case_sensitive: bool = False) -> None:
        self._raw_text = raw_text
        self._case_sensitive = case_sensitive
        self._tokens: List[str] = []
        self._segment_boundaries: List[int] = []   # índice do 1º token de cada UCI
        self._parse()

    @staticmethod
    def _fold(text: str) -> str:
        nfd = unicodedata.normalize("NFD", text)
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()

    def _parse(self) -> None:
        """Tokeniza o corpus preservando as fronteiras de UCI."""
        current_pos = 0
        for line in self._raw_text.splitlines():
            if self._COMMAND_LINE.match(line):
                # Registra a posição do próximo token como nova UCI
                self._segment_boundaries.append(len(self._tokens))
                continue
            for m in self._WORD_RE.finditer(line):
                word = m.group(0)
                if not self._case_sensitive:
                    word = self._fold(word)
                self._tokens.append(word)

        log.debug("RollingWindow: %d tokens, %d segmentos",
                  len(self._tokens), len(self._segment_boundaries))

    # ------------------------------------------------------------------
    # Análise
    # ------------------------------------------------------------------

    def run(
        self,
        terms: Sequence[str],
        window_size: int = 100,
        step: int = 10,
        metric: str = "ratio",
    ) -> RollingWindowResult:
        """
        Executa a análise.

        Args:
            terms:       Lista de termos a rastrear.
            window_size: Tamanho da janela em tokens.
            step:        Passo entre janelas (tokens). step=1 = janela completamente deslizante.
            metric:      "raw_count" | "ratio" | "presence".

        Returns:
            RollingWindowResult com as séries de cada termo.
        """
        if metric not in self.METRICS:
            raise ValueError(f"metric deve ser um de {self.METRICS}")

        tokens = self._tokens
        n = len(tokens)
        if n == 0:
            raise ValueError("Corpus vazio — nenhum token encontrado.")

        window_size = max(1, min(window_size, n))
        step        = max(1, step)

        # Normalizar termos
        if self._case_sensitive:
            norm_terms = list(terms)
        else:
            norm_terms = [self._fold(t) for t in terms]

        # Construir séries
        series_list: List[WindowSeries] = []

        for original_term, norm_term in zip(terms, norm_terms):
            positions: List[int] = []
            values:    List[float] = []

            i = 0
            while i + window_size <= n:
                window = tokens[i: i + window_size]
                count = sum(1 for t in window if t == norm_term)

                if metric == "raw_count":
                    val = float(count)
                elif metric == "ratio":
                    val = count / len(window) if window else 0.0
                else:  # presence
                    val = 1.0 if count > 0 else 0.0

                center = i + window_size // 2
                positions.append(center)
                values.append(val)
                i += step

            series_list.append(WindowSeries(
                term=original_term,
                positions=positions,
                values=values,
                metric=metric,
                window_size=window_size,
                step=step,
            ))

        return RollingWindowResult(
            series=series_list,
            total_tokens=n,
            window_size=window_size,
            step=step,
            metric=metric,
            segment_boundaries=list(self._segment_boundaries),
        )

    # ------------------------------------------------------------------
    # Exportação CSV
    # ------------------------------------------------------------------

    @staticmethod
    def export_csv(result: RollingWindowResult, path) -> None:
        """Exporta as séries em CSV (posição + valor por termo)."""
        import csv
        from pathlib import Path
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        header = ["position"] + [s.term for s in result.series]
        # Alinhar posições (podem diferir ligeiramente por tamanho; usar posições do 1º)
        all_positions = result.series[0].positions if result.series else []

        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            for idx, pos in enumerate(all_positions):
                row = [pos] + [
                    (s.values[idx] if idx < len(s.values) else "")
                    for s in result.series
                ]
                w.writerow(row)

        log.info("Rolling Window CSV exportado: %s", path)
