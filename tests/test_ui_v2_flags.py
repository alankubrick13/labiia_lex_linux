import pytest


def test_config_manager_contains_ui_v2_defaults():
    from src.core.config_manager import ConfigManager

    cfg = ConfigManager._build_default_config()
    ui = cfg.get("ui")
    assert isinstance(ui, dict)
    assert ui.get("v2_enabled") is True
    assert ui.get("v2_scope") == ["shell", "results", "feedback"]
    assert ui.get("density") == "comfortable"
    assert ui.get("nav_collapsed") is False
    assert ui.get("shell_version") == "modern_academic_v1"
    assert cfg.get("guided_tour_version_seen") in ("", None)
    assert cfg.get("show_guided_tour_on_startup") is True


def test_main_window_resolve_ui_v2_settings_fallbacks():
    from src.ui.main_window import MainWindow

    enabled, scope, density = MainWindow._resolve_ui_v2_settings(
        {"v2_enabled": True, "v2_scope": ["shell", "results", "invalid"], "density": "compact"}
    )
    assert enabled is True
    assert "shell" in scope
    assert "results" in scope
    assert "invalid" not in scope
    assert density == "compact"

    enabled2, scope2, density2 = MainWindow._resolve_ui_v2_settings("invalid")
    assert enabled2 is True
    assert scope2 == {"shell", "results", "feedback"}
    assert density2 == "comfortable"


def test_main_window_build_command_registry_exposes_core_actions():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    registry = MainWindow._build_command_registry(window)

    assert isinstance(registry, dict)
    for key in (
        "import",
        "open_project",
        "save_project",
        "settings",
        "statistics",
        "wordcloud",
        "similarity",
        "chd",
    ):
        assert key in registry
        assert callable(registry[key]["command"])
        assert registry[key]["section"] in {
            "dashboard",
            "corpus",
            "analises",
            "resultados",
            "ajustes",
        }


def test_main_window_build_analysis_catalog_registry_exposes_groups_and_contract():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    window._voyant_suite_enabled = True
    registry = MainWindow._build_analysis_catalog_registry(window)

    assert isinstance(registry, dict)
    expected_groups = {"Essenciais", "Semânticas", "Exploratórios", "Extras"}
    assert {payload["group"] for payload in registry.values()} == expected_groups
    for key in (
        "statistics",
        "similarity",
        "chd",
        "wordcloud",
        "concordance",
        "yake",
        "lda",
        "associative_heatmap",
        "thematic_chd",
        "voyant_suite",
        "emotions",
        "network_text",
        "cca",
        "bigrams_extra",
        "trigrams_extra",
        "word_tree_extra",
        "wordfish_extra",
        "xray_extra",
        "sentiment_extra",
        "keyness",
    ):
        assert key in registry
        assert callable(registry[key]["command"])
        assert isinstance(registry[key]["label"], str) and registry[key]["label"]
        assert isinstance(registry[key]["description"], str) and registry[key]["description"]
        assert isinstance(registry[key]["requires_corpus"], bool)

    assert registry["network_text"]["label"] == "Rede Textual"
    assert registry["network_text"]["ribbon_label"] == "Rede Textual"
    assert registry["network_text"]["group"] == "Exploratórios"


def test_main_window_build_help_ribbon_registry_exposes_html_actions():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    calls = []
    window._open_help_page = lambda _page: None
    window._show_about = lambda: calls.append("about")
    window._start_guided_tour = lambda auto=False: None
    registry = MainWindow._build_help_ribbon_registry(window)

    assert isinstance(registry, dict)
    for key in (
        "geral",
        "analises",
        "matriz",
        "limpeza",
        "faq",
        "glossario",
        "sobre",
        "tutorial",
    ):
        assert key in registry
        assert callable(registry[key]["command"])
        assert isinstance(registry[key]["label"], str) and registry[key]["label"]

    registry["sobre"]["command"]()
    assert calls == ["about"]


def test_analysis_ribbon_accepts_prepare_corpus_action_contract():
    import inspect

    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView

    signature = inspect.signature(AnalysisRibbonView.__init__)

    assert "on_prepare_corpus" in signature.parameters
    assert "on_save_project" in signature.parameters


