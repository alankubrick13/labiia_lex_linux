"""
Distancia de Labbe entre textos.
Usa script R: distance-labbe.R
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, Dict, List

import numpy as np

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger
from ..utils.paths import PathManager


@dataclass
class LabbeResult:
    """Resultado da analise de distancia de Labbe."""

    distance_matrix: np.ndarray
    dendrogram_path: Optional[Path] = None
    heatmap_path: Optional[Path] = None


class LabbeAnalysisError(Exception):
    """
    Erro amigavel para analise Labbe.

    Segue o padrao: o que aconteceu, por que aconteceu, como resolver.
    """

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class LabbeAnalysis:
    """
    Distancia de Labbe entre textos.

    Calcula distancia intertextual para comparar similaridade entre documentos.
    """

    DEFAULT_PARAMS = {
        "min_freq": 3,
        "use_lemmas": False,
        "width": 800,
        "height": 600,
    }

    def __init__(self, corpus: Corpus, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.processor = TextProcessor(corpus)
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)
        self._rscripts_dir = PathManager.rscripts_dir()

    def run(self, params: Optional[Dict[str, Any]] = None) -> LabbeResult:
        """Executa analise de distancia de Labbe."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}

        try:
            min_freq = int(config.get("min_freq", 3))
            use_lemmas = bool(config.get("use_lemmas", False))

            self.processor.build_dtm(min_freq=min_freq, use_lemmas=use_lemmas)
            matrix = self.processor.dtm
            if matrix is None:
                raise LabbeAnalysisError(
                    what="Matriz documento-termo nao gerada.",
                    why="O corpus nao possui UCEs suficientes.",
                    how="Verifique o corpus e tente novamente.",
                )

            n_docs = matrix.shape[0]
            if n_docs < 2:
                raise LabbeAnalysisError(
                    what="Documentos insuficientes para análise Labbé.",
                    why=f"São necessários no mínimo 2 documentos, mas apenas {n_docs} foi(ram) encontrado(s).",
                    how="Importe um corpus com mais documentos.",
                )

            from scipy import sparse as sp
            doc_sums = np.asarray(
                matrix.sum(axis=1) if sp.issparse(matrix) else matrix.sum(axis=1)
            ).ravel()
            empty_mask = doc_sums == 0
            if empty_mask.any():
                n_empty = int(empty_mask.sum())
                raise LabbeAnalysisError(
                    what=f"{n_empty} documento(s) sem termos após filtragem.",
                    why=f"Com frequência mínima = {min_freq}, documentos curtos perderam todos os termos.",
                    how="Reduza a frequência mínima ou remova documentos muito curtos do corpus.",
                )

            table_path = self.output_dir / "labbe_table.csv"
            self._export_term_doc(matrix, table_path)

            script_path = self.output_dir / "labbe_script.R"
            self._write_r_script(script_path, table_path, config)

            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )

            distance_path = self.output_dir / "labbe_distance.csv"
            distance_matrix = self._read_distance_matrix(distance_path)

            dendro_path = self.output_dir / "labbe_dendrogram.png"
            heatmap_path = self.output_dir / "labbe_heatmap.png"

            return LabbeResult(
                distance_matrix=distance_matrix,
                dendrogram_path=dendro_path if dendro_path.exists() else None,
                heatmap_path=heatmap_path if heatmap_path.exists() else None,
            )

        except RNotFoundError as exc:
            raise LabbeAnalysisError(
                what="R nao encontrado no sistema.",
                why=str(exc),
                how="Instale o R (4.0+) e verifique se o Rscript esta disponivel no PATH.",
            ) from exc
        except RTimeoutError as exc:
            raise LabbeAnalysisError(
                what="Tempo limite excedido na analise Labbe.",
                why=str(exc),
                how="Tente reduzir o corpus ou aumente o tempo limite.",
            ) from exc
        except RExecutionError as exc:
            raise LabbeAnalysisError(
                what="Falha na execucao do script Labbe.",
                why=str(exc),
                how="Verifique se os pacotes R necessarios estao instalados.",
            ) from exc
        except LabbeAnalysisError:
            raise
        except Exception as exc:
            raise LabbeAnalysisError(
                what="Falha ao executar a analise Labbe.",
                why=str(exc),
                how="Verifique os dados exportados e tente novamente.",
            ) from exc

    def _export_term_doc(self, matrix: Any, path: Path) -> None:
        """Exporta matriz termo-documento para CSV."""
        vocab = self.processor.vocabulary
        doc_ids = self.processor.doc_ids

        dense = matrix.T.toarray()
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow([""] + [str(doc_id) for doc_id in doc_ids])
            for idx, word in enumerate(vocab):
                row = [word] + list(dense[idx])
                writer.writerow(row)

    def _write_r_script(self, script_path: Path, table_path: Path, params: Dict[str, Any]) -> None:
        """Cria script R para calcular distancia Labbe e gerar graficos."""
        rscripts_path = self._rscripts_dir.as_posix()
        data_name = table_path.name
        width = int(params.get("width", 800))
        height = int(params.get("height", 600))

        content = (
            f"source(\"{rscripts_path}/distance-labbe.R\")\n"
            f"tab <- read.csv(\"{data_name}\", header=TRUE, row.names=1, sep=\";\", dec=\".\")\n"
            "distmat <- dist.labbe(tab)\n"
            "write.csv(distmat, \"labbe_distance.csv\")\n"
            f"png(\"labbe_dendrogram.png\", width={width}, height={height}, units='px', res=200)\n"
            "hc <- hclust(as.dist(distmat))\n"
            "plot(hc, main=\"Distancia de Labbe\", xlab=\"\", sub=\"\")\n"
            "dev.off()\n"
            f"png(\"labbe_heatmap.png\", width={width}, height={height}, units='px', res=200)\n"
            "heatmap(as.matrix(distmat), symm=TRUE)\n"
            "dev.off()\n"
        )

        script_path.write_text(content, encoding="utf-8")

    def _read_distance_matrix(self, path: Path) -> np.ndarray:
        """Le matriz de distancia gerada pelo R."""
        if not path.exists():
            return np.array([])

        data: List[List[float]] = []
        with path.open("r", encoding="utf-8") as file:
            reader = csv.reader(file)
            header = next(reader, None)
            for row in reader:
                if len(row) <= 1:
                    continue
                try:
                    data.append([float(val) for val in row[1:] if val != ""])
                except ValueError:
                    continue
        return np.array(data, dtype=float)
