"""Gephi Toolkit Java backend adapter for ForceAtlas2 textual layouts."""

from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import networkx as nx

from ...utils.paths import PathManager
from ...utils.subprocess_utils import no_console_kwargs

log = logging.getLogger(__name__)


@dataclass
class GephiJavaBackendResult:
    positions: Dict[Any, Tuple[float, float]]
    diagnostics: Dict[str, Any]
    diagnostics_path: Path


class GephiJavaBackendError(RuntimeError):
    """Raised when Gephi Java backend cannot produce a valid layout."""


def _bundled_java_home() -> Path:
    """Return the bundled JRE17 home directory."""
    root = PathManager.project_root()
    return root / "resources" / "jre17"


def _bundled_java_path() -> Path:
    root = PathManager.project_root()
    java_bin = "java.exe" if os.name == "nt" else "java"
    return root / "resources" / "jre17" / "bin" / java_bin


def _get_java_environment(java_executable: str) -> Dict[str, str]:
    """
    Create process env for Java execution with deterministic DLL/path resolution.

    - Prefers bundled JRE when that executable is selected.
    - Keeps system Java execution clean when fallback java is used.
    """
    env = os.environ.copy()
    current_path = env.get("PATH", "") or env.get("Path", "") or ""
    prepend: list[str] = []

    bundled_home = _bundled_java_home()
    bundled_java = _bundled_java_path()
    try:
        is_bundled_java = Path(java_executable).resolve() == bundled_java.resolve()
    except Exception:
        is_bundled_java = False

    if is_bundled_java and bundled_home.exists():
        env["JAVA_HOME"] = str(bundled_home)
        bundled_bin = bundled_home / "bin"
        if bundled_bin.exists():
            prepend.append(str(bundled_bin))
    else:
        env.pop("JAVA_HOME", None)

    # When frozen, keep internal dirs in PATH to avoid missing runtime DLLs.
    if PathManager.is_frozen():
        root = PathManager.project_root()
        if root.exists():
            prepend.append(str(root))
        app_dir = root.parent
        if app_dir.exists():
            prepend.append(str(app_dir))

    path_parts: list[str] = []
    seen: set[str] = set()
    for item in prepend:
        key = str(item).strip().lower()
        if key and key not in seen:
            seen.add(key)
            path_parts.append(str(item))
    if current_path:
        path_parts.append(current_path)
    merged_path = os.pathsep.join(path_parts)

    if os.name == "nt":
        env["PATH"] = merged_path
        env["Path"] = merged_path
    else:
        env["PATH"] = merged_path
    return env


def _resolve_java_executable() -> Tuple[str, str]:
    """
    Resolve Java executable path, preferring bundled JRE with validation.
    
    Returns:
        Tuple of (java_executable_path, source_type)
        source_type is one of: "bundled_jre17", "system_path"
    
    Raises:
        GephiJavaBackendError: When no valid Java installation is found
    """
    bundled = _bundled_java_path()
    bundled_jre_home = _bundled_java_home()
    
    # First try bundled JRE with validation
    if bundled.exists():
        # Verify critical JVM DLL exists (required for Java to function)
        jvm_dll_candidates = [
            bundled_jre_home / "bin" / "server" / "jvm.dll",
            bundled_jre_home / "bin" / "client" / "jvm.dll",
        ]
        jvm_exists = any(dll.exists() for dll in jvm_dll_candidates)
        
        if jvm_exists:
            return str(bundled), "bundled_jre17"
        log.warning(f"Bundled JRE found but jvm.dll missing at {bundled_jre_home}")
    
    # Fallback to system Java
    system_java = shutil.which("java")
    if system_java:
        log.info("Using system Java installation")
        return system_java, "system_path"
    
    # Build detailed error message
    error_parts = [
        "Java não encontrado para executar o layout ForceAtlas2.",
        f"JRE bundled: {bundled} - {'existe' if bundled.exists() else 'AUSENTE'}",
    ]
    if bundled.exists():
        jvm_dll = bundled_jre_home / "bin" / "server" / "jvm.dll"
        if not jvm_dll.exists():
            error_parts.append(f"  Erro: jvm.dll não encontrada em {jvm_dll}")
    error_parts.append(f"Java no PATH: {'não encontrado' if not system_java else system_java}")
    
    raise GephiJavaBackendError("\n".join(error_parts))


def _resolve_runner_jar() -> Path:
    return PathManager.project_root() / "resources" / "gephi_runner" / "gephi-runner.jar"