def test_analysis_ribbon_save_project_button_is_between_export_and_normalize():
    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView
    import customtkinter

    calls = []

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        view = AnalysisRibbonView(
            root,
            registry={},
            on_execute=lambda _key: None,
            on_import=lambda: None,
            on_save_project=lambda: calls.append("save"),
            on_normalize=lambda: None,
        )
        view.pack(fill="both", expand=True)

        assert view.get_primary_button("export") is not None
        assert view.get_primary_button("save") is not None
        assert view.get_primary_button("normalize") is not None
        assert view.get_primary_button("save").cget("text") == "Salvar"
        assert view.get_primary_button("save").cget("state") == "disabled"

        fixed_actions = view.get_primary_button("save").master
        labels = [
            child.cget("text")
            for child in fixed_actions.winfo_children()
            if hasattr(child, "cget")
        ]
        assert labels[:4] == ["Importar", "Exportar", "Salvar", "Normalizar"]

        view._dispatch_save_project()
        assert calls == []

        view.refresh_enabled_state(corpus_loaded=True)
        assert view.get_primary_button("save").cget("state") == "normal"
        view._dispatch_save_project()
        assert calls == ["save"]
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_analysis_ribbon_normalize_reveals_second_level_options():
    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView
    import customtkinter

    calls = []

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        view = AnalysisRibbonView(
            root,
            registry={},
            on_execute=lambda _key: None,
            on_import=lambda: None,
            on_normalize=lambda: calls.append("normalize"),
            on_prepare_corpus=lambda: calls.append("prepare"),
        )
        view.pack(fill="both", expand=True)
        view.refresh_enabled_state(corpus_loaded=True)

        view._dispatch_normalize()

        assert calls == []
        assert view._normalize_visible is True
        assert view._actions_row.winfo_manager() == "pack"
        assert view.get_normalize_option_button("prepare") is not None
        view.get_normalize_option_button("prepare").invoke()
        assert calls == ["prepare"]
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_main_window_about_text_is_current_and_contains_contact_links():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    text = MainWindow._build_about_text(window)

    assert "coordenador do Labiia Lab" in text
    assert "ChatGPT Codex (v. 5.2, 5.3, 5.4, 5.5)" in text
    assert "Claude Code Opus (v. 4.5, 4.6, 4.7)" in text
    assert "Antigravity (Gemini 3.1 Pro)" in text
    assert "https://andersonheri.github.io/acR/" in text
    assert "cardososampaio@gmail.com" in text
    assert "200 horas" in text
    assert "quatro meses" in text
    assert "80 horas" not in text
    assert "dois meses" not in text


def test_main_window_should_auto_start_guided_tour_is_versioned():
    from src.ui.main_window import MainWindow

    class _Config:
        def __init__(self, seen=None, enabled=True):
            self._seen = seen
            self._enabled = enabled

        def get(self, key, default=None):
            if key == "guided_tour_version_seen":
                return self._seen
            if key == "show_guided_tour_on_startup":
                return self._enabled
            return default

    window = MainWindow.__new__(MainWindow)
    window.config = _Config(seen=None, enabled=True)
    assert MainWindow._should_auto_start_guided_tour(window) is True

    window.config = _Config(seen="modern_shell_v1", enabled=True)
    assert MainWindow._should_auto_start_guided_tour(window) is False

    window.config = _Config(seen=None, enabled=False)
    assert MainWindow._should_auto_start_guided_tour(window) is False


def test_main_window_manual_start_reopens_hidden_active_guided_tour():
    from src.ui.main_window import MainWindow

    class _FakeTour:
        def __init__(self):
            self.is_active = True
            self.bring_calls = []

        def bring_to_front(self, reset_to_first=False):
            self.bring_calls.append(reset_to_first)

    window = MainWindow.__new__(MainWindow)
    window._guided_tour_start_job = None
    window._guided_tour = _FakeTour()

    MainWindow._start_guided_tour(window, auto=False)

    assert window._guided_tour.bring_calls == [True]


def test_main_window_navigation_sections_default_to_dashboard():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    sections = MainWindow._build_shell_sections(window)

    assert [section["key"] for section in sections] == [
        "dashboard",
        "corpus",
        "analises",
        "resultados",
        "ajustes",
    ]
    assert MainWindow._default_shell_section(window) == "dashboard"


