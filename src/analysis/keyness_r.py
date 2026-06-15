"""R-only Keyness backend using quanteda::textstat_keyness."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from ..visualization.r_integration.r_bridge import RBridge


log = get_logger(__name__)


@dataclass
class KeynessRRow:
    """Single row for keyness comparison output."""

    word: str
    statistic: float
    p_value: float
    freq_a: int
    freq_b: int
    norm_a: float
    norm_b: float
    direction: str  # A | B


@dataclass
class KeynessRResult:
    """Full keyness output produced by the R backend."""

    rows: List[KeynessRRow]
    total_a: int
    total_b: int
    name_a: str
    name_b: str
    min_freq: int
    measure: str
    top_n: int
    table_path: Optional[Path]
    graph_path: Optional[Path]
    summary_path: Optional[Path]

    @property
    def key_in_a(self) -> List[KeynessRRow]:
        return [row for row in self.rows if str(row.direction).upper() == "A"]

    @property
    def key_in_b(self) -> List[KeynessRRow]:
        return [row for row in self.rows if str(row.direction).upper() == "B"]

    def sorted_by(self, metric: str = "statistic") -> List[KeynessRRow]:
        metric_key = str(metric or "statistic").strip().lower()
        if metric_key == "p_value":
            return sorted(
                self.rows,
                key=lambda row: (
                    float(row.p_value) if not math.isnan(float(row.p_value)) else 9e99,
                    -abs(float(row.statistic)),
                    row.word,
                ),
            )
        if metric_key == "freq_a":
            return sorted(self.rows, key=lambda row: (-int(row.freq_a), row.word))
        if metric_key == "freq_b":
            return sorted(self.rows, key=lambda row: (-int(row.freq_b), row.word))
        if metric_key == "norm_a":
            return sorted(self.rows, key=lambda row: (-float(row.norm_a), row.word))
        if metric_key == "norm_b":
            return sorted(self.rows, key=lambda row: (-float(row.norm_b), row.word))
        return sorted(self.rows, key=lambda row: (-abs(float(row.statistic)), row.word))


class KeynessRAnalysisError(Exception):
    """Friendly error payload for Keyness R backend failures."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(
            f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        )


class KeynessRScriptRunner:
    """Executes R scripts through RBridge."""

    def __init__(self, bridge: Optional[RBridge] = None):
        self.bridge = bridge or RBridge()

    def run_script(self, script_name: str, args: Dict[str, Any], timeout: int = 240) -> str:
        if not self.bridge.r_available:
            raise KeynessRAnalysisError(
                what="R não encontrado para o teste de keyness.",
                why="O backend de keyness foi definido como exclusivo em R.",
                how="Instale o R (4.0+) e garanta que o Rscript esteja disponível.",
            )
        ok, output, _bytes = self.bridge.execute_script(script_name, args, timeout=timeout)
        if not ok:
            detail = str(output or "").strip()
            raise KeynessRAnalysisError(
                what="Falha ao executar o script R de keyness.",
                why=detail or "O Rscript retornou erro sem detalhes.",
                how=(
                    "Verifique se os pacotes R (quanteda, quanteda.textstats, "
                    "quanteda.textplots, jsonlite) estão instalados."
                ),
            )
        return str(output or "")


