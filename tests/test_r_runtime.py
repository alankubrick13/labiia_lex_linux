from pathlib import Path


def test_resolver_selects_newest_compatible_r():
    from src.core.r_runtime import RCandidate, RRuntimeResolver

    candidates = [
        RCandidate(Path(r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe"), "programfiles:R-4.5.1"),
        RCandidate(Path(r"C:\Program Files\R\R-4.6.0\bin\Rscript.exe"), "programfiles:R-4.6.0"),
    ]
    versions = {
        str(candidates[0].path): "Rscript (R) version 4.5.1 (2025-06-13)",
        str(candidates[1].path): "Rscript (R) version 4.6.0 (2026-04-24)",
    }

    resolver = RRuntimeResolver(
        candidate_provider=lambda: candidates,
        version_probe=lambda path: versions[str(path)],
    )

    runtime = resolver.resolve()

    assert str(runtime.rscript_path).endswith(r"R-4.6.0\bin\Rscript.exe")
    assert runtime.version_token == "4.6.0"


def test_resolver_respects_explicit_compatible_override():
    from src.core.r_runtime import RCandidate, RRuntimeResolver

    candidates = [
        RCandidate(Path(r"C:\Program Files\R\R-4.6.0\bin\Rscript.exe"), "programfiles:R-4.6.0"),
    ]
    explicit = Path(r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe")
    versions = {
        str(explicit): "Rscript (R) version 4.5.1 (2025-06-13)",
        str(candidates[0].path): "Rscript (R) version 4.6.0 (2026-04-24)",
    }

    resolver = RRuntimeResolver(
        candidate_provider=lambda: candidates,
        version_probe=lambda path: versions[str(path)],
    )

    runtime = resolver.resolve(explicit_path=explicit)

    assert runtime.rscript_path == explicit
    assert runtime.source == "explicit"
    assert runtime.version_token == "4.5.1"


def test_resolver_rejects_invalid_and_old_candidates():
    from src.core.r_runtime import RCandidate, RRuntimeResolver

    candidates = [
        RCandidate(Path(r"C:\bad\Rscript.exe"), "bad"),
        RCandidate(Path(r"C:\Program Files\R\R-3.6.3\bin\Rscript.exe"), "old"),
        RCandidate(Path(r"C:\Program Files\R\R-4.0.5\bin\Rscript.exe"), "ok"),
    ]

    def probe(path: Path) -> str:
        text = str(path)
        if r"C:\bad" in text:
            raise OSError("not executable")
        if "R-3.6.3" in text:
            return "Rscript (R) version 3.6.3 (2020-02-29)"
        return "Rscript (R) version 4.0.5 (2021-03-31)"

    resolver = RRuntimeResolver(candidate_provider=lambda: candidates, version_probe=probe)

    runtime = resolver.resolve()

    assert runtime.version_token == "4.0.5"
    assert len(runtime.diagnostics["rejected"]) == 2


def test_versioned_library_path_uses_r_minor_version(monkeypatch, tmp_path):
    from src.core.r_runtime import resolve_versioned_r_libs_user

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("LEXIANALYST_R_LIBS_USER", raising=False)
    monkeypatch.delenv("R_LIBS_USER", raising=False)

    path = resolve_versioned_r_libs_user("4.6.0")

    assert path == str(tmp_path / "LabiiaLex" / "R" / "library" / "4.6")


def test_r_executor_and_r_bridge_share_runtime_and_versioned_library(monkeypatch, tmp_path):
    from src.core.r_runtime import RRuntimeInfo
    from src.core import r_executor as r_executor_module
    from src.visualization.r_integration import r_bridge as r_bridge_module

    runtime = RRuntimeInfo(
        rscript_path=Path(r"C:\Program Files\R\R-4.6.0\bin\Rscript.exe"),
        source="test",
        version_text="Rscript (R) version 4.6.0 (2026-04-24)",
        version_token="4.6.0",
    )

    class FakeResolver:
        def resolve(self, explicit_path=None):
            return runtime

    monkeypatch.setattr(r_executor_module, "RRuntimeResolver", FakeResolver)
    monkeypatch.setattr(r_bridge_module, "RRuntimeResolver", FakeResolver)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("LEXIANALYST_R_LIBS_USER", raising=False)
    monkeypatch.delenv("R_LIBS_USER", raising=False)

    executor = r_executor_module.RExecutor()
    bridge = r_bridge_module.RBridge()

    assert executor.r_path == str(runtime.rscript_path)
    assert bridge.r_executable == str(runtime.rscript_path)
    assert executor._build_r_env()["R_LIBS_USER"].endswith(r"LabiiaLex\R\library\4.6")
    assert bridge._build_r_env()["R_LIBS_USER"].endswith(r"LabiiaLex\R\library\4.6")
