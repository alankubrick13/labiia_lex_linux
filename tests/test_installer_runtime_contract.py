from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_frozen_self_test_requires_lock_not_bundled_r():
    import main

    required = main._required_resource_relatives(frozen=True)

    assert "installer/manifests/r_environment_lock.json" in required
    assert "resources/R/bin/Rscript.exe" not in required


def test_r_core_manifest_matches_required_packages():
    from src.visualization.r_integration.r_bridge import REQUIRED_PACKAGES
    from src.analysis.similitude.visualization import _STRICT_R_PACKAGES

    manifest_path = PROJECT_ROOT / "installer" / "manifests" / "r_packages_core.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_packages = set(manifest_payload["packages"])

    assert manifest_packages == set(REQUIRED_PACKAGES)
    assert {"topicmodels", "slam", "rgexf", "ldatuning", "fmsb"}.issubset(manifest_packages)
    assert set(_STRICT_R_PACKAGES).issubset(manifest_packages)


def test_r_optional_manifest_contains_only_base_runtime_helpers():
    from src.visualization.r_integration.r_bridge import OPTIONAL_PACKAGES

    manifest_path = PROJECT_ROOT / "installer" / "manifests" / "r_packages_optional.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_packages = set(manifest_payload["packages"])

    assert manifest_packages == set(OPTIONAL_PACKAGES)
    assert manifest_packages == {"tcltk"}


def test_r_lock_manifest_matches_external_r_strategy_and_lda_packages():
    from src.analysis.similitude.visualization import _STRICT_R_PACKAGES

    lock_path = PROJECT_ROOT / "installer" / "manifests" / "r_environment_lock.json"
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_packages = set(lock_payload["packages"])

    assert lock_payload["require_bundled_runtime"] is False
    assert lock_payload["external_runtime_required"] is True
    assert lock_payload["versioned_library"] is True
    assert lock_payload["r_version_min"] == "4.0.0"
    assert lock_payload["mirror_policy"]["r_4_6_plus_primary"] == "https://cloud.r-project.org"
    assert {"topicmodels", "slam", "rgexf", "ldatuning", "fmsb"}.issubset(lock_packages)
    assert set(_STRICT_R_PACKAGES).issubset(lock_packages)
    assert lock_payload["archive_sources"]["rgexf"].endswith("rgexf_0.16.2.tar.gz")
    assert lock_payload["archive_sources"]["ldatuning"].endswith("ldatuning_1.0.2.tar.gz")


def test_build_script_does_not_require_bundled_r_runtime():
    build_script = (PROJECT_ROOT / "scripts" / "build_release_installer.ps1").read_text(
        encoding="utf-8"
    )

    assert "BundledRRuntimeDir" not in build_script
    assert "AllowNoBundledR" not in build_script
    assert "resources\\R\\bin\\Rscript.exe" not in build_script
    assert "install_python_packages.py" not in build_script
    assert "validate_install.ps1" in build_script
    assert "lda_topicmodels.R" in build_script
    assert "topicmodels" in build_script
    assert "slam" in build_script
    assert "not_configured" in build_script
    assert "function Get-TrimmedEnvValue" in build_script
    assert "function Test-IsWindowsAppAlias" in build_script
    assert "Microsoft\\WindowsApps" in build_script
    assert "Get-TrimmedEnvValue \"LEXI_SIGN_PFX_PATH\"" in build_script
    assert "ForEach-Object { $_.Trim() }" not in build_script
    assert "labiia_lex-Setup-x64-" in build_script


def test_verify_script_validates_staged_installer_runtime_by_default():
    verify_script = (
        PROJECT_ROOT / "scripts" / "verify_release_installer.ps1"
    ).read_text(encoding="utf-8")

    assert "[switch]$FullRuntimeCheck" in verify_script
    assert '$selfTestProfile = if ($FullRuntimeCheck) { "full" } else { "installer_quick" }' in verify_script
    assert '$stageExe = Join-Path $stageDir "LabiiaLex.exe"' in verify_script
    assert "Start-Process -FilePath $stageExe" in verify_script
    assert "--exe $stageExe" in verify_script
    assert "Resolve-PythonForVerification" in verify_script


def test_pyinstaller_spec_does_not_bundle_legacy_textual_network_resource():
    spec_text = (PROJECT_ROOT / "labiialex_app.spec").read_text(encoding="utf-8")

    assert "analisador_rede_textual" not in spec_text


def test_pyinstaller_spec_bundles_semantic_runtime_dependencies():
    spec_text = (PROJECT_ROOT / "labiialex_app.spec").read_text(encoding="utf-8")

    assert "collect_submodules('sklearn.feature_extraction')" in spec_text
    assert "collect_submodules('sklearn.decomposition')" in spec_text
    assert "collect_submodules('yake')" in spec_text
    assert "collect_data_files('yake')" in spec_text
    assert "'cleantext'" in spec_text
    assert "'tkinterweb'" in spec_text
    assert "'sklearn'," not in spec_text


