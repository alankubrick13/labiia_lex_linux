#!/usr/bin/env python
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_line(lines: List[str], message: str) -> None:
    line = f"[{_now()}] {message}"
    print(line)
    lines.append(line)


def _run(cmd: List[str], timeout: int = 1200) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _load_manifest(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


def _extract_package_name(spec: str) -> str:
    base = spec.split(";", 1)[0].strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)", base)
    return match.group(1) if match else spec


def _pip_show(python_exe: str, package_name: str) -> bool:
    code, _, _ = _run([python_exe, "-m", "pip", "show", package_name], timeout=120)
    return code == 0


def _ensure_pip(python_exe: str, log_lines: List[str]) -> bool:
    code, out, err = _run([python_exe, "-m", "pip", "--version"], timeout=120)
    if code == 0:
        _log_line(log_lines, f"pip detected: {(out or err).strip()}")
        return True

    _log_line(log_lines, "pip not available, running ensurepip --upgrade")
    code, out, err = _run([python_exe, "-m", "ensurepip", "--upgrade"], timeout=600)
    if code != 0:
        _log_line(log_lines, f"ensurepip failed: {(err or out).strip()}")
        return False

    code, out, err = _run([python_exe, "-m", "pip", "--version"], timeout=120)
    if code == 0:
        _log_line(log_lines, f"pip ready: {(out or err).strip()}")
        return True

    _log_line(log_lines, "pip still unavailable after ensurepip")
    return False


def _install_package(
    python_exe: str,
    spec: str,
    index_url: str,
    log_lines: List[str],
    retries: int = 2,
    timeout_sec: int = 1200,
    allow_user_fallback: bool = True,
) -> Dict[str, object]:
    package_name = _extract_package_name(spec)
    if _pip_show(python_exe, package_name):
        _log_line(log_lines, f"[SKIP] {spec} already installed")
        return {"ok": True, "attempts": 0, "mode": "already_installed", "error": ""}

    base_cmd = [
        python_exe,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--prefer-binary",
        "--upgrade",
        "--retries",
        "3",
        "--timeout",
        "120",
        "--index-url",
        index_url,
        spec,
    ]

    last_error = ""
    for attempt in range(1, retries + 1):
        _log_line(log_lines, f"Installing {spec} (attempt {attempt}/{retries}, mode=system)")
        code, out, err = _run(base_cmd, timeout=timeout_sec)
        if code == 0 and _pip_show(python_exe, package_name):
            _log_line(log_lines, f"[OK] {spec} installed (system)")
            return {"ok": True, "attempts": attempt, "mode": "system", "error": ""}

        last_error = (err or out).strip()[-2000:]
        _log_line(log_lines, f"[WARN] {spec} system install failed: {last_error}")

        if not allow_user_fallback:
            continue

        user_cmd = list(base_cmd)
        user_cmd.insert(-1, "--user")
        _log_line(log_lines, f"Installing {spec} (attempt {attempt}/{retries}, mode=user)")
        code, out, err = _run(user_cmd, timeout=timeout_sec)
        if code == 0 and _pip_show(python_exe, package_name):
            _log_line(log_lines, f"[OK] {spec} installed (user)")
            return {"ok": True, "attempts": attempt, "mode": "user", "error": ""}

        last_error = (err or out).strip()[-2000:]
        _log_line(log_lines, f"[WARN] {spec} user install failed: {last_error}")

    _log_line(log_lines, f"[FAIL] {spec}")
    return {"ok": False, "attempts": retries, "mode": "failed", "error": last_error}


def _model_installed(python_exe: str, model_name: str) -> bool:
    code, _, _ = _run(
        [python_exe, "-c", f"import spacy; spacy.load('{model_name}')"],
        timeout=180,
    )
    return code == 0


