"""Persistent cache for import extraction and text preprocessing."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from ..utils.paths import PathManager


class ImportProcessingCache:
    """Disk-backed cache keyed by source files and preprocessing options."""

    SCHEMA_VERSION = 2
    DEFAULT_MAX_BYTES = 250 * 1024 * 1024
    DEFAULT_MAX_AGE_DAYS = 60

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = Path(cache_dir or PathManager.user_data_dir() / "import_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def build_key(
        self,
        *,
        source_paths: Sequence[Path],
        mode: str,
        options: Dict[str, Any],
        stopwords: Sequence[str],
        pipeline_hash: str,
    ) -> str:
        payload = {
            "schema": self.SCHEMA_VERSION,
            "sources": [self._file_signature(Path(path)) for path in source_paths],
            "mode": str(mode or ""),
            "options": self._stable(options),
            "stopwords": sorted(str(item).strip().lower() for item in stopwords if str(item).strip()),
            "pipeline_hash": str(pipeline_hash or ""),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._entry_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if int(data.get("schema", 0) or 0) != self.SCHEMA_VERSION:
            return None
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return None
        data["last_accessed_at"] = time.time()
        try:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return payload

    def put(self, key: str, payload: Dict[str, Any]) -> None:
        data = {
            "schema": self.SCHEMA_VERSION,
            "created_at": time.time(),
            "last_accessed_at": time.time(),
            "payload": payload,
        }
        path = self._entry_path(key)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.prune()

    def clear(self) -> None:
        for path in self.cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                continue

    def prune(
        self,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> None:
        entries = list(self.cache_dir.glob("*.json"))
        if not entries:
            return
        now = time.time()
        max_age_seconds = max(1, int(max_age_days)) * 86400
        kept = []
        for path in entries:
            try:
                stat = path.stat()
            except OSError:
                continue
            if now - stat.st_mtime > max_age_seconds:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            kept.append(path)

        def sort_key(path: Path) -> float:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return float(data.get("last_accessed_at", path.stat().st_mtime) or 0)
            except Exception:
                return 0.0

        total = self._total_size(kept)
        for path in sorted(kept, key=sort_key):
            if total <= max_bytes:
                break
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
            except OSError:
                continue

    def _entry_path(self, key: str) -> Path:
        safe_key = "".join(ch for ch in str(key or "") if ch.isalnum())[:64]
        return self.cache_dir / f"{safe_key}.json"

    @staticmethod
    def _total_size(paths: Iterable[Path]) -> int:
        total = 0
        for path in paths:
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    @staticmethod
    def _stable(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): ImportProcessingCache._stable(value[key]) for key in sorted(value)}
        if isinstance(value, (list, tuple)):
            return [ImportProcessingCache._stable(item) for item in value]
        return value

    @staticmethod
    def _file_signature(path: Path) -> Dict[str, Any]:
        resolved = path.resolve()
        if resolved.is_dir():
            files = [
                child
                for child in sorted(resolved.rglob("*"))
                if child.is_file()
                and not child.name.startswith(".")
                and "__pycache__" not in child.parts
            ]
            digest = hashlib.sha256()
            for child in files:
                digest.update(str(child.relative_to(resolved)).encode("utf-8", errors="ignore"))
                digest.update(ImportProcessingCache._hash_file(child).encode("ascii"))
            return {
                "path": str(resolved),
                "kind": "dir",
                "file_count": len(files),
                "sha256": digest.hexdigest(),
            }
        stat = resolved.stat()
        return {
            "path": str(resolved),
            "kind": "file",
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sha256": ImportProcessingCache._hash_file(resolved),
        }

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
