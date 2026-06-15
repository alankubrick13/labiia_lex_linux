"""Metadata-driven keyness analysis (R-only backend)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.corpus import Corpus
from ..utils.logger import get_logger
from ._extras_common import build_uci_records, detect_metadata_values, most_common_variable
from .keyness_r import KeynessRAnalysis, KeynessRAnalysisError, KeynessRScriptRunner


@dataclass
class KeynessExtraResult:
    """Result payload for keyness by metadata groups."""

    variable: str
    target_value: str
    graph_path: Optional[Path] = None
    table_path: Optional[Path] = None
    top_terms: List[Tuple[str, float, int, int, str]] = field(default_factory=list)


class KeynessExtraAnalysisError(Exception):
    """Friendly error for keyness extra analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}")


class KeynessExtraAnalysis:
    """Compute keyness between metadata groups using quanteda in R."""

    DEFAULT_PARAMS = {
        "variable": "",
        "target_value": "",
        "min_freq": 3,
        "top_n": 20,
        "measure": "lr",
        "remove_stopwords": True,
    }

    def __init__(
        self,
        corpus: Corpus,
        output_dir: Path,
        runner: Optional[KeynessRScriptRunner] = None,
    ) -> None:
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)
        self._runner = runner

    def run(self, params: Optional[Dict[str, Any]] = None) -> KeynessExtraResult:
        config = {**self.DEFAULT_PARAMS, **(params or {})}

        records = build_uci_records(self.corpus)
        if not records:
            raise KeynessExtraAnalysisError(
                what="Corpus sem UCIs para análise de keyness.",
                why="Nenhum documento foi encontrado após a importação.",
                how="Importe um corpus válido e tente novamente.",
            )

        metadata_values = detect_metadata_values(records)
        if not metadata_values:
            raise KeynessExtraAnalysisError(
                what="Não há variáveis de metadado para keyness.",
                why="As UCIs não possuem etoiles no formato *variavel_valor.",
                how="Importe um corpus com metadados e tente novamente.",
            )

        variable = str(config.get("variable", "") or "").strip().lower()
        if not variable:
            variable = most_common_variable(records) or ""
        if variable not in metadata_values:
            available = ", ".join(sorted(metadata_values.keys()))
            raise KeynessExtraAnalysisError(
                what="Variável de metadado inválida para keyness.",
                why=f"Variável '{variable}' não encontrada no corpus.",
                how=f"Use uma das variáveis disponíveis: {available}.",
            )

        target_value = str(config.get("target_value", "") or "").strip()
        if not target_value:
            target_value = str(metadata_values[variable][0] or "")

        target_docs: List[str] = []
        reference_docs: List[str] = []
        for record in records:
            value = str(record.metadata.get(variable, "") or "")
            if not value:
                continue
            clean_text = str(record.text or "").strip()
            if not clean_text:
                continue
            if value == target_value:
                target_docs.append(clean_text)
            else:
                reference_docs.append(clean_text)

        if not target_docs:
            raise KeynessExtraAnalysisError(
                what="Grupo alvo sem documentos para keyness.",
                why=f"Nenhuma UCI foi encontrada para {variable}={target_value}.",
                how="Escolha outro valor de metadado e tente novamente.",
            )
        if not reference_docs:
            raise KeynessExtraAnalysisError(
                what="Grupo de referência vazio para keyness.",
                why="Não há documentos fora do grupo alvo para comparação.",
                how="Escolha uma variável mais diversa ou outro valor alvo.",
            )

        min_freq = max(1, int(config.get("min_freq", 3)))
        top_n = max(5, int(config.get("top_n", 20)))
        measure = str(config.get("measure", "lr") or "lr").strip().lower()
        if measure not in {"lr", "chi2", "exact"}:
            measure = "lr"

        analyzer = KeynessRAnalysis(self.output_dir, runner=self._runner)
        try:
            result = analyzer.run(
                text_a="\n".join(target_docs),
                text_b="\n".join(reference_docs),
                name_a=f"{variable}={target_value}",
                name_b=f"outros {variable}",
                params={
                    "min_freq": min_freq,
                    "top_n": top_n,
                    "measure": measure,
                    "remove_stopwords": bool(config.get("remove_stopwords", True)),
                    "stopwords_lang": "pt",
                },
            )
        except KeynessRAnalysisError as exc:
            raise KeynessExtraAnalysisError(
                what="Falha ao executar keyness em R.",
                why=f"{exc.what} {exc.why}",
                how=exc.how,
            ) from exc

        top_rows = result.sorted_by("statistic")[:top_n]
        top_terms: List[Tuple[str, float, int, int, str]] = []
        for row in top_rows:
            direction = "target" if str(row.direction).upper() == "A" else "reference"
            top_terms.append((row.word, float(row.statistic), int(row.freq_a), int(row.freq_b), direction))

        return KeynessExtraResult(
            variable=variable,
            target_value=target_value,
            graph_path=result.graph_path,
            table_path=result.table_path,
            top_terms=top_terms,
        )
