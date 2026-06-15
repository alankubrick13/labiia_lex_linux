"""Persistent analysis history for LabiiaLex."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from ..utils.logger import get_logger
from ..utils.paths import PathManager


@dataclass(frozen=True)
class HistoryEntry:
    """One persisted analysis execution entry."""

    entry_id: str
    analysis_type: str
    params: Dict[str, Any]
    result_path: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class HistoryError(Exception):
    """Friendly error for history persistence operations."""


class AnalysisHistory:
    """
    JSON-based history of completed analyses.

    Stores metadata in a JSON file and copies result artifacts to a
    persistent folder so outputs can be reopened across sessions.
    """

    def __init__(
        self,
        history_path: Optional[Union[str, Path]] = None,
        artifacts_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        if PathManager.is_frozen():
            base_dir = PathManager.user_data_dir() / "history"
        else:
            base_dir = PathManager.project_root() / "history"
        self._history_path = Path(history_path) if history_path else base_dir / "analysis_history.json"
        self._artifacts_dir = Path(artifacts_dir) if artifacts_dir else base_dir / "artifacts"
        self._logger = get_logger(__name__)

    @property
    def history_path(self) -> Path:
        """Return the JSON history file path."""
        return self._history_path

    @property
    def artifacts_dir(self) -> Path:
        """Return the root directory used to persist copied artifacts."""
        return self._artifacts_dir

    def save_result(
        self,
        analysis_type: str,
        params: Optional[Dict[str, Any]],
        result_path: Optional[Union[str, Path]],
        timestamp: Optional[Union[str, datetime]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryEntry:
        """
        Persist one analysis execution entry.

        Args:
            analysis_type: Logical analysis type (e.g., chd, matrix_afc).
            params: Parameters used in the execution.
            result_path: Output artifact path, when available.
            timestamp: Optional datetime/ISO string. Uses UTC now if omitted.
            metadata: Optional extra fields to persist.

        Returns:
            Saved history entry.
        """
        entry_id = uuid4().hex
        ts = self._normalize_timestamp(timestamp)
        safe_params = self._to_json_compatible(params or {})
        safe_metadata = self._to_json_compatible(metadata or {})
        stored_result_path = self._persist_artifact(entry_id, result_path)
        safe_metadata = self._persist_metadata_artifacts(entry_id, safe_metadata)

        entry = HistoryEntry(
            entry_id=entry_id,
            analysis_type=str(analysis_type or "").strip().lower(),
            params=safe_params,
            result_path=stored_result_path,
            timestamp=ts,
            metadata=safe_metadata,
        )

        entries = self.load_results()
        entries.insert(0, entry)
        self._write_entries(entries)
        return entry

    def load_results(self) -> List[HistoryEntry]:
        """Load all saved history entries (most recent first)."""
        if not self._history_path.exists():
            return []

        try:
            with self._history_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.error("Falha ao carregar historico de analises: %s", exc)
            raise HistoryError(
                "O que aconteceu: Nao foi possivel ler o historico de analises.\n"
                "Por que aconteceu: O arquivo JSON esta indisponivel ou corrompido.\n"
                "Como resolver: Feche o app, remova o arquivo de historico e tente novamente."
            ) from exc

        if not isinstance(payload, list):
            return []

        entries: List[HistoryEntry] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            entries.append(
                HistoryEntry(
                    entry_id=str(raw.get("entry_id", "")),
                    analysis_type=str(raw.get("analysis_type", "")),
                    params=raw.get("params", {}) if isinstance(raw.get("params"), dict) else {},
                    result_path=str(raw.get("result_path", "")),
                    timestamp=str(raw.get("timestamp", "")),
                    metadata=raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {},
                )
            )
        return entries

    def get_result(self, entry_id: str) -> HistoryEntry:
        """Return one history entry by id."""
        for entry in self.load_results():
            if entry.entry_id == entry_id:
                return entry
        raise KeyError(entry_id)

    def delete_result(self, entry_id: str) -> bool:
        """Delete one history entry and its artifact folder."""
        entries = self.load_results()
        kept: List[HistoryEntry] = []
        removed = False
        for entry in entries:
            if entry.entry_id == entry_id:
                removed = True
                artifact_dir = self._artifacts_dir / entry_id
                if artifact_dir.exists():
                    try:
                        shutil.rmtree(artifact_dir)
                    except OSError as exc:
                        self._logger.warning("Falha ao remover artefatos do historico %s: %s", entry_id, exc)
            else:
                kept.append(entry)

        if removed:
            self._write_entries(kept)
        return removed

    def _write_entries(self, entries: List[HistoryEntry]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "entry_id": entry.entry_id,
                "analysis_type": entry.analysis_type,
                "params": entry.params,
                "result_path": entry.result_path,
                "timestamp": entry.timestamp,
                "metadata": entry.metadata,
            }
            for entry in entries
        ]
        try:
            with self._history_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2, ensure_ascii=False)
        except OSError as exc:
            self._logger.error("Falha ao salvar historico de analises: %s", exc)
            raise HistoryError(
                "O que aconteceu: Nao foi possivel salvar o historico de analises.\n"
                "Por que aconteceu: O arquivo de historico nao pode ser gravado.\n"
                "Como resolver: Verifique permissao de escrita na pasta do projeto."
            ) from exc

    def _persist_artifact(self, entry_id: str, result_path: Optional[Union[str, Path]]) -> str:
        if not result_path:
            return ""

        source = Path(result_path)
        if not source.exists():
            return str(source)

        target_dir = self._artifacts_dir / entry_id
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._logger.warning("Falha ao preparar pasta de artefatos (%s): %s", target_dir, exc)
            return str(source)
        target = target_dir / source.name
        if source.is_dir():
            try:
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(source, target)
                self._rewrite_copied_manifests(source, target)
                return str(target)
            except OSError as exc:
                self._logger.warning("Falha ao copiar pasta de artefatos para historico: %s", exc)
                return str(source)
        if not source.is_file():
            return str(source)
        try:
            shutil.copy2(source, target)
            return str(target)
        except OSError as exc:
            self._logger.warning("Falha ao copiar artefato para historico: %s", exc)
            return str(source)

    def _rewrite_copied_manifests(self, source_dir: Path, target_dir: Path) -> None:
        """Rewrite manifest paths copied from a temp analysis dir into history paths."""
        source_dir = Path(source_dir)
        target_dir = Path(target_dir)
        try:
            source_root = source_dir.resolve()
            target_root = target_dir.resolve()
        except Exception:
            source_root = source_dir
            target_root = target_dir

        for manifest_path in target_dir.rglob("manifest.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            changed = False

            def transform(value: Any) -> Any:
                nonlocal changed
                if isinstance(value, dict):
                    return {str(key): transform(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [transform(item) for item in value]
                if not isinstance(value, str) or not value.strip():
                    return value
                try:
                    candidate = Path(value)
                except Exception:
                    return value
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(source_root)
                except Exception:
                    return value
                rewritten = str(target_root / relative)
                if rewritten != value:
                    changed = True
                return rewritten

            rewritten_payload = transform(payload)
            if not changed:
                continue
            try:
                manifest_path.write_text(
                    json.dumps(rewritten_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                self._logger.warning("Falha ao reescrever manifest do historico (%s): %s", manifest_path, exc)

    def _persist_metadata_artifacts(self, entry_id: str, metadata: Any) -> Any:
        """Copy file paths found in metadata into the entry artifact folder."""
        copied: Dict[str, str] = {}

        def transform(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): transform(item) for key, item in value.items()}
            if isinstance(value, list):
                return [transform(item) for item in value]
            if isinstance(value, tuple):
                return [transform(item) for item in value]
            if isinstance(value, Path):
                return copy_file(value)
            if isinstance(value, str):
                return copy_file(value)
            return value

        def copy_file(path_like: Union[str, Path]) -> str:
            text = str(path_like or "").strip()
            if not text:
                return text
            try:
                source = Path(text)
            except Exception:
                return text
            if not source.exists() or not source.is_file():
                return text

            try:
                source_key = str(source.resolve())
            except Exception:
                source_key = str(source)
            if source_key in copied:
                return copied[source_key]

            target_dir = self._artifacts_dir / entry_id
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._logger.warning("Falha ao preparar pasta de artefatos de metadata (%s): %s", target_dir, exc)
                return text

            target = target_dir / source.name
            if target.exists():
                stem = source.stem
                suffix = source.suffix
                index = 2
                while target.exists():
                    target = target_dir / f"{stem}_{index}{suffix}"
                    index += 1
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                self._logger.warning("Falha ao copiar metadata para historico (%s): %s", source, exc)
                return text

            target_str = str(target)
            copied[source_key] = target_str
            return target_str

        return transform(metadata)

    @staticmethod
    def _normalize_timestamp(timestamp: Optional[Union[str, datetime]]) -> str:
        if isinstance(timestamp, datetime):
            dt = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        if isinstance(timestamp, str) and timestamp.strip():
            return timestamp.strip()
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_json_compatible(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            normalized: Dict[str, Any] = {}
            for key, item in value.items():
                normalized[str(key)] = AnalysisHistory._to_json_compatible(item)
            return normalized
        if isinstance(value, (list, tuple, set)):
            return [AnalysisHistory._to_json_compatible(item) for item in value]
        return str(value)