def _install_spacy_model(
    python_exe: str,
    model_name: str,
    log_lines: List[str],
) -> Dict[str, object]:
    if _model_installed(python_exe, model_name):
        _log_line(log_lines, f"[SKIP] spaCy model {model_name} already installed")
        return {"ok": True, "mode": "already_installed", "error": ""}

    _log_line(log_lines, f"Installing spaCy model: {model_name}")
    code, out, err = _run([python_exe, "-m", "spacy", "download", model_name], timeout=1800)
    if code == 0 and _model_installed(python_exe, model_name):
        _log_line(log_lines, f"[OK] spaCy model {model_name} installed")
        return {"ok": True, "mode": "installed", "error": ""}

    msg = (err or out).strip()[-2000:]
    _log_line(log_lines, f"[FAIL] spaCy model {model_name}: {msg}")
    return {"ok": False, "mode": "failed", "error": msg}


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 4:
        print(
            "Usage: python install_python_packages.py "
            "<core_manifest> <optional_manifest> <log_file> <state_json> [index_url]"
        )
        return 2

    core_manifest = Path(args[0]).expanduser().resolve()
    optional_manifest = Path(args[1]).expanduser().resolve()
    log_file = Path(args[2]).expanduser().resolve()
    state_file = Path(args[3]).expanduser().resolve()
    index_url = args[4] if len(args) >= 5 and args[4].strip() else "https://pypi.org/simple"

    log_lines: List[str] = []
    python_exe = sys.executable
    _log_line(log_lines, f"Python executable: {python_exe}")
    _log_line(log_lines, f"Package index: {index_url}")

    core_data = _load_manifest(core_manifest)
    optional_data = _load_manifest(optional_manifest)

    core_packages = list(core_data.get("packages", []) or [])
    optional_packages = list(optional_data.get("packages", []) or [])
    core_models = list(core_data.get("spacy_models", []) or [])
    optional_models = list(optional_data.get("spacy_models", []) or [])

    _log_line(log_lines, f"Core package count: {len(core_packages)}")
    _log_line(log_lines, f"Optional package count: {len(optional_packages)}")
    _log_line(log_lines, f"Core spaCy models: {len(core_models)}")
    _log_line(log_lines, f"Optional spaCy models: {len(optional_models)}")

    if not _ensure_pip(python_exe, log_lines):
        state = {
            "timestamp": datetime.now().isoformat(),
            "python_executable": python_exe,
            "index_url": index_url,
            "core_success": False,
            "optional_success": False,
            "error": "pip_not_available",
        }
        _write_json(state_file, state)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("\n".join(log_lines), encoding="utf-8")
        return 1

    core_results: Dict[str, Dict[str, object]] = {}
    optional_results: Dict[str, Dict[str, object]] = {}
    core_model_results: Dict[str, Dict[str, object]] = {}
    optional_model_results: Dict[str, Dict[str, object]] = {}

    for spec in core_packages:
        core_results[spec] = _install_package(
            python_exe,
            str(spec),
            index_url,
            log_lines,
            retries=2,
            timeout_sec=1200,
            allow_user_fallback=True,
        )

    for spec in optional_packages:
        optional_results[spec] = _install_package(
            python_exe,
            str(spec),
            index_url,
            log_lines,
            retries=1,
            timeout_sec=300,
            allow_user_fallback=False,
        )

    if core_models or optional_models:
        # Ensure spaCy exists before model installation
        spacy_bootstrap = _install_package(python_exe, "spacy>=3.5.0", index_url, log_lines)
        if not spacy_bootstrap.get("ok", False):
            for model_name in core_models:
                core_model_results[model_name] = {
                    "ok": False,
                    "mode": "blocked",
                    "error": "spacy_install_failed",
                }
            for model_name in optional_models:
                optional_model_results[model_name] = {
                    "ok": False,
                    "mode": "blocked",
                    "error": "spacy_install_failed",
                }
        else:
            for model_name in core_models:
                core_model_results[model_name] = _install_spacy_model(python_exe, str(model_name), log_lines)
            for model_name in optional_models:
                optional_model_results[model_name] = _install_spacy_model(python_exe, str(model_name), log_lines)

    core_failed = sorted([name for name, res in core_results.items() if not bool(res.get("ok"))])
    optional_failed = sorted([name for name, res in optional_results.items() if not bool(res.get("ok"))])
    core_model_failed = sorted([name for name, res in core_model_results.items() if not bool(res.get("ok"))])
    optional_model_failed = sorted([name for name, res in optional_model_results.items() if not bool(res.get("ok"))])

    core_success = len(core_failed) == 0 and len(core_model_failed) == 0
    optional_success = len(optional_failed) == 0 and len(optional_model_failed) == 0

    state = {
        "timestamp": datetime.now().isoformat(),
        "python_executable": python_exe,
        "index_url": index_url,
        "core_packages": core_packages,
        "optional_packages": optional_packages,
        "core_spacy_models": core_models,
        "optional_spacy_models": optional_models,
        "core_results": core_results,
        "optional_results": optional_results,
        "core_model_results": core_model_results,
        "optional_model_results": optional_model_results,
        "core_failed": core_failed,
        "optional_failed": optional_failed,
        "core_model_failed": core_model_failed,
        "optional_model_failed": optional_model_failed,
        "core_success": core_success,
        "optional_success": optional_success,
    }

    _write_json(state_file, state)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("\n".join(log_lines), encoding="utf-8")

    if not core_success:
        _log_line(log_lines, "Core Python provisioning failed")
        log_file.write_text("\n".join(log_lines), encoding="utf-8")
        return 1

    _log_line(log_lines, "Core Python provisioning completed successfully")
    log_file.write_text("\n".join(log_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
