"""
Contratos compartilhados da Suite Semantica Classica.

Fonte unica de verdade para tipos publicos, excecoes e contratos
de dados entre os modulos de analise semantica.

Este modulo NAO importa nada de ``src.ui`` nem de ``src.core``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Excecao de dominio
# ---------------------------------------------------------------------------

class SemanticAnalysisError(Exception):
    """Erro amigavel para analises semanticas.

    Segue o padrao What / Why / How do restante do LabiiaLex.
    """

    def __init__(self, what: str, why: str, how: str) -> None:
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que: {why}\nComo resolver: {how}"
        super().__init__(message)


# ---------------------------------------------------------------------------
# Manifest de artefatos
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class ArtifactManifest:
    """Concentra todos os caminhos de artefatos de uma analise."""

    primary_image: Optional[Path] = None
    primary_table: Optional[Path] = None
    summary_json: Optional[Path] = None
    secondary_images: List[Path] = field(default_factory=list)
    secondary_tables: List[Path] = field(default_factory=list)
    extra_files: List[Path] = field(default_factory=list)

    def all_paths(self) -> List[Path]:
        """Retorna todos os caminhos nao-None achatados."""
        paths: List[Path] = []
        for p in (self.primary_image, self.primary_table, self.summary_json):
            if p is not None:
                paths.append(p)
        paths.extend(self.secondary_images)
        paths.extend(self.secondary_tables)
        paths.extend(self.extra_files)
        return paths


# ---------------------------------------------------------------------------
# Base de parametros
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class BaseSemanticParams:
    """Base para todos os *Params das analises semanticas.

    Subclasses devem expor ``from_mapping`` como unica borda de parsing.
    """

    random_state: int = 42


# ---------------------------------------------------------------------------
# Base de resultado
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class BaseSemanticResult:
    """Base para todos os *Result das analises semanticas."""

    analysis_type: str
    output_dir: Path

    # -- helpers obrigatorios --------------------------------------------------

    def primary_image_path(self) -> Optional[Path]:
        """Retorna caminho da imagem principal, se existir."""
        return None  # subclasses devem sobrescrever

    def primary_table_path(self) -> Optional[Path]:
        """Retorna caminho da tabela principal, se existir."""
        return None  # subclasses devem sobrescrever

    def artifact_manifest(self) -> ArtifactManifest:
        """Retorna manifest completo de artefatos."""
        return ArtifactManifest(
            primary_image=self.primary_image_path(),
            primary_table=self.primary_table_path(),
        )

    def to_history_metadata(self) -> Dict[str, object]:
        """Serializa resultado para persistencia em historico.

        Converte todos os ``Path`` para ``str`` nesta borda.
        """
        manifest = self.artifact_manifest()
        result: Dict[str, object] = {
            "analysis_type": self.analysis_type,
            "output_dir": str(self.output_dir),
        }
        if manifest.primary_image is not None:
            result["primary_image"] = str(manifest.primary_image)
        if manifest.primary_table is not None:
            result["primary_table"] = str(manifest.primary_table)
        if manifest.summary_json is not None:
            result["summary_json"] = str(manifest.summary_json)
        if manifest.secondary_images:
            result["secondary_images"] = [str(p) for p in manifest.secondary_images]
        if manifest.secondary_tables:
            result["secondary_tables"] = [str(p) for p in manifest.secondary_tables]
        if manifest.extra_files:
            result["extra_files"] = [str(p) for p in manifest.extra_files]
        return result


# ---------------------------------------------------------------------------
# Contrato compartilhado de palavras-chave
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class KeyphraseCandidate:
    """Candidato a frase-chave extraido pelo YAKE.

    Contrato compartilhado entre componentes semanticos ativos.
    Nao depende de CSV; e transportado em memoria.
    """

    phrase: str
    normalized_phrase: str
    score: float
    frequency: int
    degree: int
    doc_count: int = 0
    mean_position: float = 0.0
    raw_yake_score: Optional[float] = None