class KeynessRAnalysis:
    """Run corpus keyness comparison via quanteda in R."""

    DEFAULT_PARAMS: Dict[str, Any] = {
        "min_freq": 3,
        "top_n": 30,
        "remove_stopwords": True,
        "stopwords_lang": "pt",
        "measure": "lr",  # lr | chi2 | exact
        "plot_width": 1200,
        "plot_height": 700,
        "timeout_sec": 300,
    }

    def __init__(
        self,
        output_dir: Path,
        runner: Optional[KeynessRScriptRunner] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.runner = runner or KeynessRScriptRunner()

    def run(
        self,
        text_a: str,
        text_b: str,
        name_a: str = "Corpus A",
        name_b: str = "Corpus B (Referência)",
        params: Optional[Dict[str, Any]] = None,
    ) -> KeynessRResult:
        config: Dict[str, Any] = {**self.DEFAULT_PARAMS, **(params or {})}
        text_a = str(text_a or "")
        text_b = str(text_b or "")
        if not text_a.strip() or not text_b.strip():
            raise KeynessRAnalysisError(
                what="Corpora insuficientes para keyness.",
                why="É necessário informar texto em A e B para comparação.",
                how="Defina os dois corpora no diálogo de keyness e execute novamente.",
            )

        input_a = self.output_dir / "keyness_corpus_a.txt"
        input_b = self.output_dir / "keyness_corpus_b.txt"
        table_path = self.output_dir / "keyness_terms.csv"
        graph_path = self.output_dir / "keyness_plot.png"
        summary_path = self.output_dir / "keyness_summary.json"

        input_a.write_text(text_a, encoding="utf-8")
        input_b.write_text(text_b, encoding="utf-8")

        min_freq = max(1, int(config.get("min_freq", 3)))
        top_n = max(5, int(config.get("top_n", 30)))
        measure = str(config.get("measure", "lr") or "lr").strip().lower()
        if measure not in {"lr", "chi2", "exact"}:
            measure = "lr"

        args = {
            "input_a": str(input_a),
            "input_b": str(input_b),
            "name_a": str(name_a or "Corpus A"),
            "name_b": str(name_b or "Corpus B (Referência)"),
            "min_freq": min_freq,
            "top_n": top_n,
            "remove_stopwords": bool(config.get("remove_stopwords", True)),
            "stopwords_lang": str(config.get("stopwords_lang", "pt") or "pt"),
            "measure": measure,
            "plot_width": int(max(700, int(config.get("plot_width", 1200)))),
            "plot_height": int(max(500, int(config.get("plot_height", 700)))),
            "output_csv": str(table_path),
            "output_plot": str(graph_path),
            "output_summary": str(summary_path),
        }
        timeout = int(max(60, int(config.get("timeout_sec", 300))))
        self.runner.run_script("keyness_quanteda.R", args, timeout=timeout)

        rows = self._read_rows(table_path)
        if not rows:
            raise KeynessRAnalysisError(
                what="O script R de keyness não retornou termos válidos.",
                why="A tabela de saída ficou vazia após os filtros configurados.",
                how="Reduza a frequência mínima ou desative filtros de limpeza.",
            )

        summary = self._read_summary(summary_path)
        total_a = int(summary.get("tokens_a", 0) or 0)
        total_b = int(summary.get("tokens_b", 0) or 0)
        if total_a <= 0 or total_b <= 0:
            # fallback defensivo se summary falhar
            total_a = max(1, sum(int(row.freq_a) for row in rows))
            total_b = max(1, sum(int(row.freq_b) for row in rows))

        return KeynessRResult(
            rows=rows,
            total_a=total_a,
            total_b=total_b,
            name_a=str(name_a or "Corpus A"),
            name_b=str(name_b or "Corpus B (Referência)"),
            min_freq=min_freq,
            measure=measure,
            top_n=top_n,
            table_path=table_path if table_path.exists() else None,
            graph_path=graph_path if graph_path.exists() else None,
            summary_path=summary_path if summary_path.exists() else None,
        )

    @staticmethod
    def _read_rows(path: Path) -> List[KeynessRRow]:
        if not Path(path).exists():
            return []
        rows: List[KeynessRRow] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            for item in reader:
                term = str(item.get("term", "") or "").strip()
                if not term:
                    continue
                try:
                    p_raw = str(item.get("p_value", "") or "").strip()
                    p_value = float(p_raw) if p_raw not in {"", "NA", "NaN"} else float("nan")
                except Exception:
                    p_value = float("nan")
                rows.append(
                    KeynessRRow(
                        word=term,
                        statistic=float(item.get("keyness_score", 0.0) or 0.0),
                        p_value=p_value,
                        freq_a=int(float(item.get("target_count", 0) or 0)),
                        freq_b=int(float(item.get("reference_count", 0) or 0)),
                        norm_a=float(item.get("norm_a", 0.0) or 0.0),
                        norm_b=float(item.get("norm_b", 0.0) or 0.0),
                        direction=str(item.get("direction", "A") or "A").strip().upper(),
                    )
                )
        return rows

    @staticmethod
    def _read_summary(path: Path) -> Dict[str, Any]:
        if not Path(path).exists():
            return {}
        try:
            return dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception:
            return {}

    @staticmethod
    def export_csv(result: KeynessRResult, path: Path, metric: str = "statistic") -> None:
        dst = Path(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        sorted_rows = result.sorted_by(metric)
        with dst.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(
                [
                    "rank",
                    "term",
                    "direction",
                    "keyness_score",
                    "p_value",
                    "target_count",
                    "reference_count",
                    "norm_a",
                    "norm_b",
                    "measure",
                ]
            )
            for idx, row in enumerate(sorted_rows, start=1):
                writer.writerow(
                    [
                        idx,
                        row.word,
                        row.direction,
                        f"{row.statistic:.6f}",
                        "" if math.isnan(float(row.p_value)) else f"{row.p_value:.8f}",
                        row.freq_a,
                        row.freq_b,
                        f"{row.norm_a:.3f}",
                        f"{row.norm_b:.3f}",
                        result.measure,
                    ]
                )
        log.info("Keyness CSV exportado: %s", dst)