def test_python_manifest_includes_semantic_runtime_dependencies():
    manifest_path = PROJECT_ROOT / "installer" / "manifests" / "python_packages_core.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    packages = set(payload["packages"])

    assert "scikit-learn>=1.3.0" in packages
    assert "clean-text>=0.7.1" in packages
    assert "tkinterweb>=3.24.0" in packages
    assert "yake>=0.4.8" in packages


def test_self_test_validates_semantic_dependencies():
    main_text = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    assert "semantic_dependencies_ok" in main_text
    assert "sklearn.feature_extraction.text" in main_text
    assert "sklearn.decomposition" in main_text
    assert "yake" in main_text
    assert "KeywordExtractor" in main_text
    assert "r_libs_user" in main_text
    assert "r_packages_built_mismatch" in main_text
    assert "r_text_pipeline_smoke_ok" in main_text


def test_inno_installer_uses_external_r_check_script():
    iss_text = (PROJECT_ROOT / "installer" / "inno" / "LabiiaLex.iss").read_text(
        encoding="utf-8"
    )

    assert "check_r.ps1" in iss_text
    assert "R externo obrigatorio" in iss_text
    assert "MajorMinorVersionToken" in iss_text
    assert "R\\library\\" in iss_text
    assert "FindBundledRScript" not in iss_text
    assert "Reparar pacotes R do labiia_lex" in iss_text
    assert "--repair-r-packages" in iss_text
    assert "DelTree(ExpandConstant('{app}')" not in iss_text


def test_inno_installer_keeps_app_installed_when_post_install_checks_warn():
    iss_text = (PROJECT_ROOT / "installer" / "inno" / "LabiiaLex.iss").read_text(
        encoding="utf-8"
    )

    assert "GetExceptionMessage" in iss_text
    assert "AddPostInstallWarning" in iss_text
    assert "ShowPostInstallWarnings" in iss_text
    assert "Abort;" not in iss_text


def test_r_package_installer_cleans_stale_lock_directories():
    installer_text = (
        PROJECT_ROOT / "installer" / "scripts" / "install_r_packages.R"
    ).read_text(encoding="utf-8")

    assert "cleanup_install_artifacts" in installer_text
    assert "00LOCK" in installer_text
    assert "00LOCK-%s" in installer_text
    assert "Final clean retry" in installer_text


def test_r_package_installer_load_validates_strict_similitude_packages():
    installer_text = (
        PROJECT_ROOT / "installer" / "scripts" / "install_r_packages.R"
    ).read_text(encoding="utf-8")

    assert "critical_load_pkgs <- unique(core_pkgs)" in installer_text
    assert "archive_source_url <- function(pkg)" in installer_text
    assert "ldatuning_1.0.2.tar.gz" in installer_text
    assert "rgexf_0.16.2.tar.gz" in installer_text


def test_r_installer_uses_versioned_library_and_r46_mirror_policy():
    installer_text = (
        PROJECT_ROOT / "installer" / "scripts" / "install_r_packages.R"
    ).read_text(encoding="utf-8")
    check_r_text = (PROJECT_ROOT / "installer" / "scripts" / "check_r.ps1").read_text(
        encoding="utf-8"
    )

    assert "ensure_versioned_lib_path" in installer_text
    assert "r_version_minor" in installer_text
    assert "package_needs_reinstall_for_r" in installer_text
    assert "run_text_pipeline_smoke" in installer_text
    assert "text_pipeline_smoke" in installer_text
    assert "allow_source_fallback" in installer_text
    assert "r_version_at_least(\"4.6.0\")" in installer_text
    assert '[string]$MinVersion = "4.0.0"' in check_r_text
    assert '"stopwords"' in installer_text
    assert '"stringi"' in installer_text
    assert '"path_priority"' in check_r_text
    assert '{ $_["version_sort_key"] }, { $_["path_priority"] } -Descending' in check_r_text
    assert '"C:\\R"' in check_r_text
    assert '"C:\\tools\\R"' in check_r_text


def test_repair_r_packages_cli_is_exposed_without_opening_main_ui():
    main_text = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    assert "--repair-r-packages" in main_text
    assert "r_package_repair_state_" in main_text
    assert "r_repair_state.json" in main_text
    assert "install_r_packages.R" in main_text


def test_help_mentions_current_wordcloud_shapes():
    help_text = (PROJECT_ROOT / "docs" / "help" / "geral.html").read_text(
        encoding="utf-8"
    )

    for shape in (
        "cardioid",
        "diamond",
        "square",
        "triangle-forward",
        "triangle-upright",
        "pentagon",
        "star",
    ):
        assert shape in help_text
