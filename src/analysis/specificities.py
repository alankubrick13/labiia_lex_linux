"""Specificities analysis (chi2/hypergeometric) by metadata categories."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import hypergeom

from ..core.corpus import Corpus
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger


@dataclass
class SpecificityEntry:
    """One specificity score for a word in one metadata category."""

    word: str
    variable: str
    score: float
    frequency: int
    relative_per_thousand: float
    sign: str


@dataclass
class SpecificitiesResult:
    """Specificities analysis output."""

    index_type: str
    min_freq: int
    metadata_tokens: List[str]
    scores_by_variable: Dict[str, List[SpecificityEntry]] = field(default_factory=dict)
    lexical_table_path: Optional[Path] = None
    gram_table_path: Optional[Path] = None
    scores_csv_path: Optional[Path] = None
    relative_csv_path: Optional[Path] = None
    specificities_plot_data_path: Optional[Path] = None
    specificities_plot_path: Optional[Path] = None
    afc_graph_path: Optional[Path] = None
    backend_used: str = "python"
    fallback_reason: Optional[str] = None


class SpecificitiesAnalysisError(Exception):
    """Friendly error for specificities analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class SpecificitiesAnalysis:
    """
    Specificities analysis from lexical table lemma x metadata token.

    Supports:
    - chi2 index (signed)
    - hypergeometric index (signed -log10 p-value)
    """

    DEFAULT_PARAMS = {
        "index_type": "chi2",  # chi2 | hypergeo
        "min_freq": 3,
        "gram_type": 0,  # 0=actives+supp, 1=actives, 2=supp
        "metadata_tokens": None,
        "metadata_variables": None,
        "backend": "python",  # python | r
        "allow_python_fallback": True,
        "run_afc": False,
        "max_terms_per_variable": 200,
        "width": 900,
        "height": 900,
        "generate_plot": True,
        "plot_top_n": 30,
        "plot_bw": False,
        "plot_width": 1200,
        "plot_height": 800,
        "plot_typegraph": "png",
    }

    def __init__(self, corpus: Corpus, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)

        self._prepared: Dict[str, Any] = {}
        self._execution_meta: Dict[str, Any] = {}

    def run(self, params: Optional[Dict[str, Any]] = None) -> SpecificitiesResult:
        """Execute complete specificities analysis."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        try:
            prepared = self._prepare_data(config)
            script_path = self._generate_script(prepared, config)
            execution_meta = self._execute_script(script_path, prepared, config)
            return self._parse_results(prepared, execution_meta, config)
        except SpecificitiesAnalysisError:
            raise
        except Exception as exc:
            raise SpecificitiesAnalysisError(
                what="Falha ao executar a analise de especificidades.",
                why=str(exc),
                how="Revise os parametros e os metadados selecionados e tente novamente.",
            ) from exc

    def _prepare_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build lexical and grammatical tables from corpus metadata."""
        if self.corpus.getucinb() == 0 or self.corpus.getucenb() == 0:
            raise SpecificitiesAnalysisError(
                what="Corpus vazio para especificidades.",
                why="Nao ha UCIs/UCEs suficientes para construir a tabela lexical.",
                how="Importe um corpus valido antes de executar a analise.",
            )

        index_type = str(params.get("index_type", "chi2")).lower()
        if index_type not in {"chi2", "hypergeo"}:
            raise SpecificitiesAnalysisError(
                what="Indice de especificidade invalido.",
                why=f"Indice '{index_type}' nao e suportado.",
                how="Use 'chi2' ou 'hypergeo'.",
            )

        metadata_tokens = self._resolve_metadata_tokens(params)
        if not metadata_tokens:
            raise SpecificitiesAnalysisError(
                what="Nenhum metadado selecionado.",
                why="A analise exige pelo menos uma categoria de metadado.",
                how="Selecione uma ou mais variaveis/metadados e tente novamente.",
            )

        min_freq = max(1, int(params.get("min_freq", 3)))
        gram_type = int(params.get("gram_type", 0))

        lexical_table = self.corpus.make_lexitable(min_freq, metadata_tokens, gram=gram_type)
        if len(lexical_table) <= 1:
            raise SpecificitiesAnalysisError(
                what="Tabela lexical vazia.",
                why="Nenhum lema atingiu os filtros de frequencia/metadado.",
                how="Reduza a frequencia minima ou ajuste os metadados selecionados.",
            )

        gram_table = self.corpus.make_efftype_from_etoiles(metadata_tokens)

        lexical_table_path = self.output_dir / "specificities_lexical_table.csv"
        gram_table_path = self.output_dir / "specificities_gram_table.csv"
        self._write_table(lexical_table, lexical_table_path)
        self._write_table(gram_table, gram_table_path)

        row_labels = [str(row[0]) for row in lexical_table[1:]]
        col_labels = [str(col) for col in lexical_table[0][1:]]
        counts = np.array([row[1:] for row in lexical_table[1:]], dtype=float)

        prepared = {
            "index_type": index_type,
            "min_freq": min_freq,
            "gram_type": gram_type,
            "metadata_tokens": metadata_tokens,
            "lexical_table": lexical_table,
            "gram_table": gram_table,
            "lexical_table_path": lexical_table_path,
            "gram_table_path": gram_table_path,
            "row_labels": row_labels,
            "col_labels": col_labels,
            "counts": counts,
        }
        self._prepared = prepared
        return prepared

    def _generate_script(self, prepared: Dict[str, Any], params: Dict[str, Any]) -> Optional[Path]:
        """Generate optional R script for specificities computation."""
        backend = str(params.get("backend", "python")).lower()
        if backend != "r":
            return None

        data_name = prepared["lexical_table_path"].name
        scores_name = "specificities_scores.csv"
        relative_name = "specificities_relative.csv"
        afc_name = "specificities_afc.png"
        index_type = prepared["index_type"]
        run_afc = "TRUE" if bool(params.get("run_afc", False)) else "FALSE"
        width = int(params.get("width", 900))
        height = int(params.get("height", 900))

        script_path = self.output_dir / "specificities_script.R"
        content = f"""
# Generated by LabiiaLex - Specificities
tab <- read.csv("{data_name}", sep=";", header=TRUE, row.names=1, check.names=FALSE)
mat <- as.matrix(tab)
rel <- sweep(mat, 2, pmax(colSums(mat), 1), FUN="/") * 1000
write.csv2(rel, "{relative_name}")

index_type <- "{index_type}"
score <- matrix(0, nrow=nrow(mat), ncol=ncol(mat))
rownames(score) <- rownames(mat)
colnames(score) <- colnames(mat)

M <- sum(mat)
for (i in 1:nrow(mat)) {{
  K <- sum(mat[i, ])
  for (j in 1:ncol(mat)) {{
    n <- sum(mat[, j])
    obs11 <- mat[i, j]
    obs12 <- K - obs11
    obs21 <- n - obs11
    obs22 <- M - K - n + obs11
    exp11 <- (K * n) / M
    if (index_type == "chi2") {{
      exp12 <- (K * (M - n)) / M
      exp21 <- ((M - K) * n) / M
      exp22 <- ((M - K) * (M - n)) / M
      c1 <- ifelse(exp11 > 0, ((obs11 - exp11)^2) / exp11, 0)
      c2 <- ifelse(exp12 > 0, ((obs12 - exp12)^2) / exp12, 0)
      c3 <- ifelse(exp21 > 0, ((obs21 - exp21)^2) / exp21, 0)
      c4 <- ifelse(exp22 > 0, ((obs22 - exp22)^2) / exp22, 0)
      value <- c1 + c2 + c3 + c4
      if (obs11 < exp11) value <- -value
      score[i, j] <- value
    }} else {{
      if (obs11 >= exp11) {{
        p <- phyper(obs11 - 1, K, M - K, n, lower.tail = FALSE)
        value <- -log10(max(p, 1e-300))
      }} else {{
        p <- phyper(obs11, K, M - K, n, lower.tail = TRUE)
        value <- -log10(max(p, 1e-300))
        value <- -value
      }}
      score[i, j] <- value
    }}
  }}
}}
write.csv2(score, "{scores_name}")

if ({run_afc} && ncol(mat) > 2 && nrow(mat) > 2) {{
  suppressPackageStartupMessages(library(ca))
  afc <- ca(mat)
  png("{afc_name}", width={width}, height={height}, units="px", res=200)
  plot(afc, main="AFC - Tabela lexical")
  dev.off()
}}
"""
        script_path.write_text(content.strip() + "\n", encoding="utf-8")
        return script_path

    def _execute_script(
        self,
        script_path: Optional[Path],
        prepared: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute R script when requested; otherwise keep python mode."""
        backend = str(params.get("backend", "python")).lower()
        if backend != "r" or script_path is None:
            return {"backend_used": "python"}

        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )
            return {
                "backend_used": "r",
                "scores_csv_path": self.output_dir / "specificities_scores.csv",
                "relative_csv_path": self.output_dir / "specificities_relative.csv",
                "afc_graph_path": self.output_dir / "specificities_afc.png",
            }
        except (RNotFoundError, RTimeoutError, RExecutionError) as exc:
            if bool(params.get("allow_python_fallback", True)):
                self._logger.warning(
                    "Falha na execucao R para especificidades; usando fallback Python. Erro: %s",
                    exc,
                )
                return {
                    "backend_used": "python_fallback",
                    "fallback_reason": str(exc),
                }
            raise SpecificitiesAnalysisError(
                what="Falha na execucao R da analise de especificidades.",
                why=str(exc),
                how="Verifique instalacao do R/pacotes ou habilite fallback Python.",
            ) from exc

    def _parse_results(
        self,
        prepared: Dict[str, Any],
        execution_meta: Dict[str, Any],
        params: Dict[str, Any],
    ) -> SpecificitiesResult:
        """Parse results from R outputs or compute in Python."""
        backend_used = execution_meta.get("backend_used", "python")
        fallback_reason = execution_meta.get("fallback_reason")

        if backend_used == "r":
            scores_csv = execution_meta.get("scores_csv_path")
            relative_csv = execution_meta.get("relative_csv_path")
            if scores_csv and Path(scores_csv).exists() and relative_csv and Path(relative_csv).exists():
                row_labels, col_labels, scores = self._read_matrix_csv(Path(scores_csv))
                _, _, relative = self._read_matrix_csv(Path(relative_csv))
                counts = prepared["counts"]
            else:
                # Safety fallback if R did not emit expected files
                row_labels = prepared["row_labels"]
                col_labels = prepared["col_labels"]
                counts = prepared["counts"]
                scores, relative = self._compute_scores(prepared["index_type"], counts)
                backend_used = "python_fallback"
                fallback_reason = "Arquivos de saida R ausentes; calculo Python utilizado."
        else:
            row_labels = prepared["row_labels"]
            col_labels = prepared["col_labels"]
            counts = prepared["counts"]
            scores, relative = self._compute_scores(prepared["index_type"], counts)

        scores_csv_path = self.output_dir / "specificities_scores.csv"
        relative_csv_path = self.output_dir / "specificities_relative.csv"
        self._write_matrix_csv(scores_csv_path, row_labels, col_labels, scores)
        self._write_matrix_csv(relative_csv_path, row_labels, col_labels, relative)

        max_terms = int(params.get("max_terms_per_variable", 200))
        scores_by_variable = self._build_entries(
            row_labels=row_labels,
            col_labels=col_labels,
            counts=counts,
            scores=scores,
            relative=relative,
            max_terms=max_terms,
        )
        plot_path, plot_data_path = self._generate_specificities_plot(
            row_labels=row_labels,
            col_labels=col_labels,
            scores=scores,
            params=params,
        )

        afc_path = execution_meta.get("afc_graph_path")
        afc_graph_path = Path(afc_path) if afc_path and Path(afc_path).exists() else None

        return SpecificitiesResult(
            index_type=prepared["index_type"],
            min_freq=prepared["min_freq"],
            metadata_tokens=prepared["metadata_tokens"],
            scores_by_variable=scores_by_variable,
            lexical_table_path=prepared["lexical_table_path"],
            gram_table_path=prepared["gram_table_path"],
            scores_csv_path=scores_csv_path if scores_csv_path.exists() else None,
            relative_csv_path=relative_csv_path if relative_csv_path.exists() else None,
            specificities_plot_data_path=plot_data_path,
            specificities_plot_path=plot_path,
            afc_graph_path=afc_graph_path,
            backend_used=backend_used,
            fallback_reason=fallback_reason,
        )

    def _resolve_metadata_tokens(self, params: Dict[str, Any]) -> List[str]:
        tokens = params.get("metadata_tokens")
        if tokens:
            normalized = []
            for token in tokens:
                t = str(token).strip()
                if not t:
                    continue
                if not t.startswith("*"):
                    t = f"*{t}"
                normalized.append(t)
            return sorted(set(normalized))

        variables = params.get("metadata_variables")
        all_tokens = self.corpus.make_etoiles()
        if variables:
            selected: List[str] = []
            names = {str(var).strip().lstrip("*") for var in variables if str(var).strip()}
            for token in all_tokens:
                raw = token.lstrip("*")
                key = raw.split("_", 1)[0]
                if key in names:
                    selected.append(token)
            return sorted(set(selected))

        return sorted(set(all_tokens))

    @staticmethod
    def _write_table(table: List[List[Any]], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=';')
            for row in table:
                writer.writerow(row)

    @staticmethod
    def _compute_scores(index_type: str, counts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Compute specificity scores and relative frequencies per thousand."""
        matrix = counts.astype(float, copy=True)
        if matrix.size == 0:
            return matrix, matrix

        row_totals = matrix.sum(axis=1)
        col_totals = matrix.sum(axis=0)
        total = float(matrix.sum())
        if total <= 0:
            return np.zeros_like(matrix), np.zeros_like(matrix)

        relative = np.zeros_like(matrix, dtype=float)
        for j in range(matrix.shape[1]):
            denom = col_totals[j]
            if denom > 0:
                relative[:, j] = (matrix[:, j] / denom) * 1000.0

        scores = np.zeros_like(matrix, dtype=float)
        for i in range(matrix.shape[0]):
            K = row_totals[i]
            for j in range(matrix.shape[1]):
                n = col_totals[j]
                obs11 = matrix[i, j]
                obs12 = K - obs11
                obs21 = n - obs11
                obs22 = total - K - n + obs11
                exp11 = (K * n) / total if total > 0 else 0.0

                if index_type == "chi2":
                    exp12 = (K * (total - n)) / total if total > 0 else 0.0
                    exp21 = ((total - K) * n) / total if total > 0 else 0.0
                    exp22 = ((total - K) * (total - n)) / total if total > 0 else 0.0
                    chi = 0.0
                    if exp11 > 0:
                        chi += ((obs11 - exp11) ** 2) / exp11
                    if exp12 > 0:
                        chi += ((obs12 - exp12) ** 2) / exp12
                    if exp21 > 0:
                        chi += ((obs21 - exp21) ** 2) / exp21
                    if exp22 > 0:
                        chi += ((obs22 - exp22) ** 2) / exp22
                    scores[i, j] = chi if obs11 >= exp11 else -chi
                else:
                    M = int(round(total))
                    K_int = int(round(K))
                    n_int = int(round(n))
                    x = int(round(obs11))
                    exp = exp11
                    if obs11 >= exp:
                        p = float(hypergeom.sf(x - 1, M, K_int, n_int))
                        p = max(min(p, 1.0), 1e-300)
                        score = -math.log10(p)
                    else:
                        p = float(hypergeom.cdf(x, M, K_int, n_int))
                        p = max(min(p, 1.0), 1e-300)
                        score = -math.log10(p)
                        score = -score
                    scores[i, j] = score

        return scores, relative

    @staticmethod
    def _write_matrix_csv(
        path: Path,
        row_labels: List[str],
        col_labels: List[str],
        matrix: np.ndarray,
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow([""] + col_labels)
            for idx, row_label in enumerate(row_labels):
                row_values = [float(val) for val in matrix[idx, :]]
                writer.writerow([row_label] + row_values)

    @staticmethod
    def _read_matrix_csv(path: Path) -> Tuple[List[str], List[str], np.ndarray]:
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.reader(file, delimiter=';')
            header = next(reader, None)
            if not header:
                return [], [], np.array([])
            col_labels = [str(label) for label in header[1:]]
            row_labels: List[str] = []
            values: List[List[float]] = []
            for row in reader:
                if not row:
                    continue
                row_labels.append(str(row[0]))
                converted = []
                for val in row[1:]:
                    try:
                        converted.append(float(val))
                    except ValueError:
                        converted.append(0.0)
                values.append(converted)
        return row_labels, col_labels, np.array(values, dtype=float)

    @staticmethod
    def _build_entries(
        row_labels: List[str],
        col_labels: List[str],
        counts: np.ndarray,
        scores: np.ndarray,
        relative: np.ndarray,
        max_terms: int,
    ) -> Dict[str, List[SpecificityEntry]]:
        entries: Dict[str, List[SpecificityEntry]] = {}
        for j, variable in enumerate(col_labels):
            class_entries: List[SpecificityEntry] = []
            for i, word in enumerate(row_labels):
                freq = int(round(counts[i, j]))
                if freq <= 0:
                    continue
                score = float(scores[i, j])
                rel = float(relative[i, j])
                sign = "+" if score >= 0 else "-"
                class_entries.append(
                    SpecificityEntry(
                        word=word,
                        variable=variable,
                        score=score,
                        frequency=freq,
                        relative_per_thousand=rel,
                        sign=sign,
                    )
                )
            class_entries.sort(key=lambda item: abs(item.score), reverse=True)
            if max_terms > 0:
                class_entries = class_entries[:max_terms]
            entries[variable] = class_entries
        return entries

    def _generate_specificities_plot(
        self,
        row_labels: List[str],
        col_labels: List[str],
        scores: np.ndarray,
        params: Dict[str, Any],
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Generate IRaMuTeQ-like specificities plot through specificities.R."""
        if not bool(params.get("generate_plot", True)):
            return None, None

        if scores.size == 0 or not row_labels or not col_labels:
            return None, None

        plot_data_path = self.output_dir / "specificities_plot_data.csv"
        self._write_specificities_plot_data(plot_data_path, row_labels, col_labels, scores)
        if not plot_data_path.exists():
            return None, None

        typegraph = str(
            params.get("plot_typegraph", params.get("typegraph", "png")) or "png"
        ).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"
        output_file = self.output_dir / f"specificities_plot.{typegraph}"

        top_n = int(params.get("plot_top_n", params.get("top_n", 30)))
        width = int(params.get("plot_width", 1200))
        height = int(params.get("plot_height", 800))
        bw = bool(params.get("plot_bw", params.get("bw", False)))

        try:
            from ..visualization.r_integration import RBridge, RVisualizer

            # Preferred path: high-level visualizer API
            viz = RVisualizer()
            if viz.r_available:
                viz.create_specificities_plot(
                    spec_file=str(plot_data_path),
                    output_file=str(output_file),
                    width=width,
                    height=height,
                    top_n=top_n,
                    bw=bw,
                )
                if output_file.exists():
                    return output_file, plot_data_path

            # Fallback path: execute script directly through RBridge
            bridge = RBridge()
            if not bridge.r_available:
                return None, plot_data_path

            success, stdout, _ = bridge.execute_script(
                "specificities.R",
                {
                    "spec_file": str(plot_data_path),
                    "output_file": str(output_file),
                    "width": width,
                    "height": height,
                    "top_n": top_n,
                    "bw": bw,
                },
                timeout=180,
            )
            if success and output_file.exists():
                return output_file, plot_data_path

            self._logger.warning("Falha ao gerar specificities plot via R: %s", stdout.strip())
            return None, plot_data_path
        except Exception as exc:
            self._logger.warning("Erro ao gerar specificities plot via R: %s", exc)
            return None, plot_data_path

    @staticmethod
    def _write_specificities_plot_data(
        path: Path,
        row_labels: List[str],
        col_labels: List[str],
        scores: np.ndarray,
    ) -> None:
        """Write class_id/word/score CSV consumed by specificities.R."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["class_id", "class_label", "word", "score"])
            for class_idx, class_label in enumerate(col_labels, start=1):
                for row_idx, word in enumerate(row_labels):
                    if row_idx >= scores.shape[0] or (class_idx - 1) >= scores.shape[1]:
                        continue
                    value = float(scores[row_idx, class_idx - 1])
                    if not np.isfinite(value):
                        continue
                    writer.writerow([class_idx, class_label, word, value])
