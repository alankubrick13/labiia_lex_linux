"""Frequency analysis for tabular matrices."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..core.tableau import Tableau


@dataclass
class FrequencyEntry:
    """One frequency row for one categorical value."""

    value: str
    count: int
    percent: float


@dataclass
class FrequencyResult:
    """Output of frequency analysis over selected columns."""

    columns: Dict[str, List[FrequencyEntry]] = field(default_factory=dict)
    tables: Dict[str, Path] = field(default_factory=dict)
    graphs: Dict[str, Path] = field(default_factory=dict)
    summary_csv_path: Optional[Path] = None
    backend_used: str = "python+r"


class FrequencyAnalysisError(Exception):
    """Friendly error for matrix frequency analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class FrequencyAnalysis:
    """Frequency distribution analysis for matrix columns."""

    DEFAULT_PARAMS = {
        "top_n": 50,
        "typegraph": "png",
        "width": 1200,
        "height": 800,
    }

    def __init__(self, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.r_executor = r_executor or RExecutor()

        self._prepared: Dict[str, Any] = {}
        self._script_path: Optional[Path] = None
        self._script_graph_map: Dict[str, Path] = {}

    def run(
        self,
        tableau: Tableau,
        columns: Optional[Sequence[str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> FrequencyResult:
        """Execute complete frequency workflow."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        try:
            prepared = self._prepare_data(tableau, columns, config)
            script_path = self._generate_script(prepared, config)
            self._execute_script(script_path)
            return self._parse_results(prepared)
        except FrequencyAnalysisError:
            raise
        except Exception as exc:
            raise FrequencyAnalysisError(
                what="Falha na análise de frequências.",
                why=str(exc),
                how="Revise as colunas selecionadas e tente novamente.",
            ) from exc

    def _prepare_data(
        self,
        tableau: Tableau,
        columns: Optional[Sequence[str]],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        if tableau is None or tableau.data is None or tableau.data.empty:
            raise FrequencyAnalysisError(
                what="Matriz vazia para análise de frequências.",
                why="Não há dados tabulares carregados.",
                how="Abra uma matriz CSV/XLSX antes de executar a análise.",
            )

        selected_columns = list(columns or tableau.col_names)
        if not selected_columns:
            raise FrequencyAnalysisError(
                what="Nenhuma coluna selecionada.",
                why="A análise precisa de pelo menos uma variável categórica.",
                how="Selecione uma ou mais colunas e tente novamente.",
            )

        missing = [col for col in selected_columns if col not in tableau.data.columns]
        if missing:
            raise FrequencyAnalysisError(
                what="Coluna inválida na análise de frequências.",
                why=f"As colunas não existem na matriz: {', '.join(missing)}.",
                how="Escolha nomes de colunas presentes no arquivo carregado.",
            )

        top_n = max(1, int(params.get("top_n", 50)))
        table_paths: Dict[str, Path] = {}
        freq_entries: Dict[str, List[FrequencyEntry]] = {}
        summary_rows: List[Dict[str, Any]] = []

        for column in selected_columns:
            series = tableau.data[column].copy()
            series = series.fillna("(NA)").astype(str).str.strip()
            series = series.replace("", "(vazio)")

            counts = series.value_counts(dropna=False).head(top_n)
            total = int(counts.sum()) if int(counts.sum()) > 0 else 1

            entries: List[FrequencyEntry] = []
            for value, count in counts.items():
                percent = (float(count) / float(total)) * 100.0
                entry = FrequencyEntry(value=str(value), count=int(count), percent=float(percent))
                entries.append(entry)
                summary_rows.append(
                    {
                        "column": column,
                        "value": entry.value,
                        "count": entry.count,
                        "percent": round(entry.percent, 4),
                    }
                )
            freq_entries[column] = entries

            table_path = self.output_dir / f"frequency_{self._slug(column)}.csv"
            frame = pd.DataFrame(
                [{"value": row.value, "count": row.count, "percent": row.percent} for row in entries]
            )
            frame.to_csv(table_path, sep=";", index=False, encoding="utf-8")
            table_paths[column] = table_path

        summary_path = self.output_dir / "frequency_summary.csv"
        pd.DataFrame(summary_rows).to_csv(summary_path, sep=";", index=False, encoding="utf-8")

        prepared = {
            "columns": selected_columns,
            "entries": freq_entries,
            "table_paths": table_paths,
            "summary_path": summary_path,
        }
        self._prepared = prepared
        return prepared

    def _generate_script(self, prepared: Dict[str, Any], params: Dict[str, Any]) -> Path:
        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"

        width = int(params.get("width", 1200))
        height = int(params.get("height", 800))

        lines: List[str] = [
            "# Generated by LabiiaLex - Matrix Frequency",
            f"setwd('{self.output_dir.as_posix()}')",
            "",
        ]

        graph_map: Dict[str, Path] = {}
        for column in prepared["columns"]:
            table_path: Path = prepared["table_paths"][column]
            graph_name = f"frequency_{self._slug(column)}.{typegraph}"
            graph_path = self.output_dir / graph_name
            graph_map[column] = graph_path

            lines.extend(
                [
                    f"tab <- read.csv('{table_path.name}', sep=';', header=TRUE, stringsAsFactors=FALSE, check.names=FALSE)",
                    "if (nrow(tab) > 0) {",
                    f"  if ('{typegraph}' == 'svg') {{ svg('{graph_name}', width={width}/72, height={height}/72) }} else {{ png('{graph_name}', width={width}, height={height}, units='px', res=200) }}",
                    "  par(mar=c(10, 4, 4, 1))",
                    "  barplot(tab$count, names.arg=tab$value, las=2, col='steelblue', border='white', cex.names=0.7, ylab='Contagem',",
                    f"          main='Frequências - {self._escape_r(column)}')",
                    "  dev.off()",
                    "}",
                    "",
                ]
            )

        script_path = self.output_dir / "matrix_frequency_script.R"
        script_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        self._script_path = script_path
        self._script_graph_map = graph_map
        return script_path

    def _execute_script(self, script_path: Path) -> None:
        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )
        except RNotFoundError as exc:
            raise FrequencyAnalysisError(
                what="R não encontrado para gerar gráficos de frequência.",
                why=str(exc),
                how="Instale/configure o R e tente novamente.",
            ) from exc
        except RTimeoutError as exc:
            raise FrequencyAnalysisError(
                what="Tempo excedido na geração dos gráficos de frequência.",
                why=str(exc),
                how="Reduza o número de colunas analisadas ou tente novamente.",
            ) from exc
        except RExecutionError as exc:
            raise FrequencyAnalysisError(
                what="Falha ao executar script R de frequências.",
                why=str(exc),
                how="Verifique pacotes R necessários e tente novamente.",
            ) from exc

    def _parse_results(self, prepared: Dict[str, Any]) -> FrequencyResult:
        graphs: Dict[str, Path] = {}
        for column, graph_path in self._script_graph_map.items():
            if graph_path.exists():
                graphs[column] = graph_path

        return FrequencyResult(
            columns=prepared["entries"],
            tables=prepared["table_paths"],
            graphs=graphs,
            summary_csv_path=prepared["summary_path"] if prepared["summary_path"].exists() else None,
            backend_used="python+r",
        )

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "column"

    @staticmethod
    def _escape_r(value: str) -> str:
        return str(value or "").replace("'", "\\'")
