"""
Analise Prototipica (frequencia x rank de evocacao).
Usa script R: prototypical.R
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from ..core.corpus import Corpus
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger
from ..utils.paths import PathManager


@dataclass
class PrototypicalResult:
    """Resultado da analise prototipica."""

    core: List[str]
    first_periphery: List[str]
    contrast_zone: List[str]
    second_periphery: List[str]
    graph_path: Optional[Path] = None


class PrototypicalAnalysisError(Exception):
    """
    Erro amigavel para analise prototipica.

    Segue o padrao: o que aconteceu, por que aconteceu, como resolver.
    """

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class PrototypicalAnalysis:
    """
    Analise Prototipica / Representacao Social.

    Classifica palavras em 4 quadrantes baseado em frequencia e rank.
    """

    DEFAULT_PARAMS = {
        "mfreq": None,
        "mrank": None,
        "type": "classical",
        "cloud": True,
        "width": 900,
        "height": 700,
    }

    def __init__(self, corpus: Corpus, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)
        self._rscripts_dir = PathManager.rscripts_dir()

    def run(self, params: Optional[Dict[str, Any]] = None) -> PrototypicalResult:
        """Executa analise prototipica."""
        config = {**self.DEFAULT_PARAMS, **(params or {})}

        rows = self._load_freq_rank(config)
        if not rows:
            raise PrototypicalAnalysisError(
                what="Nao ha dados para analise prototipica.",
                why="A tabela de frequencia e rank esta vazia.",
                how="Forneca dados com colunas word, freq e rank.",
            )

        mfreq = config.get("mfreq")
        mrank = config.get("mrank")

        total_freq = sum(freq for _, freq, _ in rows)
        if mfreq is None:
            mfreq = total_freq / len(rows)
        if mrank is None:
            mrank = sum(freq * rank for _, freq, rank in rows) / total_freq

        core, first_p, contrast, second_p = self._classify(rows, mfreq, mrank)

        data_file = self.output_dir / "prototypical_input.csv"
        self._write_data(rows, data_file)

        graph_path = self.output_dir / "prototypical.png"
        script_path = self.output_dir / "prototypical_script.R"
        self._write_r_script(data_file, graph_path, script_path, config, mfreq, mrank)

        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )
        except RNotFoundError as exc:
            raise PrototypicalAnalysisError(
                what="R nao encontrado no sistema.",
                why=str(exc),
                how="Instale o R (4.0+) e verifique se o Rscript esta disponivel no PATH.",
            ) from exc
        except RTimeoutError as exc:
            raise PrototypicalAnalysisError(
                what="Tempo limite excedido na analise prototipica.",
                why=str(exc),
                how="Tente reduzir o corpus ou aumente o tempo limite.",
            ) from exc
        except RExecutionError as exc:
            raise PrototypicalAnalysisError(
                what="Falha na execucao do script prototipico.",
                why=str(exc),
                how="Verifique se os pacotes R necessarios estao instalados.",
            ) from exc

        return PrototypicalResult(
            core=core,
            first_periphery=first_p,
            contrast_zone=contrast,
            second_periphery=second_p,
            graph_path=graph_path if graph_path.exists() else None,
        )

    def _load_freq_rank(self, params: Dict[str, Any]) -> List[Tuple[str, float, float]]:
        """Carrega dados de frequencia e rank de parametros ou arquivo."""
        rows: List[Tuple[str, float, float]] = []

        if "freq_rank" in params and params["freq_rank"] is not None:
            data = params["freq_rank"]
            if isinstance(data, dict):
                for word, values in data.items():
                    freq, rank = values
                    rows.append((str(word), float(freq), float(rank)))
            else:
                for item in data:
                    if len(item) >= 3:
                        word, freq, rank = item[0], item[1], item[2]
                        rows.append((str(word), float(freq), float(rank)))
            return rows

        data_path = params.get("data_path")
        if data_path:
            path = Path(data_path)
            if not path.exists():
                raise PrototypicalAnalysisError(
                    what="Arquivo de dados nao encontrado.",
                    why=f"O arquivo {path} nao existe.",
                    how="Verifique o caminho do arquivo de dados.",
                )

            with path.open("r", encoding="utf-8") as file:
                reader = csv.reader(file, delimiter=';')
                header = next(reader, None)
                for row in reader:
                    if not row:
                        continue
                    if len(row) >= 3:
                        word = row[0]
                        try:
                            freq = float(row[1])
                            rank = float(row[2])
                        except ValueError:
                            continue
                        rows.append((word, freq, rank))
            return rows

        raise PrototypicalAnalysisError(
            what="Dados de frequencia/rank nao fornecidos.",
            why="A analise prototipica precisa de frequencia e rank das palavras.",
            how="Forneca 'freq_rank' ou 'data_path' nos parametros.",
        )

    def _classify(
        self,
        rows: List[Tuple[str, float, float]],
        mfreq: float,
        mrank: float,
    ) -> Tuple[List[str], List[str], List[str], List[str]]:
        """Classifica palavras nos quatro quadrantes."""
        core: List[str] = []
        first_p: List[str] = []
        contrast: List[str] = []
        second_p: List[str] = []

        for word, freq, rank in rows:
            if freq >= mfreq and rank <= mrank:
                core.append(word)
            elif freq >= mfreq and rank > mrank:
                first_p.append(word)
            elif freq < mfreq and rank <= mrank:
                contrast.append(word)
            else:
                second_p.append(word)

        return core, first_p, contrast, second_p

    def _write_data(self, rows: List[Tuple[str, float, float]], path: Path) -> None:
        """Escreve tabela de frequencia/rank para CSV."""
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow(["word", "freq", "rank"])
            for word, freq, rank in rows:
                writer.writerow([word, freq, rank])

    def _write_r_script(
        self,
        data_file: Path,
        graph_path: Path,
        script_path: Path,
        params: Dict[str, Any],
        mfreq: float,
        mrank: float,
    ) -> None:
        """Cria script R para gerar o grafico prototipico."""
        rscripts_path = self._rscripts_dir.as_posix()
        data_name = data_file.name
        graph_name = graph_path.name
        mfreq_val = "NULL" if params.get("mfreq") is None else mfreq
        mrank_val = "NULL" if params.get("mrank") is None else mrank
        cloud_val = "TRUE" if params.get("cloud", True) else "FALSE"
        type_val = params.get("type", "classical")
        width = int(params.get("width", 900))
        height = int(params.get("height", 700))

        content = (
            f"source(\"{rscripts_path}/prototypical.R\")\n"
            f"data <- read.csv(\"{data_name}\", header=TRUE, sep=\";\", dec=\".\")\n"
            "rownames(data) <- data[,1]\n"
            "data <- data[, -1]\n"
            f"png(\"{graph_name}\", width={width}, height={height}, units='px', res=200)\n"
            f"prototypical(data, mfreq={mfreq_val}, mrank={mrank_val}, cloud={cloud_val}, type=\"{type_val}\")\n"
            "dev.off()\n"
        )

        script_path.write_text(content, encoding="utf-8")
