"""
Ponto de entrada da aplicação.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, Tuple

# Resolver diretórios base independentemente do ponto de execução.
if getattr(sys, "frozen", False):
    base_dir = Path(sys.executable).resolve().parent
else:
    base_dir = Path(__file__).resolve().parent
src_path = base_dir / "src"

# Forçar CWD para a pasta do projeto quando iniciado por duplo clique.
try:
    os.chdir(base_dir)
except OSError:
    pass

# Adicionar src ao path se necessário.
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.utils.logger import get_logger
from src.core.version import APP_NAME, DISPLAY_APP_NAME, DISPLAY_APP_TITLE


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Executa autoteste de dependencias e recursos sem abrir UI.",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Caminho opcional para salvar JSON do autoteste.",
    )
    parser.add_argument(
        "--repair-r-packages",
        action="store_true",
        help="Reinstala/verifica os pacotes R do labiia_lex sem abrir a interface principal.",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def _write_json_output(path_str: str, payload: Dict[str, Any]) -> None:
    if not path_str:
        return
    out_path = Path(path_str).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_synthetic_profiles() -> Dict[int, list[tuple[str, float, int, float, str]]]:
    profiles: Dict[int, list[tuple[str, float, int, float, str]]] = {}
    class_prefixes = ("alfa", "beta", "gama", "delta")
    term_suffixes = (
        "analise", "arquivo", "campo", "debate", "escola", "fonte", "gestao",
        "historia", "indice", "jornal", "leitura", "memoria", "narrativa",
        "opiniao", "pesquisa", "questao", "registro", "sentido", "tecnica",
        "unidade", "valor", "contexto", "documento", "expressao", "forma",
        "grafico", "hipotese", "interprete", "linguagem", "metodo", "noçao",
        "processo", "relato", "sistema", "tema", "variavel", "corpus",
        "classe", "perfil", "matriz", "resultado", "coordenada", "frequencia",
        "categoria", "segmento",
    )
    for class_id, class_prefix in enumerate(class_prefixes, start=1):
        rows: list[tuple[str, float, int, float, str]] = []
        for i, suffix in enumerate(term_suffixes, start=1):
            term = f"{class_prefix}{suffix}"
            chi2 = float(18.0 - (i * 0.18) + (class_id * 0.7))
            freq = max(1, 70 - i)
            pct = max(1.0, 100.0 - (i * 1.4))
            rows.append((term, chi2, freq, pct, "+"))
        rows.append((f"{class_prefix}ruido", -3.1, 3, 2.0, "-"))
        profiles[class_id] = rows
    return profiles


def _installer_requires_external_r() -> bool:
    """Windows installer profile uses external R as the only prerequisite."""
    return True


def _required_resource_relatives(*, frozen: bool) -> list[str]:
    required = [
        "src",
        "Rscripts",
        "resources",
        "resources/gephi_runner/gephi-runner.jar",
        "resources/jre17/bin/java.exe",
        "Rscripts/lda_topicmodels.R",
        "dictionaries/lexique_pt.txt",
        "docs/help/geral.html",
    ]
    if frozen:
        required.append("installer/manifests/r_environment_lock.json")
        if not _installer_requires_external_r():
            required.append("resources/R/bin/Rscript.exe")
    return required


def _resolve_bundle_path(relative: str) -> Path:
    direct = base_dir / relative
    if direct.exists():
        return direct
    internal = base_dir / "_internal" / relative
    if internal.exists():
        return internal
    return direct


def _user_data_root() -> Path:
    local_appdata = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
    if local_appdata:
        return Path(local_appdata) / APP_NAME
    return Path.home() / f".{APP_NAME}"


def _repair_summary_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    missing = []
    for key in (
        "core_failed",
        "critical_load_failed",
        "functional_smoke_failed",
        "r_packages_built_mismatch",
    ):
        values = state.get(key, [])
        if isinstance(values, list):
            missing.extend(str(item) for item in values if str(item).strip())
    return {
        "core_success": bool(state.get("core_success", False)),
        "critical_load_success": bool(state.get("critical_load_success", False)),
        "functional_smoke_success": bool(state.get("functional_smoke_success", False)),
        "missing_or_failed": sorted(set(missing)),
    }


def _run_r_package_repair(logger) -> Tuple[int, Dict[str, Any]]:
    payload: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "app_root": str(base_dir),
        "r_executable": "",
        "r_version": "",
        "r_libs_user": "",
        "log_path": "",
        "state_path": "",
        "errors": [],
        "warnings": [],
    }

    data_root = _user_data_root()
    logs_root = data_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_root / f"r_package_repair_{stamp}.log"
    state_path = logs_root / f"r_package_repair_state_{stamp}.json"
    latest_state_path = data_root / "r_repair_state.json"
    payload["log_path"] = str(log_path)
    payload["state_path"] = str(state_path)

    try:
        from src.core.r_runtime import RRuntimeResolver, resolve_versioned_r_libs_user

        runtime = RRuntimeResolver().resolve()
        libs_user = resolve_versioned_r_libs_user(runtime.version_token, app_name=APP_NAME)
        payload["r_executable"] = str(runtime.rscript_path)
        payload["r_version"] = runtime.version_token
        payload["r_libs_user"] = libs_user
    except Exception as exc:  # noqa: BLE001
        payload["errors"].append(f"R nao encontrado ou incompativel: {exc}")
        _write_json_output(str(latest_state_path), payload)
        return 2, payload

    script_path = _resolve_bundle_path("installer/scripts/install_r_packages.R")
    core_manifest = _resolve_bundle_path("installer/manifests/r_packages_core.json")
    optional_manifest = _resolve_bundle_path("installer/manifests/r_packages_optional.json")
    lock_manifest = _resolve_bundle_path("installer/manifests/r_environment_lock.json")
    for required_path in (script_path, core_manifest, optional_manifest, lock_manifest):
        if not required_path.exists():
            payload["errors"].append(f"Arquivo obrigatorio ausente: {required_path}")
    if payload["errors"]:
        _write_json_output(str(latest_state_path), payload)
        return 1, payload

    env = os.environ.copy()
    env["R_LIBS_USER"] = str(payload["r_libs_user"])
    env["LEXIANALYST_R_LIBS_USER"] = str(payload["r_libs_user"])
    env["RGL_USE_NULL"] = "TRUE"

    cmd = [
        str(payload["r_executable"]),
        str(script_path),
        str(core_manifest),
        str(optional_manifest),
        str(log_path),
        str(state_path),
        str(payload["r_libs_user"]),
        "https://cloud.r-project.org",
        str(lock_manifest),
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(base_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        payload["r_installer_exit_code"] = int(proc.returncode)
        if proc.stdout:
            payload["r_installer_stdout_tail"] = proc.stdout[-4000:]
        if proc.stderr:
            payload["r_installer_stderr_tail"] = proc.stderr[-4000:]
    except subprocess.TimeoutExpired:
        payload["errors"].append("Tempo limite excedido ao instalar pacotes R.")
        _write_json_output(str(latest_state_path), payload)
        return 2, payload
    except Exception as exc:  # noqa: BLE001
        payload["errors"].append(f"Falha ao executar reparo de pacotes R: {exc}")
        _write_json_output(str(latest_state_path), payload)
        return 2, payload

    state_payload: Dict[str, Any] = {}
    if state_path.exists():
        try:
            state_payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
            payload["r_install_state"] = state_payload
            payload.update(_repair_summary_from_state(state_payload))
        except Exception as exc:  # noqa: BLE001
            payload["warnings"].append(f"Nao foi possivel ler estado JSON do R: {exc}")
    else:
        payload["warnings"].append(f"Estado JSON nao foi gerado: {state_path}")

    payload["ok"] = (
        int(payload.get("r_installer_exit_code", 1)) == 0
        and bool(payload.get("core_success", False))
        and bool(payload.get("critical_load_success", False))
        and bool(payload.get("functional_smoke_success", False))
    )
    if not payload["ok"] and not payload["errors"]:
        failed = payload.get("missing_or_failed", [])
        if failed:
            payload["errors"].append("Pacotes/validacoes com falha: " + ", ".join(failed))
        else:
            payload["errors"].append("O reparo de pacotes R nao concluiu com sucesso.")

    _write_json_output(str(latest_state_path), payload)
    logger.info("Reparo de pacotes R finalizado com ok=%s", payload["ok"])
    return (0 if payload["ok"] else 2), payload


def _run_r_package_repair_ui(logger) -> Tuple[int, Dict[str, Any]]:
    try:
        import threading
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        return _run_r_package_repair(logger)

    result_holder: Dict[str, Any] = {"done": False, "code": 2, "payload": {}}
    root = tk.Tk()
    root.title(f"Reparar pacotes R - {DISPLAY_APP_NAME}")
    root.geometry("560x240")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame,
        text=f"Reparando pacotes R do {DISPLAY_APP_NAME}",
        font=("Segoe UI", 12, "bold"),
    ).pack(anchor="w")
    status_var = tk.StringVar(
        value="Aguarde. O processo pode demorar alguns minutos e precisa de internet."
    )
    ttk.Label(frame, textvariable=status_var, wraplength=500).pack(anchor="w", pady=(12, 10))
    progress = ttk.Progressbar(frame, mode="indeterminate")
    progress.pack(fill="x", pady=(0, 14))
    progress.start(12)
    close_button = ttk.Button(frame, text="Fechar", command=root.destroy)
    close_button.configure(state="disabled")
    close_button.pack(anchor="e")

    def worker() -> None:
        code, payload = _run_r_package_repair(logger)
        result_holder["code"] = code
        result_holder["payload"] = payload
        result_holder["done"] = True

    def poll() -> None:
        if not result_holder["done"]:
            root.after(300, poll)
            return
        progress.stop()
        payload = dict(result_holder.get("payload") or {})
        close_button.configure(state="normal")
        if payload.get("ok"):
            status_var.set(
                "Pacotes R verificados e reparados com sucesso.\n"
                f"Log: {payload.get('log_path', '')}"
            )
            messagebox.showinfo(
                f"{DISPLAY_APP_NAME} - Reparo concluido",
                "Pacotes R verificados e reparados com sucesso.",
                parent=root,
            )
        else:
            errors = payload.get("errors") or ["Falha nao especificada."]
            status_var.set(
                "O reparo nao foi concluido.\n"
                f"Problema: {'; '.join(str(e) for e in errors[:3])}\n"
                f"Log: {payload.get('log_path', '')}"
            )
            messagebox.showwarning(
                f"{DISPLAY_APP_NAME} - Reparo incompleto",
                (
                    "Nao foi possivel concluir o reparo dos pacotes R.\n\n"
                    + "\n".join(str(e) for e in errors[:5])
                    + "\n\nLog tecnico:\n"
                    + str(payload.get("log_path", ""))
                ),
                parent=root,
            )

    threading.Thread(target=worker, daemon=True).start()
    root.after(300, poll)
    root.mainloop()
    return int(result_holder.get("code", 2)), dict(result_holder.get("payload") or {})


def _run_self_test(logger) -> Tuple[int, Dict[str, Any]]:
    self_test_profile = str(
        os.environ.get("LEXIANALYST_SELF_TEST_PROFILE", "full")
    ).strip().lower()
    quick_installer_mode = self_test_profile in {"installer_quick", "quick", "installer"}

    payload: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_root": str(base_dir),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "self_test_profile": self_test_profile,
        "import_ok": False,
        "resource_ok": False,
        "java_ok": False,
        "gephi_ok": False,
        "gephi_smoke_ok": False,
        "network_text_smoke_ok": False,
        "r_ok": False,
        "r_missing_core": [],
        "r_libs_user": "",
        "r_packages_built_mismatch": [],
        "r_text_pipeline_smoke_ok": False,
        "importer_backends_ok": False,
        "importer_backend_checks": {},
        "semantic_dependencies_ok": False,
        "semantic_dependency_checks": {},
        "afc_ok": False,
        "afc_error": "",
        "wordcloud_ok": False,
        "wordcloud_error": "",
        "errors": [],
        "warnings": [],
    }

    dependency_missing = False
    functional_failure = False

    try:
        imports_to_check = (
            "customtkinter",
            "numpy",
            "pandas",
            "networkx",
            "matplotlib",
            "src.ui.main_window",
            "src.analysis.chd_reinert",
            "src.analysis.similarity",
            "src.analysis.network_text_analysis",
            "src.analysis.wordcloud",
            "src.analysis.lda_analysis",
            "src.analysis.topic_modeling",
        )
        failed_imports: list[str] = []
        for module_name in imports_to_check:
            try:
                module_ref = __import__(module_name)
                if module_name == "customtkinter":
                    for attr in ("CTk", "CTkToplevel", "CTkFrame"):
                        if not hasattr(module_ref, attr):
                            raise AttributeError(f"atributo ausente: {attr}")
            except Exception as exc:  # noqa: BLE001
                failed_imports.append(f"{module_name}: {exc}")
        if failed_imports:
            dependency_missing = True
            payload["errors"].append("Falha de importacao de modulos essenciais.")
            payload["warnings"].extend(failed_imports)
        else:
            payload["import_ok"] = True
    except Exception as exc:  # noqa: BLE001
        functional_failure = True
        payload["errors"].append(f"Erro no bloco de validacao de imports: {exc}")

    try:
        import importlib

        from src.importers import get_importer_for_file

        importer_checks: Dict[str, Any] = {
            "modules": {},
            "routing": {},
        }
        importer_failures: list[str] = []

        module_requirements = {
            "docx": ("docx", "lxml.etree"),
            "pdf": ("pdfplumber",),
            "xlsx": ("openpyxl",),
        }

        for backend_name, modules in module_requirements.items():
            module_state: Dict[str, str] = {}
            for module_name in modules:
                try:
                    importlib.import_module(module_name)
                    module_state[module_name] = "ok"
                except Exception as exc:  # noqa: BLE001
                    module_state[module_name] = f"error: {exc}"
                    importer_failures.append(
                        f"{backend_name}:{module_name}:{exc}"
                    )
            importer_checks["modules"][backend_name] = module_state

        if not importer_failures:
            try:
                docx_module = importlib.import_module("docx")
                _ = docx_module.Document()
                importer_checks["docx_smoke"] = "ok"
            except Exception as exc:  # noqa: BLE001
                importer_checks["docx_smoke"] = f"error: {exc}"
                importer_failures.append(f"docx_smoke:{exc}")

            try:
                openpyxl_module = importlib.import_module("openpyxl")
                wb = openpyxl_module.Workbook()
                wb.active["A1"] = "smoke"
                wb.close()
                importer_checks["xlsx_smoke"] = "ok"
            except Exception as exc:  # noqa: BLE001
                importer_checks["xlsx_smoke"] = f"error: {exc}"
                importer_failures.append(f"xlsx_smoke:{exc}")

            try:
                pdfplumber_module = importlib.import_module("pdfplumber")
                importer_checks["pdf_smoke"] = (
                    "ok" if hasattr(pdfplumber_module, "open") else "error: missing_open"
                )
                if importer_checks["pdf_smoke"] != "ok":
                    importer_failures.append("pdf_smoke:missing_open")
            except Exception as exc:  # noqa: BLE001
                importer_checks["pdf_smoke"] = f"error: {exc}"
                importer_failures.append(f"pdf_smoke:{exc}")

        expected_routing = {
            "arquivo.txt": "TXTImporter",
            "arquivo.pdf": "PDFImporter",
            "arquivo.docx": "DOCXImporter",
            "arquivo.odt": "ODTImporter",
            "arquivo.xlsx": "XLSXImporter",
            "arquivo.csv": "XLSXImporter",
            "arquivo.zip": "ZipImporter",
        }
        for sample_path, expected_name in expected_routing.items():
            try:
                importer_name = get_importer_for_file(sample_path).__class__.__name__
                importer_checks["routing"][sample_path] = importer_name
                if importer_name != expected_name:
                    importer_failures.append(
                        f"routing:{sample_path}:expected={expected_name}:got={importer_name}"
                    )
            except Exception as exc:  # noqa: BLE001
                importer_checks["routing"][sample_path] = f"error: {exc}"
                importer_failures.append(f"routing:{sample_path}:{exc}")

        payload["importer_backend_checks"] = importer_checks
        payload["importer_backends_ok"] = len(importer_failures) == 0
        if importer_failures:
            dependency_missing = True
            payload["errors"].append("Backends de importacao incompletos.")
            payload["warnings"].extend(importer_failures)
    except Exception as exc:  # noqa: BLE001
        dependency_missing = True
        payload["errors"].append(f"Falha ao validar backends de importacao: {exc}")

    try:
        import importlib

        semantic_modules = (
            "sklearn.feature_extraction.text",
            "sklearn.decomposition",
            "yake",
        )
        semantic_checks: Dict[str, str] = {}
        semantic_failures: list[str] = []
        for module_name in semantic_modules:
            try:
                module_ref = importlib.import_module(module_name)
                if module_name == "yake":
                    extractor = module_ref.KeywordExtractor(
                        lan="pt",
                        n=1,
                        dedupLim=0.9,
                        top=3,
                    )
                    sample_keywords = extractor.extract_keywords(
                        "analise textual automatizada com metodos semanticos"
                    )
                    if not isinstance(sample_keywords, list):
                        raise RuntimeError("KeywordExtractor retornou tipo inesperado")
                semantic_checks[module_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                semantic_checks[module_name] = f"error: {exc}"
                semantic_failures.append(f"{module_name}:{exc}")

        payload["semantic_dependency_checks"] = semantic_checks
        payload["semantic_dependencies_ok"] = len(semantic_failures) == 0
        if semantic_failures:
            dependency_missing = True
            payload["errors"].append("Dependencias semanticas Python incompletas.")
            payload["warnings"].extend(semantic_failures)
    except Exception as exc:  # noqa: BLE001
        dependency_missing = True
        payload["errors"].append(f"Falha ao validar dependencias semanticas: {exc}")

    try:
        def _exists_in_bundle(relative: str) -> bool:
            p1 = base_dir / relative
            p2 = base_dir / "_internal" / relative
            return p1.exists() or p2.exists()

        required_relatives = _required_resource_relatives(
            frozen=bool(getattr(sys, "frozen", False))
        )
        missing_paths = [rel for rel in required_relatives if not _exists_in_bundle(rel)]
        if missing_paths:
            dependency_missing = True
            payload["errors"].append("Recursos essenciais ausentes no pacote.")
            payload["warnings"].extend(missing_paths)
        else:
            payload["resource_ok"] = True
    except Exception as exc:  # noqa: BLE001
        functional_failure = True
        payload["errors"].append(f"Erro ao validar arquivos de recurso: {exc}")

    try:
        from src.analysis.layout_backends import gephi_java_backend as gjb
        import networkx as nx

        java_exec, java_source = gjb._resolve_java_executable()
        runner_jar = gjb._resolve_runner_jar()
        java_version = gjb._java_version(java_exec)

        payload["java_executable"] = java_exec
        payload["java_source"] = java_source
        payload["java_version"] = java_version
        payload["gephi_runner_jar"] = str(runner_jar)

        payload["java_ok"] = bool(java_exec)
        payload["gephi_ok"] = runner_jar.exists()
        if not payload["java_ok"] or not payload["gephi_ok"]:
            dependency_missing = True
            payload["errors"].append("Backend Gephi Java incompleto.")
        elif quick_installer_mode:
            payload["gephi_smoke_ok"] = True
            payload["warnings"].append("gephi_smoke_skipped_installer_quick")
        else:
            smoke_graph = nx.Graph()
            smoke_graph.add_edge("n1", "n2", weight=1.0)
            smoke_graph.add_edge("n2", "n3", weight=1.0)
            smoke_graph.add_edge("n3", "n1", weight=1.0)
            with tempfile.TemporaryDirectory(prefix="lexianalyst_gephi_smoke_") as tmpdir:
                smoke_result = gjb.run_layout(
                    graph=smoke_graph,
                    params={
                        "fa2_iterations": 40,
                        "fa2_scaling": 2.0,
                        "fa2_gravity": 1.0,
                        "fa2_barnes_hut_optimize": False,
                        "noverlap_enabled": True,
                        "noverlap_iterations": 10,
                        "layout_timeout_sec": 60,
                        "seed": 42,
                    },
                    output_dir=Path(tmpdir),
                )
                smoke_nodes = set(smoke_result.positions.keys())
                expected_nodes = {"n1", "n2", "n3"}
                payload["gephi_smoke_ok"] = smoke_nodes == expected_nodes
                payload["gephi_smoke_elapsed_sec"] = float(
                    smoke_result.diagnostics.get("elapsed_sec", 0.0) or 0.0
                )
                payload["gephi_smoke_diag_path"] = str(smoke_result.diagnostics_path)
                if not payload["gephi_smoke_ok"]:
                    dependency_missing = True
                    payload["errors"].append(
                        "Backend Gephi Java respondeu, mas retornou posicoes invalidas no smoke test."
                    )
    except Exception as exc:  # noqa: BLE001
        dependency_missing = True
        payload["errors"].append(f"Falha ao validar Gephi/Java: {exc}")

    if quick_installer_mode:
        payload["network_text_smoke_ok"] = True
        payload["warnings"].append("network_text_smoke_skipped_installer_quick")
    else:
        try:
            from src.analysis.network_text_analysis import NetworkTextAnalysis
            from src.core.corpus import Corpus

            with tempfile.TemporaryDirectory(prefix="lexianalyst_network_selftest_") as tmpdir:
                out_dir = Path(tmpdir) / "network_out"
                out_dir.mkdir(parents=True, exist_ok=True)

                corpus = Corpus({"ucemethod": 0, "ucesize": 80})
                uci = corpus.add_uci("**** *doc_smoke")
                texts = [
                    "dados metodo analise rede textual algoritmo grafo",
                    "grafo rede comunidade centralidade dados",
                    "analise textual coocorrencia rede dados metodo",
                    "algoritmo cluster comunidade rede grafo",
                ]
                for idx, text in enumerate(texts, start=1):
                    uce = corpus.add_uce(uci.ident, idx, text)
                    for token in text.split():
                        corpus.add_word(token, gram="nom", lem=token, uce_id=uce.ident)

                result = NetworkTextAnalysis(corpus, out_dir).run(
                    {
                        "min_freq": 1,
                        "window_size": 2,
                        "min_cooc": 1,
                        "max_nodes": 40,
                        "auto_tune": False,
                        "layout_backend": "spring_smoke",
                        "strict_layout_backend": False,
                        "spring_iterations": 80,
                        "fa2_iterations": 40,
                        "noverlap_enabled": False,
                        "render_quality_auto": False,
                        "label_adjust": False,
                        "label_hide_overlap": False,
                        "label_anchor_lines": False,
                        "typegraph": "png",
                        "width": 900,
                        "height": 700,
                        "dpi": 120,
                        "export_gexf": False,
                        "export_csv": False,
                        "export_net": False,
                        "active_only": False,
                    }
                )

                image_path = Path(result.graph_image_path) if result.graph_image_path else None
                image_ok = bool(image_path and image_path.exists() and image_path.stat().st_size > 0)
                payload["network_text_nodes"] = int(result.n_nodes)
                payload["network_text_edges"] = int(result.n_edges)
                payload["network_text_backend"] = str(result.layout_backend_used)
                payload["network_text_output_file"] = str(image_path) if image_path else ""
                payload["network_text_smoke_ok"] = bool(
                    result.n_nodes >= 4 and result.n_edges >= 3 and image_ok
                )
                if not payload["network_text_smoke_ok"]:
                    dependency_missing = True
                    payload["errors"].append(
                        "Autoteste de rede textual retornou estrutura invalida."
                    )
        except Exception as exc:  # noqa: BLE001
            dependency_missing = True
            payload["errors"].append(f"Falha no autoteste de rede textual: {exc}")

    try:
        from src.visualization.r_integration.r_bridge import RBridge, REQUIRED_PACKAGES

        bridge = RBridge()
        payload["r_executable"] = bridge.r_executable
        payload["r_version"] = bridge.get_r_version() if bridge.r_available else "not_found"
        payload["r_libs_user"] = bridge._build_r_env().get("R_LIBS_USER", "")

        if not bridge.r_available:
            if quick_installer_mode:
                payload["r_ok"] = True
                payload["r_text_pipeline_smoke_ok"] = True
                payload["warnings"].append("r_not_found_skipped_installer_quick")
            else:
                dependency_missing = True
                payload["errors"].append("Rscript nao encontrado.")
        else:
            status = bridge.check_packages(REQUIRED_PACKAGES)
            missing = sorted([pkg for pkg, ok in status.items() if not ok])
            payload["r_missing_core"] = missing
            payload["r_packages_built_mismatch"] = bridge.get_package_build_mismatches(
                REQUIRED_PACKAGES
            )
            if quick_installer_mode:
                payload["r_ok"] = True
                payload["r_text_pipeline_smoke_ok"] = True
                if missing:
                    payload["warnings"].append(
                        "missing_r_core_skipped_installer_quick=" + ",".join(missing)
                    )
                if payload["r_packages_built_mismatch"]:
                    payload["warnings"].append("r_built_mismatch_skipped_installer_quick")
            else:
                payload["r_ok"] = len(missing) == 0 and not payload["r_packages_built_mismatch"]
                if missing:
                    dependency_missing = True
                    payload["errors"].append("Pacotes R essenciais ausentes.")
                    payload["warnings"].append("missing_r_core=" + ",".join(missing))
                if payload["r_packages_built_mismatch"]:
                    dependency_missing = True
                    payload["errors"].append("Pacotes R compilados para outra versao menor.")
    except Exception as exc:  # noqa: BLE001
        if quick_installer_mode:
            payload["r_ok"] = True
            payload["r_text_pipeline_smoke_ok"] = True
            payload["warnings"].append(f"r_validation_skipped_installer_quick={exc}")
        else:
            dependency_missing = True
            payload["errors"].append(f"Falha ao validar R: {exc}")

    if not quick_installer_mode and payload.get("r_ok", False):
        try:
            from src.core.r_text_pipeline import RTextPipeline

            pipeline_result = RTextPipeline().run(
                text="**** *doc_1\nEste e um corpus minimo para validar o pipeline textual.",
                mode="iramuteq",
                lowercase=False,
                remove_numbers=False,
                remove_accents=False,
                clean_web_data=False,
                detect_bigrams=False,
                selected_bigrams=[],
                extra_stopwords=[],
                bigram_top_n=5,
                bigram_min_freq=2,
                aggressive_noise_filter=True,
            )
            payload["r_text_pipeline_smoke_ok"] = bool(pipeline_result.prepared_text.strip())
        except Exception as exc:  # noqa: BLE001
            dependency_missing = True
            payload["r_text_pipeline_smoke_ok"] = False
            payload["errors"].append(f"Falha no autoteste do pipeline textual R: {exc}")

    if quick_installer_mode:
        payload["afc_ok"] = True
        payload["wordcloud_ok"] = True
        payload["warnings"].append("afc_self_test_skipped_installer_quick")
        payload["warnings"].append("wordcloud_self_test_skipped_installer_quick")
    elif not payload.get("r_ok", False):
        payload["afc_ok"] = False
        payload["wordcloud_ok"] = False
        payload["afc_error"] = "AFC self-test skipped: R dependencies unavailable"
        payload["wordcloud_error"] = "WordCloud self-test skipped: R dependencies unavailable"
    else:
        try:
            from src.analysis.chd_reinert import CHDAnalysis
            from src.core.corpus import Corpus

            with tempfile.TemporaryDirectory(prefix="lexianalyst_afc_selftest_") as tmpdir:
                out_dir = Path(tmpdir) / "afc_selftest_out"
                out_dir.mkdir(parents=True, exist_ok=True)
                corpus = Corpus({"ucemethod": 0, "ucesize": 80})
                analysis = CHDAnalysis(corpus, out_dir)
                profiles = _build_synthetic_profiles()

                graph_path, row_coords, col_coords = analysis._run_post_chd_afc(
                    profiles,
                    {
                        "typegraph": "png",
                        "width": 1400,
                        "height": 1100,
                        "dpi": 180,
                        "max_words": 220,
                        "nb_per_class": 80,
                        "adaptive_label_scaling": True,
                        "min_visible_words": 80,
                        "require_profile_afc_output": True,
                    },
                )

                graph_ok = bool(graph_path and Path(graph_path).exists() and Path(graph_path).stat().st_size > 0)
                row_ok = bool(getattr(row_coords, "shape", None) and row_coords.shape[1] >= 2)
                col_ok = bool(getattr(col_coords, "shape", None) and col_coords.shape[1] >= 2)

                payload["afc_graph_path"] = str(graph_path) if graph_path else ""
                payload["afc_row_shape"] = list(row_coords.shape) if getattr(row_coords, "shape", None) else None
                payload["afc_col_shape"] = list(col_coords.shape) if getattr(col_coords, "shape", None) else None
                payload["afc_ok"] = bool(graph_ok and row_ok and col_ok)
                if not payload["afc_ok"]:
                    dependency_missing = True
                    payload["afc_error"] = (
                        "AFC self-test failed: graph/coords invalid "
                        f"(graph_ok={graph_ok}, row_ok={row_ok}, col_ok={col_ok})"
                    )
                    payload["errors"].append(payload["afc_error"])
        except Exception as exc:  # noqa: BLE001
            dependency_missing = True
            payload["afc_error"] = str(exc)
            payload["errors"].append(f"Falha no autoteste AFC: {exc}")

        try:
            from src.analysis.wordcloud import WordCloudAnalysis
            from src.core.corpus import Corpus
            import numpy as np
            from PIL import Image

            requested_shapes = (
                "cardioid",
                "diamond",
                "square",
                "triangle-forward",
                "triangle-upright",
                "pentagon",
                "star",
            )
            with tempfile.TemporaryDirectory(prefix="lexianalyst_wordcloud_selftest_") as tmpdir:
                shape_checks: list[Dict[str, Any]] = []
                image_hashes: Dict[str, str] = {}
                corner_ratios: Dict[str, float] = {}
                shape_mask_modes: Dict[str, str] = {}

                def _corner_nonwhite_ratio(image_file: Path) -> float:
                    image = Image.open(image_file).convert("RGB")
                    arr = np.asarray(image)
                    nonwhite = np.any(arr < 245, axis=2)
                    height, width = nonwhite.shape
                    corner_size = max(8, int(min(height, width) * 0.12))
                    corners = np.concatenate(
                        [
                            nonwhite[:corner_size, :corner_size].ravel(),
                            nonwhite[:corner_size, -corner_size:].ravel(),
                            nonwhite[-corner_size:, :corner_size].ravel(),
                            nonwhite[-corner_size:, -corner_size:].ravel(),
                        ]
                    )
                    return float(corners.mean())

                for requested_shape in requested_shapes:
                    out_dir = Path(tmpdir) / f"wordcloud_out_{requested_shape.replace('-', '_')}"
                    out_dir.mkdir(parents=True, exist_ok=True)

                    corpus = Corpus({"ucemethod": 0, "ucesize": 80})
                    corpus.add_uci("**** *doc_1")
                    text = (
                        "pesquisa pesquisa pesquisa analise analise textual textual textual "
                        "dados dados metodo metodo resultado resultado ciencia ciencia ciencia "
                        "academico academico ferramenta ferramenta projeto projeto"
                    )
                    uce = corpus.add_uce(0, 0, text)
                    for token in text.split():
                        corpus.add_word(token, gram="nom", lem=token, uce_id=uce.ident)

                    result = WordCloudAnalysis(corpus, out_dir).run(
                        {
                            "shape": requested_shape,
                            "sizing_mode": "area",
                            "typegraph": "png",
                            "min_freq": 1,
                            "max_words": 80,
                            "active_only": False,
                            "use_lemmas": True,
                            "colors": "Dark2",
                            "eccentricity": 0.65,
                            "graph_out": f"wordcloud_{requested_shape}.png",
                        }
                    )

                    meta_file = out_dir / "wordcloud_render_meta.json"
                    if not meta_file.exists():
                        raise RuntimeError(f"metadata ausente: {meta_file}")
                    metadata = json.loads(meta_file.read_text(encoding="utf-8"))
                    shape_effective = str(metadata.get("shape_effective", "")).strip().lower()
                    shape_mask_mode = str(metadata.get("shape_mask_mode", "")).strip().lower()
                    image_path = Path(result.image_path)
                    image_ok = image_path.exists() and image_path.stat().st_size > 0
                    if not image_ok:
                        raise RuntimeError(f"imagem de wordcloud invalida: {image_path}")
                    if shape_effective != requested_shape:
                        raise RuntimeError(
                            f"shape_effective divergente: esperado={requested_shape}, obtido={shape_effective}"
                        )

                    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
                    image_hashes[requested_shape] = digest
                    corner_ratio = _corner_nonwhite_ratio(image_path)
                    corner_ratios[requested_shape] = corner_ratio
                    shape_mask_modes[requested_shape] = shape_mask_mode
                    shape_checks.append(
                        {
                            "shape_requested": requested_shape,
                            "shape_effective": shape_effective,
                            "image_path": str(image_path),
                            "image_sha256": digest,
                            "corner_nonwhite_ratio": corner_ratio,
                            "shape_mask_mode": shape_mask_mode,
                        }
                    )

                base_hash = image_hashes.get("square", "")
                for shape_name in requested_shapes:
                    if shape_name == "square":
                        continue
                    if image_hashes.get(shape_name, "") == base_hash:
                        raise RuntimeError(
                            f"wordcloud smoke: {shape_name} gerou imagem identica ao square"
                        )
                payload["wordcloud_shape_checks"] = shape_checks
                payload["wordcloud_shape_hashes"] = image_hashes
                payload["wordcloud_shape_corner_ratios"] = corner_ratios
                payload["wordcloud_shape_mask_modes"] = shape_mask_modes
                payload["wordcloud_ok"] = True
        except Exception as exc:  # noqa: BLE001
            dependency_missing = True
            payload["wordcloud_error"] = str(exc)
            payload["errors"].append(f"Falha no autoteste WordCloud: {exc}")

    payload["ok"] = (
        payload["import_ok"]
        and payload["resource_ok"]
        and payload["java_ok"]
        and payload["gephi_ok"]
        and payload["gephi_smoke_ok"]
        and payload["network_text_smoke_ok"]
        and payload["r_ok"]
        and payload["r_text_pipeline_smoke_ok"]
        and payload["importer_backends_ok"]
        and payload["semantic_dependencies_ok"]
        and payload["afc_ok"]
        and payload["wordcloud_ok"]
    )

    if functional_failure:
        code = 1
    elif dependency_missing:
        code = 2
    else:
        code = 0

    payload["exit_code"] = code
    logger.info("Self-test finalizado com codigo=%s", code)
    return code, payload


def _show_startup_error(title: str, message: str) -> None:
    """Exibe erro de inicialização também em janela para execução via duplo clique."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"\n[{title}]\n{message}")