class _FakeManagedWidget:
    def __init__(self):
        self._manager = ""

    def pack(self, **_kwargs):
        self._manager = "pack"

    def pack_forget(self):
        self._manager = ""

    def winfo_manager(self):
        return self._manager


class _FakeButton:
    def __init__(self):
        self.calls = []
        self._manager = ""

    def configure(self, **kwargs):
        self.calls.append(kwargs)

    def cget(self, key):
        if key == "state":
            for payload in reversed(self.calls):
                if "state" in payload:
                    return payload["state"]
        return None


def test_main_window_switch_shell_section_keeps_results_center_for_analises_and_resultados():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    window._shell_sections = MainWindow._build_shell_sections(window)
    window._active_shell_section = "dashboard"
    window.dashboard_view = _FakeManagedWidget()
    window.analysis_catalog_host = _FakeManagedWidget()
    window.results_host = _FakeManagedWidget()
    window._refresh_shell_nav = lambda: None
    window._refresh_workspace_header = lambda: None
    window._refresh_dashboard_summary = lambda: None
    window._refresh_quick_actions = lambda: None
    window._refresh_context_panel = lambda: None

    MainWindow._show_dashboard_workspace(window)
    MainWindow._switch_shell_section(window, "analises")
    assert window._active_shell_section == "analises"
    assert window.results_host.winfo_manager() == "pack"
    assert window.analysis_catalog_host.winfo_manager() == ""
    assert window.dashboard_view.winfo_manager() == ""

    MainWindow._switch_shell_section(window, "resultados")
    assert window._active_shell_section == "resultados"
    assert window.results_host.winfo_manager() == "pack"
    assert window.analysis_catalog_host.winfo_manager() == ""
    assert window.dashboard_view.winfo_manager() == ""


def test_main_window_show_results_workspace_preserves_existing_result_host_state():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    window.dashboard_view = _FakeManagedWidget()
    window.analysis_catalog_host = _FakeManagedWidget()
    window.results_host = _FakeManagedWidget()

    MainWindow._show_results_workspace(window)
    assert window.results_host.winfo_manager() == "pack"

    MainWindow._show_results_workspace(window)
    assert window.results_host.winfo_manager() == "pack"

    MainWindow._show_results_workspace(window)
    assert window.results_host.winfo_manager() == "pack"


