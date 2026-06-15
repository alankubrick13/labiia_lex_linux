"""Project save/load support for LabiiaLex."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from ..utils.logger import get_logger


@dataclass
class Project:
    """Serializable project metadata."""

    name: str
    corpus_path: Optional[Path]
    db_path: Optional[Path]
    config: Dict[str, Any]
    analyses: List[Dict[str, Any]]
    created_at: str
    updated_at: str
    project_dir: Optional[Path] = None
    lexproj_path: Optional[Path] = None
    history_path: Optional[Path] = None
    artifacts_dir: Optional[Path] = None
    corpus_snapshot_path: Optional[Path] = None
    corpus_snapshot: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProjectError(Exception):
    """Friendly project persistence error."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(
            f"O que aconteceu: {what}\n"
            f"Por que aconteceu: {why}\n"
            f"Como resolver: {how}"
        )


class ProjectManager:
    """Handles `.lexproj` save/load/export operations."""

    EXTENSION = ".lexproj"

    def __init__(self) -> None:
        self._logger = get_logger(__name__)

    def save(self, project: Project, path: Path) -> Project:
        """Save project metadata + assets and return normalized project."""
        lexproj_path = self._normalize_lexproj_path(path)
        project_dir = lexproj_path.with_suffix("")
        project_dir.mkdir(parents=True, exist_ok=True)

        history_path = project_dir / "analysis_history.json"
        artifacts_dir = project_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        config_path = project_dir / "config.json"
        db_path: Optional[Path] = project_dir / "corpus.db"
        snapshot_path = project_dir / "corpus_snapshot.txt"

        source_db = Path(project.db_path) if project.db_path else None
        if source_db and source_db.exists() and source_db.is_file():
            shutil.copy2(source_db, db_path)
        else:
            db_path = None

        self._write_json(config_path, project.config or {})
        normalized_analyses = self._normalize_analyses(project.analyses or [], artifacts_dir)
        self._write_json(history_path, normalized_analyses)

        if project.corpus_snapshot:
            snapshot_path.write_text(project.corpus_snapshot, encoding="utf-8")
        elif not snapshot_path.exists():
            snapshot_path = None

        now = datetime.now(timezone.utc).isoformat()
        created_at = project.created_at or now
        updated_at = now

        project_json_path = project_dir / "project.json"
        project_payload = {
            "name": project.name or lexproj_path.stem,
            "created_at": created_at,
            "updated_at": updated_at,
            "corpus_path": str(project.corpus_path or ""),
            "db_path": db_path.name if db_path else "",
            "config_path": config_path.name,
            "history_path": history_path.name,
            "artifacts_dir": artifacts_dir.name,
            "corpus_snapshot_path": snapshot_path.name if snapshot_path else "",
            "metadata": project.metadata or {},
        }
        self._write_json(project_json_path, project_payload)

        lexproj_payload = {
            "project_dir": project_dir.name,
            "project_file": "project.json",
            "version": 1,
        }
        self._write_json(lexproj_path, lexproj_payload)

        return Project(
            name=project_payload["name"],
            corpus_path=Path(project_payload["corpus_path"]) if project_payload["corpus_path"] else None,
            db_path=db_path,
            config=dict(project.config or {}),
            analyses=normalized_analyses,
            created_at=created_at,
            updated_at=updated_at,
            project_dir=project_dir,
            lexproj_path=lexproj_path,
            history_path=history_path,
            artifacts_dir=artifacts_dir,
            corpus_snapshot_path=snapshot_path,
            corpus_snapshot=project.corpus_snapshot,
            metadata=project.metadata or {},
        )

    def load(self, path: Path) -> Project:
        """Load project from `.lexproj` manifest."""
        lexproj_path = Path(path)
        if not lexproj_path.exists():
            raise ProjectError(
                what="Arquivo de projeto não encontrado.",
                why=f"O caminho {lexproj_path} não existe.",
                how="Selecione um arquivo .lexproj válido e tente novamente.",
            )

        lexproj_payload = self._read_json(lexproj_path)
        project_dir_name = str(lexproj_payload.get("project_dir", "")).strip()
        project_file = str(lexproj_payload.get("project_file", "project.json")).strip() or "project.json"
        project_dir = (lexproj_path.parent / project_dir_name) if project_dir_name else lexproj_path.with_suffix("")

        if not project_dir.exists():
            raise ProjectError(
                what="Pasta de dados do projeto não encontrada.",
                why=f"A pasta esperada {project_dir} não existe.",
                how="Mantenha o arquivo .lexproj junto com sua pasta de dados e tente novamente.",
            )

        project_payload = self._read_json(project_dir / project_file)
        config_path = project_dir / str(project_payload.get("config_path", "config.json"))
        history_path = project_dir / str(project_payload.get("history_path", "analysis_history.json"))
        db_rel = str(project_payload.get("db_path", "")).strip()
        db_path = project_dir / db_rel if db_rel else None
        snapshot_rel = str(project_payload.get("corpus_snapshot_path", "")).strip()
        snapshot_path = project_dir / snapshot_rel if snapshot_rel else None
        artifacts_dir = project_dir / str(project_payload.get("artifacts_dir", "artifacts"))

        config = self._read_json(config_path) if config_path.exists() else {}
        analyses = self._read_json(history_path) if history_path.exists() else []
        if not isinstance(analyses, list):
            analyses = []

        return Project(
            name=str(project_payload.get("name", lexproj_path.stem)),
            corpus_path=Path(str(project_payload.get("corpus_path", ""))) if project_payload.get("corpus_path") else None,
            db_path=db_path,
            config=config if isinstance(config, dict) else {},
            analyses=analyses,
            created_at=str(project_payload.get("created_at", "")),
            updated_at=str(project_payload.get("updated_at", "")),
            project_dir=project_dir,
            lexproj_path=lexproj_path,
            history_path=history_path,
            artifacts_dir=artifacts_dir,
            corpus_snapshot_path=snapshot_path,
            corpus_snapshot=snapshot_path.read_text(encoding="utf-8") if snapshot_path and snapshot_path.exists() else None,
            metadata=project_payload.get("metadata", {}) if isinstance(project_payload.get("metadata"), dict) else {},
        )

    def export_portable(self, project: Project, zip_path: Path) -> Path:
        """Export project `.lexproj` + data folder as ZIP."""
        if not project.lexproj_path or not project.project_dir:
            raise ProjectError(
                what="Projeto sem caminhos persistidos para exportação.",
                why="É necessário salvar o projeto antes de exportar.",
                how="Use 'Salvar Projeto' e tente a exportação novamente.",
            )

        destination = Path(zip_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, mode="w", compression=ZIP_DEFLATED) as zip_file:
            zip_file.write(project.lexproj_path, arcname=project.lexproj_path.name)
            for file_path in project.project_dir.rglob("*"):
                if file_path.is_file():
                    arcname = Path(project.project_dir.name) / file_path.relative_to(project.project_dir)
                    zip_file.write(file_path, arcname=str(arcname))
        return destination

    def _normalize_analyses(self, analyses: List[Dict[str, Any]], artifacts_dir: Path) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for idx, raw in enumerate(analyses):
            item = dict(raw or {})
            entry_id = str(item.get("entry_id") or uuid4().hex)
            analysis_type = str(item.get("analysis_type", "")).strip().lower()
            params = item.get("params", {}) if isinstance(item.get("params"), dict) else {}
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            timestamp = str(item.get("timestamp", "")).strip() or datetime.now(timezone.utc).isoformat()

            result_path = str(item.get("result_path", "")).strip()
            stored_result_path = ""
            if result_path:
                source = Path(result_path)
                if source.exists() and source.is_file():
                    target_dir = artifacts_dir / entry_id
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target = target_dir / source.name
                    try:
                        shutil.copy2(source, target)
                        stored_result_path = str(target)
                    except OSError as exc:
                        self._logger.warning("Falha ao copiar artefato de analise (%s): %s", source, exc)
                        stored_result_path = str(source)
                else:
                    stored_result_path = result_path

            target_dir = artifacts_dir / entry_id
            metadata = self._copy_metadata_artifacts(metadata, target_dir)

            normalized.append(
                {
                    "entry_id": entry_id,
                    "analysis_type": analysis_type,
                    "params": params,
                    "result_path": stored_result_path,
                    "timestamp": timestamp,
                    "metadata": metadata,
                }
            )
        return normalized

    def _copy_metadata_artifacts(self, value: Any, target_dir: Path) -> Any:
        """Copy file paths embedded in history metadata into the project folder."""
        if isinstance(value, dict):
            return {str(key): self._copy_metadata_artifacts(item, target_dir) for key, item in value.items()}
        if isinstance(value, list):
            return [self._copy_metadata_artifacts(item, target_dir) for item in value]
        if isinstance(value, tuple):
            return [self._copy_metadata_artifacts(item, target_dir) for item in value]
        if not isinstance(value, str) or not value.strip():
            return value

        source = Path(value)
        if not source.exists() or not source.is_file():
            return value

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name
            if target.exists() and target.resolve() != source.resolve():
                stem = source.stem
                suffix = source.suffix
                counter = 2
                while target.exists():
                    target = target_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            if target.resolve() != source.resolve():
                shutil.copy2(source, target)
            return str(target)
        except OSError as exc:
            self._logger.warning("Falha ao copiar artefato de metadata (%s): %s", source, exc)
            return value

    @classmethod
    def _normalize_lexproj_path(cls, path: Path) -> Path:
        target = Path(path)
        if target.suffix.lower() != cls.EXTENSION:
            target = target.with_suffix(cls.EXTENSION)
        return target

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)

    def _read_json(self, path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectError(
                what="Falha ao ler arquivo de projeto.",
                why=f"Não foi possível interpretar {path}: {exc}",
                how="Verifique se o projeto está íntegro e tente novamente.",
            ) from exc
