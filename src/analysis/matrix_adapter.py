"""Adapters to reuse CHD/AFC/Similarity workflows on matrix data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..core.r_script_generator import RScriptGenerator
from ..core.tableau import Tableau


@dataclass
class MatrixAFCResult:
    """AFC output for a numeric matrix."""

    graph_path: Optional[Path]
    row_coords: np.ndarray
    col_coords: np.ndarray
    eigenvalues: np.ndarray
    explained_variance: List[float]
    row_labels: List[str]
    col_labels: List[str]


@dataclass
class MatrixCHDResult:
    """CHD output for a numeric matrix."""

    dendrogram_path: Optional[Path]
    clusters_path: Optional[Path]
    assignments: Dict[str, int]


@dataclass
class MatrixSimilarityResult:
    """Similarity output for a numeric matrix."""

    graph_path: Optional[Path]
    adjacency_matrix_path: Path
    communities: Optional[Dict[str, int]]
    centrality: Optional[Dict[str, float]]


class MatrixAnalysisAdapterError(Exception):
    """Friendly error for matrix adapter workflows."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class MatrixAnalysisAdapter:
    """Reuse R templates for CHD/AFC/Similarity over a generic matrix."""

    DEFAULT_AFC_PARAMS = {
        "n_dim": 2,
        "typegraph": "png",
        "width": 800,
        "height": 800,
    }
    DEFAULT_CHD_PARAMS = {
        "nb_classes": 4,
        "method": "ward.D2",
        "typegraph": "png",
        "width": 1200,
        "height": 900,
    }
    DEFAULT_SIM_PARAMS = {
        "coefficient": 0,
        "layout": "frutch",
        "min_edge": 0,
        "vertex_size_min": 5,
        "vertex_size_max": 30,
        "grayscale": False,
        "label_cex": 0.7,
        "arbremax": True,
        "detect_communities": False,
        "community_method": "edge_betweenness",
        "typegraph": "png",
        "width": 1000,
        "height": 1000,
    }

    def __init__(self, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.r_executor = r_executor or RExecutor()
        self.script_generator = RScriptGenerator()

    def run_afc(self, tableau: Tableau, params: Optional[Dict[str, Any]] = None) -> MatrixAFCResult:
        """Run AFC directly on the matrix."""
        config = {**self.DEFAULT_AFC_PARAMS, **(params or {})}
        run_dir = self._ensure_dir("afc")
        numeric = self._prepare_numeric_matrix(tableau, min_rows=2, min_cols=2)
        data_path = run_dir / "ContTable.csv"
        numeric.to_csv(data_path, sep=";", encoding="utf-8")

        typegraph = self._normalize_typegraph(config.get("typegraph"))
        graph_out = config.get("graph_out") or f"matrix_afc.{typegraph}"
        script_path = self.script_generator.generate_and_save(
            "afc",
            {
                **config,
                "pathout": str(run_dir),
                "typegraph": typegraph,
                "data_file": data_path.name,
                "graph_out": graph_out,
            },
            run_dir / "matrix_afc_script.R",
        )
        self._execute(script_path, run_dir, "AFC sobre matriz")

        row_coords, row_labels = self._read_coords(run_dir / "row_coords.csv")
        col_coords, col_labels = self._read_coords(run_dir / "col_coords.csv")
        eigenvalues, explained_variance = self._read_eigenvalues(run_dir / "eigenvalues.csv")
        graph_path = run_dir / str(graph_out)

        return MatrixAFCResult(
            graph_path=graph_path if graph_path.exists() else None,
            row_coords=row_coords,
            col_coords=col_coords,
            eigenvalues=eigenvalues,
            explained_variance=explained_variance,
            row_labels=row_labels,
            col_labels=col_labels,
        )

    def run_chd(self, tableau: Tableau, params: Optional[Dict[str, Any]] = None) -> MatrixCHDResult:
        """Run CHD over the matrix rows."""
        config = {**self.DEFAULT_CHD_PARAMS, **(params or {})}
        run_dir = self._ensure_dir("chd")
        numeric = self._prepare_numeric_matrix(tableau, min_rows=2, min_cols=2)
        data_path = run_dir / "TableUc1.csv"
        numeric.to_csv(data_path, sep=";", encoding="utf-8")

        typegraph = self._normalize_typegraph(config.get("typegraph"))
        graph_out = config.get("graph_out") or f"matrix_chd.{typegraph}"
        script_path = self.script_generator.generate_and_save(
            "chd",
            {
                **config,
                "pathout": str(run_dir),
                "typegraph": typegraph,
                "nb_classes": int(config.get("nb_classes", 5)),
                "data_file": data_path.name,
                "graph_out": graph_out,
            },
            run_dir / "matrix_chd_script.R",
        )
        self._execute(script_path, run_dir, "CHD sobre matriz")

        dendrogram_path = run_dir / str(graph_out)
        clusters_path = run_dir / "clusters.csv"
        assignments = self._read_clusters(clusters_path)

        return MatrixCHDResult(
            dendrogram_path=dendrogram_path if dendrogram_path.exists() else None,
            clusters_path=clusters_path if clusters_path.exists() else None,
            assignments=assignments,
        )

    def run_similarity(
        self,
        tableau: Tableau,
        params: Optional[Dict[str, Any]] = None,
    ) -> MatrixSimilarityResult:
        """Run similarity graph from matrix-derived co-occurrence."""
        config = {**self.DEFAULT_SIM_PARAMS, **(params or {})}
        run_dir = self._ensure_dir("similarity")
        numeric = self._prepare_numeric_matrix(tableau, min_rows=2, min_cols=2)

        cooc = numeric.transpose().dot(numeric)
        np.fill_diagonal(cooc.values, 0.0)
        cooc_path = run_dir / "contingency.csv"
        cooc.to_csv(cooc_path, sep=";", encoding="utf-8")

        typegraph = self._normalize_typegraph(config.get("typegraph"))
        graph_out = config.get("graph_out") or f"matrix_similarity.{typegraph}"
        communities_out = config.get("communities_out") or "matrix_similarity_communities.csv"
        centrality_out = config.get("centrality_out") or "matrix_similarity_centrality.csv"

        script_path = self.script_generator.generate_and_save(
            "similarity",
            {
                **config,
                "pathout": str(run_dir),
                "typegraph": typegraph,
                "data_file": cooc_path.name,
                "graph_out": graph_out,
                "communities_out": communities_out,
                "centrality_out": centrality_out,
            },
            run_dir / "matrix_similarity_script.R",
        )
        self._execute(script_path, run_dir, "Similaridade sobre matriz")

        graph_path = run_dir / str(graph_out)
        communities = self._read_communities(run_dir / str(communities_out))
        centrality = self._read_centrality(run_dir / str(centrality_out))
        return MatrixSimilarityResult(
            graph_path=graph_path if graph_path.exists() else None,
            adjacency_matrix_path=cooc_path,
            communities=communities,
            centrality=centrality,
        )

    def _execute(self, script_path: Path, working_dir: Path, label: str) -> None:
        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(working_dir),
                timeout=900,
            )
        except RNotFoundError as exc:
            raise MatrixAnalysisAdapterError(
                what=f"R não encontrado para {label}.",
                why=str(exc),
                how="Instale/configure o R e tente novamente.",
            ) from exc
        except RTimeoutError as exc:
            raise MatrixAnalysisAdapterError(
                what=f"Tempo excedido durante {label}.",
                why=str(exc),
                how="Reduza a matriz ou ajuste parâmetros da análise.",
            ) from exc
        except RExecutionError as exc:
            raise MatrixAnalysisAdapterError(
                what=f"Falha ao executar {label}.",
                why=str(exc),
                how="Verifique pacotes R necessários e tente novamente.",
            ) from exc

    def _prepare_numeric_matrix(self, tableau: Tableau, min_rows: int, min_cols: int) -> pd.DataFrame:
        if tableau is None or tableau.data is None or tableau.data.empty:
            raise MatrixAnalysisAdapterError(
                what="Matriz vazia para análise.",
                why="Nenhum dado foi carregado no módulo de matriz.",
                how="Abra uma matriz CSV/XLSX antes de executar a análise.",
            )

        numeric = tableau.numeric_data(fill_value=0.0)
        numeric = numeric.replace([np.inf, -np.inf], 0.0)
        numeric = numeric.loc[(numeric.sum(axis=1) != 0), (numeric.sum(axis=0) != 0)]
        numeric = numeric.fillna(0.0)

        if numeric.shape[0] < min_rows or numeric.shape[1] < min_cols:
            raise MatrixAnalysisAdapterError(
                what="Matriz insuficiente após filtro numérico.",
                why=(
                    f"A análise requer pelo menos {min_rows} linhas e {min_cols} colunas "
                    f"(matriz atual: {numeric.shape[0]}x{numeric.shape[1]})."
                ),
                how="Use uma matriz com mais dados numéricos ou reduza filtros.",
            )

        numeric.columns = [str(col) for col in numeric.columns]
        numeric.index = [str(idx) for idx in numeric.index]
        return numeric

    def _ensure_dir(self, name: str) -> Path:
        folder = self.output_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _normalize_typegraph(value: Any) -> str:
        graph_type = str(value or "png").strip().lower()
        return graph_type if graph_type in {"png", "svg"} else "png"

    @staticmethod
    def _read_coords(path: Path) -> Tuple[np.ndarray, List[str]]:
        if not path.exists():
            return np.array([]), []
        labels: List[str] = []
        rows: List[List[float]] = []
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.reader(file)
            next(reader, None)
            for row in reader:
                if len(row) < 2:
                    continue
                labels.append(str(row[0]))
                values: List[float] = []
                for value in row[1:]:
                    try:
                        values.append(float(value))
                    except ValueError:
                        values.append(0.0)
                rows.append(values)
        return np.array(rows, dtype=float), labels

    @staticmethod
    def _read_eigenvalues(path: Path) -> Tuple[np.ndarray, List[float]]:
        if not path.exists():
            return np.array([]), []

        values: List[float] = []
        variance: List[float] = []
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    values.append(float(row.get("eigenvalue", 0) or 0))
                except (TypeError, ValueError):
                    values.append(0.0)
                try:
                    variance.append(float(row.get("variance", 0) or 0))
                except (TypeError, ValueError):
                    variance.append(0.0)
        return np.array(values, dtype=float), variance

    @staticmethod
    def _read_clusters(path: Path) -> Dict[str, int]:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            delimiter = ","
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
            except csv.Error:
                delimiter = ";" if ";" in sample else ","
            reader = csv.reader(file, delimiter=delimiter)
            next(reader, None)
            result: Dict[str, int] = {}
            for row in reader:
                if len(row) < 2:
                    continue
                key = str(row[0]).strip().strip('"')
                value_raw = str(row[1]).strip()
                if not key:
                    continue
                try:
                    result[key] = int(float(value_raw))
                except ValueError:
                    continue
            return result

    def _read_communities(self, path: Path) -> Optional[Dict[str, int]]:
        rows = self._read_csv_rows(path)
        if not rows:
            return None

        communities: Dict[str, int] = {}
        for row in rows:
            term = str(row.get("term", "")).strip()
            raw = row.get("community", "")
            if not term or raw in ("", None):
                continue
            try:
                communities[term] = int(float(str(raw)))
            except ValueError:
                continue
        return communities or None

    def _read_centrality(self, path: Path) -> Optional[Dict[str, float]]:
        rows = self._read_csv_rows(path)
        if not rows:
            return None

        centrality: Dict[str, float] = {}
        for row in rows:
            term = str(row.get("term", "")).strip()
            if not term:
                continue
            raw = row.get("weighted_degree", row.get("degree", ""))
            try:
                centrality[term] = float(str(raw))
            except ValueError:
                continue
        return centrality or None

    @staticmethod
    def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            delimiter = ","
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
            except csv.Error:
                delimiter = ";" if ";" in sample else ","
            reader = csv.DictReader(file, delimiter=delimiter)
            return [dict(row) for row in reader if row]