def _parse_positions(path: Path) -> Dict[Any, Tuple[float, float]]:
    if not path.exists():
        raise GephiJavaBackendError(f"positions.csv não encontrado: {path}")

    positions: Dict[Any, Tuple[float, float]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        for row in reader:
            node_id = row.get("id")
            if not node_id:
                continue
            try:
                x = float(row.get("x", 0.0) or 0.0)
                y = float(row.get("y", 0.0) or 0.0)
            except (TypeError, ValueError) as exc:
                raise GephiJavaBackendError(
                    f"positions.csv inválido para nó '{node_id}'"
                ) from exc
            positions[node_id] = (x, y)
    return positions


def _write_edges_csv(graph: nx.Graph, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["source", "target", "weight"])
        for source, target, data in graph.edges(data=True):
            weight = float(data.get("weight", 1.0) or 1.0)
            writer.writerow([source, target, weight])


def _java_version(java_executable: str) -> str:
    try:
        # Use the Java environment to ensure DLLs are found
        java_env = _get_java_environment(java_executable)
        proc = subprocess.run(
            [java_executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=java_env,
            **no_console_kwargs(),
        )
    except Exception:
        return "unknown"
    stderr = (proc.stderr or "").strip().splitlines()
    stdout = (proc.stdout or "").strip().splitlines()
    version_line = stderr[0] if stderr else (stdout[0] if stdout else "unknown")
    return version_line.strip()


def run_layout(
    graph: nx.Graph,
    params: Dict[str, Any],
    output_dir: Path,
) -> GephiJavaBackendResult:
    """Compute layout via Gephi Toolkit Java runner."""

    java_executable, java_source = _resolve_java_executable()
    runner_jar = _resolve_runner_jar()

    if not runner_jar.exists():
        raise GephiJavaBackendError(f"Runner Gephi nao encontrado: {runner_jar}")

    # Get Java environment with JAVA_HOME and PATH set correctly
    java_env = _get_java_environment(java_executable)

    with tempfile.TemporaryDirectory(prefix="gephi_layout_") as tmpdir:
        work = Path(tmpdir)
        edges_csv = work / "edges.csv"
        params_json = work / "params.json"
        positions_csv = work / "positions.csv"
        diag_json = work / "layout_diag.json"

        _write_edges_csv(graph, edges_csv)

        runner_params = {
            "edges_csv": str(edges_csv),
            "positions_csv": str(positions_csv),
            "diag_json": str(diag_json),
            # ForceAtlas2 — fallbacks alinhados com DEFAULT_PARAMS (compacto)
            "fa2_iterations": int(params.get("fa2_iterations", 6000) or 6000),
            "fa2_scaling": float(params.get("fa2_scaling", 8.0) or 8.0),
            "fa2_gravity": float(params.get("fa2_gravity", 1.5) or 1.5),
            "fa2_strong_gravity_mode": bool(params.get("fa2_strong_gravity_mode", True)),
            "fa2_edge_weight_influence": float(params.get("fa2_edge_weight_influence", 0.5) or 0.5),
            "fa2_jitter_tolerance": float(params.get("fa2_jitter_tolerance", 1.0) or 1.0),
            "fa2_barnes_hut_theta": float(params.get("fa2_barnes_hut_theta", 1.2) or 1.2),
            "fa2_barnes_hut_optimize": bool(params.get("fa2_barnes_hut_optimize", graph.number_of_nodes() > 1000)),
            # Noverlap — fallbacks alinhados com DEFAULT_PARAMS
            "noverlap_enabled": bool(params.get("noverlap_enabled", True)),
            "noverlap_speed": float(params.get("noverlap_speed", 3.0) or 3.0),
            "noverlap_ratio": float(params.get("noverlap_ratio", 1.1) or 1.1),
            "noverlap_margin": float(params.get("noverlap_margin", 3.0) or 3.0),
            "noverlap_iterations": int(params.get("noverlap_iterations", 100) or 100),
            "seed": int(params.get("seed", 42) or 42),
        }

        params_json.write_text(
            json.dumps(runner_params, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        cmd = [
            java_executable,
            "-Djava.awt.headless=true",
            "-Dfile.encoding=UTF-8",
            "-Xms64m",
            "-Xmx1024m",
            "-jar",
            str(runner_jar),
            "--params",
            str(params_json),
        ]

        timeout_sec = int(params.get("layout_timeout_sec", 180) or 180)
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                env=java_env,
                **no_console_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise GephiJavaBackendError(
                f"Runner Gephi excedeu timeout de {timeout_sec}s."
            ) from exc
        elapsed = time.perf_counter() - started

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            details = stderr or stdout or "sem detalhes"
            raise GephiJavaBackendError(
                f"Runner Gephi falhou (code={proc.returncode}): {details[:1200]}"
            )

        positions = _parse_positions(positions_csv)
        if len(positions) != graph.number_of_nodes():
            missing = graph.number_of_nodes() - len(positions)
            raise GephiJavaBackendError(
                f"Runner Gephi retornou posições incompletas: faltam {missing} nós."
            )

        diagnostics: Dict[str, Any] = {}
        if diag_json.exists():
            try:
                diagnostics = json.loads(diag_json.read_text(encoding="utf-8"))
            except Exception as exc:
                log.warning("Falha ao ler layout_diag.json: %s", exc)

        diagnostics.setdefault("backend", "gephi_java")
        diagnostics.setdefault("elapsed_sec", round(elapsed, 4))
        diagnostics.setdefault("java_executable", java_executable)
        diagnostics.setdefault("java_source", java_source)
        diagnostics.setdefault("java_version", _java_version(java_executable))
        diagnostics.setdefault("runner_jar", str(runner_jar))

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        diag_out = output_dir / "layout_diag.json"
        diag_out.write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return GephiJavaBackendResult(
            positions=positions,
            diagnostics=diagnostics,
            diagnostics_path=diag_out,
        )


def compute_layout(
    graph: nx.Graph,
    params: Dict[str, Any],
    output_dir: Path,
) -> Dict[Any, Tuple[float, float]]:
    """Compatibility contract: return only node positions."""
    return run_layout(graph=graph, params=params, output_dir=output_dir).positions
