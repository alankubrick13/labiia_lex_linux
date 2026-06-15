from __future__ import annotations

import subprocess
from pathlib import Path

from src.analysis.similitude import visualization as viz


def test_probe_r_environment_uses_script_file_instead_of_dash_e(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        captured["kwargs"] = dict(kwargs)
        script_path = Path(args[1])
        captured["script_path"] = script_path
        captured["script_exists_during_run"] = script_path.exists()
        captured["script_body"] = script_path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                "version|R version fake\n"
                "pkg|igraph|TRUE|1.0.0\n"
                "pkg|sna|TRUE|2.0.0\n"
                "pkg|network|TRUE|3.0.0\n"
                "pkg|intergraph|TRUE|4.0.0\n"
                "pkg|jsonlite|TRUE|5.0.0\n"
                "cap|cairo|TRUE\n"
                "cap|png|TRUE\n"
                "cap|jpeg|TRUE\n"
                "session|fake\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(viz.subprocess, "run", fake_run)
    monkeypatch.setattr(viz.tempfile, "gettempdir", lambda: str(tmp_path))

    r_env = {"R_LIBS_USER": r"C:\Users\cardo\AppData\Local\LabiiaLex\R\4.6"}
    env = viz._probe_r_environment(Path(r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe"), env=r_env)

    args = captured["args"]
    assert args[0] == r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe"
    assert captured["kwargs"]["env"] == r_env
    assert args[1] != "-e"
    assert captured["script_exists_during_run"] is True
    assert "requireNamespace" in captured["script_body"]
    assert env["strict_ready"] is True
    assert env["missing_packages"] == []