def test_results_viewer_uses_treeview_when_v2_enabled(tmp_path):
    from src.ui.widgets.results_viewer import ResultsViewer
    import customtkinter

    csv_file = tmp_path / "table.csv"
    csv_file.write_text("col1;col2\n1;2\n3;4\n", encoding="utf-8")

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        viewer = ResultsViewer(
            root,
            ui_v2_enabled=True,
            ui_v2_scope=["results"],
            ui_density="comfortable",
        )
        viewer.pack(fill="both", expand=True)
        viewer.show_table(csv_file)
        assert viewer._has_table_content is True
        assert viewer._current_table_treeview is not None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_analysis_ribbon_view_disables_actions_without_corpus_and_reveals_group_row_on_selection():
    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView
    import customtkinter

    registry = {
        "statistics": {
            "label": "Estatísticas",
            "group": "Essenciais",
            "description": "Resumo quantitativo.",
            "command": lambda: None,
            "requires_corpus": True,
        },
        "voyant_suite": {
            "label": "Voyant Suite",
            "group": "Exploratórios",
            "description": "Painéis exploratórios.",
            "command": lambda: None,
            "requires_corpus": False,
        },
    }

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        view = AnalysisRibbonView(
            root,
            registry=registry,
            on_execute=lambda _key: None,
            on_import=lambda: None,
            on_normalize=lambda: None,
        )
        view.pack(fill="both", expand=True)
        view.refresh_enabled_state(corpus_loaded=False)
        assert view._action_buttons["statistics"].cget("state") == "disabled"
        assert view._action_buttons["voyant_suite"].cget("state") == "normal"
        assert view._actions_row.winfo_manager() == ""
        view.set_group_filter("Essenciais")
        assert view._actions_row.winfo_manager() == "pack"
        view.refresh_enabled_state(corpus_loaded=True)
        assert view._action_buttons["statistics"].cget("state") == "normal"
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_analysis_ribbon_view_does_not_render_shell_section_buttons():
    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView
    import customtkinter

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        view = AnalysisRibbonView(
            root,
            registry={},
            on_execute=lambda _key: None,
            on_import=lambda: None,
            on_normalize=lambda: None,
        )
        view.pack(fill="both", expand=True)
        assert not hasattr(view, "_section_buttons")
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_analysis_ribbon_view_about_button_reveals_help_row():
    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView
    import customtkinter

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        view = AnalysisRibbonView(
            root,
            registry={},
            help_entries={
                "geral": {"label": "Geral do Software", "command": lambda: None},
                "limpeza": {"label": "Limpeza de Corpus", "command": lambda: None},
            },
            on_execute=lambda _key: None,
            on_import=lambda: None,
            on_normalize=lambda: None,
        )
        view.pack(fill="both", expand=True)
        assert view._actions_row.winfo_manager() == ""
        view._dispatch_about()
        assert view._help_visible is True
        assert view._actions_row.winfo_manager() == "pack"
        assert set(view._help_buttons.keys()) == {"geral", "limpeza"}
        view._dispatch_about()
        assert view._help_visible is False
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_analysis_ribbon_view_exposes_stable_tour_targets():
    from src.ui.widgets.analysis_ribbon import AnalysisRibbonView
    import customtkinter

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        view = AnalysisRibbonView(
            root,
            registry={
                "statistics": {
                    "label": "Estatísticas",
                    "group": "Essenciais",
                    "description": "Resumo quantitativo.",
                    "command": lambda: None,
                    "requires_corpus": False,
                }
            },
            help_entries={
                "geral": {"label": "Geral do Software", "command": lambda: None},
            },
            on_execute=lambda _key: None,
            on_import=lambda: None,
            on_normalize=lambda: None,
        )
        view.pack(fill="both", expand=True)
        view.set_group_filter("Essenciais")
        view.show_help_panel()

        assert view.get_primary_button("import") is not None
        assert view.get_primary_button("normalize") is not None
        assert view.get_primary_button("about") is not None
        assert view.get_primary_button("about").cget("text") == "Ajuda"
        assert view.get_group_button("Essenciais") is not None
        assert view.get_active_group_button("statistics") is not None
        assert view.get_help_button("geral") is not None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_main_window_refresh_workspace_ribbon_hides_legacy_top_actions_and_keeps_ribbon_visible():
    from src.ui.main_window import MainWindow

    window = MainWindow.__new__(MainWindow)
    window._active_shell_section = "dashboard"
    window.workspace_quick_actions_bar = _FakeManagedWidget()
    window.analysis_ribbon_host = _FakeManagedWidget()
    window.workspace_body = object()
    window.analysis_ribbon_view = type(
        "_Ribbon",
        (),
        {
            "refresh_enabled_state": lambda self, corpus_loaded: None,
            "collapse_actions_row": lambda self: setattr(self, "_collapsed", True),
        },
    )()
    window._shell_header_buttons = [_FakeButton(), _FakeButton()]
    window.corpus = None

    MainWindow._refresh_quick_actions(window)
    assert window.workspace_quick_actions_bar.winfo_manager() == "pack"
    assert window.analysis_ribbon_host.winfo_manager() == "pack"
    assert getattr(window.analysis_ribbon_view, "_collapsed", False) is True
    assert all(button.calls == [] for button in window._shell_header_buttons)


def test_results_viewer_fallback_when_v2_disabled(tmp_path):
    from src.ui.widgets.results_viewer import ResultsViewer
    import customtkinter

    csv_file = tmp_path / "table.csv"
    csv_file.write_text("col1;col2\n1;2\n", encoding="utf-8")

    try:
        root = customtkinter.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

    try:
        root.withdraw()
        viewer = ResultsViewer(
            root,
            ui_v2_enabled=False,
            ui_v2_scope=["results"],
        )
        viewer.pack(fill="both", expand=True)
        viewer.show_table(csv_file)
        assert viewer._has_table_content is True
        assert viewer._current_table_treeview is None
    finally:
        try:
            root.destroy()
        except Exception:
            pass
