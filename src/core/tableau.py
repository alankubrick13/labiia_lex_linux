"""Tableau data structure for matrix analyses (CSV/XLSX)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd


class TableauError(Exception):
    """Friendly error for matrix loading and serialization."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


@dataclass
class Tableau:
    """Represents a tabular matrix loaded from CSV/XLSX."""

    data: pd.DataFrame
    row_names: List[str]
    col_names: List[str]
    has_header: bool
    has_rownames: bool
    source_path: Optional[Path] = None

    @classmethod
    def from_csv(
        cls,
        path: Union[str, Path],
        sep: Optional[str] = ";",
        header: bool = True,
        rownames: bool = True,
        encoding: str = "utf-8",
    ) -> "Tableau":
        """Load a matrix from CSV."""
        source = Path(path)
        if not source.exists():
            raise TableauError(
                what="Arquivo de matriz não encontrado.",
                why=f"O caminho informado não existe: {source}",
                how="Selecione um arquivo CSV válido e tente novamente.",
            )

        candidates = [encoding]
        for fallback in ("utf-8-sig", "latin-1", "cp1252"):
            if fallback not in candidates:
                candidates.append(fallback)

        dataframe: Optional[pd.DataFrame] = None
        used_encoding: Optional[str] = None
        last_error: Optional[Exception] = None

        for candidate in candidates:
            try:
                delimiter = sep or cls._detect_delimiter(source, candidate)
                dataframe = pd.read_csv(
                    source,
                    sep=delimiter,
                    header=0 if header else None,
                    index_col=0 if rownames else None,
                    encoding=candidate,
                )
                used_encoding = candidate
                break
            except UnicodeDecodeError as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - pandas-specific branches
                last_error = exc

        if dataframe is None:
            raise TableauError(
                what="Falha ao ler arquivo CSV.",
                why=str(last_error) if last_error else "Erro de leitura desconhecido.",
                how="Verifique delimitador/encoding do arquivo e tente novamente.",
            )

        normalized = cls._normalize_dataframe(dataframe, header=header, rownames=rownames)
        result = cls._from_dataframe(
            normalized,
            has_header=header,
            has_rownames=rownames,
            source_path=source,
        )
        # Track effective encoding for diagnostics in-memory only.
        result.data.attrs["encoding"] = used_encoding or encoding
        return result

    @classmethod
    def from_xlsx(
        cls,
        path: Union[str, Path],
        sheet: Union[int, str] = 0,
        header: bool = True,
        rownames: bool = False,
    ) -> "Tableau":
        """Load a matrix from XLSX."""
        source = Path(path)
        if not source.exists():
            raise TableauError(
                what="Arquivo de matriz não encontrado.",
                why=f"O caminho informado não existe: {source}",
                how="Selecione uma planilha válida e tente novamente.",
            )

        try:
            dataframe = pd.read_excel(
                source,
                sheet_name=sheet,
                header=0 if header else None,
                index_col=0 if rownames else None,
            )
        except Exception as exc:
            raise TableauError(
                what="Falha ao ler planilha XLSX.",
                why=str(exc),
                how="Verifique se o arquivo não está corrompido e tente novamente.",
            ) from exc

        normalized = cls._normalize_dataframe(dataframe, header=header, rownames=rownames)
        return cls._from_dataframe(
            normalized,
            has_header=header,
            has_rownames=rownames,
            source_path=source,
        )

    def to_csv(self, path: Union[str, Path], sep: str = ";") -> Path:
        """Persist matrix as CSV."""
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.data.to_csv(target, sep=sep, index=self.has_rownames, encoding="utf-8")
            return target
        except OSError as exc:
            raise TableauError(
                what="Falha ao salvar matriz em CSV.",
                why=str(exc),
                how="Verifique permissões de escrita no diretório de destino.",
            ) from exc

    def numeric_data(self, fill_value: float = 0.0) -> pd.DataFrame:
        """Return numeric view of the matrix with non-numeric values replaced."""
        numeric = self.data.apply(pd.to_numeric, errors="coerce")
        return numeric.fillna(fill_value)

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    @staticmethod
    def _from_dataframe(
        dataframe: pd.DataFrame,
        has_header: bool,
        has_rownames: bool,
        source_path: Optional[Path],
    ) -> "Tableau":
        col_names = [str(col) for col in dataframe.columns]
        if has_rownames:
            row_names = [str(idx) for idx in dataframe.index]
        else:
            row_names = [str(i + 1) for i in range(len(dataframe))]
        return Tableau(
            data=dataframe,
            row_names=row_names,
            col_names=col_names,
            has_header=has_header,
            has_rownames=has_rownames,
            source_path=source_path,
        )

    @staticmethod
    def _normalize_dataframe(dataframe: pd.DataFrame, header: bool, rownames: bool) -> pd.DataFrame:
        working = dataframe.copy()
        if not header:
            working.columns = [f"col_{idx + 1}" for idx in range(working.shape[1])]

        working.columns = Tableau._deduplicate_labels([str(col).strip() for col in working.columns], prefix="col")
        if rownames:
            index_values = [str(value).strip() for value in working.index]
            working.index = Tableau._deduplicate_labels(index_values, prefix="row")
        return working

    @staticmethod
    def _deduplicate_labels(labels: List[str], prefix: str) -> List[str]:
        counts = {}
        normalized: List[str] = []
        for idx, raw in enumerate(labels):
            base = raw if raw else f"{prefix}_{idx + 1}"
            count = counts.get(base, 0)
            counts[base] = count + 1
            normalized.append(base if count == 0 else f"{base}_{count + 1}")
        return normalized

    @staticmethod
    def _detect_delimiter(path: Path, encoding: str) -> str:
        try:
            with path.open("r", encoding=encoding, newline="") as file:
                sample = file.read(4096)
        except OSError:
            return ";"

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            delimiters = {",": sample.count(","), ";": sample.count(";"), "\t": sample.count("\t"), "|": sample.count("|")}
            best = max(delimiters, key=delimiters.get)
            return best if delimiters[best] > 0 else ";"
