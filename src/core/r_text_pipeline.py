"""R-first text preprocessing pipeline for import and lexical cleanup."""

from __future__ import annotations

import json
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .r_executor import RExecutionError, RExecutor, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger
from ..utils.paths import PathManager


@dataclass
class RTextPipelineResult:
    """Structured output from the R text pipeline."""

    prepared_text: str
    preview_text: str
    bigram_candidates: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]
    warnings: List[str]


class RTextPipelineError(RuntimeError):
    """Friendly error for preprocessing failures in R pipeline."""


class RTextPipeline:
    """Runs the unified text preprocessing contract in R."""

    REQUIRED_PACKAGES = ("jsonlite", "quanteda", "stopwords", "stringi")

    def __init__(self, r_executor: Optional[RExecutor] = None) -> None:
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)
        self._packages_checked = False

    def _script_path(self) -> Path:
        path = PathManager.rscripts_dir() / "text_pipeline.R"
        if not path.exists():
            raise RTextPipelineError(
                f"Script de pipeline R nao encontrado: {path}. "
                "Verifique a inclusao de Rscripts no build."
            )
        return path

    def script_hash(self) -> str:
        """Return a stable hash for cache invalidation when the R script changes."""
        path = self._script_path()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _ensure_packages(self) -> None:
        if self._packages_checked:
            return
        status = self.r_executor.check_packages(self.REQUIRED_PACKAGES)
        missing = [pkg for pkg in self.REQUIRED_PACKAGES if not bool(status.get(pkg, False))]
        if missing:
            self._logger.warning("Pacotes R ausentes para pipeline textual: %s", missing)
            if not self.r_executor.install_packages(missing):
                raise RTextPipelineError(
                    "Falha ao instalar pacotes R obrigatorios para preprocessamento: "
                    + ", ".join(missing)
                )
            status_after = self.r_executor.check_packages(missing)
            still_missing = [pkg for pkg in missing if not bool(status_after.get(pkg, False))]
            if still_missing:
                raise RTextPipelineError(
                    "Pacotes R obrigatorios ainda ausentes apos tentativa de instalacao: "
                    + ", ".join(still_missing)
                )
        self._packages_checked = True

    def run(
        self,
        *,
        text: str,
        mode: str,
        lowercase: bool,
        remove_numbers: bool,
        remove_accents: bool,
        clean_web_data: bool,
        detect_bigrams: bool,
        selected_bigrams: Optional[Sequence[Dict[str, Any]]] = None,
        extra_stopwords: Optional[Sequence[str]] = None,
        bigram_top_n: int = 30,
        bigram_min_freq: int = 3,
        ngram_max: int = 3,
        min_is_norm: float = 0.35,
        aggressive_noise_filter: bool = True,
    ) -> RTextPipelineResult:
        """Execute preprocessing in R and return normalized output payload."""
        self._ensure_packages()
        payload: Dict[str, Any] = {
            "text": str(text or ""),
            "mode": str(mode or "traditional"),
            "options": {
                "lowercase": bool(lowercase),
                "remove_numbers": bool(remove_numbers),
                "remove_accents": bool(remove_accents),
                "clean_web_data": bool(clean_web_data),
                "detect_bigrams": bool(detect_bigrams),
                "aggressive_noise_filter": bool(aggressive_noise_filter),
                "bigram_top_n": max(1, int(bigram_top_n or 30)),
                "bigram_min_freq": max(1, int(bigram_min_freq or 3)),
                "ngram_max": min(3, max(2, int(ngram_max or 3))),
                "min_is_norm": max(0.0, float(min_is_norm if min_is_norm is not None else 0.35)),
            },
            "selected_bigrams": list(selected_bigrams or []),
            "extra_stopwords": [str(item) for item in (extra_stopwords or []) if str(item).strip()],
        }

        script_path = self._script_path()
        with tempfile.TemporaryDirectory(prefix="lexianalyst_r_text_pipeline_") as tmpdir:
            workdir = Path(tmpdir)
            input_path = workdir / "input.json"
            output_path = workdir / "output.json"
            input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            self._run_script(script_path=script_path, input_path=input_path, output_path=output_path, workdir=workdir)

            if not output_path.exists():
                raise RTextPipelineError("Pipeline R nao gerou arquivo de saida JSON.")

            data = json.loads(output_path.read_text(encoding="utf-8"))
            ok = bool(data.get("ok", False))
            if not ok:
                reason = str(data.get("error", "")).strip() or "erro nao especificado no pipeline R"
                raise RTextPipelineError(f"Pipeline R falhou: {reason}")

            return RTextPipelineResult(
                prepared_text=str(data.get("prepared_text", "") or ""),
                preview_text=str(data.get("preview_text", "") or ""),
                bigram_candidates=list(data.get("bigram_candidates", []) or []),
                diagnostics=dict(data.get("diagnostics", {}) or {}),
                warnings=[str(item) for item in list(data.get("warnings", []) or [])],
            )

    def _run_script(self, *, script_path: Path, input_path: Path, output_path: Path, workdir: Path) -> None:
        args = [str(input_path), str(output_path)]
        try:
            self.r_executor.execute_with_args(
                script_path=str(script_path),
                args=args,
                working_dir=str(workdir),
                timeout=240,
            )
        except (RNotFoundError, RExecutionError, RTimeoutError) as exc:
            raise RTextPipelineError(str(exc)) from exc