def _hide_console_window_windows() -> None:
    """
    Oculta a janela de console no Windows sem encerrar o processo principal.

    Para depuração, definir `LEXIANALYST_SHOW_CONSOLE=1`.
    """
    if os.name != "nt":
        return
    if str(os.environ.get("LEXIANALYST_SHOW_CONSOLE", "")).strip().lower() in {"1", "true", "yes", "sim"}:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        # Falha de ocultação não deve bloquear abertura da UI.
        pass


def _relaunch_detached_windows() -> bool:
    """
    Relança o app destacado do terminal no Windows e encerra o processo pai.

    Retorna True quando o processo atual deve encerrar imediatamente.
    """
    if os.name != "nt":
        return False
    # Modo de depuração: manter console visível.
    if str(os.environ.get("LEXIANALYST_SHOW_CONSOLE", "")).strip().lower() in {"1", "true", "yes", "sim"}:
        return False
    # Proibição explícita de detach (fallback de segurança).
    if str(os.environ.get("LEXIANALYST_NO_DETACH", "")).strip().lower() in {"1", "true", "yes", "sim"}:
        return False
    # Evitar loop infinito: já rodando como processo destacado.
    if str(os.environ.get("LEXIANALYST_DETACHED", "")).strip().lower() in {"1", "true", "yes", "sim"}:
        return False
    # Nunca destacar durante testes automatizados.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        has_console = bool(kernel32.GetConsoleWindow())
    except Exception:
        has_console = False

    if not has_console:
        return False

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, *sys.argv[1:]]
    else:
        py_exec = Path(sys.executable)
        pyw_exec = py_exec.with_name("pythonw.exe")
        launcher = str(pyw_exec if pyw_exec.exists() else py_exec)
        cmd = [launcher, str(Path(__file__).resolve()), *sys.argv[1:]]

    env = os.environ.copy()
    env["LEXIANALYST_DETACHED"] = "1"

    creationflags = 0
    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, flag_name, 0) or 0)

    startupinfo = None
    startup_cls = getattr(subprocess, "STARTUPINFO", None)
    if startup_cls is not None:
        startupinfo = startup_cls()
        startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0) or 0)
        startupinfo.wShowWindow = 0

    popen_kwargs = {
        "cwd": str(base_dir),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if creationflags:
        popen_kwargs["creationflags"] = creationflags
    if startupinfo is not None:
        popen_kwargs["startupinfo"] = startupinfo

    try:
        subprocess.Popen(cmd, **popen_kwargs)
        return True
    except Exception:
        # Se falhar o relançamento, segue fluxo normal.
        return False


def main() -> None:
    """
    Inicializa e executa a aplicação gráfica.
    """
    args = _parse_args(sys.argv[1:])
    logger = get_logger(__name__)

    if args.self_test:
        logger.info("Executando autoteste de inicializacao...")
        code, payload = _run_self_test(logger)
        try:
            _write_json_output(args.json_out, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao gravar JSON de autoteste: %s", exc)
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(code)

    if args.repair_r_packages:
        logger.info("Executando reparo de pacotes R...")
        if str(os.environ.get("LEXIANALYST_REPAIR_R_NO_UI", "")).strip().lower() in {"1", "true", "yes", "sim"}:
            code, payload = _run_r_package_repair(logger)
        else:
            code, payload = _run_r_package_repair_ui(logger)
        try:
            _write_json_output(args.json_out, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao gravar JSON de reparo R: %s", exc)
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(code)

    if _relaunch_detached_windows():
        return
    _hide_console_window_windows()
    logger.info("Iniciando %s...", APP_NAME)
    
    try:
        from src.ui.main_window import run_app
        run_app()
    except ImportError as e:
        missing_module = str(getattr(e, "name", "") or "").strip()
        is_customtkinter_missing = (
            missing_module == "customtkinter"
            or missing_module.startswith("customtkinter.")
        )

        if is_customtkinter_missing:
            logger.error(
                "O que aconteceu: Não foi possível carregar a interface gráfica.\n"
                "Por que aconteceu: Dependência CustomTkinter não encontrada.\n"
                "Como resolver: Execute 'pip install customtkinter' e tente novamente."
            )
            user_message = (
                "Nao foi possivel carregar a interface grafica.\n\n"
                "Instale as dependencias e tente novamente:\n"
                "pip install -r requirements.txt\n\n"
                f"Python em uso: {sys.executable}"
            )
            window_title = f"{DISPLAY_APP_NAME} - Dependências ausentes"
        else:
            missing_text = missing_module or str(e)
            logger.error(
                "O que aconteceu: Não foi possível carregar a interface gráfica.\n"
                "Por que aconteceu: Um módulo interno da aplicação não pôde ser importado.\n"
                f"Como resolver: Verifique se os arquivos do {DISPLAY_APP_NAME} estão completos e atualizados."
            )
            user_message = (
                "Nao foi possivel carregar a interface grafica.\n\n"
                "Modulo interno ausente ou invalido:\n"
                f"{missing_text}\n\n"
                f"Verifique a integridade dos arquivos do {DISPLAY_APP_NAME} e tente novamente."
            )
            window_title = f"{DISPLAY_APP_NAME} - Erro de inicialização"

        logger.error("Erro técnico: %s", e)
        _show_startup_error(window_title, user_message)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Erro inesperado ao iniciar")
        logger.error(
            f"O que aconteceu: O {DISPLAY_APP_NAME} encontrou um erro inesperado.\n"
            "Por que aconteceu: Uma exceção ocorreu durante a inicialização.\n"
            "Como resolver: Verifique o log técnico e tente novamente."
        )
        error_log = base_dir / "startup_error.log"
        try:
            error_log.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        _show_startup_error(
            f"{DISPLAY_APP_TITLE} - Erro ao iniciar",
            (
                f"{exc}\n\n"
                "Um log tecnico foi salvo em:\n"
                f"{error_log}"
            ),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
