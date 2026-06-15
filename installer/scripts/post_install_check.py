from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, help="Path to LabiiaLex.exe")
    parser.add_argument("--json-out", required=True, help="Path to write combined diagnostics JSON")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--profile", default="full", help="Self-test profile: installer_quick or full")

    return parser.parse_args()


def _safe_json_load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_embedded_self_test(exe_path: Path, timeout: int, profile: str, self_test_json: Path) -> Dict[str, Any]:
    env = dict(os.environ)
    env["LEXIANALYST_SELF_TEST_PROFILE"] = (str(profile or "full").strip() or "full").lower()

    cmd = [str(exe_path), "--self-test", "--json-out", str(self_test_json)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(exe_path.parent),
        env=env,
    )

    return {
        "command": cmd,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "profile": env["LEXIANALYST_SELF_TEST_PROFILE"],
        "self_test_json": str(self_test_json),
    }


def build_combined_payload(execution: Dict[str, Any], self_test_payload: Dict[str, Any]) -> Dict[str, Any]:
    wordcloud_ok = bool(self_test_payload.get("wordcloud_ok", False))
    importer_backends_ok = bool(self_test_payload.get("importer_backends_ok", False))

    combined: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ok": bool(self_test_payload.get("ok", False)),
        "labiialex_self_test": {
            **execution,
            "payload": self_test_payload,
        },
        "wordcloud_self_test": {
            "ok": wordcloud_ok,
            "error": str(self_test_payload.get("wordcloud_error", "") or ""),
        },
        "importer_backends": {
            "ok": importer_backends_ok,
            "checks": self_test_payload.get("importer_backend_checks", {}),
        },
        "errors": list(self_test_payload.get("errors", [])),
    }

    if not combined["ok"] and execution.get("return_code") not in (0, 1, 2):
        combined["errors"].append("self_test_process_failed")

    if execution.get("return_code") == 2 or int(self_test_payload.get("exit_code", 0) or 0) == 2:
        combined["errors"].append("dependency_missing")
    if not importer_backends_ok:
        combined["errors"].append("importer_backends_failed")

    return combined


def main() -> int:
    args = parse_args()
    exe_path = Path(args.exe).expanduser().resolve()
    json_out = Path(args.json_out).expanduser().resolve()
    self_test_json = json_out.with_name("self_test_result.json")

    if not exe_path.exists():
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "errors": [f"exe_not_found: {exe_path}"],
        }
        _write_json(json_out, payload)
        return 2

    try:
        execution = run_embedded_self_test(
            exe_path=exe_path,
            timeout=args.timeout,
            profile=args.profile,
            self_test_json=self_test_json,
        )
    except subprocess.TimeoutExpired:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "errors": ["self_test_timeout"],
            "timeout": args.timeout,
        }
        _write_json(json_out, payload)
        return 1

    if not self_test_json.exists():
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "labiialex_self_test": execution,
            "errors": ["self_test_json_not_found"],
        }
        _write_json(json_out, payload)
        return 1

    self_test_payload = _safe_json_load(self_test_json)
    if not self_test_payload:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "labiialex_self_test": execution,
            "errors": ["self_test_json_parse_error"],
        }
        _write_json(json_out, payload)
        return 1

    combined = build_combined_payload(execution, self_test_payload)
    _write_json(json_out, combined)

    print(json.dumps(combined, ensure_ascii=False))

    if combined.get("ok", False):
        return 0

    process_rc = int(execution.get("return_code", 1) or 1)
    self_test_rc = int(self_test_payload.get("exit_code", process_rc) or process_rc)
    if process_rc == 2 or self_test_rc == 2:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
