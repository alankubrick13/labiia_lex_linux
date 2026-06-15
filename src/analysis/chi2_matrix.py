"""Chi-square analysis for categorical matrix columns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..core.tableau import Tableau


@dataclass
class Chi2Result:
    """Output of chi-square matrix analysis."""

    row_var: str
    col_var: str
    chi2: float
    dof: int
    p_value: float
    contingency_csv_path: Path
    expected_csv_path: Path
    residuals_csv_path: Path
    graph_path: Optional[Path] = None


class Chi2MatrixAnalysisError(Exception):
    """Friendly error for chi-square matrix analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class Chi2MatrixAnalysis:
    """Chi-square of independence for two matrix variables."""

    DEFAULT_PARAMS = {
        "typegraph": "png",
        "width": 1200,
        "height": 850,
    }

    def __init__(self, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.r_executor = r_executor or RExecutor()

        self._prepared: Dict[str, Any] = {}
        self._script_path: Optional[Path] = None

    def run(
        self,
        tableau: Tableau,
        row_var: str,
        col_var: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Chi2Result:
        """Execute complete chi-square workflow."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        try:
            prepared = self._prepare_data(tableau, row_var, col_var)
            script_path = self._generate_script(prepared, config)
            self._execute_script(script_path)
            return self._parse_results(prepared)
        except Chi2MatrixAnalysisError:
            raise
        except Exception as exc:
            raise Chi2MatrixAnalysisError(
                what="Falha na análise Qui-quadrado da matriz.",
                why=str(exc),
                how="Verifique as colunas categóricas escolhidas e tente novamente.",
            ) from exc

    def _prepare_data(self, tableau: Tableau, row_var: str, col_var: str) -> Dict[str, Any]:
        if tableau is None or tableau.data is None or tableau.data.empty:
            raise Chi2MatrixAnalysisError(
                what="Matriz vazia para Qui-quadrado.",
                why="Não há dados tabulares carregados.",
                how="Abra uma matriz CSV/XLSX antes de executar a análise.",
            )

        missing = [name for name in (row_var, col_var) if name not in tableau.data.columns]
        if missing:
            raise Chi2MatrixAnalysisError(
                what="Coluna inválida para Qui-quadrado.",
                why=f"Colunas ausentes na matriz: {', '.join(missing)}.",
                how="Escolha colunas existentes para a análise.",
            )

        row_series = tableau.data[row_var].fillna("(NA)").astype(str).str.strip().replace("", "(vazio)")
        col_series = tableau.data[col_var].fillna("(NA)").astype(str).str.strip().replace("", "(vazio)")

        contingency = pd.crosstab(row_series, col_series, dropna=False)
        if contingency.shape[0] < 2 or contingency.shape[1] < 2:
            raise Chi2MatrixAnalysisError(
                what="Tabela de contingência insuficiente.",
                why="O teste Qui-quadrado requer pelo menos 2 categorias em cada variável.",
                how="Selecione variáveis com maior diversidade de categorias.",
            )

        chi2_value, p_value, dof, expected = chi2_contingency(contingency.to_numpy())
        expected_df = pd.DataFrame(expected, index=contingency.index, columns=contingency.columns)
        residuals = (contingency.to_numpy() - expected) / np.sqrt(np.maximum(expected, 1e-12))
        residuals_df = pd.DataFrame(residuals, index=contingency.index, columns=contingency.columns)

        contingency_path = self.output_dir / "chi2_contingency.csv"
        expected_path = self.output_dir / "chi2_expected.csv"
        residuals_path = self.output_dir / "chi2_residuals.csv"

        contingency.to_csv(contingency_path, sep=";", encoding="utf-8")
        expected_df.to_csv(expected_path, sep=";", encoding="utf-8")
        residuals_df.to_csv(residuals_path, sep=";", encoding="utf-8")

        prepared = {
            "row_var": row_var,
            "col_var": col_var,
            "chi2": float(chi2_value),
            "p_value": float(p_value),
            "dof": int(dof),
            "contingency_path": contingency_path,
            "expected_path": expected_path,
            "residuals_path": residuals_path,
        }
        self._prepared = prepared
        return prepared

    def _generate_script(self, prepared: Dict[str, Any], params: Dict[str, Any]) -> Path:
        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"

        width = int(params.get("width", 1200))
        height = int(params.get("height", 850))
        graph_name = f"chi2_{prepared['row_var']}_x_{prepared['col_var']}.{typegraph}".replace(" ", "_")

        script_lines = [
            "# Generated by LabiiaLex - Matrix Chi2",
            f"setwd('{self.output_dir.as_posix()}')",
            f"tab <- as.matrix(read.csv('{prepared['contingency_path'].name}', sep=';', header=TRUE, row.names=1, check.names=FALSE))",
            "if (nrow(tab) > 1 && ncol(tab) > 1) {",
            f"  if ('{typegraph}' == 'svg') {{ svg('{graph_name}', width={width}/72, height={height}/72) }} else {{ png('{graph_name}', width={width}, height={height}, units='px', res=200) }}",
            "  par(mar=c(8, 5, 4, 2))",
            (
                "  mosaicplot(tab, color=TRUE, las=2, cex.axis=0.8,"
                f" main='Qui-quadrado: {self._escape_r(prepared['row_var'])} x {self._escape_r(prepared['col_var'])}',"
                f" xlab='{self._escape_r(prepared['row_var'])}', ylab='{self._escape_r(prepared['col_var'])}')"
            ),
            "  dev.off()",
            "}",
        ]

        script_path = self.output_dir / "chi2_matrix_script.R"
        script_path.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
        prepared["graph_path"] = self.output_dir / graph_name
        self._script_path = script_path
        return script_path

    def _execute_script(self, script_path: Path) -> None:
        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )
        except RNotFoundError as exc:
            raise Chi2MatrixAnalysisError(
                what="R não encontrado para gerar gráfico de Qui-quadrado.",
                why=str(exc),
                how="Instale/configure o R e tente novamente.",
            ) from exc
        except RTimeoutError as exc:
            raise Chi2MatrixAnalysisError(
                what="Tempo excedido na geração do gráfico de Qui-quadrado.",
                why=str(exc),
                how="Tente novamente com menos categorias ou ajuste o ambiente.",
            ) from exc
        except RExecutionError as exc:
            raise Chi2MatrixAnalysisError(
                what="Falha ao executar script R de Qui-quadrado.",
                why=str(exc),
                how="Verifique pacotes R necessários e tente novamente.",
            ) from exc

    def _parse_results(self, prepared: Dict[str, Any]) -> Chi2Result:
        graph_path = prepared.get("graph_path")
        resolved_graph = graph_path if isinstance(graph_path, Path) and graph_path.exists() else None
        return Chi2Result(
            row_var=prepared["row_var"],
            col_var=prepared["col_var"],
            chi2=float(prepared["chi2"]),
            dof=int(prepared["dof"]),
            p_value=float(prepared["p_value"]),
            contingency_csv_path=prepared["contingency_path"],
            expected_csv_path=prepared["expected_path"],
            residuals_csv_path=prepared["residuals_path"],
            graph_path=resolved_graph,
        )

    @staticmethod
    def _escape_r(value: str) -> str:
        return str(value or "").replace("'", "\\'")
