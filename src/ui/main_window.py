"""
Janela principal do <labiia_lex>.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import logging
import platform
import threading
import tempfile
import shutil
import json
import csv
import webbrowser
import re
import unicodedata
from datetime import datetime, timezone

from .styles import apply_theme, COLORS, FONTS, SIZES, get_themed_color, style_native_menu, get_current_colors, apply_dwm_to_widget
from .theme_bridge import apply_ttk_windows_styles
from .component_factory import create_button, style_button
from .feedback import FeedbackService, MessageBoxBridge
from .iconography import label_with_icon
from .modern_components import (
    create_nav_button,
    create_pill_button,
    create_section_title,
    create_surface,
    set_nav_button_state,
)
from .dialogs.error_dialog import ErrorDialog, show_error
from .tk_helpers import cleanup_widget_menus, patch_customtkinter_entry_callback
from .widgets.corpus_tree import CorpusTree
from .widgets.corpus_navigator import CorpusNavigator
from .widgets.results_viewer import ResultsViewer
from .widgets.analysis_catalog import AnalysisCatalogView
from .widgets.analysis_ribbon import AnalysisRibbonView
from .widgets.guided_tour import GuidedTour, TourStep
from .widgets.tooltip import CTkTooltip

from ..core.corpus import Corpus, decouperlist
from ..core.config_manager import ConfigManager
from ..core.history import AnalysisHistory, HistoryError
from ..core.lexicon import Lexicon, resolve_expression_path, resolve_lexicon_path
from ..core.project import Project, ProjectManager, ProjectError
from ..core.import_processing_cache import ImportProcessingCache
from ..core.r_text_pipeline import RTextPipeline, RTextPipelineError
from ..core.stopword_layers import (
    get_global_custom_stopwords,
    merge_stopword_layers,
    set_global_custom_stopwords,
)
from ..core.tableau import Tableau, TableauError
from ..core.report_generator import ReportGenerator
from ..core.version import (
    APP_VERSION,
    DISPLAY_APP_NAME,
    DISPLAY_APP_TITLE,
)
from ..utils.paths import PathManager

from dataclasses import dataclass
from typing import Callable, Type, Optional, Any

from .dialogs import (
    YAKEDialog,
    LDADialog,
    AssociativeHeatmapDialog,
    ThematicMapDialog,
    ThematicCHDDialog,
)

log = logging.getLogger(__name__)
GUIDED_TOUR_VERSION = "modern_shell_v1"
LINK_PATTERN = re.compile(
    r"https?://[^\s]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)


@dataclass
class SemanticAnalysisEntry:
    analysis_type: str
    display_name: str
    dialog_class: Type
    runner_factory: Callable
    primary_image_field: str
    primary_table_field: str
    report_mode: str
    history_metadata_adapter: Callable
    legacy_fallback_analysis_type: Optional[str] = None


def _dummy_runner(*args, **kwargs):
    raise NotImplementedError("Runner not implemented yet.")

def _dummy_adapter(result) -> dict:
    return {}

def _validate_output_dir(output_dir, analysis_name: str):
    """Valida output_dir antes de chamar a analise."""
    if output_dir is None:
        raise TypeError(
            f"output_dir e None para '{analysis_name}'. "
            f"Isto indica que _get_analysis_output_dir nao foi chamado corretamente."
        )
    from pathlib import Path
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _run_yake(corpus, output_dir, **kwargs):
    output_dir = _validate_output_dir(output_dir, "yake")
    from ..analysis.yake_analysis import YAKEAnalysis, YAKEParams
    return YAKEAnalysis().run(corpus, output_dir, YAKEParams(**kwargs))

def _run_lda(corpus, output_dir, **kwargs):
    output_dir = _validate_output_dir(output_dir, "lda")
    from ..analysis.lda_analysis import LDAAnalysis, LDAParams
    return LDAAnalysis().run(corpus, output_dir, LDAParams(**kwargs))

def _run_heatmap(corpus, output_dir, **kwargs):
    output_dir = _validate_output_dir(output_dir, "heatmap")
    from ..analysis.associative_heatmap_analysis import AssociativeHeatmapAnalysis, AssociativeHeatmapParams
    return AssociativeHeatmapAnalysis().run(corpus, output_dir, AssociativeHeatmapParams(**kwargs))

def _run_thematic_map(corpus, output_dir, **kwargs):
    output_dir = _validate_output_dir(output_dir, "thematic_map")
    from ..analysis.thematic_map_analysis import ThematicMapAnalysis, ThematicMapParams
    return ThematicMapAnalysis().run(corpus, output_dir, ThematicMapParams(**kwargs))

def _run_thematic_chd(corpus, output_dir, **kwargs):
    output_dir = _validate_output_dir(output_dir, "thematic_chd")
    from ..analysis.thematic_chd_analysis import ThematicCHDAnalysis, ThematicCHDParams
    return ThematicCHDAnalysis().run(corpus, output_dir, ThematicCHDParams(**kwargs))

SEMANTIC_REGISTRY: Dict[str, SemanticAnalysisEntry] = {
    "yake": SemanticAnalysisEntry(
        "yake", "Palavras-Chave (YAKE)", YAKEDialog, _run_yake,
        "yake_ranking.png", "yake_keyphrases.csv", "yake", lambda r: r.to_history_metadata()
    ),
    "lda": SemanticAnalysisEntry(
        "lda", "Tópicos LDA", LDADialog, _run_lda,
        "lda_distribution.png", "lda_terms_beta.csv", "lda", lambda r: r.to_history_metadata()
    ),
    "associative_heatmap": SemanticAnalysisEntry(
        "associative_heatmap", "Heatmap Associativo", AssociativeHeatmapDialog, _run_heatmap,
        "heatmap.png", "association_matrix.csv", "heatmap", lambda r: r.to_history_metadata(),
        legacy_fallback_analysis_type="heatmap"
    ),
    "thematic_map": SemanticAnalysisEntry(
        "thematic_map", "Mapa Temático", ThematicMapDialog, _run_thematic_map,
        "strategic_map.png", "thematic_communities.csv", "thematic_map", lambda r: r.to_history_metadata()
    ),
    "thematic_chd": SemanticAnalysisEntry(
        "thematic_chd", "CHD Temático", ThematicCHDDialog, _run_thematic_chd,
        "thematic_chd_class_topic_heatmap.png", "class_topic_mix.csv", "thematic_chd", lambda r: r.to_history_metadata()
    ),
}


class MainWindow(ctk.CTk):
    """
    Janela principal do <labiia_lex>.

    Layout:
    +------------------------------------------+
    |  Menu Bar                                |
    +------------------------------------------+
    |  Toolbar (botoes de acao)                |
    +----------+-------------------------------+
    |          |                               |
    |  Corpus  |       Results Viewer          |
    |   Tree   |                               |
    |  (left)  |          (center)             |
    |          |                               |
    +----------+-------------------------------+
    |  Status Bar                              |
    +------------------------------------------+
    """

    def __init__(self):
        # No Linux, o WM_CLASS deve ser definido via `className` no construtor
        # do `tk.Tk` (repassado pelo CustomTkinter via **kwargs). Isso é o único
        # método confiável — chamar wm_class() depois pode ser ignorado pelo WM.
        # O WM_CLASS define o nome exibido na barra de tarefas e o ícone associado
        # pelo gerenciador de janelas (GNOME/KDE), via StartupWMClass no .desktop.
        _init_kwargs = {}
        if platform.system() == "Linux":
            _init_kwargs["className"] = "LabiiaLex"
        super().__init__(**_init_kwargs)
        patch_customtkinter_entry_callback()

        # Reforçar nome da aplicação Tk (parte de instância do WM_CLASS).
        if platform.system() == "Linux":
            try:
                self.tk.call("tk", "appname", "LabiiaLex")
            except Exception:
                pass

        # Carregar config ANTES de aplicar tema para ler preferência dark/light
        self.config = ConfigManager()
        _saved_theme = str(self.config.get("theme", "light") or "light").lower()
        if _saved_theme not in ("dark", "light", "system"):
            _saved_theme = "light"
        self._ui_v2_enabled, self._ui_v2_scope, self._ui_density = self._resolve_ui_v2_settings(
            self.config.get("ui", {})
        )
        self._force_enable_v2_startup()
        self._ui_v2_enabled, self._ui_v2_scope, self._ui_density = self._resolve_ui_v2_settings(
            self.config.get("ui", {})
        )
        self._ui_v2_shell = self._ui_v2_enabled and ("shell" in self._ui_v2_scope)
        self._ui_v2_results = self._ui_v2_enabled and ("results" in self._ui_v2_scope)
        self._ui_v2_feedback = self._ui_v2_enabled and ("feedback" in self._ui_v2_scope)
        _ui_cfg = self.config.get("ui", {})
        if not isinstance(_ui_cfg, dict):
            _ui_cfg = {}
        self._shell_version = str(_ui_cfg.get("shell_version", "modern_academic_v1") or "modern_academic_v1")
        self._nav_collapsed_default = bool(_ui_cfg.get("nav_collapsed", False))
        self.command_registry = self._build_command_registry()
        self.analysis_catalog_registry = self._build_analysis_catalog_registry()
        self.help_ribbon_registry = self._build_help_ribbon_registry()
        self._shell_sections = self._build_shell_sections()
        self._active_shell_section = self._default_shell_section()
        self._voyant_suite_enabled = bool(
            self.config.is_feature_enabled("voyant_suite", default=True)
        )
        apply_theme(mode=_saved_theme)
        self.configure(fg_color=get_themed_color("background"))
        self._configure_native_windows_style()

        self.title(DISPLAY_APP_TITLE)
        self._apply_app_icon()
        # Reaplicar o ícone após 300ms para garantir que sobrescreva qualquer
        # chamada interna do CustomTkinter (que usa after(200, ...)).
        # No Linux isso é essencial para o ícone aparecer na barra de tarefas.
        if platform.system() == "Linux":
            self.after(300, lambda: self._apply_window_icon(self))
            self.after(600, lambda: self._apply_window_icon(self))
        # self.geometry("1200x800") # Removido para priorizar tela cheia
        self.minsize(900, 600)
        self._startup_onboarding_finished = False

        # Estado
        self.corpus: Optional[Corpus] = None
        self._corpus_db_path: Optional[Path] = None
        self._analysis_output_root: Optional[Path] = None
        self.current_project_path: Optional[Path] = None
        self.analysis_history = AnalysisHistory()
        self._cleanup_previous_session_history()
        self._last_analysis_result = None
        self._last_analysis_runner = None
        self._last_saved_history_entry_id: Optional[str] = None
        self._last_analysis_context: Dict[str, Any] = {}
        self._loaded_lexicon: Optional[Lexicon] = None
        self._loaded_lexicon_language: Optional[str] = None
        self._loaded_lexicon_strict_mode: Optional[bool] = None
        self._project_custom_stopwords: List[str] = []
        self._last_import_file_path: Optional[Path] = None
        self._last_import_metadata: Dict[str, Any] = {}
        self._last_import_mode: str = "traditional"
        self._last_import_options: Dict[str, Any] = {}
        self._last_corpus_text: str = ""    # texto bruto do último corpus importado
        self.tableau: Optional[Tableau] = None
        self._last_report_path: Optional[Path] = None
        self._similarity_halo_refresh_running = False
        self._similarity_halo_context: Dict[str, Any] = {}
        self._pending_result_run_key: Optional[str] = None
        self._pending_result_tab_label: Optional[str] = None
        self._guided_tour: Optional[GuidedTour] = None
        self._guided_tour_start_job: Optional[str] = None

        # Construir interface
        self._create_menu()
        self._create_toolbar()
        self._create_main_area()
        if hasattr(self.results_viewer, "configure_similarity_halo_toggle"):
            self.results_viewer.configure_similarity_halo_toggle(
                visible=False,
                callback=self._on_similarity_halo_toggle,
            )
        if hasattr(self.results_viewer, "set_analysis_tab_click_callback"):
            self.results_viewer.set_analysis_tab_click_callback(self._on_results_tab_clicked)
        self.corpus_tree.load_history(
            self.analysis_history,
            on_select=self._open_history_entry,
            on_action=self._handle_corpus_tree_action,
        )
        self.corpus_tree.set_export_callback(self._export_corpus_to_txt)
        self.corpus_tree.set_export_iramuteq_callback(self._export_corpus_to_iramuteq)
        self._create_status_bar()
        self.feedback = FeedbackService(status_callback=self._set_status, logger=log)
        self._messagebox_bridge = MessageBoxBridge(self.feedback)
        if self._ui_v2_feedback:
            self._messagebox_bridge.install()

        # Bindings
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-o>", lambda _e: self._import_file())
        self.bind("<Control-O>", lambda _e: self._import_file())
        self.bind("<Control-s>", lambda _e: self._save_project() if self.corpus else None)
        self.bind("<Control-S>", lambda _e: self._save_project() if self.corpus else None)
        self.bind("<F5>", lambda _e: self._run_statistics() if self.corpus else None)
        self.bind("<F6>", self._cycle_focus_regions)
        self._enforce_fullscreen_startup()

        # Aplicar DWM (barra de titulo nativa Windows 11 com cor do tema)
        self.after(50, lambda: apply_dwm_to_widget(self))

        # Verificar popup de boas-vindas/sobre
        self.after(40, self._show_startup_popup)

    def get_global_custom_stopwords(self) -> List[str]:
        """Expose global stopwords for import dialog."""
        return list(get_global_custom_stopwords(self.config))

    def get_project_custom_stopwords(self) -> List[str]:
        """Expose project-level stopwords for import dialog."""
        return list(self._project_custom_stopwords)

    def _enforce_fullscreen_startup(self) -> None:
        """Garante abertura em tela cheia (janela maximizada) no startup."""
        self._apply_fullscreen_window_state()
        # Reforcos para evitar corrida de layout/timing no primeiro paint.
        self.after(0, self._apply_fullscreen_window_state)
        self.after(120, self._apply_fullscreen_window_state)
        self.after(420, self._apply_fullscreen_window_state)

    def _apply_fullscreen_window_state(self) -> None:
        """Aplica estado maximizado com fallback para ocupar toda a tela."""
        try:
            self.update_idletasks()
        except Exception:
            pass

        # No Linux, o método correto para maximizar sem ocultar a barra de títulos/controles
        # é usar o atributo "-zoomed" do Tkinter.
        if platform.system() == "Linux":
            try:
                self.attributes("-zoomed", True)
                return
            except Exception:
                pass

        screen_w = max(1024, int(self.winfo_screenwidth()))
        screen_h = max(720, int(self.winfo_screenheight()))
        try:
            self.state("zoomed")
        except Exception:
            try:
                # No Linux, definir geometry para o tamanho total da tela empurra a barra de títulos
                # para baixo do painel do sistema ou para fora da tela. Evitamos isso no Linux.
                if platform.system() != "Linux":
                    self.geometry(f"{screen_w}x{screen_h}+0+0")
                else:
                    self.geometry("1200x800")
                    self._center_window()
            except Exception:
                pass
            return

        # Fallback defensivo caso o WM ignore/atrase o zoomed (apenas fora do Linux).
        if platform.system() != "Linux":
            try:
                cur_w = int(self.winfo_width())
                cur_h = int(self.winfo_height())
                if cur_w < int(screen_w * 0.96) or cur_h < int(screen_h * 0.96):
                    self.geometry(f"{screen_w}x{screen_h}+0+0")
            except Exception:
                pass

    def _show_startup_popup(self):
        """Mostra popup 'Sobre' no inicio — layout Windows padrao."""
        if not self.config.get("show_startup_about", True):
            self._schedule_guided_tour_startup()
            return

        about_window = ctk.CTkToplevel(self)
        about_window.title(f"Sobre o {DISPLAY_APP_NAME}")
        about_window.geometry("520x480")
        about_window.resizable(False, False)
        about_window.transient(self)

        about_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width()  - 520) // 2
        y = self.winfo_y() + (self.winfo_height() - 480) // 2
        about_window.geometry(f"+{x}+{y}")
        about_window.grab_set()

        # Aplicar DWM ao popup tambem
        about_window.after(50, lambda: apply_dwm_to_widget(about_window))

        content = ctk.CTkFrame(about_window, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(20, 8))

        # Titulo compacto (como About Windows)
        ctk.CTkLabel(
            content,
            text=DISPLAY_APP_NAME,
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        
        ctk.CTkLabel(
            content,
            text=f"Versão {APP_VERSION} — Análise Textual Avançada",
            font=("Segoe UI", 9),
            text_color=get_themed_color("text_secondary"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 16))

        text_box = ctk.CTkTextbox(
            content,
            font=FONTS["body"],
            wrap="word",
            fg_color=get_themed_color("background"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            activate_scrollbars=False,
        )
        text_box.pack(fill="both", expand=True)
        self._insert_clickable_about_text(text_box, self._build_about_text())

        # Checkbox "Nao mostrar novamente"
        dont_show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            content,
            text="Nao mostrar novamente ao iniciar",
            variable=dont_show_var,
            font=FONTS["small"],
            checkbox_width=16,
            checkbox_height=16,
        ).pack(anchor="w", pady=(10, 0))

        def close_popup():
            if dont_show_var.get():
                self.config.set("show_startup_about", False)
                self.config.save()
            about_window.destroy()
            self._schedule_guided_tour_startup()

        about_window.protocol("WM_DELETE_WINDOW", close_popup)

        # Rodape com divisoria + botao OK (padrao Windows)
        ctk.CTkFrame(about_window, height=1, fg_color=get_themed_color("border")
                     ).pack(fill="x", side="bottom")
        btn_row = ctk.CTkFrame(about_window, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=12, pady=8)
        ctk.CTkButton(
            btn_row, text="OK", width=80, height=26,
            fg_color=get_themed_color("primary"),
            hover_color=get_themed_color("primary_hover"),
            text_color=("#FFFFFF", "#FFFFFF"),
            border_width=0, corner_radius=3,
            command=close_popup,
        ).pack(side="right")


    def _cleanup_previous_session_history(self):
        """Limpa histórico e artefatos da sessão anterior para começar limpo."""
        try:
            if not getattr(self, "analysis_history", None):
                self.analysis_history = AnalysisHistory()
                
            path = self.analysis_history.history_path
            if path.exists():
                path.unlink()
                
            artifacts = path.parent / "artifacts"
            if artifacts.exists():
                shutil.rmtree(artifacts, ignore_errors=True)
                artifacts.mkdir(parents=True, exist_ok=True)
                
            # Recria o objeto limpo
            self.analysis_history = AnalysisHistory()
            log.info("Histórico de sessão limpo com sucesso.")
        except Exception as e:
            log.warning("Falha ao limpar histórico de sessão anterior: %s", e)

    def _center_window(self):
        """Centraliza janela na tela."""
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.geometry(f"+{x}+{y}")

    @staticmethod
    def _resolve_ui_v2_settings(ui_cfg: Any) -> Tuple[bool, set, str]:
        """Resolve feature flags da UI v2 com fallback seguro."""
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        enabled = bool(ui_cfg.get("v2_enabled", True))
        raw_scope = ui_cfg.get("v2_scope", ["shell", "results", "feedback"])
        allowed = {"shell", "results", "dialogs", "feedback", "icons"}
        scope: set = set()
        if isinstance(raw_scope, (list, tuple, set)):
            scope = {
                str(item).strip().lower()
                for item in raw_scope
                if str(item).strip().lower() in allowed
            }
        elif isinstance(raw_scope, str):
            scope = {
                part.strip().lower()
                for part in raw_scope.split(",")
                if part.strip().lower() in allowed
            }
        if not scope:
            scope = {"shell", "results", "feedback"}
        density = str(ui_cfg.get("density", "comfortable") or "comfortable").strip().lower()
        if density not in {"compact", "comfortable"}:
            density = "comfortable"
        return enabled, scope, density

    def _force_enable_v2_startup(self) -> None:
        """
        Força habilitação da UI V2 no startup.

        Mantém fallback interno por escopo sem exigir ação manual do usuário.
        """
        ui_cfg = self.config.get("ui", {})
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        changed = False
        if not bool(ui_cfg.get("v2_enabled", False)):
            ui_cfg["v2_enabled"] = True
            changed = True
        raw_scope = ui_cfg.get("v2_scope", ["shell", "results", "feedback"])
        if isinstance(raw_scope, str):
            scope = [part.strip().lower() for part in raw_scope.split(",") if part.strip()]
        elif isinstance(raw_scope, (list, tuple, set)):
            scope = [str(item).strip().lower() for item in raw_scope if str(item).strip()]
        else:
            scope = []
        for required in ("shell", "results", "feedback"):
            if required not in scope:
                scope.append(required)
                changed = True
        ui_cfg["v2_scope"] = scope
        if changed:
            self.config.set("ui", ui_cfg)
            try:
                self.config.save()
            except OSError:
                log.warning("Nao foi possivel persistir auto-enable da UI V2.")

    def _cycle_focus_regions(self, _event=None) -> None:
        """Atalho F6: alterna foco entre áreas principais da janela."""
        regions: List[Any] = []
        for candidate in (
            getattr(self, "btn_import", None),
            getattr(getattr(self, "corpus_tree", None), "tree", None),
            getattr(getattr(self, "results_viewer", None), "tabview", None),
            getattr(self, "status_label", None),
        ):
            if candidate is not None:
                regions.append(candidate)
        if not regions:
            return
        current_focus = self.focus_get()
        idx = -1
        for pos, region in enumerate(regions):
            try:
                if current_focus is region or str(current_focus).startswith(str(region)):
                    idx = pos
                    break
            except Exception:
                continue
        target = regions[(idx + 1) % len(regions)]
        try:
            target.focus_set()
        except Exception:
            pass

    def _build_command_registry(self) -> Dict[str, Dict[str, Any]]:
        """Expõe ações centrais da aplicação para shell, atalhos e launcher."""
        return {
            "import": {
                "label": "Importar",
                "section": "dashboard",
                "command": self._import_file,
            },
            "open_project": {
                "label": "Abrir Projeto",
                "section": "corpus",
                "command": self._open_project,
            },
            "save_project": {
                "label": "Salvar Projeto",
                "section": "corpus",
                "command": self._save_project,
            },
            "settings": {
                "label": "Ajustes",
                "section": "ajustes",
                "command": self._show_settings,
            },
            "statistics": {
                "label": "Estatísticas",
                "section": "dashboard",
                "command": self._run_statistics,
            },
            "wordcloud": {
                "label": "Nuvem",
                "section": "analises",
                "command": self._run_wordcloud,
            },
            "similarity": {
                "label": "Rede",
                "section": "analises",
                "command": self._run_similarity,
            },
            "chd": {
                "label": "CHD",
                "section": "analises",
                "command": self._run_chd,
            },
            "voyant_suite": {
                "label": "Painéis",
                "section": "resultados",
                "command": self._run_voyant_suite,
            },
            "concordance": {
                "label": "Concordância",
                "section": "resultados",
                "command": self._run_concordance,
            },
        }

    def _build_analysis_catalog_registry(self) -> Dict[str, Dict[str, Any]]:
        """Registro único das análises exibidas no catálogo central."""
        return {
            "statistics": {
                "label": "Estatísticas",
                "group": "Essenciais",
                "ribbon_label": "Estat.",
                "ribbon_width": 78,
                "description": "Visão geral quantitativa do corpus, frequências, hapax e gráficos de distribuição.",
                "command": self._run_statistics,
                "requires_corpus": True,
            },
            "similarity": {
                "label": "Similitude",
                "group": "Essenciais",
                "ribbon_label": "Rede",
                "ribbon_width": 72,
                "description": "Grafo de coocorrência lexical com seleção de termos e halos configuráveis.",
                "command": self._run_similarity,
                "requires_corpus": True,
            },
            "chd": {
                "label": "CHD",
                "group": "Essenciais",
                "ribbon_width": 64,
                "description": "Classificação Hierárquica Descendente com perfis, segmentos e AFC associados.",
                "command": self._run_chd,
                "requires_corpus": True,
            },
            "wordcloud": {
                "label": "Nuvem",
                "group": "Essenciais",
                "ribbon_width": 78,
                "description": "Nuvem de palavras com parâmetros de frequência, cor e layout.",
                "command": self._run_wordcloud,
                "requires_corpus": True,
            },
            "concordance": {
                "label": "Concordância",
                "group": "Essenciais",
                "ribbon_label": "Concord.",
                "ribbon_width": 88,
                "description": "Busca KWIC para localizar termos e inspeção rápida do contexto textual.",
                "command": self._run_concordance,
                "requires_corpus": True,
            },
            "yake": {
                "label": "YAKE",
                "group": "Semânticas",
                "ribbon_width": 70,
                "description": "Extração de palavras-chave candidatas com ranking e exportação tabular.",
                "command": lambda: self._run_semantic_analysis("yake"),
                "requires_corpus": True,
            },
            "lda": {
                "label": "LDA",
                "group": "Semânticas",
                "ribbon_width": 64,
                "description": "Modelagem de tópicos com distribuição por documento e visualizações auxiliares.",
                "command": lambda: self._run_semantic_analysis("lda"),
                "requires_corpus": True,
            },
            "associative_heatmap": {
                "label": "Heatmap Associativo",
                "group": "Semânticas",
                "ribbon_label": "Assoc.",
                "ribbon_width": 74,
                "description": "Mapa de associações entre pares de termos com matriz exportável.",
                "command": lambda: self._run_semantic_analysis("associative_heatmap"),
                "requires_corpus": True,
            },
            "thematic_map": {
                "label": "Mapa Temático",
                "group": "Semânticas",
                "ribbon_label": "Temas",
                "ribbon_width": 82,
                "description": "Rede de expressões compostas, comunidades e mapa estratégico de temas.",
                "command": lambda: self._run_semantic_analysis("thematic_map"),
                "requires_corpus": True,
            },
            "thematic_chd": {
                "label": "CHD Temático",
                "group": "Semânticas",
                "ribbon_label": "CHD Tem.",
                "ribbon_width": 92,
                "description": "Segmentação temática combinando classes e tópicos em heatmap interpretativo.",
                "command": lambda: self._run_semantic_analysis("thematic_chd"),
                "requires_corpus": True,
            },
            "voyant_suite": {
                "label": "Voyant Suite",
                "group": "Exploratórios",
                "ribbon_label": "Voyant",
                "ribbon_width": 80,
                "description": "Painéis TermsBerry, tendências, termos por documento e coocorrências.",
                "command": self._run_voyant_suite,
                "requires_corpus": True,
                "is_enabled_predicate": lambda: bool(self._voyant_suite_enabled and self.corpus),
            },
            "emotions": {
                "label": "Emoções",
                "group": "Exploratórios",
                "ribbon_width": 84,
                "description": "Leitura de emoções com base no léxico NRC e saídas complementares.",
                "command": self._run_emotions,
                "requires_corpus": True,
            },
            "network_text": {
                "label": "Rede Textual",
                "group": "Exploratórios",
                "ribbon_label": "Rede Textual",
                "ribbon_width": 118,
                "description": "Rede textual avançada para exploração estrutural do corpus.",
                "command": self._run_network_text_analysis,
                "requires_corpus": True,
            },
            "cca": {
                "label": "CCA",
                "group": "Exploratórios",
                "ribbon_width": 64,
                "description": "Construção de conceitos e coocorrências inspirada no fluxo Textometrica.",
                "command": self._run_cca_analysis,
                "requires_corpus": True,
            },
            "bigrams_extra": {
                "label": "Bigramas",
                "group": "Extras",
                "ribbon_width": 86,
                "description": "Rede de bigramas frequentes para exploração lexical complementar.",
                "command": self._run_bigram_network_extra,
                "requires_corpus": True,
            },
            "trigrams_extra": {
                "label": "Trigramas",
                "group": "Extras",
                "ribbon_width": 86,
                "description": "Rede de trigramas para inspeção de padrões compostos.",
                "command": self._run_trigram_network_extra,
                "requires_corpus": True,
            },
            "word_tree_extra": {
                "label": "Word Tree",
                "group": "Extras",
                "ribbon_label": "Tree",
                "ribbon_width": 66,
                "description": "Árvore de contexto para expansão visual de sequências ao redor de termos.",
                "command": self._run_word_tree_extra,
                "requires_corpus": True,
            },
            "wordfish_extra": {
                "label": "Wordfish",
                "group": "Extras",
                "ribbon_width": 82,
                "description": "Escalonamento 1D para comparar posições lexicais entre documentos.",
                "command": self._run_wordfish_extra,
                "requires_corpus": True,
            },
            "xray_extra": {
                "label": "X-Ray",
                "group": "Extras",
                "ribbon_width": 70,
                "description": "Mapa de ocorrência longitudinal ao longo do corpus e dos documentos.",
                "command": self._run_xray_extra,
                "requires_corpus": True,
            },
            "sentiment_extra": {
                "label": "Sentimento",
                "group": "Extras",
                "ribbon_label": "Sentim.",
                "ribbon_width": 84,
                "description": "Análise de polaridade e distribuição temporal de sentimento.",
                "command": self._run_sentiment_extra,
                "requires_corpus": True,
            },
            "keyness": {
                "label": "Keyness",
                "group": "Extras",
                "ribbon_width": 82,
                "description": "Comparação entre subconjuntos para destacar termos distintivos.",
                "command": self._run_keyness,
                "requires_corpus": True,
            },
        }

    def _build_help_ribbon_registry(self) -> Dict[str, Dict[str, Any]]:
        """Registro das páginas auxiliares exibidas pela faixa inferior de Ajuda."""
        return {
            "geral": {
                "label": "Geral do Software",
                "command": lambda: self._open_help_page("geral"),
            },
            "analises": {
                "label": "Análises Textuais",
                "command": lambda: self._open_help_page("analises"),
            },
            "matriz": {
                "label": "Análises de Matriz",
                "command": lambda: self._open_help_page("matriz"),
            },
            "limpeza": {
                "label": "Limpeza de Corpus",
                "command": lambda: self._open_help_page("limpeza"),
            },
            "faq": {
                "label": "FAQ",
                "command": lambda: self._open_help_page("faq"),
            },
            "glossario": {
                "label": "Glossário",
                "command": lambda: self._open_help_page("glossario"),
            },
            "sobre": {
                "label": "Sobre o Software",
                "command": self._show_about,
            },
            "tutorial": {
                "label": "Tutorial Guiado",
                "command": lambda: self._start_guided_tour(auto=False),
            },
        }

    def _build_shell_sections(self) -> List[Dict[str, str]]:
        """Define a arquitetura fixa da shell moderna."""
        return [
            {"key": "dashboard", "label": "Dashboard"},
            {"key": "corpus", "label": "Corpus"},
            {"key": "analises", "label": "Análises"},
            {"key": "resultados", "label": "Resultados"},
            {"key": "ajustes", "label": "Ajustes"},
        ]

    def _default_shell_section(self) -> str:
        return "dashboard"

    def _refresh_shell_nav(self) -> None:
        """A navegação lateral foi removida da ribbon superior."""
        return

    def _get_shell_section_title(self, key: str) -> Tuple[str, str]:
        mapping = {
            "dashboard": (
                "Visão Geral da Análise",
                "Acompanhe corpus, histórico recente e atalhos operacionais em um só lugar.",
            ),
            "corpus": (
                "Explorador de Corpus",
                "Documentos, histórico e ações de exportação permanecem no painel contextual.",
            ),
            "analises": (
                "Análises Disponíveis",
                "Lance os fluxos principais sem depender do menu nativo legado.",
            ),
            "resultados": (
                "Resultados",
                "Gráficos, tabelas e relatórios ganham prioridade na área de trabalho principal.",
            ),
            "ajustes": (
                "Preferências",
                "Tema, comportamento da shell e caminho do R ficam centralizados na nova folha de ajustes.",
            ),
        }
        return mapping.get(key, mapping["dashboard"])

    def _refresh_context_panel(self) -> None:
        """Atualiza título e descrição do painel contextual."""
        title, subtitle = self._get_shell_section_title(self._active_shell_section)
        if hasattr(self, "context_panel_title"):
            self.context_panel_title.configure(text=title)
        if hasattr(self, "context_panel_subtitle"):
            self.context_panel_subtitle.configure(text=subtitle)
        self._refresh_sidebar_context()

    def _refresh_workspace_header(self) -> None:
        """Atualiza cabeçalho do workspace principal."""
        title, subtitle = self._get_shell_section_title(self._active_shell_section)
        if hasattr(self, "app_bar_context_label"):
            self.app_bar_context_label.configure(text=title)
        if hasattr(self, "workspace_title_label"):
            self.workspace_title_label.configure(text=title)

        corpus_status = "Nenhum corpus ativo"
        if self.corpus is not None:
            try:
                n_ucis = self.corpus.getucinb() if hasattr(self.corpus, "getucinb") else 0
            except Exception:
                n_ucis = 0
            corpus_status = f"{n_ucis} documento(s) prontos para análise"

        if hasattr(self, "workspace_subtitle_label"):
            self.workspace_subtitle_label.configure(text=f"{subtitle} {corpus_status}".strip())

    def _refresh_dashboard_summary(self) -> None:
        """Atualiza cartões-resumo do dashboard conforme estado atual."""
        history_entries = []
        try:
            history_entries = list(self.analysis_history.list_results())
        except Exception:
            history_entries = []

        if hasattr(self, "dashboard_corpus_value_label"):
            if self.corpus is None:
                self.dashboard_corpus_value_label.configure(text="Nenhum corpus importado")
            else:
                try:
                    docs = self.corpus.getucinb() if hasattr(self.corpus, "getucinb") else 0
                    forms = len(self.corpus.formes) if hasattr(self.corpus, "formes") else 0
                    self.dashboard_corpus_value_label.configure(
                        text=f"{docs} documento(s) · {forms} formas"
                    )
                except Exception:
                    self.dashboard_corpus_value_label.configure(text="Corpus carregado")

        if hasattr(self, "dashboard_history_value_label"):
            self.dashboard_history_value_label.configure(
                text=f"{len(history_entries)} resultado(s) recente(s)"
            )

        if hasattr(self, "dashboard_last_run_value_label"):
            if history_entries:
                latest = history_entries[0]
                label = str(getattr(latest, "analysis_type", "Análise")).upper()
                when = str(getattr(latest, "timestamp", "") or "").strip()
                self.dashboard_last_run_value_label.configure(
                    text=f"{label} {'· ' + when if when else ''}".strip()
                )
            else:
                self.dashboard_last_run_value_label.configure(text="Nenhuma análise executada")

        if hasattr(self, "dashboard_section_hint_label"):
            hints = {
                "dashboard": "Use os atalhos abaixo para iniciar o fluxo principal.",
                "corpus": "Use a faixa superior para alternar entre corpus, análises e resultados sem perder o contexto.",
                "analises": "Escolha um conjunto na faixa superior; os testes aparecem logo abaixo e o resultado continua no centro.",
                "resultados": "As abas centrais mantêm os resultados abertos para comparação rápida.",
                "ajustes": "Abra a folha de ajustes para alterar tema, densidade e caminho do R.",
            }
            self.dashboard_section_hint_label.configure(text=hints.get(self._active_shell_section, ""))
        self._refresh_analysis_catalog_context()
        self._refresh_results_sidebar_context()

    def _refresh_quick_actions(self) -> None:
        """Mantém a ribbon superior visível acima do workspace."""
        quick_bar = getattr(self, "workspace_quick_actions_bar", None)
        if quick_bar is None:
            return
        if quick_bar.winfo_manager() != "pack":
            quick_bar.pack(fill="x", padx=0, pady=(0, 0))
        self._refresh_workspace_ribbon()

    def _set_shell_header_actions_visible(self, visible: bool) -> None:
        """Ações antigas do topo foram removidas da UI."""
        return

    def _refresh_workspace_ribbon(self) -> None:
        """Mantém ribbon visível e atualiza estado de habilitação dos botões."""
        ribbon_host = getattr(self, "analysis_ribbon_host", None)
        ribbon_view = getattr(self, "analysis_ribbon_view", None)
        if ribbon_host is None:
            return
        if ribbon_host.winfo_manager() != "pack":
            ribbon_host.pack(fill="x")
        if ribbon_view is not None:
            if hasattr(ribbon_view, "collapse_actions_row") and self._active_shell_section != "analises":
                try:
                    ribbon_view.collapse_actions_row()
                except Exception:
                    pass
            ribbon_view.refresh_enabled_state(corpus_loaded=self.corpus is not None)

    def _show_dashboard_workspace(self) -> None:
        """Exibe o dashboard como landing page da shell moderna."""
        if hasattr(self, "analysis_catalog_host") and self.analysis_catalog_host.winfo_manager():
            self.analysis_catalog_host.pack_forget()
        if hasattr(self, "results_host") and self.results_host.winfo_manager():
            self.results_host.pack_forget()
        if hasattr(self, "dashboard_view") and self.dashboard_view.winfo_manager() != "pack":
            self.dashboard_view.pack(fill="both", expand=True)

    def _show_analysis_catalog_workspace(self) -> None:
        """Mantém resultados no centro e usa o catálogo no painel esquerdo."""
        self._show_results_workspace()

    def _show_results_workspace(self) -> None:
        """Exibe o visualizador de resultados como workspace principal."""
        dashboard_view = self.__dict__.get("dashboard_view")
        analysis_catalog_host = self.__dict__.get("analysis_catalog_host")
        results_host = self.__dict__.get("results_host")
        if dashboard_view is not None and dashboard_view.winfo_manager():
            dashboard_view.pack_forget()
        if analysis_catalog_host is not None and analysis_catalog_host.winfo_manager():
            analysis_catalog_host.pack_forget()
        if results_host is not None and results_host.winfo_manager() != "pack":
            results_host.pack(fill="both", expand=True)

    def _switch_shell_section(self, key: str) -> None:
        """Alterna entre seções da shell mantendo contratos legados."""
        valid_keys = {item["key"] for item in self._shell_sections}
        target = key if key in valid_keys else self._default_shell_section()
        self._active_shell_section = target
        self._refresh_shell_nav()
        self._refresh_context_panel()
        self._refresh_workspace_header()
        self._refresh_dashboard_summary()
        self._refresh_quick_actions()
        self._show_results_workspace()

    def _refresh_sidebar_context(self) -> None:
        """A coluna lateral foi removida da interface principal."""
        return

    def _refresh_analysis_catalog_context(self) -> None:
        """Atualiza resumo contextual da seção Análises."""
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is not None:
            ribbon.refresh_enabled_state(corpus_loaded=self.corpus is not None)

    def _refresh_results_sidebar_context(self) -> None:
        """Atualiza navegador lateral de resultados abertos e históricos."""
        state = getattr(self, "__dict__", {})
        open_frame = state.get("results_open_tabs_frame")
        recent_frame = state.get("results_recent_entries_frame")
        history_frame = state.get("results_history_entries_frame")
        viewer = state.get("results_viewer")
        if open_frame is None or recent_frame is None or history_frame is None or viewer is None:
            return

        for frame in (open_frame, recent_frame, history_frame):
            for child in frame.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass

        open_tabs = []
        if hasattr(viewer, "list_analysis_tabs"):
            try:
                open_tabs = viewer.list_analysis_tabs()
            except Exception:
                open_tabs = []

        for tab in open_tabs:
            if str(tab.get("key")) == "inicio":
                continue
            status = str(tab.get("status", "ready"))
            prefix = "● " if status == "pending" else "! " if status == "error" else ""
            button = create_pill_button(
                open_frame,
                text=f"{prefix}{tab.get('label', tab.get('key', 'Resultado'))}",
                command=lambda target=str(tab.get("key")): self.results_viewer.focus_analysis_tab(target),
                width=186,
            )
            button.pack(fill="x", pady=(0, 8))

        recent_entries: List[Any] = []
        try:
            recent_entries = list(self.analysis_history.list_results())[:10]
        except Exception:
            recent_entries = []

        for entry in recent_entries[:4]:
            entry_key = f"history_{getattr(entry, 'entry_id', '')}"
            label = str(getattr(entry, "analysis_type", "resultado")).upper()
            button = create_pill_button(
                recent_frame,
                text=label,
                command=lambda item=entry: self._open_or_focus_result_entry(item, source="recent"),
                width=186,
            )
            if hasattr(self.results_viewer, "has_analysis_tab") and self.results_viewer.has_analysis_tab(entry_key):
                button.configure(fg_color=get_themed_color("primary"), text_color=get_themed_color("text_inverse"))
            button.pack(fill="x", pady=(0, 8))

        for entry in recent_entries:
            entry_key = f"history_{getattr(entry, 'entry_id', '')}"
            label = str(getattr(entry, "analysis_type", "resultado")).upper()
            button = create_pill_button(
                history_frame,
                text=label,
                command=lambda item=entry: self._open_or_focus_result_entry(item, source="history"),
                width=186,
            )
            if hasattr(self.results_viewer, "has_analysis_tab") and self.results_viewer.has_analysis_tab(entry_key):
                button.configure(fg_color=get_themed_color("primary"), text_color=get_themed_color("text_inverse"))
            button.pack(fill="x", pady=(0, 8))

    def _create_pending_result_tab(self, run_key: str, label: str) -> None:
        """Cria aba temporária para execução em andamento."""
        viewer = getattr(self, "results_viewer", None)
        if viewer is None or not hasattr(viewer, "create_pending_analysis_tab"):
            return
        self._pending_result_run_key = str(run_key)
        self._pending_result_tab_label = str(label)
        viewer.create_pending_analysis_tab(self._pending_result_run_key, str(label))
        self._refresh_results_sidebar_context()

    def _prepare_new_analysis_run(self) -> None:
        """Limpa identidade persistida da execução anterior antes de iniciar outra."""
        self._last_saved_history_entry_id = None
        self._last_report_path = None

    def _bind_completed_run_to_history_entry(self, run_key: Optional[str], entry_id: Optional[str], label: Optional[str]) -> str:
        """Liga aba temporária ao id persistido no histórico."""
        viewer = getattr(self, "results_viewer", None)
        history_key = f"history_{entry_id}" if entry_id else str(run_key or "")
        if viewer is None or not history_key:
            return history_key
        pending_key = str(run_key or "").strip()
        final_label = str(label or self._pending_result_tab_label or "Resultado")
        if pending_key and hasattr(viewer, "has_analysis_tab") and viewer.has_analysis_tab(pending_key):
            if hasattr(viewer, "rekey_analysis_tab"):
                viewer.rekey_analysis_tab(pending_key, history_key, label=final_label)
            if hasattr(viewer, "finalize_analysis_tab"):
                viewer.finalize_analysis_tab(history_key, label=final_label)
        else:
            if hasattr(viewer, "set_analysis_tab"):
                viewer.set_analysis_tab(final_label, key=history_key, closable=True)
            if hasattr(viewer, "finalize_analysis_tab"):
                viewer.finalize_analysis_tab(history_key, label=final_label)
        self._pending_result_run_key = None
        self._pending_result_tab_label = None
        self._refresh_results_sidebar_context()
        return history_key

    def _mark_pending_result_tab_error(self, message: str = "") -> None:
        """Marca a aba temporária atual como erro."""
        viewer = getattr(self, "results_viewer", None)
        run_key = str(getattr(self, "_pending_result_run_key", "") or "").strip()
        if viewer is not None and run_key and hasattr(viewer, "mark_analysis_tab_error"):
            viewer.mark_analysis_tab_error(run_key, message=message)
        self._pending_result_run_key = None
        self._pending_result_tab_label = None
        self._refresh_results_sidebar_context()

    def _resolve_history_entry_by_id(self, entry_id: Optional[str], entries: Optional[List[Any]] = None) -> Optional[Any]:
        """Retorna a entrada do histórico correspondente ao id persistido."""
        normalized_id = str(entry_id or "").strip()
        if not normalized_id:
            return None
        candidates = entries
        if candidates is None:
            try:
                candidates = self.analysis_history.load_results()
            except Exception:
                return None
        for entry in candidates or []:
            if str(getattr(entry, "entry_id", "") or "").strip() == normalized_id:
                return entry
        return None

    def _open_or_focus_result_entry(self, entry: Any, source: str = "history", activate: bool = True) -> None:
        """Abre ou apenas foca um resultado já existente."""
        if entry is None:
            return
        entry_key = f"history_{getattr(entry, 'entry_id', '')}"
        viewer = getattr(self, "results_viewer", None)
        if (
            activate
            and viewer is not None
            and hasattr(viewer, "has_analysis_tab")
            and viewer.has_analysis_tab(entry_key)
            and hasattr(viewer, "focus_analysis_tab")
        ):
            self._ensure_results_workspace()
            viewer.focus_analysis_tab(entry_key)
            self._set_status(f"Resultado focado: {getattr(entry, 'analysis_type', 'resultado')}", 1.0)
            self._refresh_results_sidebar_context()
            return
        self._open_history_entry(entry)

    def _run_analysis_catalog_item(self, key: str) -> None:
        """Dispara item do catálogo central respeitando o registry único."""
        payload = self.analysis_catalog_registry.get(str(key or "").strip().lower())
        if not isinstance(payload, dict):
            return
        if bool(payload.get("requires_corpus", False)) and not self.corpus:
            return
        command = payload.get("command")
        # Itens de documentação/sobre não produzem aba de resultado
        skip_tab = bool(payload.get("skip_result_tab", False))
        if not skip_tab:
            label = str(payload.get("label", key))
            self._create_pending_result_tab(
                run_key=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                label=label,
            )
            self._show_results_workspace()
        if callable(command):
            try:
                command()
            except Exception as exc:
                if not skip_tab:
                    self._mark_pending_result_tab_error(str(exc))
                raise

    def _ensure_results_workspace(self) -> None:
        """Promove a área de resultados ao primeiro plano quando algo é renderizado."""
        self._show_results_workspace()

    def _open_command_launcher(self) -> None:
        """Exibe menu rápido com as ações declaradas no registry."""
        menu = tk.Menu(self, tearoff=False, font=FONTS["menu"])
        grouped_sections = ["dashboard", "corpus", "analises", "resultados", "ajustes"]
        for section_idx, section in enumerate(grouped_sections):
            entries = []
            if section == "analises":
                entries = list(self.analysis_catalog_registry.values())
            else:
                entries = [
                    payload
                    for payload in self.command_registry.values()
                    if payload.get("section") == section
                ]
            if not entries:
                continue
            if section_idx:
                menu.add_separator()
            for payload in entries:
                state = "normal"
                if bool(payload.get("requires_corpus", False)) and not self.corpus:
                    state = "disabled"
                menu.add_command(
                    label=str(payload.get("label", "Ação")),
                    command=payload["command"],
                    state=state,
                )
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _decorate_results_viewer_methods(self) -> None:
        """Garante que qualquer renderização abra automaticamente a seção de resultados."""
        viewer = getattr(self, "results_viewer", None)
        if viewer is None or getattr(viewer, "_shell_wrapped", False):
            return

        for method_name in (
            "show_image",
            "show_image_gallery",
            "show_table",
            "show_table_gallery",
            "show_text",
            "show_statistics",
            "show_chd_profiles",
        ):
            original = getattr(viewer, method_name, None)
            if not callable(original):
                continue

            def _wrapped(*args, _original=original, **kwargs):
                self._ensure_results_workspace()
                result = _original(*args, **kwargs)
                try:
                    if hasattr(viewer, "_sync_active_tab_state"):
                        viewer._sync_active_tab_state()
                except Exception:
                    log.exception("Falha ao sincronizar snapshot após renderização de resultados.")
                try:
                    self._refresh_results_sidebar_context()
                except Exception:
                    log.exception("Falha ao atualizar barra lateral de resultados após renderização.")
                return result

            setattr(viewer, method_name, _wrapped)

        viewer._shell_wrapped = True

    def _create_menu(self):
        """Cria menu nativo do Windows."""
        self.menu_bar = tk.Menu(self, tearoff=False, font=FONTS["menu"])

        self._file_menu_native = tk.Menu(
            self.menu_bar,
            tearoff=False,
            font=FONTS["menu"],
            postcommand=self._refresh_native_file_menu,
        )
        self._file_menu_native.add_command(label="Importar...", command=self._import_file)
        self._file_menu_native.add_command(label="Normalizar Formas...", command=self._open_fuzzy_normalizer)
        self._file_menu_native.add_separator()
        self._file_menu_native.add_command(label="Salvar Projeto", command=self._save_project)
        self._file_menu_native.add_command(label="Abrir Projeto", command=self._open_project)
        self._file_menu_native.add_separator()
        self._file_menu_native.add_command(label="Sair", command=self._on_close)
        self.menu_bar.add_cascade(label="Arquivo", menu=self._file_menu_native)

        self._analysis_menu_native = tk.Menu(
            self.menu_bar,
            tearoff=False,
            font=FONTS["menu"],
            postcommand=self._refresh_native_analysis_menu,
        )
        self._analysis_menu_native.add_command(label="Bigramas (Extra)", command=self._run_bigram_network_extra)
        self._analysis_menu_native.add_command(label="Trigramas (Extra)", command=self._run_trigram_network_extra)
        self._analysis_menu_native.add_command(label="CCA (Textometrica)", command=self._run_cca_analysis)
        self._analysis_menu_native.add_command(label="CHD (Reinert)", command=self._run_chd)
        self._analysis_menu_native.add_command(label="Concordância (KWIC)", command=self._run_concordance)
        self._analysis_menu_native.add_command(label="Dist. Labbé", command=self._run_labbe)
        self._analysis_menu_native.add_command(label="Emoções (NRC)", accelerator="Ctrl+E", command=self._run_emotions)
        self._analysis_menu_native.add_command(label="Especificidades", command=self._run_specificities)
        self._analysis_menu_native.add_command(label="Estatísticas", command=self._run_statistics)
        self._analysis_menu_native.add_command(label="Keyness (Comparação)", command=self._run_keyness)
        self._analysis_menu_native.add_command(label="Nuvem de Palavras", command=self._run_wordcloud)
        self._analysis_menu_native.add_command(
            label="Pacote Voyant (Novo)",
            command=self._run_voyant_suite,
            state=("normal" if self._voyant_suite_enabled else "disabled"),
        )
        self._analysis_menu_native.add_command(label="Prototípica", command=self._run_prototypical)
        self._analysis_menu_native.add_separator()
        self._analysis_menu_native.add_command(label="Palavras-Chave (YAKE)", command=lambda: self._run_semantic_analysis("yake"))
        self._analysis_menu_native.add_command(label="Tópicos LDA", command=lambda: self._run_semantic_analysis("lda"))
        self._analysis_menu_native.add_command(label="Heatmap Associativo", command=lambda: self._run_semantic_analysis("associative_heatmap"))
        self._analysis_menu_native.add_command(label="Mapa Temático", command=lambda: self._run_semantic_analysis("thematic_map"))
        self._analysis_menu_native.add_command(label="CHD Temático", command=lambda: self._run_semantic_analysis("thematic_chd"))
        self._analysis_menu_native.add_separator()
        self._analysis_menu_native.add_command(label="Rede Textual (Extra)", command=self._run_network_text_analysis)
        self._analysis_menu_native.add_command(label="Rolling Window (Lexos)", command=self._run_rolling_window)
        self._analysis_menu_native.add_command(label="Sentimentos (Extra)", command=self._run_sentiment_extra)
        self._analysis_menu_native.add_command(label="Similitude", command=self._run_similarity)
        self._analysis_menu_native.add_command(label="Word Tree (Extra)", command=self._run_word_tree_extra)
        self._analysis_menu_native.add_command(label="Wordfish (Extra)", command=self._run_wordfish_extra)
        self._analysis_menu_native.add_command(label="X-Ray (Extra)", command=self._run_xray_extra)
        self._analysis_menu_native.add_separator()
        self._analysis_menu_native.add_command(label="Reabrir Último", command=self._reload_last_history_result)

        self.bind("<Control-e>", lambda e: self._run_emotions() if self.corpus else None)
        self.bind("<Control-E>", lambda e: self._run_emotions() if self.corpus else None)
        self.menu_bar.add_cascade(label="Análise", menu=self._analysis_menu_native)

        self._matrix_menu_native = tk.Menu(
            self.menu_bar,
            tearoff=False,
            font=FONTS["menu"],
            postcommand=self._refresh_native_matrix_menu,
        )
        self._matrix_menu_native.add_command(label="Abrir Matriz...", command=self._open_matrix_file)
        self._matrix_menu_native.add_command(label="Frequências", command=self._run_matrix_frequency)
        self._matrix_menu_native.add_command(label="Qui-Quadrado", command=self._run_matrix_chi2)
        self._matrix_menu_native.add_command(label="AFC (Matriz)", command=self._run_matrix_afc)
        self._matrix_menu_native.add_command(label="CHD (Matriz)", command=self._run_matrix_chd)
        self._matrix_menu_native.add_command(label="Similitude (Matriz)", command=self._run_matrix_similarity)
        self.menu_bar.add_cascade(label="Matriz", menu=self._matrix_menu_native)

        # Menu de Documentação Detalhada
        self._docs_menu_native = tk.Menu(
            self.menu_bar,
            tearoff=False,
            font=FONTS["menu"],
        )
        self._docs_menu_native.add_command(label="Geral do Software", command=lambda: self._open_help_page("geral"))
        self._docs_menu_native.add_command(label="Análises Textuais", command=lambda: self._open_help_page("analises"))
        self._docs_menu_native.add_command(label="Análises de Matriz", command=lambda: self._open_help_page("matriz"))
        self._docs_menu_native.add_command(label="Limpeza de Corpus", command=lambda: self._open_help_page("limpeza"))
        self._docs_menu_native.add_command(label="Tutorial Guiado", command=lambda: self._start_guided_tour(auto=False))
        self._docs_menu_native.add_separator()
        self._docs_menu_native.add_command(label="Sobre", command=self._show_about)

        self.menu_bar.add_command(label="Configurações", command=self._show_settings)
        self.menu_bar.add_cascade(label="Ajuda", menu=self._docs_menu_native)
        if not self._ui_v2_shell:
            self.configure(menu=self.menu_bar)

        # Aplicar cores dark/light aos menus nativos tk.Menu
        self._style_all_native_menus()

    def _create_toolbar(self):
        """Cria app bar e faixa contextual de ações da shell moderna."""
        ui_cfg = self.config.get("ui", {}) if isinstance(self.config.get("ui", {}), dict) else {}
        compact_toolbar = bool(
            self._ui_v2_shell
            and ui_cfg.get("enable_compact_toolbar", False)
        )

        self.toolbar = ctk.CTkFrame(
            self,
            fg_color=get_themed_color("background"),
            corner_radius=0,
            border_width=0,
        )
        self.toolbar.pack(fill="x", padx=0, pady=0)

        self.app_bar = ctk.CTkFrame(
            self.toolbar,
            fg_color=get_themed_color("background"),
            corner_radius=0,
            border_width=0,
            height=66 if self._ui_v2_shell else 46,
        )
        self.app_bar.pack(fill="x", padx=0, pady=0)
        self.app_bar.pack_propagate(False)

        brand_wrap = ctk.CTkFrame(self.app_bar, fg_color="transparent")
        brand_wrap.pack(side="left", padx=(20, 12), pady=(10, 12))
        ctk.CTkLabel(
            brand_wrap,
            text=DISPLAY_APP_NAME,
            font=FONTS["display"],
            text_color=get_themed_color("rail_bg"),
        ).pack(anchor="w")
        self.app_bar_context_label = ctk.CTkLabel(
            brand_wrap,
            text="Modern Academic Workspace",
            font=FONTS["body"],
            text_color=get_themed_color("text_secondary"),
        )

        ctk.CTkFrame(self.app_bar, fg_color="transparent").pack(side="left", fill="x", expand=True)

        def create_btn(parent, text, command, width=None, state="normal", tooltip_text=None, primary=False):
            btn = create_button(
                parent,
                text=text,
                command=command,
                width=(width or 92),
                state=state,
                variant=("primary" if primary else "secondary"),
                size=("sm" if compact_toolbar else "md"),
            )
            btn.configure(font=FONTS["toolbar"], anchor="center")
            if tooltip_text:
                CTkTooltip(btn, message=tooltip_text)
            return btn

        self._toolbar_button_cache = ctk.CTkFrame(self.toolbar, fg_color="transparent", height=1, width=1)

        self.btn_import = create_btn(
            self._toolbar_button_cache,
            "Importar",
            self._import_file,
            width=104,
            tooltip_text="Importar novo corpus (txt, csv, xlsx, pdf, zip).",
            primary=True,
        )

        self.btn_open_project = create_btn(
            self._toolbar_button_cache,
            "Abrir",
            self._open_project,
            width=90,
            tooltip_text="Abrir projeto salvo.",
        )

        self.btn_save_project = create_btn(
            self._toolbar_button_cache,
            "Salvar",
            self._save_project,
            width=90,
            state="disabled",
            tooltip_text="Salvar estado atual do corpus e dos resultados.",
        )

        self.btn_shell_settings = create_btn(
            self._toolbar_button_cache,
            "Ajustes",
            self._show_settings,
            width=92,
            tooltip_text="Abrir preferências da interface.",
        )

        self.btn_command_launcher = create_btn(
            self._toolbar_button_cache,
            "Mais ações",
            self._open_command_launcher,
            width=106,
            tooltip_text="Abrir launcher interno com todas as ações registradas.",
        )
        self._shell_header_buttons = []

        self.workspace_quick_actions_bar = ctk.CTkFrame(
            self.toolbar,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        self.workspace_quick_actions_bar.pack(fill="x", padx=0, pady=(0, 0))
        self.analysis_ribbon_host = ctk.CTkFrame(self.workspace_quick_actions_bar, fg_color="transparent")

        self.analysis_ribbon_view = AnalysisRibbonView(
            self.analysis_ribbon_host,
            registry=self.analysis_catalog_registry,
            help_entries=self.help_ribbon_registry,
            on_execute=self._run_analysis_catalog_item,
            on_import=self._import_file,
            on_save_project=self._save_project,
            on_normalize=self._open_fuzzy_normalizer,
            on_prepare_corpus=self._open_corpus_preparation_dialog,
            on_export_txt=self._export_corpus_to_txt,
            on_export_iramuteq=self._export_corpus_to_iramuteq,
        )
        self.analysis_ribbon_view.pack(fill="x")

        hidden_specs = [
            ("btn_stats", "Estatísticas", self._run_statistics, "Visão geral quantitativa (frequências, lemas, hapax)."),
            ("btn_similarity", "Rede", self._run_similarity, "Análise de Similitude (grafos de coocorrência)."),
            ("btn_chd", "CHD", self._run_chd, "Classificação Hierárquica Descendente (Método Reinert)."),
            ("btn_wordcloud", "Nuvem", self._run_wordcloud, "Nuvem de palavras mais frequentes."),
            ("btn_concordance", "Concordância", self._run_concordance, "Concordância (KWIC): palavra em contexto."),
            ("btn_voyant_suite", "Painéis", self._run_voyant_suite, "TermsBerry, tendências e painéis do pacote Voyant."),
            ("btn_fuzzy_normalizer", "Normalizar", self._open_fuzzy_normalizer, "Normalizar variações ortográficas no corpus (fingerprint, n-gram, Levenshtein)."),
            ("btn_bigrams_extra", "Bigramas", self._run_bigram_network_extra, "Rede de coocorrência de bigramas."),
            ("btn_trigrams_extra", "Trigramas", self._run_trigram_network_extra, "Rede de coocorrência de trigramas."),
            ("btn_cca", "CCA", self._run_cca_analysis, "CCA (Textometrica): cria conceitos e mede coocorrências para montar rede conceitual."),
            ("btn_emotions", "Emoções", self._run_emotions, "Análise de emoções pelo léxico NRC."),
            ("btn_keyness", "Keyness", self._run_keyness, "Keyness (Comparação): compara dois corpora e destaca termos distintivos."),
            ("btn_network_text", "Rede Textual", self._run_network_text_analysis, "Análise de rede textual avançada."),
            ("btn_rolling", "Rolling", self._run_rolling_window, "Rolling Window (Lexos): acompanha evolução de termos."),
            ("btn_sentiment_extra", "Sentimento", self._run_sentiment_extra, "Análise de sentimentos e polaridade."),
            ("btn_word_tree_extra", "Word Tree", self._run_word_tree_extra, "Árvore de palavras contextual."),
            ("btn_wordfish_extra", "Wordfish", self._run_wordfish_extra, "Escalonamento ideológico 1D (Wordfish)."),
            ("btn_xray_extra", "X-Ray", self._run_xray_extra, "X-Ray: mostra onde os termos aparecem ao longo dos documentos."),
        ]
        for attr_name, label, command, tooltip in hidden_specs:
            button = create_btn(
                self._toolbar_button_cache,
                label,
                command,
                width=max(86, len(label) * 8 + 24),
                state="disabled",
                tooltip_text=tooltip,
            )
            setattr(self, attr_name, button)

        if not self._voyant_suite_enabled and hasattr(self, "btn_voyant_suite"):
            self.btn_voyant_suite.configure(state="disabled")

        ctk.CTkFrame(
            self, height=1, fg_color=get_themed_color("border")
        ).pack(fill="x", padx=0, pady=0)



    def _create_main_area(self):
        """Cria shell principal com rail de navegação, painel contextual e workspace."""
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color=get_themed_color("background"),
            corner_radius=0,
            border_width=0,
        )
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self.nav_rail = None
        self._shell_nav_buttons = {}

        self.shell_body = ctk.CTkFrame(
            self.main_frame,
            fg_color=get_themed_color("background"),
            corner_radius=0,
            border_width=0,
        )
        self.shell_body.pack(fill="both", expand=True)

        self._sidebar_min_width = 180
        self._results_min_width = 640
        self._sidebar_width_preference = self._load_sidebar_width_preference()

        paned_style = ttk.Style(self)
        try:
            colors = get_current_colors()
            paned_style.configure(
                "Lexi.Horizontal.TPanedwindow",
                background=colors.get("background", "#F3F3F3"),
                sashthickness=6,
            )
        except Exception:
            pass

        self.main_pane = ttk.PanedWindow(
            self.shell_body,
            orient="horizontal",
            style="Lexi.Horizontal.TPanedwindow",
        )
        self.main_pane.pack(fill="both", expand=True, padx=0, pady=0)

        # A coluna lateral foi removida da interface, mas os hosts são mantidos
        # fora de tela para preservar contratos internos e fluxos de histórico.
        self.sidebar = ctk.CTkFrame(self, width=1, height=1, fg_color="transparent")
        self.context_panel_title = ctk.CTkLabel(self.sidebar, text="")
        self.context_panel_subtitle = ctk.CTkLabel(self.sidebar, text="")
        self.sidebar_content = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.corpus_sidebar_host = ctk.CTkFrame(self.sidebar_content, fg_color="transparent")
        self.analysis_sidebar_host = ctk.CTkScrollableFrame(self.sidebar_content, fg_color="transparent")
        self.results_sidebar_host = ctk.CTkScrollableFrame(self.sidebar_content, fg_color="transparent")

        self.corpus_tree = CorpusTree(
            self.corpus_sidebar_host,
            density=self._ui_density if self._ui_v2_shell else "compact",
            ui_v2_enabled=self._ui_v2_shell,
        )
        self.corpus_tree.pack(fill="both", expand=True)

        analysis_sidebar_title, analysis_sidebar_subtitle = create_section_title(
            self.analysis_sidebar_host,
            "Catálogo de Análises",
            "Filtre por grupo e use os atalhos recentes sem ocupar o centro com resultados antigos.",
        )
        analysis_sidebar_title.pack(anchor="w", padx=2, pady=(8, 0))
        analysis_sidebar_subtitle.pack(anchor="w", padx=2, pady=(4, 12))
        self.analysis_context_summary_label = ctk.CTkLabel(
            self.analysis_sidebar_host,
            text="Nenhum corpus ativo.",
            anchor="w",
            justify="left",
            wraplength=260,
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
        )
        self.analysis_context_summary_label.pack(fill="x", padx=2, pady=(0, 12))
        ctk.CTkLabel(
            self.analysis_sidebar_host,
            text="Grupos",
            anchor="w",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(fill="x", padx=2, pady=(0, 8))
        self.analysis_group_buttons_frame = ctk.CTkFrame(self.analysis_sidebar_host, fg_color="transparent")
        self.analysis_group_buttons_frame.pack(fill="x", padx=2, pady=(0, 14))
        ctk.CTkLabel(
            self.analysis_sidebar_host,
            text="Recentes",
            anchor="w",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(fill="x", padx=2, pady=(0, 8))
        self.analysis_recent_actions_frame = ctk.CTkFrame(self.analysis_sidebar_host, fg_color="transparent")
        self.analysis_recent_actions_frame.pack(fill="x", padx=2)
        ctk.CTkLabel(
            self.analysis_sidebar_host,
            text="Executar",
            anchor="w",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(fill="x", padx=2, pady=(14, 8))
        self.analysis_catalog_actions_frame = ctk.CTkFrame(self.analysis_sidebar_host, fg_color="transparent")
        self.analysis_catalog_actions_frame.pack(fill="x", padx=2, pady=(0, 8))

        results_sidebar_title, results_sidebar_subtitle = create_section_title(
            self.results_sidebar_host,
            "Resultados Abertos",
            "Volte para resultados recentes e compare execuções sem perder o contexto atual.",
        )
        results_sidebar_title.pack(anchor="w", padx=2, pady=(8, 0))
        results_sidebar_subtitle.pack(anchor="w", padx=2, pady=(4, 12))
        ctk.CTkLabel(
            self.results_sidebar_host,
            text="Abertos agora",
            anchor="w",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(fill="x", padx=2, pady=(0, 8))
        self.results_open_tabs_frame = ctk.CTkFrame(self.results_sidebar_host, fg_color="transparent")
        self.results_open_tabs_frame.pack(fill="x", padx=2, pady=(0, 14))
        ctk.CTkLabel(
            self.results_sidebar_host,
            text="Recentes",
            anchor="w",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(fill="x", padx=2, pady=(0, 8))
        self.results_recent_entries_frame = ctk.CTkFrame(self.results_sidebar_host, fg_color="transparent")
        self.results_recent_entries_frame.pack(fill="x", padx=2, pady=(0, 14))
        ctk.CTkLabel(
            self.results_sidebar_host,
            text="Histórico",
            anchor="w",
            font=FONTS["heading"],
            text_color=get_themed_color("text"),
        ).pack(fill="x", padx=2, pady=(0, 8))
        self.results_history_entries_frame = ctk.CTkFrame(self.results_sidebar_host, fg_color="transparent")
        self.results_history_entries_frame.pack(fill="x", padx=2, pady=(0, 8))

        # Workspace principal
        self.results_frame = ctk.CTkFrame(
            self.main_pane,
            fg_color=get_themed_color("background"),
            corner_radius=0,
            border_width=0,
        )
        self.workspace_body = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        self.workspace_body.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.dashboard_view = ctk.CTkScrollableFrame(
            self.workspace_body,
            fg_color="transparent",
        )
        self.dashboard_view.pack(fill="both", expand=True)

        hero_card = create_surface(self.dashboard_view, fg="card", radius=20)
        hero_card.pack(fill="x", pady=(0, 14))
        hero_content = ctk.CTkFrame(hero_card, fg_color="transparent")
        hero_content.pack(fill="x", padx=18, pady=18)
        hero_title, hero_subtitle = create_section_title(
            hero_content,
            "Visão Geral da Análise",
            "Uma landing page operacional para importação, leitura do corpus e acesso rápido às análises centrais.",
        )
        hero_title.pack(anchor="w")
        hero_subtitle.pack(anchor="w", pady=(4, 12))
        self.dashboard_section_hint_label = ctk.CTkLabel(
            hero_content,
            text="Use os atalhos abaixo para iniciar o fluxo principal.",
            anchor="w",
            justify="left",
            font=FONTS["body"],
            text_color=get_themed_color("text_secondary"),
        )
        self.dashboard_section_hint_label.pack(anchor="w")

        metrics_row = ctk.CTkFrame(self.dashboard_view, fg_color="transparent")
        metrics_row.pack(fill="x", pady=(0, 14))
        self._dashboard_metric_cards = []
        for idx, (title, attr_name) in enumerate(
            (
                ("Corpus Atual", "dashboard_corpus_value_label"),
                ("Histórico Recente", "dashboard_history_value_label"),
                ("Última Execução", "dashboard_last_run_value_label"),
            )
        ):
            card = create_surface(metrics_row, fg="card", radius=18)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 10, 0))
            metrics_row.grid_columnconfigure(idx, weight=1)
            content = ctk.CTkFrame(card, fg_color="transparent")
            content.pack(fill="both", expand=True, padx=16, pady=16)
            ctk.CTkLabel(
                content,
                text=title,
                anchor="w",
                font=FONTS["small"],
                text_color=get_themed_color("text_secondary"),
            ).pack(anchor="w")
            value_label = ctk.CTkLabel(
                content,
                text="",
                anchor="w",
                justify="left",
                font=FONTS["body"],
                text_color=get_themed_color("text"),
            )
            value_label.pack(anchor="w", pady=(8, 0))
            setattr(self, attr_name, value_label)

        actions_card = create_surface(self.dashboard_view, fg="card", radius=18)
        actions_card.pack(fill="x")
        actions_content = ctk.CTkFrame(actions_card, fg_color="transparent")
        actions_content.pack(fill="x", padx=18, pady=18)
        actions_title, actions_subtitle = create_section_title(
            actions_content,
            "Atalhos Operacionais",
            "Importe corpus, abra projetos e salte direto para resultados anteriores.",
        )
        actions_title.pack(anchor="w")
        actions_subtitle.pack(anchor="w", pady=(4, 12))
        action_line = ctk.CTkFrame(actions_content, fg_color="transparent")
        action_line.pack(fill="x")
        self.dashboard_import_button = create_pill_button(action_line, "Importar Corpus", self._import_file, primary=True, width=160)
        self.dashboard_import_button.pack(side="left", padx=(0, 10))
        self.dashboard_open_button = create_pill_button(action_line, "Abrir Projeto", self._open_project, width=140)
        self.dashboard_open_button.pack(side="left", padx=(0, 10))
        self.dashboard_results_button = create_pill_button(
            action_line,
            "Ver Resultados",
            lambda: self._switch_shell_section("resultados"),
            width=140,
        )
        self.dashboard_results_button.pack(side="left")

        self.analysis_catalog_host = create_surface(self.workspace_body, fg="card", radius=20)
        self.analysis_catalog_view = AnalysisCatalogView(
            self.analysis_catalog_host,
            registry=self.analysis_catalog_registry,
            on_execute=self._run_analysis_catalog_item,
        )
        self.analysis_catalog_view.pack(fill="both", expand=True, padx=8, pady=8)

        self.results_host = ctk.CTkFrame(self.workspace_body, fg_color="transparent", corner_radius=0, border_width=0)
        self.results_viewer = ResultsViewer(
            self.results_host,
            ui_v2_enabled=self._ui_v2_results,
            ui_v2_scope=sorted(self._ui_v2_scope),
            ui_density=self._ui_density,
        )
        self.results_viewer.pack(fill="both", expand=True, padx=0, pady=0)
        self._decorate_results_viewer_methods()
        self.main_pane.add(self.results_frame, weight=1)
        self.after_idle(self._restore_sidebar_width)
        for group_name in ["Todos"] + sorted({item["group"] for item in self.analysis_catalog_registry.values()}):
            button = create_pill_button(
                self.analysis_group_buttons_frame,
                text=group_name,
                command=lambda name=group_name: self.analysis_catalog_view.set_group_filter(name),
                width=124,
            )
            button.pack(fill="x", pady=(0, 8))
        self._refresh_context_panel()
        self._refresh_workspace_header()
        self._refresh_dashboard_summary()
        self._refresh_quick_actions()
        self._show_results_workspace()

    def _load_sidebar_width_preference(self) -> int:
        """Carrega largura preferida da sidebar a partir da config."""
        default_width = int(SIZES.get("sidebar_width", 220))
        ui_cfg = self.config.get("ui", {}) if isinstance(self.config, ConfigManager) else {}
        width = default_width
        if isinstance(ui_cfg, dict):
            try:
                width = int(ui_cfg.get("sidebar_width", default_width))
            except (TypeError, ValueError):
                width = default_width
        return max(180, min(800, width))

    def _save_sidebar_width_preference(self, width: int) -> None:
        """Persiste largura da sidebar sem impactar fluxos da aplicação."""
        if not isinstance(self.config, ConfigManager):
            return
        clamped = max(180, min(800, int(width)))
        ui_cfg = self.config.get("ui", {})
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        if int(ui_cfg.get("sidebar_width", -1)) == clamped:
            return
        ui_cfg["sidebar_width"] = clamped
        self.config.set("ui", ui_cfg)
        try:
            self.config.save()
        except OSError:
            log.warning("Nao foi possivel salvar largura da sidebar no config.json")

    def _restore_sidebar_width(self) -> None:
        """Aplica largura persistida ao sash após o primeiro layout."""
        if not hasattr(self, "main_pane"):
            return
        try:
            self.main_pane.update_idletasks()
            self.main_pane.sashpos(0, int(self._sidebar_width_preference))
        except Exception:
            pass
        self._enforce_main_pane_limits(persist=False)

    def _enforce_main_pane_limits(self, persist: bool = False) -> None:
        """Mantém limites mínimos para sidebar e área de resultados."""
        pane = getattr(self, "main_pane", None)
        if pane is None:
            return
        try:
            total_width = int(pane.winfo_width())
        except Exception:
            return
        if total_width <= 0:
            return
        min_sidebar = int(getattr(self, "_sidebar_min_width", 180))
        min_results = int(getattr(self, "_results_min_width", 640))
        max_sidebar = max(min_sidebar, total_width - min_results)
        if max_sidebar < min_sidebar:
            max_sidebar = min_sidebar
        try:
            current = int(pane.sashpos(0))
        except Exception:
            current = int(self._sidebar_width_preference)
        clamped = max(min_sidebar, min(current, max_sidebar))
        if clamped != current:
            try:
                pane.sashpos(0, clamped)
            except Exception:
                pass
        self._sidebar_width_preference = clamped
        if persist:
            self._save_sidebar_width_preference(clamped)

    def _on_main_pane_configure(self, _event=None) -> None:
        self._enforce_main_pane_limits(persist=False)

    def _on_main_pane_drag(self, _event=None) -> None:
        self._enforce_main_pane_limits(persist=False)

    def _on_main_pane_release(self, _event=None) -> None:
        self._enforce_main_pane_limits(persist=True)

    @staticmethod
    def _resolve_app_icon_path(prefer_png: bool = False) -> Optional[Path]:
        root_dir = PathManager.project_root()
        parents3 = Path(__file__).resolve().parents[3]
        # No Linux, preferimos PNG (suporte nativo); no Windows, .ico.
        if prefer_png:
            candidates = [
                root_dir / "assets" / "icon.png",
                parents3 / "assets" / "icon.png",
                Path.cwd() / "assets" / "icon.png",
                root_dir / "assets" / "icon.ico",
                parents3 / "assets" / "icon.ico",
                Path.cwd() / "assets" / "icon.ico",
            ]
        else:
            candidates = [
                root_dir / "assets" / "icon.ico",
                parents3 / "assets" / "icon.ico",
                Path.cwd() / "assets" / "icon.ico",
                root_dir / "assets" / "icon.png",
                parents3 / "assets" / "icon.png",
                Path.cwd() / "assets" / "icon.png",
            ]
        for icon_path in candidates:
            if icon_path.exists():
                return icon_path
        return None

    def _apply_window_icon(self, window: tk.Misc) -> None:
        """Aplica ícone da aplicação em qualquer janela/toplevel.

        No Linux, usa exclusivamente wm_iconphoto() com PNG para garantir
        que o ícone apareça corretamente na barra de tarefas.
        No Windows, tenta iconbitmap() com .ico primeiro.
        """
        is_linux = platform.system() == "Linux"
        # Preferimos PNG no Linux para wm_iconphoto
        icon_path = self._resolve_app_icon_path(prefer_png=is_linux)
        if icon_path is None:
            return

        if is_linux:
            # No Linux: wm_iconphoto é o único método confiável.
            # Carregamos e reutilizamos a referência para evitar GC.
            try:
                from PIL import Image, ImageTk
                with Image.open(icon_path) as icon_img:
                    rgba = icon_img.convert("RGBA")
                    photo = ImageTk.PhotoImage(rgba)
                    # Guardar referência persistente na classe para evitar GC
                    if not hasattr(MainWindow, "_icon_photo_ref"):
                        MainWindow._icon_photo_ref = photo
                    else:
                        MainWindow._icon_photo_ref = photo
                window.wm_iconphoto(True, MainWindow._icon_photo_ref)
                return
            except Exception:
                pass
            # Fallback: tkinter nativo (sem PIL)
            try:
                if str(icon_path).endswith(".png"):
                    photo = tk.PhotoImage(file=str(icon_path))
                    MainWindow._icon_photo_ref = photo
                    window.wm_iconphoto(True, photo)
                    return
            except Exception:
                pass
        else:
            # Windows: tenta iconbitmap com .ico
            try:
                window.iconbitmap(str(icon_path))
                window.iconbitmap(default=str(icon_path))
                return
            except Exception:
                pass
            # Fallback para Windows: wm_iconphoto com PIL
            try:
                from PIL import Image, ImageTk
                with Image.open(icon_path) as icon_img:
                    rgba = icon_img.convert("RGBA")
                    MainWindow._icon_photo_ref = ImageTk.PhotoImage(rgba)
                window.iconphoto(True, MainWindow._icon_photo_ref)
            except Exception:
                pass

    def _apply_app_icon(self) -> None:
        """Aplica ícone principal da aplicação."""
        self._apply_window_icon(self)
        
        # Monkey-patch para garantir que todas as novas janelas (CTkToplevel)
        # recebam o ícone da pena automaticamente.
        #
        # Problema: CTkToplevel agenda after(200, _windows_set_titlebar_icon) que
        # substitui o ícone — MAS apenas se iconbitmap_method_called == False.
        # Solução: aplicar o ícone após os 200ms do CTk (usamos 250ms como margem)
        # Para diálogos modais (wait_window), também precisamos de callback imediato.
        import customtkinter as ctk
        if not hasattr(ctk.CTkToplevel, "_icon_patched"):
            original_init = ctk.CTkToplevel.__init__
            icon_applier = self._apply_window_icon
            
            def _patched_init(top_self, *args, **kwargs):
                original_init(top_self, *args, **kwargs)
                # Agenda o ícone para 250ms (após o after(200) interno do CTk)
                # Isso funciona tanto para janelas normais quanto modais,
                # pois wait_window() ainda processa o event loop interno.
                try:
                    top_self.after(250, lambda: icon_applier(top_self))
                except Exception:
                    pass
                
            ctk.CTkToplevel.__init__ = _patched_init
            ctk.CTkToplevel._icon_patched = True



    def _create_status_bar(self):
        """Cria rail de status discreto para jobs e feedback operacional."""
        # Linha divisória acima
        ctk.CTkFrame(
            self, height=1, fg_color=get_themed_color("border")
        ).pack(fill="x", side="bottom")

        self.status_bar = ctk.CTkFrame(
            self,
            fg_color=get_themed_color("background"),   # Fundo = Mica (integrado)
            height=SIZES["statusbar_height"],
            corner_radius=0,
        )
        self.status_bar.pack(fill="x", side="bottom", padx=0, pady=0)
        self.status_bar.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="Pronto para importar ou abrir um projeto",
            fg_color="transparent",
            text_color=get_themed_color("text_secondary"),
            font=FONTS["small"],
            anchor="w",
        )
        self.status_label.pack(side="left", padx=12, fill="x", expand=True)

        self.progress_bar = ctk.CTkProgressBar(
            self.status_bar,
            orientation="horizontal",
            mode="determinate",
            width=180,
            height=(6 if self._ui_v2_shell else 4),
        )
        self.progress_bar.pack(side="right", padx=12, pady=8)
        self.progress_bar.set(0)


    def _set_status(self, message: str, progress: float = 0):
        """Atualiza barra de status."""
        self.status_label.configure(text=message)
        progress_valid = max(0.0, min(1.0, float(progress)))
        self.progress_bar.set(progress_valid)
        self.update_idletasks()

    def _style_all_native_menus(self) -> None:
        """Aplica cores dark/light a todos os menus nativos tk.Menu."""
        # Controle de reentrância para evitar travamento em troca rapida de tema
        if getattr(self, '_styling_menus', False):
            return
        self._styling_menus = True
        try:
            for menu_attr in (
                "menu_bar",
                "_file_menu_native",
                "_analysis_menu_native",
                "_matrix_menu_native",
                "_docs_menu_native",
            ):
                menu = getattr(self, menu_attr, None)
                if menu is not None:
                    style_native_menu(menu)
        finally:
            self._styling_menus = False

    def _configure_native_windows_style(self) -> None:
        """Configura estilos nativos ttk para aproximar do visual Windows.
        
        Tambem aplica DWM (Windows 11 title bar nativa) na janela principal
        e patcheia CTkToplevel para que TODOS os dialogos herdem o mesmo
        tratamento automaticamente, sem necessidade de chamar apply_dwm_to_widget
        em cada dialogo individualmente.
        """
        style = ttk.Style(self)
        preferred_themes = ("vista", "xpnative", "winnative", "clam")
        available = set(style.theme_names())
        for theme_name in preferred_themes:
            if theme_name in available:
                try:
                    style.theme_use(theme_name)
                    break
                except Exception:
                    continue

        colors = get_current_colors()
        apply_ttk_windows_styles(
            style,
            colors=colors,
            fonts=FONTS,
            density="comfortable",
        )
        style.configure("Toolbar.TButton", font=("Segoe UI", 9), padding=(6, 2))
        style.configure(
            "Status.Horizontal.TProgressbar",
            troughcolor=colors.get("surface", "#E2E2E2"),
            bordercolor=colors.get("border", "#BCBCBC"),
            background=colors.get("primary", "#0078D4"),
            lightcolor=colors.get("primary", "#0078D4"),
            darkcolor=colors.get("primary", "#0078D4"),
        )

        # ── Patch: todos os CTkToplevel (dialogs) recebem DWM automaticamente ──
        _original_toplevel_init = ctk.CTkToplevel.__init__

        def _patched_toplevel_init(toplevel_self, *a, **kw):
            _original_toplevel_init(toplevel_self, *a, **kw)
            # Agendar DWM apos janela ter um HWND valido
            toplevel_self.after(40, lambda: self._apply_window_icon(toplevel_self))
            toplevel_self.after(180, lambda: self._apply_window_icon(toplevel_self))
            toplevel_self.after(60, lambda: apply_dwm_to_widget(toplevel_self))

        # Apenas patchear uma vez (idempotente)
        if not getattr(ctk.CTkToplevel, "_dwm_patched", False):
            ctk.CTkToplevel.__init__ = _patched_toplevel_init
            ctk.CTkToplevel._dwm_patched = True


    def _refresh_native_file_menu(self) -> None:
        """Atualiza estados do menu nativo Arquivo."""
        if not hasattr(self, "_file_menu_native"):
            return
        save_state = "normal" if self.corpus else "disabled"
        self._file_menu_native.entryconfigure("Salvar Projeto", state=save_state)
        norm_state = "normal" if self.corpus else "disabled"
        try:
            self._file_menu_native.entryconfigure("Normalizar Formas...", state=norm_state)
        except Exception:
            pass

    def _refresh_native_analysis_menu(self) -> None:
        """Atualiza estados do menu nativo Análise."""
        if not hasattr(self, "_analysis_menu_native"):
            return
        state = "normal" if self.corpus else "disabled"
        for label in (
            "Estatísticas",
            "CHD (Reinert)",
            "Similitude",
            "Nuvem de Palavras",
            "Especificidades",
            "Concordância (KWIC)",
            "Prototípica",
            "Dist. Labbé",
            "Bigramas (Extra)",
            "Word Tree (Extra)",
            "Rede Textual (Extra)",
            "CCA (Textometrica)",
            "Rolling Window (Lexos)",
            "Keyness (Comparação)",
            "Wordfish (Extra)",
            "X-Ray (Extra)",
            "Sentimentos (Extra)",
            "Emoções (NRC)",
        ):
            try:
                self._analysis_menu_native.entryconfigure(label, state=state)
            except Exception:
                continue
        try:
            voyant_state = state if self._voyant_suite_enabled else "disabled"
            self._analysis_menu_native.entryconfigure("Pacote Voyant (Novo)", state=voyant_state)
        except Exception:
            pass

    def _refresh_native_matrix_menu(self) -> None:
        """Atualiza estados do menu nativo Matriz."""
        if not hasattr(self, "_matrix_menu_native"):
            return
        state = "normal" if self.tableau is not None else "disabled"
        for label in (
            "Frequências",
            "Qui-Quadrado",
            "AFC (Matriz)",
            "CHD (Matriz)",
            "Similitude (Matriz)",
        ):
            self._matrix_menu_native.entryconfigure(label, state=state)

    def _enable_analysis_buttons(self, enabled: bool = True):
        """Habilita/desabilita botoes de analise."""
        state = "normal" if enabled else "disabled"
        project_state = "normal" if self.corpus else "disabled"
        for name in ("btn_save_project", "dashboard_results_button"):
            button = getattr(self, name, None)
            if button is not None and hasattr(button, "configure"):
                button.configure(state=project_state)
        for name in (
            "btn_stats",
            "btn_chd",
            "btn_similarity",
            "btn_wordcloud",
            "btn_concordance",
            "btn_voyant_suite",
            "btn_bigrams_extra",
            "btn_trigrams_extra",
            "btn_word_tree_extra",
            "btn_wordfish_extra",
            "btn_xray_extra",
            "btn_sentiment_extra",
            "btn_emotions",
            "btn_network_text",
            "btn_fuzzy_normalizer",
            "btn_cca",
            "btn_rolling",
            "btn_keyness",
        ):
            button = getattr(self, name, None)
            if button is not None and hasattr(button, "configure"):
                button.configure(state=state)
        voyant_button = getattr(self, "btn_voyant_suite", None)
        if voyant_button is not None and hasattr(voyant_button, "configure"):
            voyant_state = state if self._voyant_suite_enabled else "disabled"
            voyant_button.configure(state=voyant_state)
        # Ribbon: fonte de verdade para os botões agrupados
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is not None:
            ribbon.refresh_enabled_state(corpus_loaded=bool(enabled and self.corpus))

    def _style_header_button(self, button: ctk.CTkButton) -> None:
        """Aplica estilo padrao aos botoes da barra superior."""
        style_button(button, variant="ghost", size="sm")
        button.configure(
            height=26,
            corner_radius=0,
            border_width=0,
            font=FONTS["small"],
        )

    def _style_toolbar_button(self, button: ctk.CTkButton) -> None:
        """Aplica estilo padrao aos botoes da toolbar."""
        style_button(button, variant="secondary", size="sm")
        button.configure(
            height=SIZES["button_height"],
            corner_radius=0,
            font=FONTS["small"],
        )

    def _style_popup_menu(self, menu: ctk.CTkToplevel, frame: ctk.CTkFrame) -> None:
        """Aplica estilo padrao aos menus suspensos."""
        menu.configure(fg_color=get_themed_color("surface"))
        frame.configure(
            fg_color=get_themed_color("surface"),
            corner_radius=0,
            border_width=1,
            border_color=get_themed_color("border"),
        )

    def _create_popup_button(
        self,
        frame: ctk.CTkFrame,
        *,
        text: str,
        width: int,
        command,
        state: str = "normal",
    ) -> ctk.CTkButton:
        """Cria item visual de menu suspenso com estilo consistente."""
        button = ctk.CTkButton(
            frame,
            text=text,
            width=width,
            height=32,
            anchor="w",
            state=state,
            command=command,
            fg_color=get_themed_color("surface"),
            hover_color=get_themed_color("menu_hover"),
            text_color=get_themed_color("text"),
            border_width=0,
            corner_radius=0,
            font=FONTS["body"],
        )
        style_button(button, variant="ghost", size="md")
        button.configure(anchor="w", width=width, state=state, command=command)
        button.pack(fill="x", padx=2, pady=1)
        return button

    # === Acoes de Menu ===

    def _show_file_menu(self):
        """Mostra menu de arquivo."""
        if hasattr(self, "_file_menu_native"):
            try:
                self._refresh_native_file_menu()
                self._file_menu_native.tk_popup(
                    self.winfo_rootx() + 8,
                    self.winfo_rooty() + 30,
                )
            finally:
                self._file_menu_native.grab_release()
            return

        menu = ctk.CTkToplevel(self)
        menu.title("")
        menu.geometry("200x170")
        menu.overrideredirect(True)
        menu.transient(self)
        
        # Posicionar abaixo do botao
        x = self.btn_file.winfo_rootx()
        y = self.btn_file.winfo_rooty() + self.btn_file.winfo_height()
        menu.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(menu)
        self._style_popup_menu(menu, frame)
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        self._create_popup_button(
            frame,
            text="Importar...",
            width=170,
            command=lambda: [menu.destroy(), self._import_file()],
        )

        save_state = "normal" if self.corpus else "disabled"

        self._create_popup_button(
            frame,
            text="Salvar Projeto",
            width=170,
            state=save_state,
            command=lambda: [menu.destroy(), self._save_project()],
        )

        self._create_popup_button(
            frame,
            text="Abrir Projeto",
            width=170,
            command=lambda: [menu.destroy(), self._open_project()],
        )

        self._create_popup_button(
            frame,
            text="Sair",
            width=170,
            command=lambda: [menu.destroy(), self._on_close()],
        )
        
        menu.focus_set()
        menu.bind("<FocusOut>", lambda e: menu.destroy())

    def _show_analysis_menu(self):
        """Mostra menu de analise."""
        if hasattr(self, "_analysis_menu_native"):
            try:
                self._refresh_native_analysis_menu()
                self._analysis_menu_native.tk_popup(
                    self.winfo_rootx() + 80,
                    self.winfo_rooty() + 30,
                )
            finally:
                self._analysis_menu_native.grab_release()
            return

        menu = ctk.CTkToplevel(self)
        menu.title("")
        menu.geometry("220x650")
        menu.overrideredirect(True)
        menu.transient(self)
        
        x = self.btn_analysis_menu.winfo_rootx()
        y = self.btn_analysis_menu.winfo_rooty() + self.btn_analysis_menu.winfo_height()
        menu.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(menu)
        self._style_popup_menu(menu, frame)
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        state = "normal" if self.corpus else "disabled"

        self._create_popup_button(
            frame,
            text="Bigramas (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_bigram_network_extra()],
        )

        self._create_popup_button(
            frame,
            text="Trigramas (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_trigram_network_extra()],
        )

        self._create_popup_button(
            frame,
            text="CCA (Textometrica)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_cca_analysis()],
        )

        self._create_popup_button(
            frame,
            text="CHD (Reinert)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_chd()],
        )

        self._create_popup_button(
            frame,
            text="Concordância (KWIC)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_concordance()],
        )

        self._create_popup_button(
            frame,
            text="Dist. Labbé",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_labbe()],
        )

        self._create_popup_button(
            frame,
            text="Especificidades",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_specificities()],
        )

        self._create_popup_button(
            frame,
            text="Estatísticas",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_statistics()],
        )

        self._create_popup_button(
            frame,
            text="Keyness (Comparação)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_keyness()],
        )

        self._create_popup_button(
            frame,
            text="Nuvem de Palavras",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_wordcloud()],
        )

        self._create_popup_button(
            frame,
            text="Pacote Voyant (Novo)",
            width=170,
            state=(state if self._voyant_suite_enabled else "disabled"),
            command=lambda: [menu.destroy(), self._run_voyant_suite()],
        )

        self._create_popup_button(
            frame,
            text="Prototípica",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_prototypical()],
        )

        self._create_popup_button(
            frame,
            text="Rede Textual (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_network_text_analysis()],
        )

        self._create_popup_button(
            frame,
            text="Rolling Window (Lexos)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_rolling_window()],
        )

        self._create_popup_button(
            frame,
            text="Sentimentos (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_sentiment_extra()],
        )

        self._create_popup_button(
            frame,
            text="Similitude",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_similarity()],
        )

        self._create_popup_button(
            frame,
            text="Word Tree (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_word_tree_extra()],
        )

        self._create_popup_button(
            frame,
            text="Wordfish (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_wordfish_extra()],
        )

        self._create_popup_button(
            frame,
            text="X-Ray (Extra)",
            width=170,
            state=state,
            command=lambda: [menu.destroy(), self._run_xray_extra()],
        )


        self._create_popup_button(
            frame,
            text="↺ Reabrir Último",
            width=170,
            command=lambda: [menu.destroy(), self._reload_last_history_result()],
        )
        
        menu.focus_set()
        menu.bind("<FocusOut>", lambda e: menu.destroy())

    def _show_matrix_menu(self):
        """Mostra menu de analises sobre matriz tabular (CSV/XLSX)."""
        if hasattr(self, "_matrix_menu_native"):
            try:
                self._refresh_native_matrix_menu()
                self._matrix_menu_native.tk_popup(
                    self.winfo_rootx() + 160,
                    self.winfo_rooty() + 30,
                )
            finally:
                self._matrix_menu_native.grab_release()
            return

        menu = ctk.CTkToplevel(self)
        menu.title("")
        menu.geometry("210x280")
        menu.overrideredirect(True)
        menu.transient(self)

        x = self.btn_matrix_menu.winfo_rootx()
        y = self.btn_matrix_menu.winfo_rooty() + self.btn_matrix_menu.winfo_height()
        menu.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(menu)
        self._style_popup_menu(menu, frame)
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        has_tableau = self.tableau is not None
        analysis_state = "normal" if has_tableau else "disabled"

        self._create_popup_button(
            frame,
            text="Abrir Matriz...",
            width=190,
            command=lambda: [menu.destroy(), self._open_matrix_file()],
        )

        self._create_popup_button(
            frame,
            text="Frequências",
            width=190,
            state=analysis_state,
            command=lambda: [menu.destroy(), self._run_matrix_frequency()],
        )

        self._create_popup_button(
            frame,
            text="Qui-Quadrado",
            width=190,
            state=analysis_state,
            command=lambda: [menu.destroy(), self._run_matrix_chi2()],
        )

        self._create_popup_button(
            frame,
            text="AFC (Matriz)",
            width=190,
            state=analysis_state,
            command=lambda: [menu.destroy(), self._run_matrix_afc()],
        )

        self._create_popup_button(
            frame,
            text="CHD (Matriz)",
            width=190,
            state=analysis_state,
            command=lambda: [menu.destroy(), self._run_matrix_chd()],
        )

        self._create_popup_button(
            frame,
            text="Similitude (Matriz)",
            width=190,
            state=analysis_state,
            command=lambda: [menu.destroy(), self._run_matrix_similarity()],
        )

        menu.focus_set()
        menu.bind("<FocusOut>", lambda e: menu.destroy())

    def _show_settings(self):
        """Mostra configuracoes."""
        self._switch_shell_section("ajustes")
        from .dialogs.settings_dialog import SettingsDialog  # lazy import
        # Sem callback em tempo real - tema é aplicado apenas ao salvar no dialogo
        dialog = SettingsDialog(self, self.config)
        result = dialog.get_result()
        
        # Após fechar, atualizar menus nativos se necessario
        self._style_all_native_menus()
        self._refresh_workspace_header()
        self._refresh_context_panel()
        self._refresh_dashboard_summary()
        
        # Retornar resultado para caller se necessario
        return result

    def _create_r_executor(self):
        """Cria executor R usando configuracao salva quando disponivel."""
        from ..core.r_executor import RExecutor

        configured_r_path = ""
        cran_mirror = "https://cloud.r-project.org"
        config_store = getattr(self, "config", None)
        if config_store is not None and hasattr(config_store, "get"):
            configured_r_path = str(config_store.get("r_path", "") or "").strip()
            cran_mirror = str(
                config_store.get("cran_mirror", "https://cloud.r-project.org")
                or "https://cloud.r-project.org"
            )

        if configured_r_path:
            return RExecutor(r_path=configured_r_path, cran_mirror=cran_mirror)
        return RExecutor(cran_mirror=cran_mirror)

    def _build_analysis_runner(self, runner_cls, *args):
        """
        Instancia classe de analise injetando RExecutor quando suportado.

        Mantem compatibilidade com stubs/mocks que nao recebem r_executor.
        """
        import inspect

        try:
            signature = inspect.signature(runner_cls.__init__)
            if "r_executor" in signature.parameters:
                return runner_cls(*args, r_executor=self._create_r_executor())
        except (TypeError, ValueError):
            pass
        return runner_cls(*args)

    def _open_help_page(self, page_name: str):
        """Abre página de documentação HTML no navegador padrão."""
        try:
            # Determina o diretório base do projeto
            import sys
            if getattr(sys, 'frozen', False):
                # Executando como executável PyInstaller
                base_dir = Path(sys.executable).parent
            else:
                # Executando como script Python
                base_dir = Path(__file__).resolve().parent.parent.parent

            html_file = None
            candidates = [
                base_dir / "docs" / "help" / f"{page_name}.html",
                base_dir / "_internal" / "docs" / "help" / f"{page_name}.html",
            ]
            for candidate in candidates:
                if candidate.exists():
                    html_file = candidate
                    break

            if html_file is not None and html_file.exists():
                webbrowser.open(html_file.as_uri())
            else:
                messagebox.showwarning(
                    "Documentação não encontrada",
                    (
                        "Arquivo de ajuda não encontrado.\n\n"
                        f"Verificado em:\n{candidates[0]}\n{candidates[1]}\n\n"
                        "Verifique se a pasta docs/help existe."
                    ),
                )
        except Exception as e:
            log.error("Erro ao abrir documentação: %s", e)
            messagebox.showerror(
                "Erro",
                f"Não foi possível abrir a documentação:\n{e}"
            )

    def _schedule_guided_tour_startup(self) -> None:
        """Agenda início automático do tutorial de forma idempotente."""
        if self._guided_tour_start_job:
            try:
                self.after_cancel(self._guided_tour_start_job)
            except Exception:
                pass
            self._guided_tour_start_job = None
        self._guided_tour_start_job = self.after(600, self._maybe_start_guided_tour_after_startup)

    def _should_auto_start_guided_tour(self) -> bool:
        """Decide autoabertura usando versionamento do tutorial atual."""
        try:
            if not bool(self.config.get("show_guided_tour_on_startup", True)):
                return False
            seen_version = str(self.config.get("guided_tour_version_seen", "") or "").strip()
            return seen_version != GUIDED_TOUR_VERSION
        except Exception:
            return False

    def _maybe_start_guided_tour_after_startup(self) -> None:
        """Abre tutorial automaticamente quando a versão atual ainda não foi vista."""
        self._guided_tour_start_job = None
        if not self._should_auto_start_guided_tour():
            self._startup_onboarding_finished = True
            return
        self._start_guided_tour(auto=True)

    def _start_guided_tour(self, auto: bool = False) -> None:
        """Inicia tutorial guiado com spotlight."""
        try:
            if not auto and self._guided_tour_start_job:
                try:
                    self.after_cancel(self._guided_tour_start_job)
                except Exception:
                    pass
                self._guided_tour_start_job = None
            if self._guided_tour and self._guided_tour.is_active:
                try:
                    self.lift()
                    self.focus_force()
                except Exception:
                    pass
                try:
                    self._guided_tour.bring_to_front(reset_to_first=True)
                except Exception:
                    pass
                return

            steps = self._build_guided_tour_steps()
            if not steps:
                from tkinter import messagebox
                messagebox.showerror("Erro de Tutorial", "Não foi possível carregar os passos do tutorial (vazio).")
                return

            self._guided_tour = GuidedTour(
                self,
                steps,
                on_close=lambda reason, dont_show_again: self._on_guided_tour_closed(
                    reason,
                    dont_show_again,
                    auto=auto,
                ),
                show_dont_show_option=True,
            )
            self._guided_tour.start()
        except Exception as e:
            import traceback
            from tkinter import messagebox
            err_msg = traceback.format_exc()
            messagebox.showerror("Erro ao abrir Tutorial", f"Uma falha crítica impediu o tutorial de abrir:\n{str(e)}\n\n{err_msg}")


    def _on_guided_tour_closed(self, _reason: str, dont_show_again: bool, _auto: bool) -> None:
        self._guided_tour = None
        self._startup_onboarding_finished = True
        try:
            should_persist_seen = bool(_auto or dont_show_again or _reason in {"completed", "skipped"})
            if should_persist_seen:
                self.config.set("guided_tour_version_seen", GUIDED_TOUR_VERSION)
            if dont_show_again:
                self.config.set("show_guided_tour_on_startup", False)
            self.config.save()
        except Exception as exc:
            log.warning("Nao foi possivel persistir estado do tutorial guiado: %s", exc)

    def _tour_set_shell_section(self, key: str) -> None:
        """Posiciona a shell em um estado estável para o tutorial."""
        valid_keys = {item["key"] for item in getattr(self, "_shell_sections", [])}
        target = key if key in valid_keys else self._default_shell_section()
        self._active_shell_section = target
        self._refresh_shell_nav()
        self._refresh_context_panel()
        self._refresh_workspace_header()
        self._refresh_dashboard_summary()
        self._refresh_quick_actions()
        if target == "dashboard":
            self._show_dashboard_workspace()
        else:
            self._show_results_workspace()
        self.update_idletasks()

    def _tour_prepare_ribbon_group(self, group_name: str) -> None:
        self._tour_set_shell_section("analises")
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is not None:
            try:
                ribbon.hide_help_panel()
            except Exception:
                pass
            ribbon.set_group_filter(group_name)
        self.update_idletasks()

    def _tour_prepare_help_panel(self) -> None:
        self._tour_set_shell_section("analises")
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is not None:
            try:
                ribbon.show_help_panel()
            except Exception:
                pass
        self.update_idletasks()

    def _tour_rect_for_ribbon_primary(self, key: str) -> Optional[Tuple[int, int, int, int]]:
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is None or not hasattr(ribbon, "get_primary_button"):
            return None
        return self._tour_rect_for_widget(ribbon.get_primary_button(key))

    def _tour_rect_for_ribbon_groups(self) -> Optional[Tuple[int, int, int, int]]:
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is None or not hasattr(ribbon, "get_group_button"):
            return None
        widgets = [ribbon.get_group_button(group_name) for group_name in ribbon.groups()]
        return self._tour_rect_for_widgets(widgets, padding=8)

    def _tour_rect_for_ribbon_group_actions(self, keys: List[str]) -> Optional[Tuple[int, int, int, int]]:
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is None or not hasattr(ribbon, "get_active_group_button"):
            return None
        widgets = [ribbon.get_active_group_button(key) for key in keys]
        return self._tour_rect_for_widgets(widgets, padding=8)

    def _tour_rect_for_help_buttons(self, keys: List[str]) -> Optional[Tuple[int, int, int, int]]:
        ribbon = getattr(self, "analysis_ribbon_view", None)
        if ribbon is None or not hasattr(ribbon, "get_help_button"):
            return None
        widgets = [ribbon.get_help_button(key) for key in keys]
        return self._tour_rect_for_widgets(widgets, padding=8)

    def _tour_rect_for_analysis_tab_header(self) -> Optional[Tuple[int, int, int, int]]:
        viewer = getattr(self, "results_viewer", None)
        getter = getattr(viewer, "get_analysis_tab_header_rect", None)
        if not callable(getter):
            return None
        return self._tour_rect_from_screen_rect(getter(), padding=8)

    def _tour_rect_for_widget(
        self,
        widget: Optional[tk.Misc],
        padding: int = 8,
    ) -> Optional[Tuple[int, int, int, int]]:
        if widget is None:
            return None
        try:
            if not widget.winfo_exists() or not widget.winfo_ismapped():
                return None
            self.update_idletasks()
            x1 = int(widget.winfo_rootx() - self.winfo_rootx()) - padding
            y1 = int(widget.winfo_rooty() - self.winfo_rooty()) - padding
            x2 = x1 + int(widget.winfo_width()) + (padding * 2)
            y2 = y1 + int(widget.winfo_height()) + (padding * 2)
            return x1, y1, x2, y2
        except Exception:
            return None

    def _tour_rect_for_widgets(
        self,
        widgets: List[Optional[tk.Misc]],
        padding: int = 8,
    ) -> Optional[Tuple[int, int, int, int]]:
        rects: List[Tuple[int, int, int, int]] = []
        for widget in widgets:
            rect = self._tour_rect_for_widget(widget, padding=0)
            if rect is not None:
                rects.append(rect)
        if not rects:
            return None

        x1 = min(rect[0] for rect in rects) - padding
        y1 = min(rect[1] for rect in rects) - padding
        x2 = max(rect[2] for rect in rects) + padding
        y2 = max(rect[3] for rect in rects) + padding
        return x1, y1, x2, y2

    def _tour_rect_from_screen_rect(
        self,
        screen_rect: Optional[Tuple[int, int, int, int]],
        padding: int = 8,
    ) -> Optional[Tuple[int, int, int, int]]:
        if screen_rect is None:
            return None
        try:
            self.update_idletasks()
            x1, y1, x2, y2 = screen_rect
            local_x1 = int(x1 - self.winfo_rootx()) - padding
            local_y1 = int(y1 - self.winfo_rooty()) - padding
            local_x2 = int(x2 - self.winfo_rootx()) + padding
            local_y2 = int(y2 - self.winfo_rooty()) + padding
            return local_x1, local_y1, local_x2, local_y2
        except Exception:
            return None

    def _tour_rect_for_results_tab(self, tab_name: str) -> Optional[Tuple[int, int, int, int]]:
        viewer = getattr(self, "results_viewer", None)
        if viewer is None:
            return None
        getter = getattr(viewer, "get_content_tab_button_rect", None)
        if not callable(getter):
            return None
        return self._tour_rect_from_screen_rect(getter(tab_name), padding=8)

    def _tour_rect_for_menu_strip(self) -> Optional[Tuple[int, int, int, int]]:
        try:
            self.update_idletasks()
            width = int(self.winfo_width())
            return (8, 4, max(100, width - 8), 40)
        except Exception:
            return None

    def _build_guided_tour_steps(self) -> List[TourStep]:
        return [
            TourStep(
                title="Bem-vindo",
                message=(
                    f"O {DISPLAY_APP_NAME} é um software para importar corpus, preparar textos e executar análises textuais "
                    "computacionais em um fluxo único. Este tutorial mostra onde ficam as ações principais, os grupos "
                    "de análises e a área de resultados."
                ),
                target_getter=lambda: self._tour_rect_for_widget(getattr(self, "workspace_quick_actions_bar", None)),
                before_enter=lambda: self._tour_set_shell_section("dashboard"),
                preferred_placement="bottom",
                fallback_rect=(40, 56, 1180, 190),
            ),
            TourStep(
                title="Importar",
                message=(
                    "Comece por aqui para carregar seu corpus de pesquisa e habilitar as análises."
                ),
                target_getter=lambda: self._tour_rect_for_ribbon_primary("import"),
                before_enter=lambda: self._tour_set_shell_section("dashboard"),
                preferred_placement="bottom",
                fallback_rect=(24, 56, 170, 110),
            ),
            TourStep(
                title="Normalizar",
                message=(
                    "Use Normalizar quando o corpus tiver variações ortográficas ou formas muito dispersas. "
                    "Exemplos de ruído: analise/análise/análises, Covid/COVID-19/coronavírus, ou nomes escritos de modos diferentes. "
                    "A normalização ajuda a juntar essas variações em uma forma única, sem unir termos de sentidos diferentes."
                ),
                target_getter=lambda: self._tour_rect_for_ribbon_primary("normalize"),
                before_enter=lambda: self._tour_set_shell_section("dashboard"),
                preferred_placement="bottom",
                fallback_rect=(170, 56, 340, 110),
            ),
            TourStep(
                title="Grupos de análises",
                message=(
                    "As análises foram organizadas por conjuntos. Você alterna entre grupos na faixa superior e os botões do grupo ativo aparecem logo abaixo."
                ),
                target_getter=self._tour_rect_for_ribbon_groups,
                before_enter=lambda: self._tour_prepare_ribbon_group("Essenciais"),
                preferred_placement="bottom",
                fallback_rect=(340, 56, 980, 110),
            ),
            TourStep(
                title="Essenciais",
                message=(
                    "Aqui ficam Estatísticas, CHD, Similitude, Nuvem e Concordância. É o núcleo do fluxo analítico da aplicação."
                ),
                target_getter=lambda: self._tour_rect_for_ribbon_group_actions(
                    ["statistics", "chd", "similarity", "wordcloud", "concordance"]
                ),
                before_enter=lambda: self._tour_prepare_ribbon_group("Essenciais"),
                preferred_placement="bottom",
                fallback_rect=(24, 118, 980, 180),
            ),
            TourStep(
                title="Exploratórios",
                message=(
                    "Exploratórios reúne leituras complementares como Voyant Suite, Emoções, Rede Textual e CCA."
                ),
                target_getter=lambda: self._tour_rect_for_ribbon_group_actions(
                    ["voyant_suite", "emotions", "network_text", "cca"]
                ),
                before_enter=lambda: self._tour_prepare_ribbon_group("Exploratórios"),
                preferred_placement="bottom",
                fallback_rect=(24, 118, 980, 180),
            ),
            TourStep(
                title="Semânticas",
                message=(
                    "Semânticas concentra YAKE, LDA, Heatmap Associativo, Mapa Temático e CHD Temático para aprofundar tópicos e relações lexicais."
                ),
                target_getter=lambda: self._tour_rect_for_ribbon_group_actions(
                    ["yake", "lda", "associative_heatmap", "thematic_map", "thematic_chd"]
                ),
                before_enter=lambda: self._tour_prepare_ribbon_group("Semânticas"),
                preferred_placement="bottom",
                fallback_rect=(24, 118, 980, 180),
            ),
            TourStep(
                title="Extras",
                message=(
                    "Extras reúne ferramentas complementares para comparação, contexto e exploração lexical mais fina."
                ),
                target_getter=lambda: self._tour_rect_for_ribbon_group_actions(
                    ["bigrams_extra", "trigrams_extra", "word_tree_extra", "wordfish_extra", "xray_extra", "sentiment_extra", "keyness"]
                ),
                before_enter=lambda: self._tour_prepare_ribbon_group("Extras"),
                preferred_placement="bottom",
                fallback_rect=(24, 118, 1100, 180),
            ),
            TourStep(
                title="Ajuda e documentação",
                message=(
                    "O botão Ajuda abre a faixa de documentação. Nela ficam os HTMLs e o atalho para relançar este tutorial."
                ),
                target_getter=lambda: self._tour_rect_for_help_buttons(
                    ["geral", "analises", "matriz", "limpeza", "faq", "glossario", "sobre", "tutorial"]
                ),
                before_enter=self._tour_prepare_help_panel,
                preferred_placement="bottom",
                fallback_rect=(24, 118, 1180, 180),
            ),
            TourStep(
                title="Área de trabalho",
                message=(
                    "Na interface atual, o trabalho acontece na área central. Dashboard e Resultados compartilham esse espaço."
                ),
                target_getter=lambda: self._tour_rect_for_widget(getattr(self, "workspace_body", None)),
                before_enter=lambda: self._tour_set_shell_section("dashboard"),
                preferred_placement="right",
                fallback_rect=(24, 190, 1280, 760),
            ),
            TourStep(
                title="Área central de resultados",
                message=(
                    "Quando uma análise roda, os gráficos, tabelas e relatórios passam a viver aqui sem apagar o resultado anterior automaticamente."
                ),
                target_getter=lambda: self._tour_rect_for_widget(getattr(self, "results_viewer", None)),
                before_enter=lambda: self._tour_set_shell_section("resultados"),
                preferred_placement="right",
                fallback_rect=(24, 190, 1280, 760),
            ),
            TourStep(
                title="Abas de resultados",
                message=(
                    "As abas no topo do visualizador permitem comparar execuções e voltar rapidamente a resultados já abertos."
                ),
                target_getter=self._tour_rect_for_analysis_tab_header,
                before_enter=lambda: self._tour_set_shell_section("resultados"),
                preferred_placement="bottom",
                fallback_rect=(24, 118, 1180, 170),
            ),
            TourStep(
                title="Encerramento",
                message=(
                    "Fluxo sugerido: importar, normalizar se necessário, escolher o grupo de análises, executar e comparar os resultados pelas abas abertas. "
                    "Se precisar, reabra a documentação pela faixa de ajuda."
                ),
                target_getter=lambda: self._tour_rect_for_widget(getattr(self, "workspace_quick_actions_bar", None)),
                before_enter=lambda: self._tour_prepare_ribbon_group("Essenciais"),
                preferred_placement="bottom",
                fallback_rect=(24, 56, 1180, 190),
            ),
        ]

    def _build_about_text(self) -> str:
        return (
            "<labiia_lex> 1.0.9 consolida a importação rápida e a preparação inteligente do corpus, com expressões compostas auditáveis, entidades nomeadas leves e novos apoios interpretativos para LDA e mapas temáticos.\n\n"
            "Este software foi desenvolvido pelo professor Rafael Cardoso Sampaio, professor do departamento de Ciência Política da Universidade Federal de Pernambuco, e coordenador do <labiia_lab> (Laboratório Interdisciplinar de Inteligência Artificial para Métodos, Democracia e Sociedade).\n\n"
            "O software foi todo desenvolvido por agentes de IA e pode conter erros. Os agentes utilizados foram ChatGPT Codex (v. 5.2, 5.3, 5.4, 5.5), Claude Code Opus (v. 4.5, 4.6, 4.7, 4.8), Claude Sonnet 4.6, Antigravity (Gemini 3.1 Pro) e Kimi (2.5 e 2.6). Esse software tenta ser uma reunião de diversos softwares open source de análises textuais automatizadas.\n\n"
            "1) Boa parte dos testes e da validação comparativa foram construídos sobre referências abertas de análise textual estatística, especialmente em fluxos clássicos de segmentação, classificação e similitude.\n\n"
            "2) Num segundo momento, foram incluídas as excelentes ferramentas do Voyan Tools, outra referência mundial de ferramenta aberta, gratuita. A plataforma foi criada e mantida por Stéfan Sinclair e Geoffrey Rockwell e pode ser acessada em: https://voyant-tools.org/. Ver também https://geoffreyrockwell.com/.\n\n"
            "3) Depois, buscamos incorporar algumas soluções feitas pelo grupo de pesquisa Lexomics, que criou e mantém a plataforma Lexos com apoio do Wheaton College. A ferramenta está disponível em: http://lexos.wheatoncollege.edu/. Ver também https://wheatoncollege.edu/academics/special-projects-initiatives/lexomics/.\n\n"
            "4) Para as visualizações de nuvens de palavras, integramos os pacotes wordcloud e ggwordcloud. O wordcloud original foi criado e é mantido por Ian Fellows e pode ser visto em https://cran.r-project.org/web/packages/wordcloud/index.html (veja também http://blog.fellstat.com/?cat=11). O ggwordcloud, que adiciona suporte ao ggplot2, foi desenvolvido por Erwan Le Pennec e Kamil Slowikowski, com repositório em https://github.com/lepennec/ggwordcloud. Ver também https://cran.r-project.org/web/packages/ggwordcloud/vignettes/ggwordcloud.html.\n\n"
            "5) Em seguida, usamos a base de “análise de conceitos conectados” do Textometrica, criado por Simon Lindgren e codificado para PNP por Fredrik Palm. O repositório está disponível em: https://github.com/simonlindgren/textometrica2023 e o app em https://textometrica.streamlit.app/.\n\n"
            "6) Desenvolvemos uma aplicação de sentimentos e emoções com base no pacote NLP Syuzhet. O pacote foi criado e mantido por Matthew Jockers, empregando o léxico de emoções NRC desenvolvido por Saif M. Mohammad e Peter D. Turney. O repositório está disponível em: https://github.com/mjockers/syuzhet. Ver também https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm.\n\n"
            "7) Alguns princípios e testes de limpeza e de LDA foram baseados no trabalho de Anderson Henrique. Disponível em: https://andersonheri.github.io/acR/\n\n"
            "8) Para a limpeza de dados de internet (URLs, e-mails e padrões correlatos), integramos o pacote clean-text, mantido no projeto jfilter/clean-text e distribuído no PyPI. O repositório está disponível em: https://github.com/jfilter/clean-text. Ver também https://pypi.org/project/clean-text/.\n\n"
            "9) Finalmente, usamos a base do OpenRefine para nossa ferramenta de normalização. Ele foi originalmente pensado e escrito por David Huynh. Atualmente, é mantido pela Code for Science and Society (CS&S). O repositório está disponível em https://github.com/OpenRefine/OpenRefine. Ver também https://www.codeforsociety.org/.\n\n"
            "10) Também aproveitamos o Tall para limpeza textual e apoio a alguns testes de análise. Tecnicamente, ele ajudou em etapas de padronização, tokenização, preparação de insumos textuais e checagens comparativas de pipeline, reduzindo atrito na validação de fluxos e no saneamento de corpus. Repositório: https://github.com/massimoaria/tall\n\n"
            "Este software contou com os códigos e colaboração direta de Anderson Henrique (USP), Dalson Figueiredo (UFPE), Ian Batista (Carter Center), Leonardo Nascimento (LabUFBA), Nilton Sainz (UFPR), que são os especialistas em análise automatizada de fato. Agradeço imensamente a todos!\n\n"
            "O desenvolvimento também contou com a ajuda de colaboradores do <labiia_lab>.\n\n"
            "Dúvidas, sugestões, problemas e, especialmente, elogios podem ser enviados por email para: cardososampaio@gmail.com. :)\n\n"
            "Este projeto gastou cerca de 200 horas investimento de tempo para ser realizado e seis meses de assinatura dos agentes de IA.\n\n"
            "O objetivo do software não é desincentivar que as pessoas aprendam linguagens de programação como Python e R, mas justamente mostrar que há muitas possibilidades para se aventurar."
        )

    def _insert_clickable_about_text(self, text_box: ctk.CTkTextbox, text: str) -> None:
        text_box.insert("1.0", text)
        native_text = getattr(text_box, "_textbox", text_box)
        link_color = get_themed_color("primary")
        try:
            native_text.tag_configure("about_link", foreground=link_color, underline=True)
            native_text.tag_bind("about_link", "<Enter>", lambda _event: native_text.configure(cursor="hand2"))
            native_text.tag_bind("about_link", "<Leave>", lambda _event: native_text.configure(cursor=""))
        except Exception:
            text_box.configure(state="disabled")
            return

        for index, match in enumerate(LINK_PATTERN.finditer(text)):
            raw_value = match.group(0)
            clean_value = raw_value.rstrip(".,;:)")
            if not clean_value:
                continue
            start = match.start()
            end = match.start() + len(clean_value)
            tag_name = f"about_link_{index}"
            target = clean_value if clean_value.startswith(("http://", "https://")) else f"mailto:{clean_value}"
            try:
                native_text.tag_add("about_link", f"1.0+{start}c", f"1.0+{end}c")
                native_text.tag_add(tag_name, f"1.0+{start}c", f"1.0+{end}c")
                native_text.tag_bind(tag_name, "<Button-1>", lambda _event, url=target: webbrowser.open(url, new=2))
            except Exception:
                continue
        text_box.configure(state="disabled")

    def _show_about(self):
        """Exibe janela Sobre."""
        about_window = ctk.CTkToplevel(self)
        about_window.title(f"Sobre o {DISPLAY_APP_NAME}")
        about_window.geometry("550x600")
        about_window.resizable(False, False)
        
        # Centralizar na tela
        about_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (550 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (600 // 2)
        about_window.geometry(f"+{x}+{y}")
        about_window.grab_set()

        frame = ctk.CTkFrame(about_window, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        ctk.CTkLabel(
            frame, 
            text=DISPLAY_APP_NAME,
            font=("Segoe UI", 24, "bold"),
            text_color=get_themed_color("primary")
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            frame, 
            text=f"Versão {APP_VERSION}", 
            font=("Segoe UI", 12)
        ).pack(pady=(0, 15))
        
        # Content Area - Usando Textbox para ser copiavel (read-only)
        # scroll_frame removido pois Textbox ja tem scroll
        # scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        # scroll_frame.pack(fill="both", expand=True, pady=(0, 15))

        # Usar CTkTextbox para permitir copia (read-only)
        text_box = ctk.CTkTextbox(
            frame,
            font=("Segoe UI", 13),
            text_color=get_themed_color("text"),
            wrap="word",
            fg_color="transparent",
            activate_scrollbars=True
        )
        text_box.pack(fill="both", expand=True, pady=(0, 10))
        self._insert_clickable_about_text(text_box, self._build_about_text())

        # Footer Button
        ctk.CTkButton(
            frame,
            text="OK",
            width=100,
            command=about_window.destroy
        ).pack(side="bottom")

    def _show_help(self):
        """Mostra ajuda."""
        help_dialog = ctk.CTkToplevel(self)
        help_dialog.title(f"Ajuda - {DISPLAY_APP_NAME}")
        help_dialog.geometry("500x400")
        help_dialog.configure(fg_color=COLORS["background"])
        help_dialog.transient(self)
        help_dialog.grab_set()
        
        frame = ctk.CTkFrame(
            help_dialog,
            fg_color=COLORS["surface"],
            corner_radius=0,
            border_width=1,
            border_color=COLORS["border"],
        )
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            frame,
            text=DISPLAY_APP_NAME,
            font=FONTS['title']
        ).pack(pady=10)
        
        ctk.CTkLabel(
            frame,
            text=f"Versão {APP_VERSION}",
            font=FONTS['body']
        ).pack()
        
        help_text = """
<labiia_lex> Software de Análise Textual.

Como usar:
1. Clique em "Importar" para carregar um arquivo
2. Selecione o modo de importação mais adequado ao corpus
3. Configure as opções de limpeza
4. Clique nas análises desejadas na barra de ferramentas

Análises disponíveis:
• Estatísticas - Contagens básicas do corpus
• CHD - Classificação Hierárquica Descendente
• Similitude - Grafo de co-ocorrências
• Nuvem - Visualização de frequências
• Especificidades - Associação lexical por metadados
• Concordância - Busca KWIC por palavra/regex
• Pacote Voyant - TermsBerry, Tendências, Contextos, Bubblelines e Co-ocorrências
• Prototípica - Núcleo/periferias de representação
• Dist. Labbé - Distância intertextual entre documentos
• Bigramas (Extra) - Rede de coocorrência por pares de palavras
• Wordfish (Extra) - Escalonamento 1D de documentos
• X-Ray (Extra) - Dispersão de termos ao longo das UCIs
• Sentimentos (Extra) - Polaridade lexical + timeline
• Matriz - Frequências, Qui-quadrado, CHD/AFC/Similitude em CSV/XLSX

Dúvidas? Consulte a documentação.
        """
        
        text = ctk.CTkTextbox(frame, height=250, font=FONTS['body'])
        text.pack(fill="both", expand=True, pady=10)
        text.insert("1.0", help_text)
        text.configure(state="disabled")
        
        ctk.CTkButton(
            frame,
            text="Fechar",
            command=help_dialog.destroy,
            width=100,
            height=SIZES["button_height"],
            corner_radius=0,
            border_width=1,
            border_color=get_themed_color("border"),
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            font=FONTS["small"],
        ).pack(pady=10)

    def _get_initial_analysis_params(self, analysis_type: str) -> Dict[str, Any]:
        """Retorna parametros persistidos para inicializacao de dialogos."""
        config_obj = self.__dict__.get("config")
        if isinstance(config_obj, ConfigManager):
            return dict(config_obj.get_last_analysis_params(analysis_type))
        return {}

    @staticmethod
    def _get_original_analysis_defaults(analysis_type: str) -> Dict[str, Any]:
        """Retorna defaults originais (de fábrica) de um tipo de análise."""
        analysis_key = str(analysis_type or "").strip().lower()
        defaults = ConfigManager.DEFAULT_ANALYSIS_DEFAULTS.get(analysis_key, {})
        if isinstance(defaults, dict):
            return dict(defaults)
        return {}

    def _remember_analysis_params(self, analysis_type: str, params: Dict[str, Any]) -> None:
        """Persiste ultimos parametros usados por tipo de analise."""
        config_obj = self.__dict__.get("config")
        if not isinstance(config_obj, ConfigManager):
            return
        try:
            config_obj.set_last_analysis_params(analysis_type, params)
            config_obj.save()
        except OSError:
            log.exception("Falha ao salvar parametros da analise %s", analysis_type)

    @staticmethod
    def _normalize_display_typegraph(value: Any) -> str:
        """
        Normaliza formato grafico para renderizacao na UI.

        Nota:
            A visualizacao atual usa PIL/CTkImage e nao renderiza SVG nativamente.
            Para evitar telas vazias, o formato efetivo da UI e sempre PNG.
        """
        graph_type = str(value or "png").strip().lower()
        if graph_type != "png":
            log.info("Formato de grafico '%s' solicitado; usando PNG para exibicao.", graph_type)
        return "png"



    def _reload_last_history_result(self) -> None:
        """Reabre o artefato da analise mais recente no ResultsViewer."""
        try:
            entries = self.analysis_history.load_results()
        except HistoryError as exc:
            show_error(self, error=exc)
            return

        if not entries:
            show_error(
                self,
                what="Histórico vazio",
                why="Ainda não há análises registradas para reabrir.",
                how="Execute uma análise e tente novamente.",
            )
            return

        entry = entries[0]
        self._open_history_entry(entry)

    def _save_project(self) -> None:
        """Salva estado atual como arquivo de projeto .lexproj."""
        if not self.corpus:
            show_error(
                self,
                what="Nenhum corpus carregado para salvar.",
                why="O projeto precisa de um corpus ativo para persistir estado.",
                how="Importe ou abra um corpus antes de usar 'Salvar Projeto'.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Salvar Projeto",
            defaultextension=ProjectManager.EXTENSION,
            filetypes=[(f"{DISPLAY_APP_NAME} Project", f"*{ProjectManager.EXTENSION}")],
        )
        if not path:
            return

        try:
            self._set_status("Salvando projeto...", 0.4)
            self.corpus.save_corpus()
            analyses = self._history_entries_to_dicts(self.analysis_history.load_results())
            now = datetime.now(timezone.utc).isoformat()
            project = Project(
                name=Path(path).stem,
                corpus_path=self._last_import_file_path,
                db_path=self._corpus_db_path,
                config=self.config.as_dict(),
                analyses=analyses,
                created_at=now,
                updated_at=now,
                corpus_snapshot=self._build_corpus_snapshot_text(),
                metadata={
                    "project_custom_stopwords": list(self._project_custom_stopwords),
                },
            )
            saved_project = ProjectManager().save(project, Path(path))
            self.current_project_path = saved_project.lexproj_path
            self._set_status(f"Projeto salvo: {saved_project.lexproj_path}", 1.0)
        except (ProjectError, HistoryError) as exc:
            log.exception("Falha ao salvar projeto")
            show_error(self, error=exc)
            self._set_status("Erro ao salvar projeto", 0)
        except Exception as exc:
            log.exception("Falha inesperada ao salvar projeto")
            show_error(
                self,
                what="Falha ao salvar projeto.",
                why=str(exc),
                how="Verifique permissões da pasta de destino e tente novamente.",
            )
            self._set_status("Erro ao salvar projeto", 0)

    def _open_project(self) -> None:
        """Abre um projeto .lexproj e restaura corpus/config/historico."""
        path = filedialog.askopenfilename(
            title="Abrir Projeto",
            filetypes=[(f"{DISPLAY_APP_NAME} Project", f"*{ProjectManager.EXTENSION}")],
        )
        if not path:
            return

        try:
            self._set_status("Abrindo projeto...", 0.3)
            project = ProjectManager().load(Path(path))
            project_metadata = project.metadata if isinstance(project.metadata, dict) else {}
            raw_project_stopwords = project_metadata.get("project_custom_stopwords", [])
            if isinstance(raw_project_stopwords, list):
                self._project_custom_stopwords = [str(item).strip().lower() for item in raw_project_stopwords if str(item).strip()]
            else:
                self._project_custom_stopwords = []

            if project.config:
                self.config.update(project.config)
                try:
                    self.config.save()
                except OSError:
                    log.warning("Nao foi possivel persistir configuracao carregada do projeto")

            self._cleanup_analysis_storage()
            snapshot_text = project.corpus_snapshot or ""
            if snapshot_text.strip():
                uce_size = int(self.config.get("uce_size", 40))
                self.corpus = self._create_corpus_with_temp_db(uce_size=uce_size)
                self._build_corpus_from_text(snapshot_text)
            elif project.db_path and project.db_path.exists():
                self._cleanup_corpus_storage()
                self.corpus = Corpus(lexicon=self._load_lexicon())
                self.corpus.load_corpus(project.db_path)
                self._corpus_db_path = project.db_path
            else:
                raise ProjectError(
                    what="Projeto sem dados de corpus restauráveis.",
                    why="Nenhum snapshot textual ou banco de corpus válido foi encontrado.",
                    how="Salve novamente o projeto de origem para incluir os dados completos.",
                )

            history_path = project.history_path
            artifacts_dir = project.artifacts_dir
            if history_path and artifacts_dir and history_path.exists():
                self.analysis_history = AnalysisHistory(
                    history_path=history_path,
                    artifacts_dir=artifacts_dir,
                )
            else:
                self.analysis_history = AnalysisHistory()

            self.current_project_path = project.lexproj_path
            self._last_import_file_path = project.corpus_path if project.corpus_path else None

            self.corpus_tree.load_corpus(self.corpus)
            self.corpus_tree.load_history(
                self.analysis_history,
                on_select=self._open_history_entry,
                on_action=self._handle_corpus_tree_action,
            )
            self._restore_project_history_tabs()
            self._enable_analysis_buttons(True)
            self._set_status(f"Projeto aberto: {project.name}", 1.0)
        except ProjectError as exc:
            log.exception("Erro ao abrir projeto")
            show_error(self, error=exc)
            self._set_status("Erro ao abrir projeto", 0)
        except Exception as exc:
            log.exception("Falha inesperada ao abrir projeto")
            show_error(
                self,
                what="Falha ao abrir projeto.",
                why=str(exc),
                how="Confirme se o arquivo .lexproj e a pasta associada estão íntegros.",
            )
            self._set_status("Erro ao abrir projeto", 0)

    @staticmethod
    def _history_entries_to_dicts(entries: Any) -> list:
        """Converte entradas de historico em lista serializavel."""
        results = []
        for entry in entries or []:
            params = getattr(entry, "params", {})
            metadata = getattr(entry, "metadata", {})
            results.append(
                {
                    "entry_id": str(getattr(entry, "entry_id", "")),
                    "analysis_type": str(getattr(entry, "analysis_type", "")),
                    "params": params if isinstance(params, dict) else {},
                    "result_path": str(getattr(entry, "result_path", "")),
                    "timestamp": str(getattr(entry, "timestamp", "")),
                    "metadata": metadata if isinstance(metadata, dict) else {},
                }
            )
        return results

    def _restore_project_history_tabs(self) -> None:
        """Reabre os resultados persistidos quando um projeto e carregado."""
        try:
            entries = list(self.analysis_history.load_results())
        except Exception:
            log.exception("Falha ao carregar historico para restaurar abas do projeto.")
            return
        if not entries:
            return

        # O historico e salvo do mais recente para o mais antigo. Abrir do mais
        # antigo para o mais recente preserva a ordem natural das abas e deixa o
        # ultimo resultado ativo no final.
        for entry in reversed(entries):
            try:
                self._open_or_focus_result_entry(entry, source="project_open", activate=True)
            except Exception:
                log.exception(
                    "Falha ao restaurar resultado do projeto: %s",
                    getattr(entry, "entry_id", "?"),
                )
        try:
            self._refresh_results_sidebar_context()
        except Exception:
            log.exception("Falha ao atualizar painel de resultados apos abrir projeto.")

    # === Importacao ===

    def _import_file(self):
        """Abre dialogo de importacao."""
        from .dialogs.import_dialog import ImportDialog  # lazy import
        try:
            guided_tour = getattr(self, "_guided_tour", None)
            if guided_tour and getattr(guided_tour, "is_active", False):
                guided_tour.close("import_requested")

            default_uce_size = int(self.config.get("uce_size", 40))
            dialog = ImportDialog(self, default_uce_size=default_uce_size)
            result = dialog.get_result()

            if result:
                self._load_corpus(result)
        except Exception as exc:
            log.exception("Falha ao abrir dialogo de importacao")
            show_error(
                self,
                what="Falha ao abrir importacao.",
                why=str(exc),
                how="Tente novamente. Se o erro persistir, reinicie o aplicativo.",
            )

    def _open_fuzzy_normalizer(self):
        """Abre o diálogo de normalização de variações ortográficas (FuzzyNormalizer)."""
        from .dialogs.fuzzy_normalizer_dialog import FuzzyNormalizerDialog  # lazy import
        if not self.corpus:
            from tkinter import messagebox
            messagebox.showinfo(
                "Nenhum corpus",
                "Importe um corpus antes de usar o Normalizador de Formas.",
                parent=self,
            )
            return

        # Tenta usar o cache de texto; caso não exista, reconstrói do DB.
        corpus_text = getattr(self, "_last_corpus_text", "") or ""
        if not corpus_text.strip():
            try:
                corpus_text = self._build_corpus_snapshot_text()
            except Exception:
                corpus_text = ""

        if not corpus_text.strip():
            from tkinter import messagebox
            messagebox.showinfo(
                "Corpus vazio",
                "O corpus atual não tem texto para normalizar.",
                parent=self,
            )
            return

        def on_confirm(normalized_text: str) -> None:
            """Recarrega o corpus com o texto normalizado."""
            try:
                self._set_status("Aplicando normalização ao corpus...", 0.5)
                import_result = {
                    "text": normalized_text,
                    "metadata": {
                        "source": "fuzzy_normalizer",
                        "mode": "iramuteq",
                        "uce_size": int(self.config.get("uce_size", 40)),
                        "iramuteq_text": normalized_text,
                    },
                }
                self._load_corpus(import_result)
                self._set_status("Corpus normalizado com sucesso.", 1.0)
            except Exception as exc:
                log.exception("Erro ao recarregar corpus normalizado")
                from tkinter import messagebox
                messagebox.showerror(
                    "Erro",
                    f"Falha ao aplicar normalização:\n{exc}",
                    parent=self,
                )

        FuzzyNormalizerDialog(self, corpus_text=corpus_text, on_confirm=on_confirm)

    def _open_corpus_preparation_dialog(self) -> None:
        """Abre a Fase 2 de preparacao NLP do corpus ja importado."""
        if not self.corpus:
            messagebox.showinfo(
                "Nenhum corpus",
                "Importe um corpus antes de usar Preparar corpus.",
                parent=self,
            )
            return
        from .dialogs.corpus_preparation_dialog import CorpusPreparationDialog
        from .dialogs.entity_selection_dialog import EntitySelectionDialog
        from .dialogs.multiword_selection_dialog import MultiwordSelectionDialog
        from ..importers.light_named_entities import extract_light_named_entities, selected_entities_to_multiword_payload
        from ..importers.multiword_candidates import extract_multiword_candidates

        dialog = CorpusPreparationDialog(
            self,
            initial_options=getattr(self, "_last_import_options", {}) or {},
        )
        options = dialog.get_result()
        if not options:
            return

        selected_bigrams: List[Dict[str, Any]] = []
        selected_entities: List[Dict[str, Any]] = []
        source_text_for_audit = self._corpus_preparation_source_text()
        if bool(options.get("detect_bigrams", False)):
            try:
                self._set_status("Detectando expressões compostas...", 0.25)
                detection_options = {
                    "top_n": max(1, int(options.get("bigram_top_n", 30) or 30)),
                    "min_freq": max(1, int(options.get("bigram_min_freq", 3) or 3)),
                    "ngram_max": min(3, max(2, int(options.get("ngram_max", 3) or 3))),
                    "min_is_norm": max(0.0, float(options.get("min_is_norm", 0.35) or 0.35)),
                }
                cache_key = hashlib.sha256(
                    json.dumps(
                        {
                            "text_sha256": hashlib.sha256(source_text_for_audit.encode("utf-8", errors="replace")).hexdigest(),
                            "options": detection_options,
                            "version": "1.0.9-python-multiword-v2",
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                detection_cache = getattr(self, "_multiword_detection_cache", None)
                if not isinstance(detection_cache, dict):
                    detection_cache = {}
                    setattr(self, "_multiword_detection_cache", detection_cache)
                disk_cache = ImportProcessingCache(PathManager.user_data_dir() / "multiword_detection_cache")
                disk_payload = disk_cache.get(cache_key)
                cache_hit = cache_key in detection_cache or disk_payload is not None
                if cache_key in detection_cache:
                    candidates = list(detection_cache.get(cache_key, []) or [])
                elif disk_payload is not None:
                    candidates = list(disk_payload.get("candidates", []) or [])
                    detection_cache[cache_key] = list(candidates)
                else:
                    candidates = extract_multiword_candidates(
                        source_text_for_audit,
                        top_n=detection_options["top_n"],
                        min_freq=detection_options["min_freq"],
                        ngram_max=detection_options["ngram_max"],
                        min_is_norm=detection_options["min_is_norm"],
                    )
                    detection_cache[cache_key] = list(candidates)
                    disk_cache.put(cache_key, {"candidates": list(candidates)})
                options["_multiword_detection_diagnostics"] = {
                    "method": "python_is_index_bounded",
                    "cache_hit": bool(cache_hit),
                    "top_n": detection_options["top_n"],
                    "min_freq": detection_options["min_freq"],
                    "ngram_max": detection_options["ngram_max"],
                    "min_is_norm": detection_options["min_is_norm"],
                    "candidate_count": len(candidates),
                    "source_chars": len(source_text_for_audit),
                    "bounded": True,
                }
                options["_multiword_candidates"] = candidates
                if candidates:
                    selection = MultiwordSelectionDialog(
                        self,
                        candidates=candidates,
                        min_freq=max(1, int(options.get("bigram_min_freq", 3) or 3)),
                        min_is_norm=max(0.0, float(options.get("min_is_norm", 0.35) or 0.35)),
                    )
                    if selection.was_confirmed():
                        selected_bigrams = list(selection.get_selected_bigrams() or [])
                    else:
                        return
                else:
                    messagebox.showinfo(
                        "Expressões compostas",
                        "Nenhuma expressão composta frequente foi encontrada com os parâmetros atuais.",
                        parent=self,
                    )
                    options["detect_bigrams"] = False
            except Exception as exc:
                log.exception("Falha ao detectar expressões compostas na preparação do corpus")
                show_error(
                    self,
                    what="Falha ao detectar expressões compostas.",
                    why=str(exc),
                    how="Tente reduzir filtros ou aplicar a preparação sem detecção de expressões.",
                )
                self._set_status("Erro ao preparar corpus", 0)
                return

        if bool(options.get("detect_entities", False)):
            try:
                self._set_status("Detectando entidades nomeadas...", 0.30)
                entity_candidates = extract_light_named_entities(
                    source_text_for_audit,
                    top_n=max(1, int(options.get("entity_top_n", 50) or 50)),
                    min_freq=max(1, int(options.get("entity_min_freq", 2) or 2)),
                    max_tokens=min(6, max(1, int(options.get("entity_max_tokens", 6) or 6))),
                )
                options["_entity_candidates"] = entity_candidates
                if entity_candidates:
                    entity_selection = EntitySelectionDialog(self, candidates=entity_candidates)
                    if entity_selection.was_confirmed():
                        selected_entities = list(entity_selection.get_selected_entities() or [])
                    else:
                        return
                else:
                    messagebox.showinfo(
                        "Entidades nomeadas",
                        "Nenhuma entidade nomeada recorrente foi encontrada com os parâmetros atuais.",
                        parent=self,
                    )
                    options["detect_entities"] = False
            except Exception as exc:
                log.exception("Falha ao detectar entidades nomeadas na preparação do corpus")
                show_error(
                    self,
                    what="Falha ao detectar entidades nomeadas.",
                    why=str(exc),
                    how="Tente aumentar o limite de sugestões ou aplicar a preparação sem entidades.",
                )
                self._set_status("Erro ao preparar corpus", 0)
                return

        options = dict(options)
        entity_merge_payload = selected_entities_to_multiword_payload(selected_entities)
        options["selected_bigrams"] = selected_bigrams + entity_merge_payload
        options["_selected_multiwords"] = selected_bigrams
        options["selected_entities"] = selected_entities

        def run() -> None:
            try:
                import_result = self._build_prepared_corpus_import_result(options)
            except Exception as exc:
                log.exception("Falha ao preparar corpus")
                self.after(
                    0,
                    lambda: (
                        show_error(
                            self,
                            what="Falha ao preparar corpus.",
                            why=str(exc),
                            how="Verifique as opções escolhidas e tente novamente.",
                        ),
                        self._set_status("Erro ao preparar corpus", 0),
                    ),
                )
                return
            self.after(0, lambda: self._load_corpus(import_result))

        self._set_status("Preparando corpus...", 0.35)
        threading.Thread(target=run, daemon=True).start()

    def _apply_corpus_preparation(self, options: Dict[str, Any]) -> None:
        """Aplica preparação de corpus de forma síncrona; usado por testes e pelo worker."""
        self._load_corpus(self._build_prepared_corpus_import_result(options))

    def _build_prepared_corpus_import_result(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Executa/cacheia a Fase 2 e retorna payload compatível com _load_corpus."""
        pipeline_result = self._run_corpus_preparation_pipeline(
            options=options,
            detect_bigrams=False,
            selected_bigrams=list(options.get("selected_bigrams", []) or []),
        )
        metadata = dict(getattr(self, "_last_import_metadata", {}) or {})
        prepared_text = self._drop_empty_iramuteq_uci_blocks(str(pipeline_result.prepared_text or ""))
        metadata["r_pipeline_prepared_text"] = prepared_text
        metadata["r_pipeline_diagnostics"] = dict(pipeline_result.diagnostics or {})
        metadata["phase2_prepared"] = True
        metadata["phase2_version"] = "1.0.9"
        metadata["phase2_prepared_at"] = datetime.now(timezone.utc).isoformat()
        selected_multiwords = list(options.get("_selected_multiwords", options.get("selected_bigrams", [])) or [])
        candidate_multiwords = list(options.get("_multiword_candidates", []) or [])
        metadata["multiword_candidates_count"] = len(candidate_multiwords)
        metadata["multiword_selected_count"] = len(selected_multiwords)
        metadata["multiword_selected"] = selected_multiwords
        metadata["multiword_detection_method"] = "is_index_tall_inspired"
        if isinstance(options.get("_multiword_detection_diagnostics"), dict):
            metadata["multiword_detection_diagnostics"] = dict(options.get("_multiword_detection_diagnostics") or {})
        selected_entities = list(options.get("selected_entities", []) or [])
        candidate_entities = list(options.get("_entity_candidates", []) or [])
        metadata["entity_candidates_count"] = len(candidate_entities)
        metadata["entity_selected_count"] = len(selected_entities)
        metadata["entity_selected"] = selected_entities
        metadata["entity_detection_method"] = "light_heuristic" if bool(options.get("detect_entities", False)) else ""

        audit_paths = self._write_corpus_preparation_audit_artifacts(
            options=options,
            candidates=candidate_multiwords,
            selected=selected_multiwords,
            entity_candidates=candidate_entities,
            selected_entities=selected_entities,
            diagnostics=dict(pipeline_result.diagnostics or {}),
            pipeline_hash=str(getattr(pipeline_result, "pipeline_hash", "") or ""),
        )
        for key, value in audit_paths.items():
            metadata[key] = str(value)

        merged_options = dict(getattr(self, "_last_import_options", {}) or {})
        merged_options.update({
            "lowercase": bool(options.get("lowercase", False)),
            "remove_numbers": bool(options.get("remove_numbers", False)),
            "remove_accents": bool(options.get("remove_accents", False)),
            "clean_web_data": bool(options.get("clean_web_data", False)),
            "enable_bigram_merge": bool(options.get("selected_bigrams")),
            "selected_bigrams": list(options.get("selected_bigrams", []) or []),
            "detect_bigrams": bool(options.get("detect_bigrams", False)),
            "bigram_top_n": max(1, int(options.get("bigram_top_n", 30) or 30)),
            "bigram_min_freq": max(1, int(options.get("bigram_min_freq", 3) or 3)),
            "ngram_max": min(3, max(2, int(options.get("ngram_max", 3) or 3))),
            "min_is_norm": max(0.0, float(options.get("min_is_norm", 0.35) or 0.35)),
            "detect_entities": bool(options.get("detect_entities", False)),
            "entity_top_n": max(1, int(options.get("entity_top_n", 50) or 50)),
            "entity_min_freq": max(1, int(options.get("entity_min_freq", 2) or 2)),
            "entity_max_tokens": min(6, max(1, int(options.get("entity_max_tokens", 6) or 6))),
            "selected_entities": selected_entities,
        })
        return {
            "text": prepared_text,
            "mode": getattr(self, "_last_import_mode", "traditional") or "traditional",
            "file_path": str(getattr(self, "_last_import_file_path", "") or ""),
            "metadata": metadata,
            "options": merged_options,
        }

    def _corpus_preparation_source_text(self) -> str:
        """Return the source text used by phase-2 preparation."""
        metadata = dict(getattr(self, "_last_import_metadata", {}) or {})
        source_text = metadata.get("r_pipeline_source_text")
        if not isinstance(source_text, str) or not source_text.strip():
            source_text = getattr(self, "_last_corpus_text", "") or self._build_corpus_snapshot_text()
        return str(source_text or "")

    @staticmethod
    def _drop_empty_iramuteq_uci_blocks(text: str) -> str:
        """Remove blocos `****` gerados internamente sem texto associado."""
        raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if "****" not in raw:
            return raw

        blocks: List[tuple[str, List[str]]] = []
        current_marker: Optional[str] = None
        current_body: List[str] = []
        prefix_lines: List[str] = []

        def flush() -> None:
            nonlocal current_marker, current_body
            if current_marker is None:
                return
            body = [line for line in current_body if str(line or "").strip()]
            if body:
                blocks.append((current_marker.strip(), body))
            current_marker = None
            current_body = []

        for line in raw.split("\n"):
            if line.strip().startswith("****"):
                flush()
                current_marker = line
                current_body = []
            elif current_marker is None:
                if line.strip():
                    prefix_lines.append(line)
            else:
                current_body.append(line)
        flush()

        if not blocks:
            return "\n".join(prefix_lines).strip()

        out: List[str] = []
        for marker, body in blocks:
            out.append(marker)
            out.extend(body)
            out.append("")
        return "\n".join(out).strip()

    def _run_corpus_preparation_pipeline(
        self,
        *,
        options: Dict[str, Any],
        detect_bigrams: bool,
        selected_bigrams: List[Dict[str, Any]],
    ):
        """Executa o pipeline R da Fase 2 com cache por fonte/opcoes."""
        metadata = dict(getattr(self, "_last_import_metadata", {}) or {})
        source_text = metadata.get("r_pipeline_source_text")
        if not isinstance(source_text, str) or not source_text.strip():
            source_text = getattr(self, "_last_corpus_text", "") or self._build_corpus_snapshot_text()
        if not isinstance(source_text, str) or not source_text.strip():
            raise RTextPipelineError("Texto fonte do corpus indisponível para preparação.")

        base_options = dict(getattr(self, "_last_import_options", {}) or {})
        extra_stopwords = merge_stopword_layers(
            global_words=get_global_custom_stopwords(self.config),
            project_words=getattr(self, "_project_custom_stopwords", []) or [],
            session_words=base_options.get("session_stopwords", []) or [],
        )
        mode = getattr(self, "_last_import_mode", "traditional") or "traditional"
        pipeline = RTextPipeline()
        cache = ImportProcessingCache()
        phase2_options = {
            "lowercase": bool(options.get("lowercase", False)),
            "remove_numbers": bool(options.get("remove_numbers", False)),
            "remove_accents": bool(options.get("remove_accents", False)),
            "clean_web_data": bool(options.get("clean_web_data", False)),
            "detect_bigrams": bool(detect_bigrams),
            "selected_bigrams": list(selected_bigrams or []),
            "bigram_top_n": max(1, int(options.get("bigram_top_n", 30) or 30)),
            "bigram_min_freq": max(1, int(options.get("bigram_min_freq", 3) or 3)),
            "ngram_max": min(3, max(2, int(options.get("ngram_max", 3) or 3))),
            "min_is_norm": max(0.0, float(options.get("min_is_norm", 0.35) or 0.35)),
            "aggressive_noise_filter": True,
        }
        source_paths = self._current_import_source_paths(metadata)
        cache_key = ""
        pipeline_hash = ""
        if source_paths:
            try:
                pipeline_hash = pipeline.script_hash()
                cache_key = cache.build_key(
                    source_paths=source_paths,
                    mode=mode,
                    options=phase2_options,
                    stopwords=extra_stopwords,
                    pipeline_hash=pipeline_hash,
                )
                cached = cache.get(cache_key)
                if cached is not None:
                    from ..core.r_text_pipeline import RTextPipelineResult

                    cached_result = RTextPipelineResult(
                        prepared_text=str(cached.get("prepared_text", "") or ""),
                        preview_text=str(cached.get("preview_text", "") or ""),
                        bigram_candidates=list(cached.get("bigram_candidates", []) or []),
                        diagnostics=dict(cached.get("diagnostics", {}) or {}),
                        warnings=[str(item) for item in list(cached.get("warnings", []) or [])],
                    )
                    setattr(cached_result, "pipeline_hash", pipeline_hash)
                    return cached_result
            except Exception:
                log.warning("Cache de preparação indisponível; executando pipeline sem cache.", exc_info=True)
                cache_key = ""

        result = pipeline.run(
            text=source_text,
            mode=mode,
            lowercase=phase2_options["lowercase"],
            remove_numbers=phase2_options["remove_numbers"],
            remove_accents=phase2_options["remove_accents"],
            clean_web_data=phase2_options["clean_web_data"],
            detect_bigrams=phase2_options["detect_bigrams"],
            selected_bigrams=phase2_options["selected_bigrams"],
            extra_stopwords=extra_stopwords,
            bigram_top_n=phase2_options["bigram_top_n"],
            bigram_min_freq=phase2_options["bigram_min_freq"],
            ngram_max=phase2_options["ngram_max"],
            min_is_norm=phase2_options["min_is_norm"],
            aggressive_noise_filter=True,
        )
        setattr(result, "pipeline_hash", pipeline_hash)
        if cache_key:
            try:
                cache.put(
                    cache_key,
                    {
                        "prepared_text": result.prepared_text,
                        "preview_text": result.preview_text,
                        "bigram_candidates": result.bigram_candidates,
                        "diagnostics": result.diagnostics,
                        "warnings": result.warnings,
                    },
                )
            except Exception:
                log.warning("Falha ao gravar cache da preparação do corpus.", exc_info=True)
        return result

    def _write_corpus_preparation_audit_artifacts(
        self,
        *,
        options: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        selected: List[Dict[str, Any]],
        diagnostics: Dict[str, Any],
        pipeline_hash: str,
        entity_candidates: Optional[List[Dict[str, Any]]] = None,
        selected_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Path]:
        """Persist audit files for phase-2 multiword decisions."""
        if (
            not bool(options.get("detect_bigrams", False))
            and not candidates
            and not selected
            and not bool(options.get("detect_entities", False))
            and not entity_candidates
            and not selected_entities
        ):
            return {}
        try:
            from ..importers.corpus_preparation_audit import write_corpus_preparation_audit

            metadata = dict(getattr(self, "_last_import_metadata", {}) or {})
            source_paths = self._current_import_source_paths(metadata)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output_dir = PathManager.user_data_dir() / "corpus_preparation_audit" / stamp
            return write_corpus_preparation_audit(
                output_dir,
                source_paths=source_paths,
                options=options,
                candidates=candidates,
                selected=selected,
                diagnostics=diagnostics,
                pipeline_hash=pipeline_hash,
                entity_candidates=entity_candidates or [],
                selected_entities=selected_entities or [],
            )
        except Exception:
            log.warning("Falha ao gravar auditoria da preparação do corpus.", exc_info=True)
            return {}

    def _current_import_source_paths(self, metadata: Optional[Dict[str, Any]] = None) -> List[Path]:
        """Resolve fontes usadas na importação para chave de cache."""
        metadata = metadata if isinstance(metadata, dict) else getattr(self, "_last_import_metadata", {}) or {}
        paths: List[Path] = []
        selected = metadata.get("selected_files")
        if isinstance(selected, list):
            paths.extend(Path(item) for item in selected if str(item).strip())
        source = getattr(self, "_last_import_file_path", None)
        if source:
            paths.append(Path(source))
        unique: List[Path] = []
        seen = set()
        for path in paths:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            key = str(resolved)
            if key in seen or not resolved.exists():
                continue
            seen.add(key)
            unique.append(resolved)
        return unique

    def _load_corpus(self, import_result):
        """Carrega corpus a partir do resultado de importacao."""
        try:
            self._set_status("Carregando corpus...", 0.2)
            self._cleanup_analysis_storage()
            
            # Obter texto processado
            text = import_result.get('text', '')
            self._last_corpus_text = text   # cache para FuzzyNormalizer
            metadata = import_result.get('metadata', {}) or {}
            mode = import_result.get('mode', 'iramuteq')
            options = import_result.get('options', {})
            source_path = import_result.get('file_path')
            self._last_import_file_path = Path(source_path) if source_path else None
            self._last_import_metadata = dict(metadata)
            self._last_import_mode = str(mode or "traditional")
            self._last_import_options = dict(options)
            uce_size = max(20, min(200, int(options.get('uce_size', self.config.get("uce_size", 40)))))
            session_stopwords = [str(item).strip().lower() for item in options.get("session_stopwords", []) if str(item).strip()]
            persist_project_stopwords = bool(options.get("persist_project_stopwords", False))
            persist_global_stopwords = bool(options.get("persist_global_stopwords", False))

            if session_stopwords and persist_project_stopwords:
                self._project_custom_stopwords = sorted(
                    set(self._project_custom_stopwords).union(session_stopwords)
                )
            if session_stopwords and persist_global_stopwords:
                merged_global = sorted(
                    set(get_global_custom_stopwords(self.config)).union(session_stopwords)
                )
                set_global_custom_stopwords(self.config, merged_global)
                try:
                    self.config.save()
                except OSError:
                    log.warning("Nao foi possivel salvar stopwords globais customizadas.")

            effective_extra_stopwords = merge_stopword_layers(
                global_words=get_global_custom_stopwords(self.config),
                project_words=self._project_custom_stopwords,
                session_words=session_stopwords,
            )
            metadata["effective_extra_stopwords"] = list(effective_extra_stopwords)
            used_r_pipeline = False

            source_for_pipeline = metadata.get("r_pipeline_source_text")
            prepared_from_pipeline = metadata.get("r_pipeline_prepared_text")
            if isinstance(prepared_from_pipeline, str) and prepared_from_pipeline.strip():
                text = self._drop_empty_iramuteq_uci_blocks(prepared_from_pipeline)
                if mode == "iramuteq":
                    metadata["iramuteq_text"] = text
                else:
                    metadata["traditional_text_prepared"] = text
                used_r_pipeline = True
            elif isinstance(source_for_pipeline, str) and source_for_pipeline.strip():
                self._set_status("Executando pipeline textual (R)...", 0.35)
                pipeline = RTextPipeline()
                pipeline_result = pipeline.run(
                    text=source_for_pipeline,
                    mode=mode,
                    lowercase=bool(options.get("lowercase", False)),
                    remove_numbers=bool(options.get("remove_numbers", False)),
                    remove_accents=bool(options.get("remove_accents", False)),
                    clean_web_data=bool(options.get("clean_web_data", False)),
                    detect_bigrams=False,
                    selected_bigrams=list(options.get("selected_bigrams", []) or []),
                    extra_stopwords=effective_extra_stopwords,
                    aggressive_noise_filter=True,
                )
                text = self._drop_empty_iramuteq_uci_blocks(pipeline_result.prepared_text)
                metadata["r_pipeline_diagnostics"] = dict(pipeline_result.diagnostics)
                if mode == "iramuteq":
                    metadata["iramuteq_text"] = text
                else:
                    metadata["traditional_text_prepared"] = text
                used_r_pipeline = True

            # No modo tradicional, coleções multi-arquivo precisam manter fronteiras
            # de documento para não colapsar em uma única UCI.
            if (mode != "iramuteq") and (not used_r_pipeline):
                prebuilt_traditional = metadata.get("traditional_text_prepared")
                if isinstance(prebuilt_traditional, str) and prebuilt_traditional.strip():
                    text = prebuilt_traditional
                else:
                    text = self._build_traditional_collection_text(
                        text=text,
                        metadata=metadata,
                    )
                    user_cleanup_requested = any(
                        bool(options.get(flag, False))
                        for flag in ("lowercase", "remove_numbers", "remove_accents", "clean_web_data")
                    )
                    if user_cleanup_requested:
                        from ..importers.corpus_cleaner import CorpusCleaner

                        cleaner = CorpusCleaner(
                            converter_minusculas=options.get("lowercase", False),
                            remover_numeros=options.get("remove_numbers", False),
                            remover_acentos=options.get("remove_accents", False),
                            limpar_dados_internet=options.get("clean_web_data", False),
                            usar_expressoes_padrao=False,
                        )
                        text = cleaner.limpar(text)
                self._last_corpus_text = text
            
            if not text.strip():
                show_error(
                    self,
                    what="Arquivo vazio ou não reconhecido",
                    why="O arquivo selecionado não contém texto válido.",
                    how="Verifique se o arquivo está correto e tente novamente."
                )
                self._set_status("Pronto", 0)
                return
            
            self._set_status("Processando texto...", 0.4)
            
            # Aplicar limpeza se necessario
            if mode == 'iramuteq' and not used_r_pipeline:
                from ..importers.corpus_cleaner import CorpusCleaner
                from ..importers.corpus_validator import CorpusValidator
                from ..importers.iramuteq_adapter import IramuteqAutoAdapter
                from ..importers.bigram_compounds import (
                    apply_selected_bigrams_to_text,
                    selected_bigrams_to_expressions,
                )

                adapter = IramuteqAutoAdapter()
                iramuteq_source = metadata.get('iramuteq_text')
                candidate_source = iramuteq_source if isinstance(iramuteq_source, str) else text
                if isinstance(iramuteq_source, str) and iramuteq_source.strip():
                    log.info("Usando corpus IRaMuTeQ gerado pelo importador tabular")
                if bool(options.get("clean_web_data", False)):
                    from ..importers.internet_cleaner import clean_internet_artifacts

                    candidate_source = clean_internet_artifacts(
                        candidate_source,
                        preserve_command_lines=True,
                    )

                strict_analysis = True
                config_obj = self.__dict__.get("config")
                if isinstance(config_obj, ConfigManager):
                    mode_raw = str(config_obj.get("analysis_mode", "") or "").strip().lower()
                    if mode_raw in {"strict", "legacy"}:
                        strict_analysis = mode_raw == "strict"
                    else:
                        strict_analysis = bool(config_obj.get("strict_iramuteq_clone", True))

                custom_bigrams = []
                if (not strict_analysis) and bool(options.get('enable_bigram_merge', False)):
                    custom_bigrams = selected_bigrams_to_expressions(
                        options.get('selected_bigrams', [])
                    )
                    if custom_bigrams:
                        log.info("Aplicando %s unioes opcionais de bigramas", len(custom_bigrams))

                text = adapter.to_iramuteq(
                    candidate_source,
                    source_file=str(source_path) if source_path else "",
                    source_label=Path(source_path).stem if source_path else "",
                )

                cleaner = None
                user_cleanup_requested = any(
                    bool(options.get(flag, False))
                    for flag in ("lowercase", "remove_numbers", "remove_accents", "clean_web_data")
                )
                if strict_analysis and not user_cleanup_requested:
                    # Strict clone path avoids custom cleaner substitutions that
                    # diverge from IRaMuTeQ lexical behavior (e.g. ad-hoc token rewrites).
                    log.info("Modo strict: usando texto adaptado IRaMuTeQ sem limpeza extra do CorpusCleaner")
                else:
                    cleaner = CorpusCleaner(
                        converter_minusculas=options.get('lowercase', False),
                        remover_numeros=options.get('remove_numbers', False),
                        remover_acentos=options.get('remove_accents', False),
                        limpar_dados_internet=options.get('clean_web_data', False),
                        expressoes_customizadas=custom_bigrams if custom_bigrams else None,
                        usar_expressoes_padrao=(bool(custom_bigrams) and not strict_analysis),
                    )
                    if strict_analysis:
                        log.info("Modo strict com limpezas selecionadas pelo usuario; aplicando CorpusCleaner")
                    else:
                        log.info("Aplicando limpeza IRaMuTeQ no texto importado")
                    text = cleaner.limpar(text)
                    if custom_bigrams:
                        # Segundo passe defensivo: garante união escolhida mesmo em
                        # casos com hífen/pontuação/ponte stopword (ex.: "sistema de wayfinding").
                        text, forced_merges = apply_selected_bigrams_to_text(
                            text,
                            custom_bigrams,
                            allow_stopword_bridge=True,
                        )
                        log.info(
                            "Pos-processamento de unioes opcionais aplicado: %s ocorrencias",
                            forced_merges,
                        )
                text = self._drop_empty_iramuteq_uci_blocks(text)
                report = CorpusValidator().validate(text)
                if report.errors:
                    log.warning(
                        "Validacao IRaMuTeQ com erros apos limpeza (%s). "
                        "Aplicando fallback automatico por adaptacao de texto bruto.",
                        len(report.errors),
                    )
                    fallback_source = import_result.get('text', '')
                    fallback_text = adapter.to_iramuteq(
                        fallback_source,
                        source_file=str(source_path) if source_path else "",
                        source_label=Path(source_path).stem if source_path else "",
                    )
                    if cleaner is None:
                        text = fallback_text
                    else:
                        text = cleaner.limpar(fallback_text)
                        if custom_bigrams:
                            text, forced_merges = apply_selected_bigrams_to_text(
                                text,
                                custom_bigrams,
                                allow_stopword_bridge=True,
                            )
                            log.info(
                                "Pos-processamento de unioes opcionais (fallback) aplicado: %s ocorrencias",
                                forced_merges,
                            )
                    text = self._drop_empty_iramuteq_uci_blocks(text)
                    report = CorpusValidator().validate(text)

                if report.errors:
                    why = "\n".join(
                        f"Linha {issue.line_number}: {issue.what}"
                        for issue in report.errors[:5]
                    )
                    if len(report.errors) > 5:
                        why += f"\n... e mais {len(report.errors) - 5} erro(s)."
                    how = "\n".join(report.suggestions[:4]) if report.suggestions else (
                        "O sistema tentou corrigir automaticamente. "
                        "Revise o preview e prossiga para analisar o corpus."
                    )
                    show_error(
                        self,
                        what="Corpus importado com inconsistências de metadados",
                        why=why,
                        how=how,
                    )
                if report.warnings:
                    warning_text = "\n".join(f"- {warning}" for warning in report.warnings[:10])
                    self.results_viewer.show_text(
                        warning_text,
                        title="Avisos de Validação do Corpus",
                    )
                    log.warning("Validacao do corpus retornou avisos: %s", report.warnings)
                log.info("Corpus validado com sucesso no formato IRaMuTeQ")
            elif mode == "iramuteq" and used_r_pipeline:
                from ..importers.corpus_validator import CorpusValidator

                text = self._drop_empty_iramuteq_uci_blocks(text)
                report = CorpusValidator().validate(text)
                if report.errors:
                    why = "\n".join(
                        f"Linha {issue.line_number}: {issue.what}"
                        for issue in report.errors[:5]
                    )
                    show_error(
                        self,
                        what="Corpus importado com inconsistencias de metadados",
                        why=why,
                        how="Revise o texto fonte e as opcoes de limpeza no importador.",
                    )
                if report.warnings:
                    warning_text = "\n".join(f"- {warning}" for warning in report.warnings[:10])
                    self.results_viewer.show_text(
                        warning_text,
                        title="Avisos de Validacao do Corpus",
                    )
                log.info("Corpus validado apos pipeline R (modo IRaMuTeQ)")
            
            self._set_status("Criando corpus...", 0.6)
            
            # Criar corpus e processar texto
            self.corpus = self._create_corpus_with_temp_db(uce_size=uce_size)
            if isinstance(getattr(self.corpus, "parametres", None), dict):
                self.corpus.parametres["extra_stopwords"] = list(effective_extra_stopwords)
            self._build_corpus_from_text(
                text,
                remove_numbers=bool(options.get("remove_numbers", False)),
            )
            # Atualiza cache com a versão final já adaptada/limpa do corpus.
            self._last_corpus_text = text

            try:
                self.config.set("uce_size", uce_size)
                self.config.save()
            except OSError:
                log.warning("Nao foi possivel persistir uce_size=%s na configuracao", uce_size)
            
            self._set_status("Finalizando...", 0.9)
            
            # Atualizar interface
            if hasattr(self.results_viewer, "reset_analysis_tabs"):
                self.results_viewer.reset_analysis_tabs()
            self.corpus_tree.load_corpus(self.corpus)
            self.corpus_tree.load_history(
                self.analysis_history,
                on_select=self._open_history_entry,
                on_action=self._handle_corpus_tree_action,
            )
            self._enable_analysis_buttons(True)
            
            n_ucis = self.corpus.getucinb() if hasattr(self.corpus, 'getucinb') else 0
            n_formes = len(self.corpus.formes) if hasattr(self.corpus, 'formes') else 0
            
            self._set_status(f"Corpus carregado: {n_ucis} documentos, {n_formes} formas", 1.0)
            
            log.info(f"Corpus carregado: {n_ucis} UCIs, {n_formes} formas")

        except Exception as e:
            log.exception("Erro ao carregar corpus")
            self._cleanup_corpus_storage()
            self._enable_analysis_buttons(False)
            show_error(self, error=e)
            self._set_status("Erro ao carregar corpus", 0)

    @staticmethod
    def _build_traditional_collection_text(text: str, metadata: Optional[Dict[str, Any]]) -> str:
        """Reconstrói coleção multi-arquivo em texto com marcadores de documento."""
        if not isinstance(metadata, dict) or not metadata.get("collection_mode"):
            return text

        documents = metadata.get("documents", [])
        if not isinstance(documents, list) or not documents:
            return text

        blocks: List[str] = []
        for idx, item in enumerate(documents, start=1):
            if not isinstance(item, dict):
                continue
            body = str(item.get("text") or "").strip()
            if not body:
                continue

            raw_name = str(item.get("name") or item.get("filename") or f"doc_{idx}")
            token = MainWindow._slug_iramuteq_token(raw_name, f"doc_{idx}")
            blocks.append(f"**** *doc_{token}\n{body}")

        return "\n\n".join(blocks).strip() if blocks else text

    def _create_corpus_with_temp_db(self, uce_size: int = 40) -> Corpus:
        """
        Cria corpus conectado a banco SQLite temporario.

        Necessario para persistir UCEs durante analises e estatisticas.
        """
        self._cleanup_corpus_storage()

        with tempfile.NamedTemporaryFile(
            mode="w+b",
            suffix=".db",
            prefix="lexianalyst_corpus_",
            delete=False
        ) as db_file:
            self._corpus_db_path = Path(db_file.name)

        strict_mode = True
        prefer_portuguese_br = False
        config_obj = self.__dict__.get("config")
        if isinstance(config_obj, ConfigManager):
            mode_raw = str(config_obj.get("analysis_mode", "") or "").strip().lower()
            if mode_raw in {"strict", "legacy"}:
                strict_mode = mode_raw == "strict"
            else:
                strict_mode = bool(config_obj.get("strict_iramuteq_clone", True))
            prefer_portuguese_br = bool(config_obj.get("prefer_portuguese_br", False))
            if strict_mode:
                # Strict clone parity with IRaMuTeQ disables PT-BR heuristic demotion by default.
                prefer_portuguese_br = False

        lexicon = self._load_lexicon()
        if strict_mode and lexicon is None:
            raise CorpusError(
                what="Modo strict exige léxico português carregado.",
                why="Não foi possível carregar lexicon PT-BR para lematização/gramática.",
                how="Verifique a pasta dictionaries e o arquivo lexique_pt.txt, depois reimporte o corpus.",
            )

        corpus = Corpus(
            parametres={
                "ucemethod": 1,  # segmentacao por lista de palavras
                "ucesize": max(20, min(200, int(uce_size or 40))),
                "charact": True,
                "expressions": 1,
                "keep_caract": "^a-zA-Z0-9àÀâÂäÄáÁåÅãéÉèÈêÊëËìÌîÎïÏíÍóÓòÒôÔöÖõÕøØùÙûÛüÜúÚçÇßœŒ’ñÑ.:,;!?'_-",
                "prefer_portuguese_br": bool(prefer_portuguese_br),
            },
            lexicon=lexicon,
        )
        corpus.connect(self._corpus_db_path)
        log.info(
            "Corpus conectado ao SQLite temporario: %s (uce_size=%s)",
            self._corpus_db_path,
            uce_size,
        )
        return corpus

    def _load_lexicon(self) -> Optional[Lexicon]:
        """Carrega lexico conforme idioma configurado."""
        language = "portuguese"
        strict_mode = True
        config_obj = self.__dict__.get("config")
        if isinstance(config_obj, ConfigManager):
            configured_language = str(config_obj.get("language", "portuguese") or "portuguese")
            if configured_language.strip().lower() not in {"portuguese", "pt", "pt_br"}:
                log.warning(
                    "Idioma configurado (%s) ignorado: priorizando portuguese (PT-BR) para lematizacao.",
                    configured_language,
                )
            language = "portuguese"
            mode_raw = str(config_obj.get("analysis_mode", "") or "").strip().lower()
            if mode_raw in {"strict", "legacy"}:
                strict_mode = mode_raw == "strict"
            else:
                strict_mode = bool(config_obj.get("strict_iramuteq_clone", True))

        lexicon_path = resolve_lexicon_path(language)
        cached_lexicon = self.__dict__.get("_loaded_lexicon")
        cached_language = self.__dict__.get("_loaded_lexicon_language")
        cached_strict = self.__dict__.get("_loaded_lexicon_strict_mode")
        if (
            cached_lexicon is not None
            and cached_language == language
            and cached_strict == strict_mode
        ):
            return cached_lexicon

        if not lexicon_path.exists():
            log.warning("Lexico nao encontrado para idioma %s: %s", language, lexicon_path)
            self._loaded_lexicon = None
            self._loaded_lexicon_language = None
            self._loaded_lexicon_strict_mode = None
            return None

        lexicon = Lexicon(strict_mode=strict_mode)
        try:
            loaded_entries = lexicon.load(lexicon_path)
            self._loaded_lexicon = lexicon
            self._loaded_lexicon_language = language
            self._loaded_lexicon_strict_mode = strict_mode
            log.info(
                "Lexico carregado (%s entradas) para idioma %s: %s",
                loaded_entries,
                language,
                lexicon_path,
            )
            return lexicon
        except Exception:
            log.exception("Falha ao carregar lexico em %s", lexicon_path)
            self._loaded_lexicon = None
            self._loaded_lexicon_language = None
            self._loaded_lexicon_strict_mode = None
            return None

    def _cleanup_corpus_storage(self) -> None:
        """Fecha corpus atual e remove banco temporario associado."""
        if self.corpus is not None:
            try:
                self.corpus.close()
            except Exception:
                log.exception("Falha ao fechar conexao SQLite do corpus")
            finally:
                self.corpus = None

        if self._corpus_db_path and self._corpus_db_path.exists():
            try:
                self._corpus_db_path.unlink()
                log.debug("Banco temporario removido: %s", self._corpus_db_path)
            except OSError as exc:
                log.warning("Nao foi possivel remover banco temporario %s: %s", self._corpus_db_path, exc)
            finally:
                self._corpus_db_path = None

    def _get_analysis_output_dir(self, analysis_type: str) -> Path:
        """Retorna pasta temporaria para saida de analises."""
        if self._analysis_output_root is None or not self._analysis_output_root.exists():
            self._analysis_output_root = Path(
                tempfile.mkdtemp(prefix="lexianalyst_analysis_")
            )
            log.info("Diretorio temporario de analises criado: %s", self._analysis_output_root)

        analysis_dir = self._analysis_output_root / analysis_type
        analysis_dir.mkdir(parents=True, exist_ok=True)
        return analysis_dir

    def _cleanup_analysis_storage(self) -> None:
        """Remove diretorio temporario de saida das analises."""
        if self._analysis_output_root and self._analysis_output_root.exists():
            try:
                shutil.rmtree(self._analysis_output_root)
                log.debug("Diretorio de analises removido: %s", self._analysis_output_root)
            except OSError as exc:
                log.warning(
                    "Nao foi possivel remover diretorio de analises %s: %s",
                    self._analysis_output_root,
                    exc,
                )
            finally:
                self._analysis_output_root = None

    def _build_corpus_from_text(self, text: str, remove_numbers: bool = False):
        """
        Constroi corpus a partir do texto.
        
        Processa o texto identificando:
        - Linhas de comando (****) como UCIs
        - Paragrafos segmentados em UCEs via corpus.segment_text()
        - Palavras individuais
        """
        if self.corpus is not None and self.corpus.lexicon is None:
            self.corpus.lexicon = self._loaded_lexicon

        strict_mode = True
        config_obj = self.__dict__.get("config")
        if isinstance(config_obj, ConfigManager):
            mode_raw = str(config_obj.get("analysis_mode", "") or "").strip().lower()
            if mode_raw in {"strict", "legacy"}:
                strict_mode = mode_raw == "strict"
            else:
                strict_mode = bool(config_obj.get("strict_iramuteq_clone", True))

        lines = text.split('\n')
        current_uci = None
        current_txt_lines: List[str] = []
        para_counter = -1  # IRaMuTeQ para_id is global across corpus.
        strict_keep_default = "^a-zA-Z0-9àÀâÂäÄáÁåÅãéÉèÈêÊëËìÌîÎïÏíÍóÓòÒôÔöÖõÕøØùÙûÛüÜúÚçÇßœŒ’ñÑ.:,;!?'_-"
        strict_keep_caract = str(
            self.corpus.parametres.get("keep_caract", strict_keep_default)
        ).strip()
        if strict_keep_caract and not strict_keep_caract.startswith("^"):
            strict_keep_caract = f"^{strict_keep_caract}"
        strict_charact_pattern: Optional[str] = None
        if strict_keep_caract:
            strict_charact_pattern = f"[{strict_keep_caract}]+"
        strict_expression_pairs: List[Tuple[str, str]] = []
        if strict_mode and bool(self.corpus.parametres.get("expressions", 1)):
            lexicon = getattr(self.corpus, "lexicon", None)
            if lexicon is not None:
                language_key = str(getattr(lexicon, "_language_key", "") or "portuguese")
                exp_path = resolve_expression_path(language_key)
                expressions_map = lexicon.load_expressions(exp_path)
                if expressions_map:
                    strict_expression_pairs = sorted(
                        expressions_map.items(),
                        key=lambda item: len(item[0]),
                        reverse=True,
                    )

        def _strict_clean_chunk(chunk_text: str) -> str:
            txt = str(chunk_text or "")

            # buildcleans/dolower
            txt = txt.lower()

            # buildcleans/firstclean
            txt = txt.replace("’", "'").replace("œ", "oe")
            txt = (
                txt.replace("...", " £$£ ")
                .replace("?", " ? ")
                .replace(".", " . ")
                .replace("!", " ! ")
                .replace(",", " , ")
                .replace(";", " ; ")
                .replace(":", " : ")
                .replace("…", " £$£ ")
            )

            # buildcleans/docharact using keep_caract semantics from IRaMuTeQ:
            # list_keep = "[" + keep_caract + "]+" then re.sub(list_keep, " ", txt)
            if strict_charact_pattern:
                try:
                    txt = re.sub(strict_charact_pattern, " ", txt)
                except re.error:
                    # fallback to known-safe default regex used in strict mode
                    safe_keep = strict_keep_default
                    txt = re.sub(f"[{safe_keep}]+", " ", txt)

            # buildcleans/make_expression
            for source, target in strict_expression_pairs:
                if source and source in txt:
                    txt = txt.replace(source, target)

            # buildcleans/doapos + buildcleans/dotiret
            txt = txt.replace("'", " ")
            txt = txt.replace("-", " ")

            txt = " ".join(txt.split())
            return txt

        def _strict_make_uces(chunk_text: str) -> List[str]:
            cleaned = _strict_clean_chunk(chunk_text)
            if not cleaned:
                return []
            prepared = cleaned.split() + ["$"]
            ucesize = max(1, int(self.corpus.parametres.get("ucesize", 40)))
            max_len = ucesize + 15
            ponctuation_espace = (
                [' ', '']
                if bool(self.corpus.parametres.get('keep_ponct', False))
                else [' ', '.', '£$£', ';', '?', '!', ',', ':', '']
            )
            out: List[str] = []
            found, texte_uce, suite = decouperlist(prepared, max_len, ucesize)
            while found:
                uce = " ".join([val for val in texte_uce if val not in ponctuation_espace]).strip()
                if uce:
                    out.append(uce)
                found, texte_uce, suite = decouperlist(suite, max_len, ucesize)
            uce = " ".join([val for val in texte_uce if val not in ponctuation_espace]).strip()
            if uce:
                out.append(uce)
            return out

        def _is_numeric_noise_token(token: str) -> bool:
            """Remove residual token noise from PDF/OCR when number cleanup is enabled."""
            tok = str(token or "").strip().lower()
            if not tok:
                return True
            if re.search(r"\d", tok):
                return True
            if re.fullmatch(r"[ivxlcdm]{1,6}", tok):
                return True
            if len(tok) <= 1:
                return True
            if len(tok) <= 2 and tok not in {"ia", "ai", "uf", "br", "pt"}:
                return True
            return False

        def _flush_current_txt() -> None:
            nonlocal para_counter, current_txt_lines, current_uci
            if current_uci is None or not current_txt_lines:
                current_txt_lines = []
                return

            para_text = " ".join(current_txt_lines).strip()
            current_txt_lines = []
            if not para_text:
                return

            if strict_mode:
                if not current_uci.paras:
                    para_counter += 1
                para_id = para_counter
                segments = _strict_make_uces(para_text)
                for segment in segments:
                    uce = self.corpus.add_uce(current_uci.ident, para_id, segment)
                    for token in segment.split():
                        if remove_numbers and _is_numeric_noise_token(token):
                            continue
                        self.corpus.add_word(token, uce_id=uce.ident)
                return

            # Legacy parser keeps historical behavior.
            segments = self.corpus.segment_text(para_text)
            if not segments:
                segments = [para_text]
            for segment in segments:
                seg = segment.strip()
                if not seg:
                    continue
                para_counter += 1
                uce = self.corpus.add_uce(current_uci.ident, para_counter, seg)
                for token in re.findall(r'\b[a-zA-ZÀ-ÿ]+(?:_[a-zA-ZÀ-ÿ]+)*\b', seg.lower()):
                    if remove_numbers and _is_numeric_noise_token(token):
                        continue
                    if len(token) > 2:
                        self.corpus.add_word(token, uce_id=uce.ident)

        conn = self.corpus._conn if self.corpus is not None else None
        if conn is not None:
            transaction = conn
        else:
            class DummyContext:
                def __enter__(self): pass
                def __exit__(self, exc_type, exc_val, exc_tb): pass
            transaction = DummyContext()

        with transaction:
            for raw_line in lines:
                line = raw_line.strip()
                if line.startswith('****'):
                    _flush_current_txt()
                    current_uci = self.corpus.add_uci(line)
                    log.debug("Nova UCI identificada: %s", line)
                    continue

                if line.startswith("-*") and current_uci is not None:
                    _flush_current_txt()
                    para_counter += 1
                    current_uci.paras.append(line.split()[0])
                    continue

                if line and current_uci is not None:
                    current_txt_lines.append(line)

            _flush_current_txt()

            if len(self.corpus.ucis) == 0:
                current_uci = self.corpus.add_uci("**** *doc_1")
                current_txt_lines = [line.strip() for line in lines if line.strip()]
                _flush_current_txt()
        log.info(
            "Construcao do corpus concluida: %s UCIs, %s UCEs, %s formas",
            self.corpus.getucinb(),
            self.corpus.getucenb(),
            self.corpus.getwordnb(),
        )

    def _build_corpus_snapshot_text(self) -> str:
        """Serializa corpus atual no formato textual IRaMuTeQ para persistencia."""
        corpus_obj = self.__dict__.get("corpus")
        if not corpus_obj:
            return ""

        lines = []
        for idx, uci in enumerate(corpus_obj.ucis, start=1):
            marker = self._build_iramuteq_marker(uci=uci, idx=idx)
            uce_ids = [uce.ident for uce in uci.uces]
            chunks: List[str] = []
            for _uce_id, text in corpus_obj.getconcorde(uce_ids):
                cleaned = str(text or "").strip()
                if cleaned:
                    chunks.append(cleaned)
            if not chunks:
                continue
            lines.append(marker)
            lines.extend(chunks)
            lines.append("")

        return ("\n".join(lines).strip() + "\n") if lines else ""

    @staticmethod
    def _slug_iramuteq_token(value: str, fallback: str) -> str:
        """Normaliza token para padrão IRaMuTeQ (*nome_valor)."""
        folded = unicodedata.normalize("NFD", str(value or ""))
        folded = "".join(
            char for char in folded
            if unicodedata.category(char) != "Mn"
        ).lower()
        folded = re.sub(r"[^a-z0-9_]+", "_", folded)
        folded = re.sub(r"_+", "_", folded).strip("_")
        return folded or fallback

    def _sanitize_iramuteq_var_token(self, token: str, idx: int) -> str:
        """Sanitiza metadado em formato *nome_valor aceito pelo IRaMuTeQ."""
        raw = str(token or "").strip()
        if not raw:
            return ""
        if raw.startswith("****"):
            return ""
        raw = raw.lstrip("*")
        if "_" in raw:
            name_raw, value_raw = raw.split("_", 1)
        else:
            name_raw, value_raw = "meta", raw
        name = self._slug_iramuteq_token(name_raw, "meta")
        value = self._slug_iramuteq_token(value_raw, f"uci_{idx}")
        return f"*{name}_{value}"

    def _build_iramuteq_marker(self, uci: Any, idx: int) -> str:
        """Monta linha de comando IRaMuTeQ robusta para exportação."""
        tokens = list(getattr(uci, "etoiles", None) or [])
        sanitized: List[str] = []
        seen = set()
        for token in tokens:
            safe = self._sanitize_iramuteq_var_token(str(token), idx=idx)
            if not safe or safe in seen:
                continue
            seen.add(safe)
            sanitized.append(safe)
        if not sanitized:
            sanitized = [f"*doc_{idx}", "*fonte_lexianalyst"]
        return "**** " + " ".join(sanitized)

    # === Matriz (CSV/XLSX) ===

    def _open_matrix_file(self) -> None:
        """Abre arquivo tabular para análises de matriz."""
        file_path = filedialog.askopenfilename(
            title="Abrir Matriz (CSV/XLSX)",
            filetypes=[
                ("Matriz", "*.csv *.tsv *.xlsx"),
                ("CSV/TSV", "*.csv *.tsv"),
                ("Excel", "*.xlsx"),
                ("Todos", "*.*"),
            ],
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            self._set_status("Carregando matriz...", 0.4)
            suffix = path.suffix.lower()
            if suffix == ".xlsx":
                tableau = Tableau.from_xlsx(path, sheet=0, header=True, rownames=False)
            elif suffix == ".tsv":
                tableau = Tableau.from_csv(path, sep="\t", header=True, rownames=False)
            else:
                tableau = Tableau.from_csv(path, sep=None, header=True, rownames=False)

            self.tableau = tableau

            preview_dir = self._get_analysis_output_dir("matrix_preview")
            preview_path = preview_dir / "matrix_preview.csv"
            tableau.data.head(200).to_csv(
                preview_path,
                sep=";",
                index=tableau.has_rownames,
                encoding="utf-8",
            )
            self.results_viewer.show_table(preview_path)
            self._set_status(
                f"Matriz carregada: {tableau.shape[0]} linhas x {tableau.shape[1]} colunas",
                1.0,
            )
        except TableauError as exc:
            show_error(self, error=exc)
            self._set_status("Erro ao carregar matriz", 0)
        except Exception as exc:
            log.exception("Falha ao abrir matriz")
            show_error(
                self,
                what="Falha ao abrir matriz.",
                why=str(exc),
                how="Verifique formato/encoding do arquivo e tente novamente.",
            )
            self._set_status("Erro ao carregar matriz", 0)

    def _require_tableau(self) -> Optional[Tableau]:
        """Valida se existe matriz carregada para análise."""
        if self.tableau is None:
            show_error(
                self,
                what="Nenhuma matriz carregada.",
                why="As análises de matriz exigem um arquivo CSV/XLSX aberto.",
                how="Use o menu Matriz > Abrir Matriz e tente novamente.",
            )
            return None
        return self.tableau

    def _run_matrix_frequency(self) -> None:
        """Executa distribuição de frequências em colunas da matriz."""
        from .dialogs.matrix_dialog import MatrixFrequencyDialog  # lazy import
        tableau = self._require_tableau()
        if tableau is None:
            return
        dialog = MatrixFrequencyDialog(
            self,
            columns=list(tableau.col_names),
            initial_params=self._get_initial_analysis_params("matrix_frequency"),
        )
        params = dialog.get_result()
        if not params:
            return
        columns = params.get("columns", list(tableau.col_names))
        self._remember_analysis_params("matrix_frequency", params)

        try:
            self._set_status("Calculando frequências da matriz...", 0.5)
            from ..analysis import FrequencyAnalysis

            output_dir = self._get_analysis_output_dir("matrix_frequency")
            analysis = FrequencyAnalysis(output_dir)
            result = analysis.run(
                tableau,
                columns=columns,
                params={
                    "top_n": params.get("top_n", 50),
                    "typegraph": self._normalize_display_typegraph(params.get("typegraph", "png")),
                },
            )

            result_path = None
            if result.graphs:
                freq_gallery: Dict[str, Path] = {}
                for column in sorted(result.graphs.keys(), key=lambda item: str(item)):
                    resolved_graph = self._resolve_existing_file_path(result.graphs.get(column))
                    if resolved_graph is not None:
                        freq_gallery[f"Frequência: {column}"] = resolved_graph
                if freq_gallery:
                    result_path = next(iter(freq_gallery.values()))
                    self._show_image_gallery(freq_gallery)
            elif result.tables:
                first_col = sorted(result.tables.keys())[0]
                result_path = result.tables[first_col]
                self.results_viewer.show_table(result_path)
            elif result.summary_csv_path and Path(result.summary_csv_path).exists():
                result_path = result.summary_csv_path
                self.results_viewer.show_table(result.summary_csv_path)

            self._last_analysis_result = result
            self._last_analysis_runner = analysis
            self._last_analysis_context = {
                "name": "Frequências (Matriz)",
                "analysis_type": "matrix_frequency",
                "params": params,
                "result_path": str(result_path) if result_path else "",
                "output_dir": str(output_dir),
            }
            self._generate_report_for_current_result("Frequências (Matriz)", result_path)
            self._save_analysis_to_history("Frequências (Matriz)", result_path)
            self._set_status("Frequências da matriz concluídas", 1.0)
        except Exception as exc:
            log.exception("Erro na análise de frequência de matriz")
            show_error(self, error=exc)
            self._set_status("Erro em Frequências (Matriz)", 0)

    def _run_matrix_chi2(self) -> None:
        """Executa Qui-quadrado de independência entre duas colunas da matriz."""
        from .dialogs.matrix_dialog import MatrixChi2Dialog  # lazy import
        tableau = self._require_tableau()
        if tableau is None:
            return
        if len(tableau.col_names) < 2:
            show_error(
                self,
                what="Matriz insuficiente para Qui-quadrado.",
                why="São necessárias pelo menos duas colunas categóricas.",
                how="Abra outra matriz ou inclua mais colunas.",
            )
            return

        dialog = MatrixChi2Dialog(
            self,
            columns=list(tableau.col_names),
            initial_params=self._get_initial_analysis_params("matrix_chi2"),
        )
        params = dialog.get_result()
        if not params:
            return
        self._remember_analysis_params("matrix_chi2", params)
        row_var = str(params.get("row_var", "")).strip()
        col_var = str(params.get("col_var", "")).strip()

        try:
            self._set_status("Calculando Qui-quadrado da matriz...", 0.5)
            from ..analysis import Chi2MatrixAnalysis

            output_dir = self._get_analysis_output_dir("matrix_chi2")
            analysis = Chi2MatrixAnalysis(output_dir)
            result = analysis.run(
                tableau,
                row_var=row_var,
                col_var=col_var,
                params={"typegraph": self._normalize_display_typegraph(params.get("typegraph", "png"))},
            )

            result_path = None
            if result.graph_path and Path(result.graph_path).exists():
                result_path = result.graph_path
                self.results_viewer.show_image(result.graph_path)
            else:
                result_path = result.contingency_csv_path
                self.results_viewer.show_table(result.contingency_csv_path)

            summary = (
                f"Qui-quadrado: {result.chi2:.4f}\n"
                f"Graus de liberdade: {result.dof}\n"
                f"p-valor: {result.p_value:.6g}\n\n"
                f"Tabela: {result.contingency_csv_path}\n"
                f"Esperados: {result.expected_csv_path}\n"
                f"Resíduos: {result.residuals_csv_path}"
            )
            log.info("Resultado Qui-quadrado matriz: %s", summary.replace("\n", " | "))

            self._last_analysis_result = result
            self._last_analysis_runner = analysis
            self._last_analysis_context = {
                "name": "Qui-Quadrado (Matriz)",
                "analysis_type": "matrix_chi2",
                "params": params,
                "result_path": str(result_path) if result_path else "",
                "output_dir": str(output_dir),
            }
            self._generate_report_for_current_result("Qui-Quadrado (Matriz)", result_path)
            self._save_analysis_to_history("Qui-Quadrado (Matriz)", result_path)
            self._set_status("Qui-quadrado da matriz concluído", 1.0)
        except Exception as exc:
            log.exception("Erro na análise Qui-quadrado de matriz")
            show_error(self, error=exc)
            self._set_status("Erro em Qui-Quadrado (Matriz)", 0)

    def _run_matrix_afc(self) -> None:
        """Executa AFC diretamente na matriz numérica."""
        from .dialogs.matrix_dialog import MatrixAFCDialog  # lazy import
        tableau = self._require_tableau()
        if tableau is None:
            return

        dialog = MatrixAFCDialog(
            self,
            initial_params=self._get_initial_analysis_params("matrix_afc"),
        )
        params = dialog.get_result()
        if not params:
            return
        self._remember_analysis_params("matrix_afc", params)
        n_dim = int(params.get("n_dim", 2))

        try:
            self._set_status("Executando AFC na matriz...", 0.5)
            from ..analysis import MatrixAnalysisAdapter

            output_dir = self._get_analysis_output_dir("matrix_afc")
            adapter = self._build_analysis_runner(MatrixAnalysisAdapter, output_dir)
            result = adapter.run_afc(
                tableau,
                {
                    "n_dim": n_dim,
                    "typegraph": self._normalize_display_typegraph(params.get("typegraph", "png")),
                },
            )

            result_path = result.graph_path
            if result_path and Path(result_path).exists():
                self.results_viewer.show_image(result_path)
            else:
                self.results_viewer.show_text(
                    "AFC executada sem gráfico disponível.\n"
                    "Verifique os arquivos de coordenadas exportados no diretório de saída.",
                    title="AFC (Matriz)",
                )

            self._last_analysis_result = result
            self._last_analysis_runner = adapter
            self._last_analysis_context = {
                "name": "AFC (Matriz)",
                "analysis_type": "matrix_afc",
                "params": params,
                "result_path": str(result_path) if result_path else "",
                "output_dir": str(output_dir),
            }
            self._generate_report_for_current_result("AFC (Matriz)", result_path)
            self._save_analysis_to_history("AFC (Matriz)", result_path)
            self._set_status("AFC da matriz concluída", 1.0)
        except Exception as exc:
            log.exception("Erro na AFC de matriz")
            show_error(self, error=exc)
            self._set_status("Erro em AFC (Matriz)", 0)

    def _run_matrix_chd(self) -> None:
        """Executa CHD sobre linhas da matriz numérica."""
        from .dialogs.matrix_dialog import MatrixCHDDialog  # lazy import
        tableau = self._require_tableau()
        if tableau is None:
            return

        dialog = MatrixCHDDialog(
            self,
            initial_params=self._get_initial_analysis_params("matrix_chd"),
        )
        params = dialog.get_result()
        if not params:
            return
        self._remember_analysis_params("matrix_chd", params)
        n_classes = int(params.get("nb_classes", 5))

        try:
            self._set_status("Executando CHD na matriz...", 0.5)
            from ..analysis import MatrixAnalysisAdapter

            output_dir = self._get_analysis_output_dir("matrix_chd")
            adapter = self._build_analysis_runner(MatrixAnalysisAdapter, output_dir)
            result = adapter.run_chd(
                tableau,
                {
                    "nb_classes": n_classes,
                    "method": params.get("method", "ward.D2"),
                    "typegraph": self._normalize_display_typegraph(params.get("typegraph", "png")),
                },
            )

            result_path = result.dendrogram_path or result.clusters_path
            if result.dendrogram_path and Path(result.dendrogram_path).exists():
                self.results_viewer.show_image(result.dendrogram_path)
            elif result.clusters_path and Path(result.clusters_path).exists():
                self.results_viewer.show_table(result.clusters_path)
            else:
                self.results_viewer.show_text(
                    "CHD executada sem artefatos visuais disponíveis.",
                    title="CHD (Matriz)",
                )

            self._last_analysis_result = result
            self._last_analysis_runner = adapter
            self._last_analysis_context = {
                "name": "CHD (Matriz)",
                "analysis_type": "matrix_chd",
                "params": params,
                "result_path": str(result_path) if result_path else "",
                "output_dir": str(output_dir),
            }
            self._generate_report_for_current_result("CHD (Matriz)", result_path)
            self._save_analysis_to_history("CHD (Matriz)", result_path)
            self._set_status("CHD da matriz concluída", 1.0)
        except Exception as exc:
            log.exception("Erro na CHD de matriz")
            show_error(self, error=exc)
            self._set_status("Erro em CHD (Matriz)", 0)

    def _run_matrix_similarity(self) -> None:
        """Executa similaridade sobre coocorrência derivada da matriz."""
        from .dialogs.matrix_dialog import MatrixSimilarityDialog  # lazy import
        tableau = self._require_tableau()
        if tableau is None:
            return

        dialog = MatrixSimilarityDialog(
            self,
            initial_params=self._get_initial_analysis_params("matrix_similarity"),
        )
        params = dialog.get_result()
        if not params:
            return
        self._remember_analysis_params("matrix_similarity", params)
        layout_raw = str(params.get("layout", "frutch")).strip()
        layout_alias = {
            "fruchterman": "frutch",
            "frutch": "frutch",
            "kamada": "kawa",
            "kawa": "kawa",
            "circular": "circle",
            "circle": "circle",
            "random": "random",
            "graphopt": "graphopt",
            "spirale": "spirale",
            "spirale3d": "spirale3D",
            "spirale3D": "spirale3D",
        }
        layout = layout_alias.get(layout_raw, layout_alias.get(layout_raw.lower(), "frutch"))

        try:
            self._set_status("Executando similitude na matriz...", 0.5)
            from ..analysis import MatrixAnalysisAdapter

            output_dir = self._get_analysis_output_dir("matrix_similarity")
            adapter = self._build_analysis_runner(MatrixAnalysisAdapter, output_dir)
            result = adapter.run_similarity(
                tableau,
                {
                    "layout": layout,
                    "min_edge": params.get("min_edge", 0),
                    "typegraph": self._normalize_display_typegraph(params.get("typegraph", "png")),
                    "detect_communities": params.get("detect_communities", False),
                    "community_method": params.get("community_method", "edge_betweenness"),
                },
            )

            result_path = result.graph_path or result.adjacency_matrix_path
            if result.graph_path and Path(result.graph_path).exists():
                self.results_viewer.show_image(result.graph_path)
            else:
                self.results_viewer.show_table(result.adjacency_matrix_path)

            self._last_analysis_result = result
            self._last_analysis_runner = adapter
            self._last_analysis_context = {
                "name": "Similitude (Matriz)",
                "analysis_type": "matrix_similarity",
                "params": params,
                "result_path": str(result_path) if result_path else "",
                "output_dir": str(output_dir),
            }
            self._generate_report_for_current_result("Similitude (Matriz)", result_path)
            self._save_analysis_to_history("Similitude (Matriz)", result_path)
            self._set_status("Similitude da matriz concluída", 1.0)
        except Exception as exc:
            log.exception("Erro na similitude de matriz")
            show_error(self, error=exc)
            self._set_status("Erro em Similitude (Matriz)", 0)

    # === Analises ===

    def _run_statistics(self):
        """Executa estatisticas basicas."""
        if not self.corpus:
            return

        try:
            self._set_status("Calculando estatísticas...", 0.5)
            
            from ..analysis import StatisticsAnalysis
            
            analysis = self._build_analysis_runner(StatisticsAnalysis, self.corpus)
            stats = analysis.get_corpus_statistics()
            output_dir = self._get_analysis_output_dir("statistics")
            report_txt_path = Path(output_dir) / "statistics_summary.txt"
            analysis.export_statistics_report(str(report_txt_path))
            graphs = {}
            try:
                graphs = analysis.generate_graphs(output_dir=Path(output_dir), typegraph="png")
            except Exception as graph_exc:
                log.warning("Nao foi possivel gerar graficos de estatisticas: %s", graph_exc)
            
            stats_dict = self._statistics_to_display_dict(stats)
            stats_json_path = Path(output_dir) / "statistics.json"
            stats_json_path.write_text(
                json.dumps(stats_dict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            
            self.results_viewer.show_statistics(stats_dict)
            result_path = None
            stats_gallery: Dict[str, Path] = {}
            zipf_path = self._resolve_existing_file_path(graphs.get("zipf"))
            uce_size_path = self._resolve_existing_file_path(graphs.get("uce_size_distribution"))
            if zipf_path is not None:
                stats_gallery["Zipf"] = zipf_path
                result_path = zipf_path
            if uce_size_path is not None:
                stats_gallery["Tamanho das UCEs"] = uce_size_path
                if result_path is None:
                    result_path = uce_size_path
            if stats_gallery:
                self._show_image_gallery(stats_gallery)
            elif report_txt_path.exists():
                result_path = report_txt_path

            self._last_analysis_result = {
                "stats": stats_dict,
                "graphs": graphs,
                "report_txt": str(report_txt_path),
                "stats_json_path": str(stats_json_path),
                "backend_used": "python+r" if graphs else "python",
            }
            self._last_analysis_runner = analysis
            self._last_analysis_context = {
                "name": "Estatísticas",
                "analysis_type": "statistics",
                "params": {},
                "result_path": str(result_path) if result_path else "",
                "output_dir": str(output_dir),
            }
            self._generate_report_for_current_result("Estatísticas", result_path)
            self._save_analysis_to_history("Estatísticas", result_path)
            self._set_status("Estatísticas calculadas!", 1.0)
            
        except Exception as e:
            log.exception("Erro ao calcular estatísticas")
            show_error(self, error=e)
            self._set_status("Erro nas estatísticas", 0)

    @staticmethod
    def _statistics_to_display_dict(stats):
        """Converte estatisticas para formato exibivel na UI."""
        if hasattr(stats, '__dict__'):
            return {
                'total_ucis': getattr(stats, 'total_ucis', 0),
                'total_uces': getattr(stats, 'total_uces', 0),
                'total_formes': getattr(stats, 'total_formes', 0),
                'total_occurrences': getattr(stats, 'total_occurrences', 0),
                'total_hapax': getattr(stats, 'total_hapax', 0),
                'mean_words_per_uce': getattr(stats, 'mean_words_per_uce', 0.0),
                'vocabulary_richness': getattr(stats, 'vocabulary_richness', 0.0),
            }
        if isinstance(stats, dict):
            return stats
        return {'resultado': str(stats)}

    @staticmethod
    def _load_statistics_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
        """Carrega JSON de estatísticas preservando compatibilidade de tipos."""
        if not path:
            return None
        candidate = Path(path)
        if not candidate.exists() or not candidate.is_file():
            return None
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Falha ao ler JSON de estatísticas (%s): %s", candidate, exc)
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _restore_statistics_from_history(self, entry: Any, artifact_path: Optional[Path]) -> bool:
        """Restaura estatísticas formatadas ao abrir item de histórico."""
        metadata = getattr(entry, "metadata", {}) if isinstance(getattr(entry, "metadata", {}), dict) else {}
        candidates = []

        metadata_json = metadata.get("statistics_json_path")
        if metadata_json:
            candidates.append(Path(str(metadata_json)))

        if artifact_path:
            try:
                candidates.append(Path(artifact_path).with_suffix(".json"))
            except Exception:
                pass
            candidates.append(Path(artifact_path).parent / "statistics.json")

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            payload = self._load_statistics_json(candidate)
            if isinstance(payload, dict) and payload:
                self.results_viewer.show_statistics(payload)
                return True

        return False

    @staticmethod
    def _result_attr(result: Any, attr: str, default: Any = None) -> Any:
        """Lê atributo de resultado em objetos/dataclasses ou dicionários."""
        if result is None:
            return default
        if isinstance(result, dict):
            return result.get(attr, default)
        return getattr(result, attr, default)

    @staticmethod
    def _resolve_existing_file_path(path_like: Any) -> Optional[Path]:
        """Converte caminho em Path validado (arquivo existente)."""
        if not path_like:
            return None
        try:
            path = Path(path_like)
        except Exception:
            return None
        if path.exists() and path.is_file():
            return path
        return None

    @staticmethod
    def _voyant_panel_order() -> List[str]:
        return [
            "termsberry",
            "trends",
            "document_terms",
            "bubblelines",
            "cooccurrences",
        ]

    @staticmethod
    def _voyant_panel_titles_pt() -> Dict[str, str]:
        return {
            "termsberry": "TermsBerry",
            "trends": "Tendências",
            "document_terms": "Termos do documento",
            "bubblelines": "Gráfico de bolhas",
            "cooccurrences": "Co-ocorrências",
        }

    def _extract_voyant_payload(
        self,
        *,
        result: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extrai payload versionado da suíte Voyant de resultado ou metadata."""
        candidate = self._result_attr(result, "voyant_suite_payload_v1", None)
        if not isinstance(candidate, dict):
            meta = metadata if isinstance(metadata, dict) else {}
            candidate = meta.get("voyant_suite_payload_v1")
            if isinstance(candidate, str):
                try:
                    candidate = json.loads(candidate)
                except Exception:
                    candidate = {}
        if not isinstance(candidate, dict):
            return {}
        graphs = candidate.get("graphs", {})
        tables = candidate.get("tables", {})
        if not isinstance(graphs, dict):
            graphs = {}
        if not isinstance(tables, dict):
            tables = {}
        payload = dict(candidate)
        payload["graphs"] = graphs
        payload["tables"] = tables
        tabs = payload.get("graph_tabs", [])
        if not isinstance(tabs, list) or not tabs:
            payload["graph_tabs"] = list(self._voyant_panel_order())
        return payload

    def _get_primary_image(
        self,
        analysis_type_key: str,
        result: Any,
        artifact_path: Optional[Path],
    ) -> Optional[Path]:
        """Retorna caminho da imagem principal para o tipo de análise."""
        if artifact_path and artifact_path.exists():
            if artifact_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg"}:
                return artifact_path

        image_attr_map = {
            "similarity": ["graph_path"],
            "chd": [
                "dendrogram_path",
                "afc_graph_path",
                "profile_afc_path",
            ],
            "wordcloud": ["image_path"],
            "specificities": ["specificities_plot_path", "afc_graph_path"],
            "prototypical": ["graph_path"],
            "labbe": ["dendrogram_path", "heatmap_path"],
            "keyness_extra": ["graph_path"],
            "bigram_network_extra": ["graph_path"],
            "trigram_network_extra": ["graph_path"],
            "word_tree_extra": ["graph_path"],
            "network_text": ["graph_image_path", "graph_svg_path", "graph_path"],
            "voyant_suite": [
                "termsberry_graph_path",
                "trends_graph_path",
                "document_terms_chart_path",
                "bubblelines_graph_path",
                "cooccurrences_graph_path",
                "graph_path",
            ],
            "wordfish_extra": ["graph_path"],
            "sentiment_extra": ["distribution_graph_path", "timeline_graph_path"],
            "xray_extra": ["graph_path"],
            "matrix_afc": ["graph_path"],
            "matrix_chd": ["dendrogram_path"],
            "matrix_similarity": ["graph_path"],
            "matrix_chi2": ["graph_path"],
            "matrix_frequency": [],
            # Suite semantica
            "yake": ["ranking_image_path"],
            "lda": ["distribution_image_path", "top_terms_image_path", "heatmap_image_path", "tuning_image_path", "timeline_image_path", "diagnostics_image_path"],
            "heatmap": ["heatmap_image_path"],
            "associative_heatmap": ["heatmap_image_path"],
            "thematic_map": ["strategic_map_image_path", "expression_network_image_path"],
            "thematic_chd": ["class_topic_heatmap_path"],
        }

        for attr in image_attr_map.get(str(analysis_type_key).lower(), []):
            candidate = self._resolve_existing_file_path(self._result_attr(result, attr))
            if candidate is not None:
                return candidate

        # Fallback generico: BaseSemanticResult expoe primary_image_path()
        if hasattr(result, 'primary_image_path') and callable(result.primary_image_path):
            candidate = self._resolve_existing_file_path(result.primary_image_path())
            if candidate is not None:
                return candidate

        return None

    def _append_image_gallery_item(
        self,
        gallery: Dict[str, Path],
        seen_paths: set[str],
        label: str,
        candidate: Any,
    ) -> None:
        """Adiciona item único na galeria de imagens."""
        resolved = self._resolve_existing_file_path(candidate)
        if resolved is None:
            return
        try:
            path_key = str(resolved.resolve())
        except Exception:
            path_key = str(resolved)
        if path_key in seen_paths:
            return
        clean_label = str(label or "").strip() or "Gráfico"
        if clean_label in gallery:
            # Evita duplicar botão visual para o mesmo rótulo semântico.
            # Mantemos o primeiro artefato já inserido.
            return
        gallery[clean_label] = resolved
        seen_paths.add(path_key)

    def _append_table_gallery_item(
        self,
        gallery: Dict[str, Path],
        seen_paths: set[str],
        label: str,
        candidate: Any,
    ) -> None:
        """Adiciona item unico na galeria de tabelas."""
        resolved = self._resolve_existing_file_path(candidate)
        if resolved is None:
            return
        if resolved.suffix.lower() not in {".csv", ".tsv"}:
            return
        try:
            path_key = str(resolved.resolve())
        except Exception:
            path_key = str(resolved)
        if path_key in seen_paths:
            return
        clean_label = str(label or "").strip() or "Tabela"
        if clean_label in gallery:
            suffix = 2
            unique_label = f"{clean_label} ({suffix})"
            while unique_label in gallery:
                suffix += 1
                unique_label = f"{clean_label} ({suffix})"
            clean_label = unique_label
        gallery[clean_label] = resolved
        seen_paths.add(path_key)

    def _get_image_gallery(
        self,
        analysis_type_key: str,
        result: Any,
        artifact_path: Optional[Path],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Path]:
        """Monta coleção ordenada de imagens para sub-abas do gráfico."""
        analysis_type_key = str(analysis_type_key or "").lower()
        gallery: Dict[str, Path] = {}
        seen_paths: set[str] = set()

        def add(label: str, candidate: Any) -> None:
            self._append_image_gallery_item(gallery, seen_paths, label, candidate)

        def add_semantic(label: str, candidate: Any) -> None:
            resolved = self._resolve_existing_file_path(candidate)
            if resolved is None:
                return
            clean_label = str(label or "").strip() or "Gráfico"
            if clean_label in gallery:
                return
            gallery[clean_label] = resolved

        meta = metadata if isinstance(metadata, dict) else {}
        if analysis_type_key == "chd":
            add(
                "Dendrograma",
                meta.get("dendrogram_path")
                or getattr(result, "dendrogram_path", None)
                or meta.get("polished_dendrogram_path")
                or getattr(result, "polished_dendrogram_path", None)
                or meta.get("native_dendrogram_path")
                or getattr(result, "native_dendrogram_path", None),
            )
        if analysis_type_key == "voyant_suite":
            payload = self._extract_voyant_payload(result=result, metadata=meta)
            payload_graphs = payload.get("graphs", {}) if isinstance(payload, dict) else {}
            payload_tabs = payload.get("graph_tabs", []) if isinstance(payload, dict) else []
            if not isinstance(payload_tabs, list):
                payload_tabs = []
            if not payload_tabs:
                payload_tabs = self._voyant_panel_order()
            panel_titles = self._voyant_panel_titles_pt()
            if isinstance(payload_graphs, dict):
                for panel_id in payload_tabs:
                    item = payload_graphs.get(str(panel_id), {})
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title_pt", panel_titles.get(str(panel_id), str(panel_id))))
                    add(title, item.get("image_path"))

        raw_gallery = meta.get("graph_gallery")
        if isinstance(raw_gallery, dict):
            for raw_label, raw_path in raw_gallery.items():
                add(str(raw_label), raw_path)

        raw_stats_graphs = meta.get("statistics_graphs")
        if isinstance(raw_stats_graphs, dict):
            stats_label_map = {
                "zipf": "Zipf",
                "uce_size_distribution": "Tamanho das UCEs",
            }
            for graph_key, graph_path in raw_stats_graphs.items():
                add(stats_label_map.get(str(graph_key), str(graph_key)), graph_path)

        meta_image_keys = [
            ("Especificidades", "specificities_plot_path"),
            ("TermsBerry", "termsberry_graph_path"),
            ("Tendências", "trends_graph_path"),
            ("Termos do documento", "document_terms_chart_path"),
            ("Gráfico de bolhas", "bubblelines_graph_path"),
            ("Co-ocorrências", "cooccurrences_graph_path"),
            ("Gráfico", "graph_path"),
            ("Heatmap", "heatmap_path"),
            ("Distribuição", "distribution_graph_path"),
            ("Linha do Tempo", "timeline_graph_path"),
            ("Rede Textual", "graph_image_path"),
            ("Rede Textual (SVG)", "graph_svg_path"),
            # Fallback generico para analises semanticas (BaseSemanticResult.to_history_metadata)
            ("Gráfico Principal", "primary_image"),
        ]
        if analysis_type_key in {"chd", "labbe", "matrix_chd"}:
            meta_image_keys.insert(7, ("Dendrograma", "dendrogram_path"))
        for label, key in meta_image_keys:
            add(label, meta.get(key))

        if analysis_type_key == "statistics" and isinstance(result, dict):
            graphs = result.get("graphs", {})
            if isinstance(graphs, dict):
                add("Zipf", graphs.get("zipf"))
                add("Tamanho das UCEs", graphs.get("uce_size_distribution"))

        if analysis_type_key == "matrix_frequency":
            graphs = self._result_attr(result, "graphs", {})
            if isinstance(graphs, dict):
                for column in sorted(graphs.keys(), key=lambda item: str(item)):
                    add(f"Frequência: {column}", graphs.get(column))

        if analysis_type_key == "specificities":
            add("AFC", meta.get("specificities_afc_graph_path"))

        image_attr_map = {
            "similarity": [("Similitude", "graph_path")],
            "chd": [("Dendrograma", "dendrogram_path"), ("AFC Perfis", "profile_afc_path")],
            "wordcloud": [("Nuvem", "image_path")],
            "specificities": [("Especificidades", "specificities_plot_path"), ("AFC", "afc_graph_path")],
            "prototypical": [("Prototípica", "graph_path")],
            "labbe": [("Dendrograma", "dendrogram_path"), ("Heatmap", "heatmap_path")],
            "keyness_extra": [("Keyness", "graph_path")],
            "bigram_network_extra": [("Rede de Bigramas", "graph_path")],
            "trigram_network_extra": [("Rede de Trigramas", "graph_path")],
            "word_tree_extra": [("Word Tree", "graph_path")],
            "network_text": [("Rede Textual", "graph_image_path"), ("Rede Textual (SVG)", "graph_svg_path")],
            "voyant_suite": [
                ("TermsBerry", "termsberry_graph_path"),
                ("Tendências", "trends_graph_path"),
                ("Termos do documento", "document_terms_chart_path"),
                ("Gráfico de bolhas", "bubblelines_graph_path"),
                ("Co-ocorrências", "cooccurrences_graph_path"),
            ],
            "wordfish_extra": [("Wordfish", "graph_path")],
            "sentiment_extra": [("Distribuição", "distribution_graph_path"), ("Linha do Tempo", "timeline_graph_path")],
            "emotions": [
                ("Emoções (Barras)", "bar_graph_path"),
                ("Emoções (Radar)", "radar_graph_path"),
                ("Polaridade", "polarity_graph_path"),
            ],
            "xray_extra": [("X-Ray", "graph_path")],
            "matrix_afc": [("AFC", "graph_path")],
            "matrix_chd": [("Dendrograma", "dendrogram_path")],
            "matrix_similarity": [("Similitude", "graph_path")],
            "matrix_chi2": [("Mosaico", "graph_path")],
            # Suite semantica
            "yake": [("Ranking", "ranking_image_path")],
            "lda": [
                ("Distribuição de Tópicos", "distribution_image_path"),
                ("Top Termos por Tópico", "top_terms_image_path"),
                ("Heatmap Doc-Tópico", "heatmap_image_path"),
                ("Tuning de k", "tuning_image_path"),
                ("Linha do Tempo", "timeline_image_path"),
                ("Diagnóstico Avançado", "diagnostics_image_path"),
            ],
            "heatmap": [("Heatmap Associativo", "heatmap_image_path")],
            "associative_heatmap": [("Heatmap Associativo", "heatmap_image_path")],
            "thematic_map": [
                ("Mapa Estratégico", "strategic_map_image_path"),
                ("Rede de Expressões", "expression_network_image_path"),
            ],
            "thematic_chd": [("Heatmap Classe-Topico", "class_topic_heatmap_path")],
        }
        for label, attr in image_attr_map.get(analysis_type_key, []):
            add(label, self._result_attr(result, attr))

        if analysis_type_key == "chd":
            alternate_afc_path = (
                meta.get("chd_alternative_profile_afc_path")
                or meta.get("alternate_profile_afc_path")
                or getattr(result, "alternate_profile_afc_path", None)
                or meta.get("polished_profile_afc_path")
                or getattr(result, "polished_profile_afc_path", None)
                or meta.get("publication_profile_afc_path")
                or getattr(result, "publication_profile_afc_path", None)
            )
            resolved_alternate_afc = self._resolve_existing_file_path(alternate_afc_path)
            resolved_primary_afc = self._resolve_existing_file_path(
                meta.get("chd_profile_afc_path")
                or meta.get("profile_afc_path")
                or getattr(result, "profile_afc_path", None)
            )
            if resolved_alternate_afc is not None:
                try:
                    same_afc = (
                        resolved_primary_afc is not None
                        and resolved_alternate_afc.resolve() == resolved_primary_afc.resolve()
                    )
                except Exception:
                    same_afc = resolved_primary_afc == resolved_alternate_afc
                if not same_afc:
                    add("AFC Perfis alternativo", resolved_alternate_afc)

            polished_path = (
                meta.get("polished_dendrogram_path")
                or getattr(result, "polished_dendrogram_path", None)
                or getattr(result, "native_dendrogram_path", None)
            )
            resolved_polished = self._resolve_existing_file_path(polished_path)
            resolved_dendrogram = self._resolve_existing_file_path(
                meta.get("dendrogram_path") or getattr(result, "dendrogram_path", None)
            )
            if resolved_polished is not None:
                try:
                    same_graph = (
                        resolved_dendrogram is not None
                        and resolved_polished.resolve() == resolved_dendrogram.resolve()
                    )
                except Exception:
                    same_graph = resolved_dendrogram == resolved_polished
                if not same_graph:
                    add("Phylograma", resolved_polished)

        if artifact_path and artifact_path.exists() and analysis_type_key != "chd":
            if artifact_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg"}:
                add("Principal", artifact_path)

        if not gallery:
            primary = self._get_primary_image(analysis_type_key, result, artifact_path)
            if primary is not None:
                add("Gráfico", primary)

        return gallery

    def _show_image_gallery(self, gallery: Dict[str, Path]) -> None:
        """Renderiza galeria de imagens no ResultsViewer (com fallback para imagem única)."""
        if not gallery:
            return
        if hasattr(self.results_viewer, "show_image_gallery"):
            self.results_viewer.show_image_gallery(gallery)
            return
        first_image = next(iter(gallery.values()))
        self.results_viewer.show_image(first_image)

    def _set_similarity_halo_toggle_context(
        self,
        *,
        enabled: bool,
        params: Optional[Dict[str, Any]] = None,
        base_params: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Path] = None,
        show_halo: bool = False,
    ) -> None:
        """Define contexto do botão de halos da similitude."""
        if not enabled:
            self._similarity_halo_context = {}
            if hasattr(self.results_viewer, "configure_similarity_halo_toggle"):
                self.results_viewer.configure_similarity_halo_toggle(
                    visible=False,
                    callback=self._on_similarity_halo_toggle,
                )
            return

        resolved_output_dir = Path(output_dir) if output_dir else None
        if resolved_output_dir is None:
            self._similarity_halo_context = {}
            if hasattr(self.results_viewer, "configure_similarity_halo_toggle"):
                self.results_viewer.configure_similarity_halo_toggle(
                    visible=False,
                    callback=self._on_similarity_halo_toggle,
                )
            return

        stored_params = dict(params or {})
        stored_base_params = dict(base_params or stored_params)
        self._similarity_halo_context = {
            "params": stored_params,
            "base_params": stored_base_params,
            "output_dir": str(resolved_output_dir),
            "show_halo": bool(show_halo),
        }
        if hasattr(self.results_viewer, "configure_similarity_halo_toggle"):
            self.results_viewer.configure_similarity_halo_toggle(
                visible=True,
                enabled=(not self._similarity_halo_refresh_running),
                value=bool(show_halo),
                callback=self._on_similarity_halo_toggle,
            )

    def _on_similarity_halo_toggle(self, enabled: bool) -> None:
        """Regera a similitude alternando halos sem abrir o diálogo."""
        if self._similarity_halo_refresh_running:
            return

        context = self._similarity_halo_context if isinstance(self._similarity_halo_context, dict) else {}
        params = context.get("params", {}) if isinstance(context.get("params", {}), dict) else {}
        base_params = (
            context.get("base_params", {})
            if isinstance(context.get("base_params", {}), dict)
            else {}
        )
        output_dir_raw = context.get("output_dir", "")
        if not params or not output_dir_raw:
            return
        if self.corpus is None:
            return

        output_dir = Path(str(output_dir_raw))
        output_dir.mkdir(parents=True, exist_ok=True)
        effective_base_params = dict(base_params or params)
        run_params = dict(effective_base_params)
        run_params["show_halo"] = bool(enabled)
        if enabled:
            run_params["detect_communities"] = True
            if bool(run_params.get("strict_iramuteq_style", False)):
                run_params["strict_iramuteq_style"] = False
                run_params["strict_iramuteq_clone"] = False
                run_params["analysis_mode"] = "legacy"
                run_params["parity_profile"] = "legacy_current"
                run_params["render_profile"] = "publication_polish"
        run_params["typegraph"] = "png"

        previous_show_halo = bool(context.get("show_halo", False))
        self._similarity_halo_refresh_running = True
        self._enable_analysis_buttons(False)
        if hasattr(self.results_viewer, "configure_similarity_halo_toggle"):
            self.results_viewer.configure_similarity_halo_toggle(
                visible=True,
                enabled=False,
                value=bool(enabled),
                callback=self._on_similarity_halo_toggle,
            )
        self._set_status("Atualizando halos da similitude...", 0.45)

        def run() -> None:
            from ..analysis import SimilarityAnalysis

            try:
                analysis = self._build_analysis_runner(
                    SimilarityAnalysis,
                    self.corpus,
                    output_dir,
                )
                result = analysis.run(run_params)
                self.after(
                    0,
                    lambda: self._finalize_similarity_halo_toggle(
                        error=None,
                        result=result,
                        requested_show_halo=bool(enabled),
                        previous_show_halo=previous_show_halo,
                        params=run_params,
                        base_params=effective_base_params,
                        output_dir=output_dir,
                        analysis=analysis,
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda err=exc: self._finalize_similarity_halo_toggle(
                        error=err,
                        result=None,
                        requested_show_halo=bool(enabled),
                        previous_show_halo=previous_show_halo,
                        params=run_params,
                        base_params=effective_base_params,
                        output_dir=output_dir,
                        analysis=None,
                    ),
                )

        threading.Thread(target=run, daemon=True).start()

    def _finalize_similarity_halo_toggle(
        self,
        *,
        error: Optional[Exception],
        result: Optional[Any],
        requested_show_halo: bool,
        previous_show_halo: bool,
        params: Dict[str, Any],
        base_params: Dict[str, Any],
        output_dir: Path,
        analysis: Optional[Any],
    ) -> None:
        """Finaliza atualização visual da similitude após alternar halos."""
        self._similarity_halo_refresh_running = False
        self._enable_analysis_buttons(True)

        if error is not None:
            self._set_similarity_halo_toggle_context(
                enabled=True,
                params=params,
                base_params=base_params,
                output_dir=output_dir,
                show_halo=previous_show_halo,
            )
            show_error(self, error=error)
            self._set_status("Falha ao atualizar halos da similitude", 0)
            return

        assert result is not None
        self._last_analysis_result = result
        self._last_analysis_runner = analysis
        self._last_analysis_context = {
            "name": "Similitude",
            "analysis_type": "similarity",
            "params": params,
            "result_path": str(getattr(result, "graph_path", "")),
            "output_dir": str(output_dir),
        }
        graph_path = getattr(result, "graph_path", None)
        if graph_path:
            self.results_viewer.show_image(graph_path)
        self._set_similarity_halo_toggle_context(
            enabled=True,
            params=params,
            base_params=base_params,
            output_dir=output_dir,
            show_halo=requested_show_halo,
        )
        self._set_status("Halos da similitude atualizados", 1.0)

    def _build_statistics_summary(self, analysis_type_key: str, result: Any) -> Optional[str]:
        """Gera resumo estatístico textual para o tipo de análise."""
        if result is None:
            return None

        analysis_type_key = str(analysis_type_key or "").lower()
        lines: list[str] = []

        if analysis_type_key == "statistics":
            stats_payload = {}
            if isinstance(result, dict):
                stats_payload = result.get("stats", {}) if isinstance(result.get("stats", {}), dict) else {}
            for key, value in stats_payload.items():
                label = str(key).replace("_", " ").title()
                if isinstance(value, float):
                    lines.append(f"{label}: {value:.4f}")
                else:
                    lines.append(f"{label}: {value}")

        elif analysis_type_key in {"similarity", "matrix_similarity"}:
            communities = self._result_attr(result, "communities")
            centrality = self._result_attr(result, "centrality")
            if isinstance(communities, dict) and communities:
                from collections import Counter

                community_values = list(communities.values())
                lines.append(f"Comunidades detectadas: {len(set(community_values))}")
                lines.append(f"Total de termos: {len(communities)}")
                lines.append("")
                lines.append("Distribuição por comunidade:")
                for community_id, count in sorted(Counter(community_values).items()):
                    lines.append(f"  Comunidade {community_id}: {count} termos")
            if isinstance(centrality, dict) and centrality:
                import heapq

                lines.append("")
                lines.append("Top 20 termos por centralidade:")
                for word, score in heapq.nlargest(20, centrality.items(), key=lambda item: float(item[1])):
                    lines.append(f"  {word}: {float(score):.4f}")

        elif analysis_type_key == "matrix_afc":
            eigenvalues = self._result_attr(result, "eigenvalues")
            inertia = self._result_attr(result, "inertia")
            explained = self._result_attr(result, "explained_variance")
            if inertia is not None:
                try:
                    lines.append(f"Inércia total: {float(inertia):.4f}")
                except Exception:
                    lines.append(f"Inércia total: {inertia}")
            if eigenvalues is not None:
                try:
                    eigen_seq = list(eigenvalues)
                except Exception:
                    eigen_seq = []
                if eigen_seq:
                    lines.append(f"Número de dimensões: {len(eigen_seq)}")
                    lines.append("")
                    lines.append("Autovalores:")
                    for idx, ev in enumerate(eigen_seq):
                        pct = 0.0
                        try:
                            if explained is not None and idx < len(explained):
                                pct = float(explained[idx])
                        except Exception:
                            pct = 0.0
                        try:
                            lines.append(f"  Dim {idx + 1}: {float(ev):.4f} ({pct:.1f}%)")
                        except Exception:
                            lines.append(f"  Dim {idx + 1}: {ev}")
            row_coords = self._result_attr(result, "row_coords")
            col_coords = self._result_attr(result, "col_coords")
            try:
                if row_coords is not None and hasattr(row_coords, "shape"):
                    lines.append(f"\nLinhas: {int(row_coords.shape[0])}")
            except Exception:
                pass
            try:
                if col_coords is not None and hasattr(col_coords, "shape"):
                    lines.append(f"Colunas: {int(col_coords.shape[0])}")
            except Exception:
                pass

        elif analysis_type_key in {"chd", "matrix_chd"}:
            n_classes = self._result_attr(result, "n_classes")
            class_sizes = self._result_attr(result, "class_sizes")
            if n_classes is not None:
                lines.append(f"Número de classes: {n_classes}")
            if isinstance(class_sizes, dict) and class_sizes:
                total = sum(int(v) for v in class_sizes.values())
                lines.append(f"Total de segmentos classificados: {total}")
                lines.append("")
                lines.append("Distribuição por classe:")
                for class_id, size in sorted(class_sizes.items()):
                    size_value = int(size)
                    pct = (size_value / total * 100.0) if total > 0 else 0.0
                    lines.append(f"  Classe {class_id}: {size_value} segmentos ({pct:.1f}%)")
            profiles = self._result_attr(result, "profiles")
            if isinstance(profiles, dict) and profiles:
                lines.append("")
                lines.append("Top 5 palavras por classe (chi²):")
                for class_id in sorted(profiles.keys()):
                    entries = profiles.get(class_id, [])[:5]
                    words = []
                    for entry in entries:
                        if isinstance(entry, (tuple, list)) and len(entry) >= 2:
                            try:
                                words.append(f"{entry[0]}({float(entry[1]):.1f})")
                            except Exception:
                                words.append(str(entry[0]))
                    lines.append(f"  Classe {class_id}: {', '.join(words)}")

        elif analysis_type_key == "wordcloud":
            words_displayed = self._result_attr(result, "words_displayed")
            word_freqs = self._result_attr(result, "word_frequencies")
            if words_displayed is not None:
                lines.append(f"Palavras exibidas: {words_displayed}")
            if isinstance(word_freqs, dict) and word_freqs:
                import heapq

                lines.append(f"Vocabulário total: {len(word_freqs)} palavras")
                lines.append(f"Frequência total: {sum(int(v) for v in word_freqs.values())}")
                lines.append("")
                lines.append("Top 20 palavras:")
                for word, freq in heapq.nlargest(20, word_freqs.items(), key=lambda item: int(item[1])):
                    lines.append(f"  {word}: {int(freq)}")

        elif analysis_type_key == "specificities":
            lines.append(f"Tipo de índice: {self._result_attr(result, 'index_type', '?')}")
            lines.append(f"Frequência mínima: {self._result_attr(result, 'min_freq', '?')}")
            lines.append(f"Backend: {self._result_attr(result, 'backend_used', '?')}")
            metadata_tokens = self._result_attr(result, "metadata_tokens", [])
            if metadata_tokens:
                lines.append(f"Variáveis analisadas: {', '.join(str(token) for token in metadata_tokens)}")
            scores_by_variable = self._result_attr(result, "scores_by_variable", {})
            if isinstance(scores_by_variable, dict):
                for variable, entries in scores_by_variable.items():
                    lines.append(f"\nVariável '{variable}': {len(entries)} termos")
                    for entry in list(entries)[:5]:
                        word = getattr(entry, "word", str(entry))
                        score = getattr(entry, "score", "?")
                        lines.append(f"  {word}: {score}")

        elif analysis_type_key == "prototypical":
            core = list(self._result_attr(result, "core", []) or [])
            first_periphery = list(self._result_attr(result, "first_periphery", []) or [])
            contrast_zone = list(self._result_attr(result, "contrast_zone", []) or [])
            second_periphery = list(self._result_attr(result, "second_periphery", []) or [])
            lines.append(f"Núcleo central: {len(core)} palavras")
            lines.append(f"1ª periferia: {len(first_periphery)} palavras")
            lines.append(f"Zona de contraste: {len(contrast_zone)} palavras")
            lines.append(f"2ª periferia: {len(second_periphery)} palavras")
            lines.append("")
            lines.append(f"Núcleo: {', '.join(core[:10])}")
            lines.append(f"1ª periferia: {', '.join(first_periphery[:10])}")

        elif analysis_type_key == "labbe":
            distance_matrix = self._result_attr(result, "distance_matrix")
            if distance_matrix is not None and hasattr(distance_matrix, "shape"):
                import numpy as np

                rows = int(distance_matrix.shape[0]) if len(distance_matrix.shape) > 0 else 0
                cols = int(distance_matrix.shape[1]) if len(distance_matrix.shape) > 1 else rows
                lines.append(f"Documentos comparados: {rows}")
                if rows * cols <= 2000000:
                    lines.append(f"Distância média: {float(np.mean(distance_matrix)):.4f}")
                    lines.append(f"Distância máxima: {float(np.max(distance_matrix)):.4f}")
                    if np.any(distance_matrix > 0):
                        lines.append(
                            f"Distância mínima (não-zero): {float(np.min(distance_matrix[distance_matrix > 0])):.4f}"
                        )
                else:
                    lines.append("Matriz grande: resumo estatístico detalhado omitido para manter desempenho.")

        elif analysis_type_key == "keyness_extra":
            lines.append(f"Variável: {self._result_attr(result, 'variable', '?')}")
            lines.append(f"Valor alvo: {self._result_attr(result, 'target_value', '?')}")
            top_terms = self._result_attr(result, "top_terms", []) or []
            lines.append(f"Termos significativos: {len(top_terms)}")
            if top_terms:
                lines.append("")
                lines.append("Top 10 termos:")
                for term in top_terms[:10]:
                    if isinstance(term, (tuple, list)) and len(term) >= 5:
                        lines.append(
                            f"  {term[0]}: keyness={float(term[1]):.2f} "
                            f"(alvo={int(term[2])}, ref={int(term[3])}, {term[4]})"
                        )

        elif analysis_type_key == "bigram_network_extra":
            lines.append(f"Nós: {self._result_attr(result, 'n_nodes', '?')}")
            lines.append(f"Arestas: {self._result_attr(result, 'n_edges', '?')}")

        elif analysis_type_key == "trigram_network_extra":
            lines.append(f"Nós: {self._result_attr(result, 'n_nodes', '?')}")
            lines.append(f"Arestas: {self._result_attr(result, 'n_edges', '?')}")

        elif analysis_type_key == "word_tree_extra":
            lines.append(f"Termo central: {self._result_attr(result, 'root_term', '?')}")
            lines.append(f"Ocorrências do termo central: {self._result_attr(result, 'root_frequency', '?')}")
            lines.append(f"Nós no grafo: {self._result_attr(result, 'n_nodes', '?')}")
            lines.append(f"Arestas no grafo: {self._result_attr(result, 'n_edges', '?')}")

        elif analysis_type_key == "network_text":
            report = self._result_attr(result, "report_data", {}) or {}
            lines.append(f"Nos: {report.get('n_nodes', self._result_attr(result, 'n_nodes', '?'))}")
            lines.append(f"Arestas: {report.get('n_edges', self._result_attr(result, 'n_edges', '?'))}")
            lines.append(f"Grau medio: {report.get('average_degree', self._result_attr(result, 'average_degree', '?'))}")
            lines.append(f"Densidade: {report.get('density', self._result_attr(result, 'density', '?'))}")
            lines.append(f"Diametro: {report.get('diameter', self._result_attr(result, 'diameter', '?'))}")
            lines.append(f"Modularidade: {report.get('modularity', self._result_attr(result, 'modularity_score', '?'))}")
            lines.append(f"Comunidades: {report.get('n_communities', self._result_attr(result, 'n_communities', '?'))}")
            lines.append(f"Layout: {report.get('layout', self._result_attr(result, 'layout_algorithm', '?'))}")
            lines.append(
                f"Backend layout: {report.get('layout_backend', self._result_attr(result, 'layout_backend_used', '?'))}"
            )
            lines.append(f"Selecao automatica: {report.get('auto_tune', '?')}")
            diag_path = report.get("diagnostics_path", self._result_attr(result, "diagnostics_path", ""))
            if diag_path:
                lines.append(f"Diagnostico: {diag_path}")
            net_path = self._result_attr(result, "net_path", "")
            if net_path:
                lines.append(f"Arquivo NET (Gephi/Pajek): {net_path}")
            top_degree = report.get("top_degree", [])
            if top_degree:
                lines.append("")
                lines.append("Top 10 por grau:")
                for word, score in top_degree:
                    lines.append(f"  {word}: {score}")

        elif analysis_type_key == "voyant_suite":
            lines.append(f"Documentos: {self._result_attr(result, 'n_documents', '?')}")
            lines.append(f"Segmentos: {self._result_attr(result, 'n_segments', '?')}")
            lines.append(f"Contextos KWIC: {self._result_attr(result, 'n_contexts', '?')}")
            selected_terms = self._result_attr(result, "selected_terms", []) or []
            query_terms = self._result_attr(result, "query_terms", []) or []
            if query_terms:
                lines.append(f"Consulta: {', '.join(str(term) for term in query_terms[:20])}")
            if selected_terms:
                lines.append("")
                lines.append("Top termos selecionados:")
                for term in selected_terms[:20]:
                    lines.append(f"  {term}")

        elif analysis_type_key == "wordfish_extra":
            lines.append(f"Documentos escalados: {self._result_attr(result, 'n_documents', '?')}")
            lines.append(f"Termos usados: {self._result_attr(result, 'n_terms', '?')}")

        elif analysis_type_key == "sentiment_extra":
            lines.append(f"Tokens com léxico: {self._result_attr(result, 'total_matched_tokens', '?')}")

        elif analysis_type_key == "emotions":
            totals = self._result_attr(result, "totals", {})
            if isinstance(totals, dict) and totals:
                lines.append("Contagem por emoção (NRC):")
                emotion_names_pt = {
                    "anger": "Raiva", "anticipation": "Antecipação",
                    "disgust": "Nojo", "fear": "Medo",
                    "joy": "Alegria", "sadness": "Tristeza",
                    "surprise": "Surpresa", "trust": "Confiança",
                    "positive": "Positivo", "negative": "Negativo",
                }
                for emotion, count in sorted(totals.items(), key=lambda item: -int(item[1])):
                    pt_name = emotion_names_pt.get(emotion, emotion.title())
                    lines.append(f"  {pt_name}: {int(count)}")

        elif analysis_type_key == "xray_extra":
            patterns = self._result_attr(result, "patterns", []) or []
            lines.append(f"Padrões buscados: {', '.join(patterns) if patterns else '?'}")
            lines.append(f"Ocorrências encontradas: {self._result_attr(result, 'n_points', '?')}")

        # Suite semantica
        elif analysis_type_key == "yake":
            keyphrases = self._result_attr(result, "keyphrases", [])
            if keyphrases:
                lines.append(f"Total de palavras-chave: {len(keyphrases)}")
                lines.append("")
                lines.append("Top 20 palavras-chave:")
                for kp in keyphrases[:20]:
                    phrase = getattr(kp, 'phrase', str(kp))
                    score = getattr(kp, 'score', 0)
                    freq = getattr(kp, 'frequency', 0)
                    lines.append(f"  {phrase}: score={score:.2f}, freq={freq}")

        elif analysis_type_key == "lda":
            model_result = self._result_attr(result, "model_result")
            if model_result:
                n_topics = getattr(model_result, 'n_topics', '?')
                perplexity = getattr(model_result, 'perplexity', None)
                backend = getattr(model_result, "backend", None)
                method = getattr(model_result, "method", None)
                k_requested = getattr(model_result, "k_requested", None)
                tuning_available = bool(getattr(model_result, "tuning_available", False))
                lines.append(f"Número de tópicos: {n_topics}")
                if k_requested is not None:
                    lines.append(f"k solicitado: {k_requested}")
                if method:
                    lines.append(f"Método: {method}")
                if backend:
                    lines.append(f"Backend: {backend}")
                if perplexity is not None:
                    lines.append(f"Perplexidade: {perplexity:.2f}")
                lines.append(f"Tuning de k: {'sim' if tuning_available else 'não'}")
                topic_terms = getattr(model_result, 'topic_terms', [])
                if topic_terms:
                    lines.append("")
                    lines.append("Tópicos identificados:")
                    for tt in topic_terms:
                        label = getattr(tt, 'label', f"Tópico {getattr(tt, 'topic_id', '?')}")
                        terms = getattr(tt, 'terms', [])
                        top_words = ", ".join(w for w, _ in terms[:8]) if terms else "?"
                        lines.append(f"  {label}: {top_words}")

        elif analysis_type_key in {"heatmap", "associative_heatmap"}:
            ranked_pairs = self._result_attr(result, "ranked_pairs", [])
            if ranked_pairs:
                lines.append(f"Total de pares associativos: {len(ranked_pairs)}")
                lines.append("")
                lines.append("Top 20 pares (PPMI):")
                for pair in ranked_pairs[:20]:
                    term_a = getattr(pair, 'term_a', '?')
                    term_b = getattr(pair, 'term_b', '?')
                    ppmi = getattr(pair, 'ppmi', 0)
                    lines.append(f"  {term_a} <-> {term_b}: {ppmi:.4f}")

        elif analysis_type_key == "thematic_map":
            lines.append(f"Nós: {self._result_attr(result, 'n_nodes', '?')}")
            lines.append(f"Arestas: {self._result_attr(result, 'n_edges', '?')}")
            lines.append(f"Comunidades: {self._result_attr(result, 'community_count', '?')}")

        elif analysis_type_key == "thematic_chd":
            chd_result = self._result_attr(result, "chd_result")
            if chd_result:
                class_text_paths = getattr(chd_result, 'class_text_paths', {}) or {}
                n_classes = len(class_text_paths) if class_text_paths else '?'
                lines.append(f"Número de classes CHD: {n_classes}")

        return "\n".join(lines).strip() if lines else None

    def _get_table_csv(self, analysis_type_key: str, result: Any) -> Optional[Path]:
        """Retorna caminho do CSV para exibir na aba Tabela."""
        if result is None:
            return None

        analysis_type_key = str(analysis_type_key or "").lower()
        csv_attr_map = {
            "similarity": ["adjacency_matrix"],
            "matrix_similarity": ["adjacency_matrix_path"],
            "specificities": ["scores_csv_path", "relative_csv_path", "lexical_table_path"],
            "keyness_extra": ["table_path"],
            "bigram_network_extra": ["edges_path"],
            "trigram_network_extra": ["edges_path", "combined_path"],
            "word_tree_extra": ["table_path"],
            "network_text": ["nodes_csv_path", "edges_csv_path"],
            "voyant_suite": [
                "document_terms_csv_path",
                "contexts_csv_path",
                "cooccurrences_csv_path",
                "trends_csv_path",
                "termsberry_nodes_csv_path",
                "termsberry_edges_csv_path",
                "bubblelines_points_csv_path",
            ],
            "wordfish_extra": ["scores_path"],
            "sentiment_extra": ["distribution_csv_path", "word_sentiment_csv_path", "timeline_csv_path"],
            "emotions": ["stats_csv_path", "words_summary_csv_path", "words_csv_path"],
            "xray_extra": ["points_path"],
            "matrix_chi2": ["contingency_csv_path", "expected_csv_path", "residuals_csv_path"],
            "matrix_frequency": ["summary_csv_path"],
            "matrix_chd": ["clusters_path"],
            # Suite semantica
            "yake": ["keyphrases_csv_path"],
            "lda": ["terms_beta_csv_path", "documents_gamma_csv_path", "topics_csv_path", "doc_topic_csv_path", "representative_sentences_csv_path", "tuning_csv_path", "topic_diagnostics_csv_path", "document_mixing_csv_path", "k_quality_csv_path", "stability_csv_path"],
            "heatmap": ["top_pairs_csv_path", "association_matrix_csv_path"],
            "associative_heatmap": ["top_pairs_csv_path", "association_matrix_csv_path"],
            "thematic_map": ["communities_csv_path", "strategic_map_csv_path", "representative_sentences_csv_path", "nodes_csv_path", "edges_csv_path"],
            "thematic_chd": ["class_topic_mix_csv_path"],
        }

        for attr in csv_attr_map.get(analysis_type_key, []):
            candidate = self._resolve_existing_file_path(self._result_attr(result, attr))
            if candidate is not None:
                return candidate

        if analysis_type_key == "wordcloud":
            return self._generate_wordcloud_csv(result)
        if analysis_type_key == "prototypical":
            return self._generate_prototypical_csv(result)

        # Fallback generico: BaseSemanticResult expoe primary_table_path()
        if hasattr(result, 'primary_table_path') and callable(result.primary_table_path):
            candidate = self._resolve_existing_file_path(result.primary_table_path())
            if candidate is not None:
                return candidate

        return None

    def _first_existing_path(self, candidates: List[Any]) -> Optional[Path]:
        """Retorna o primeiro caminho existente e válido da lista de candidatos."""
        for candidate in candidates:
            resolved = self._resolve_existing_file_path(candidate)
            if resolved is not None:
                return resolved
        return None

    def _collect_existing_paths(self, candidates: List[Any]) -> List[Path]:
        """Retorna caminhos existentes e únicos preservando ordem de prioridade."""
        collected: List[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            resolved = self._resolve_existing_file_path(candidate)
            if resolved is None:
                continue
            try:
                key = str(resolved.resolve())
            except Exception:
                key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            collected.append(resolved)
        return collected

    def _get_data_export_source(
        self,
        analysis_type_key: str,
        result: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        """Seleciona artefato de dados mais útil para exportação externa."""
        analysis_type_key = str(analysis_type_key or "").lower()
        meta = metadata if isinstance(metadata, dict) else {}

        result_attr_priority: Dict[str, List[str]] = {
            "network_text": ["net_path", "gexf_path", "nodes_csv_path", "edges_csv_path", "diagnostics_path"],
            "voyant_suite": [
                "document_terms_csv_path",
                "contexts_csv_path",
                "cooccurrences_csv_path",
                "trends_csv_path",
                "termsberry_nodes_csv_path",
                "termsberry_edges_csv_path",
                "bubblelines_points_csv_path",
                "summary_json_path",
            ],
            "specificities": ["scores_csv_path", "relative_csv_path", "lexical_table_path", "specificities_plot_data_path"],
            "statistics": ["stats_json_path", "report_txt"],
            "chd": ["metadata_profiles_path", "colored_corpus_path"],
            "keyness_extra": ["table_path"],
            "bigram_network_extra": ["edges_path"],
            "trigram_network_extra": ["edges_path", "combined_path"],
            "word_tree_extra": ["table_path"],
            "wordfish_extra": ["scores_path"],
            "sentiment_extra": ["distribution_csv_path", "word_sentiment_csv_path", "timeline_csv_path"],
            "xray_extra": ["points_path"],
            "matrix_similarity": ["adjacency_matrix_path"],
            "similarity": ["adjacency_matrix"],
            "matrix_chi2": ["contingency_csv_path", "expected_csv_path", "residuals_csv_path"],
            "matrix_frequency": ["summary_csv_path"],
            "matrix_chd": ["clusters_path"],
        }
        for attr in result_attr_priority.get(analysis_type_key, []):
            candidate = self._resolve_existing_file_path(self._result_attr(result, attr))
            if candidate is not None:
                return candidate

        metadata_priority: Dict[str, List[str]] = {
            "network_text": ["net_path", "gexf_path", "nodes_csv_path", "edges_csv_path", "diagnostics_path"],
            "voyant_suite": [
                "document_terms_csv_path",
                "contexts_csv_path",
                "cooccurrences_csv_path",
                "trends_csv_path",
                "termsberry_nodes_csv_path",
                "termsberry_edges_csv_path",
                "bubblelines_points_csv_path",
                "summary_json_path",
            ],
            "specificities": [
                "specificities_scores_csv_path",
                "specificities_relative_csv_path",
                "scores_csv_path",
                "table_csv_path",
            ],
            "statistics": ["statistics_json_path", "statistics_report_txt_path", "metadata_json_path"],
            "chd": ["chd_metadata_profiles_path", "chd_colored_corpus_path"],
        }
        for key in metadata_priority.get(analysis_type_key, []):
            candidate = self._resolve_existing_file_path(meta.get(key))
            if candidate is not None:
                return candidate

        table_candidate = self._get_table_csv(analysis_type_key, result)
        if table_candidate is not None:
            return table_candidate

        table_gallery = self._get_table_gallery(
            analysis_type_key=analysis_type_key,
            result=result,
            metadata=meta,
        )
        if table_gallery:
            first_table = next(iter(table_gallery.values()))
            if first_table.exists() and first_table.is_file():
                return first_table

        generic_meta_keys = [
            "table_csv_path",
            "adjacency_matrix_path",
            "nodes_csv_path",
            "edges_csv_path",
            "scores_csv_path",
            "distribution_csv_path",
            "word_sentiment_csv_path",
            "timeline_csv_path",
            "points_csv_path",
            "contingency_csv_path",
            "expected_csv_path",
            "residuals_csv_path",
            "matrix_clusters_path",
            "document_terms_csv_path",
            "contexts_csv_path",
            "cooccurrences_csv_path",
            "trends_csv_path",
            "termsberry_nodes_csv_path",
            "termsberry_edges_csv_path",
            "bubblelines_points_csv_path",
            "summary_json_path",
            "statistics_json_path",
            "statistics_report_txt_path",
            "net_path",
            "gexf_path",
            "diagnostics_path",
        ]
        return self._first_existing_path([meta.get(key) for key in generic_meta_keys])

    def _get_data_export_sources(
        self,
        analysis_type_key: str,
        result: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Path]:
        """Retorna lista de artefatos para exportação (1 arquivo ou pacote ZIP)."""
        analysis_type_key = str(analysis_type_key or "").lower()
        meta = metadata if isinstance(metadata, dict) else {}

        if analysis_type_key == "voyant_suite":
            candidates: List[Any] = [
                self._result_attr(result, "document_terms_csv_path"),
                self._result_attr(result, "contexts_csv_path"),
                self._result_attr(result, "cooccurrences_csv_path"),
                self._result_attr(result, "trends_csv_path"),
                self._result_attr(result, "termsberry_nodes_csv_path"),
                self._result_attr(result, "termsberry_edges_csv_path"),
                self._result_attr(result, "bubblelines_points_csv_path"),
                self._result_attr(result, "summary_json_path"),
                meta.get("document_terms_csv_path"),
                meta.get("contexts_csv_path"),
                meta.get("cooccurrences_csv_path"),
                meta.get("trends_csv_path"),
                meta.get("termsberry_nodes_csv_path"),
                meta.get("termsberry_edges_csv_path"),
                meta.get("bubblelines_points_csv_path"),
                meta.get("summary_json_path"),
            ]
            table_gallery = self._get_table_gallery(
                analysis_type_key=analysis_type_key,
                result=result,
                metadata=meta,
            )
            candidates.extend(list(table_gallery.values()))
            sources = self._collect_existing_paths(candidates)
            if sources:
                return sources

        if analysis_type_key == "emotions":
            candidates = [
                self._result_attr(result, "stats_csv_path"),
                self._result_attr(result, "words_summary_csv_path"),
                self._result_attr(result, "words_csv_path"),
                meta.get("stats_csv_path"),
                meta.get("words_summary_csv_path"),
                meta.get("words_csv_path"),
            ]
            table_gallery = self._get_table_gallery(
                analysis_type_key=analysis_type_key,
                result=result,
                metadata=meta,
            )
            candidates.extend(list(table_gallery.values()))
            sources = self._collect_existing_paths(candidates)
            if sources:
                return sources

        if analysis_type_key == "chd":
            candidates = [
                self._result_attr(result, "metadata_profiles_path"),
                self._result_attr(result, "colored_corpus_path"),
                self._result_attr(result, "chistable_path"),
                self._result_attr(result, "afc_row_path"),
                self._result_attr(result, "afc_col_path"),
                self._result_attr(result, "row_coords_path"),
                self._result_attr(result, "col_coords_path"),
                self._result_attr(result, "afc_facteur_path"),
                self._result_attr(result, "afc2dl_notplotted_path"),
                self._result_attr(result, "eigenvalues_path"),
                self._result_attr(result, "manifest_path"),
                meta.get("chd_metadata_profiles_path"),
                meta.get("chd_colored_corpus_path"),
                meta.get("chd_chistable_path"),
                meta.get("chd_afc_row_path"),
                meta.get("chd_afc_col_path"),
                meta.get("chd_row_coords_path"),
                meta.get("chd_col_coords_path"),
                meta.get("chd_afc_facteur_path"),
                meta.get("chd_afc2dl_notplotted_path"),
                meta.get("chd_eigenvalues_path"),
                meta.get("chd_manifest_path"),
            ]
            class_text_paths = self._result_attr(result, "class_text_paths", {})
            if isinstance(class_text_paths, dict):
                candidates.extend(list(class_text_paths.values()))
            raw_class_text_paths = meta.get("chd_class_text_paths")
            if isinstance(raw_class_text_paths, dict):
                candidates.extend(list(raw_class_text_paths.values()))
            sources = self._collect_existing_paths(candidates)
            if sources:
                return sources

        single = self._get_data_export_source(
            analysis_type_key=analysis_type_key,
            result=result,
            metadata=meta,
        )
        return [single] if single is not None else []

    def _get_table_gallery(
        self,
        analysis_type_key: str,
        result: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Path]:
        """Monta colecao ordenada de tabelas para sub-abas da tabela."""
        analysis_type_key = str(analysis_type_key or "").lower()
        gallery: Dict[str, Path] = {}
        seen_paths: set[str] = set()

        def add(label: str, candidate: Any) -> None:
            self._append_table_gallery_item(gallery, seen_paths, label, candidate)

        meta = metadata if isinstance(metadata, dict) else {}
        if analysis_type_key == "voyant_suite":
            payload = self._extract_voyant_payload(result=result, metadata=meta)
            payload_tables = payload.get("tables", {}) if isinstance(payload, dict) else {}
            panel_titles = self._voyant_panel_titles_pt()
            if isinstance(payload_tables, dict):
                for panel_id in self._voyant_panel_order():
                    item = payload_tables.get(str(panel_id), {})
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title_pt", panel_titles.get(str(panel_id), str(panel_id))))
                    add(title, item.get("csv_path"))
                    extra_csv = item.get("extra_csv", [])
                    if isinstance(extra_csv, list):
                        for extra in extra_csv:
                            if not isinstance(extra, dict):
                                continue
                            extra_title = str(extra.get("title_pt", extra.get("id", "Tabela")))
                            add(extra_title, extra.get("csv_path"))

        raw_gallery = meta.get("table_gallery")
        if isinstance(raw_gallery, dict):
            for raw_label, raw_path in raw_gallery.items():
                add(str(raw_label), raw_path)

        meta_table_keys = [
            ("Tabela", "table_csv_path"),
            ("Adjacencia", "adjacency_matrix_path"),
            ("Nos", "nodes_csv_path"),
            ("Arestas", "edges_csv_path"),
            ("Scores", "scores_csv_path"),
            ("Distribuicao", "distribution_csv_path"),
            ("Palavras por sentimento", "word_sentiment_csv_path"),
            ("Linha do tempo", "timeline_csv_path"),
            ("Pontos", "points_csv_path"),
            ("Contingencia", "contingency_csv_path"),
            ("Esperada", "expected_csv_path"),
            ("Residuos", "residuals_csv_path"),
            ("Clusters", "matrix_clusters_path"),
            ("Especificidades (scores)", "specificities_scores_csv_path"),
            ("Especificidades (relativo)", "specificities_relative_csv_path"),
            ("Termos do documento", "document_terms_csv_path"),
            ("Contextos", "contexts_csv_path"),
            ("Co-ocorrências", "cooccurrences_csv_path"),
            ("Tendências", "trends_csv_path"),
            ("Nos TermsBerry", "termsberry_nodes_csv_path"),
            ("Arestas TermsBerry", "termsberry_edges_csv_path"),
            ("Gráfico de bolhas (Pontos)", "bubblelines_points_csv_path"),
        ]
        for label, key in meta_table_keys:
            add(label, meta.get(key))

        attr_map = {
            "specificities": [
                ("Scores", "scores_csv_path"),
                ("Relativo", "relative_csv_path"),
                ("Tabela lexical", "lexical_table_path"),
            ],
            "network_text": [
                ("Nos", "nodes_csv_path"),
                ("Arestas", "edges_csv_path"),
            ],
            "sentiment_extra": [
                ("Distribuicao", "distribution_csv_path"),
                ("Palavras", "word_sentiment_csv_path"),
                ("Timeline", "timeline_csv_path"),
            ],
            "emotions": [
                ("Emoções por texto", "stats_csv_path"),
                ("Resumo por emoção", "words_summary_csv_path"),
                ("Ocorrências por token", "words_csv_path"),
            ],
            "matrix_chi2": [
                ("Contingencia", "contingency_csv_path"),
                ("Esperada", "expected_csv_path"),
                ("Residuos", "residuals_csv_path"),
            ],
            "voyant_suite": [
                ("Termos do documento", "document_terms_csv_path"),
                ("Contextos", "contexts_csv_path"),
                ("Co-ocorrências", "cooccurrences_csv_path"),
                ("Tendências", "trends_csv_path"),
                ("Nos TermsBerry", "termsberry_nodes_csv_path"),
                ("Arestas TermsBerry", "termsberry_edges_csv_path"),
                ("Gráfico de bolhas (Pontos)", "bubblelines_points_csv_path"),
            ],
            # Suite semantica
            "yake": [("Palavras-Chave", "keyphrases_csv_path")],
            "lda": [
                ("Termos por Tópico (beta)", "terms_beta_csv_path"),
                ("Prevalência Doc-Tópico (gamma)", "documents_gamma_csv_path"),
                ("Distribuição Doc-Tópico", "doc_topic_csv_path"),
                ("Termos por Tópico (compat)", "topics_csv_path"),
                ("Frases Representativas", "representative_sentences_csv_path"),
                ("Tuning de k", "tuning_csv_path"),
                ("Diagnóstico de Tópicos", "topic_diagnostics_csv_path"),
                ("Documentos Misturados", "document_mixing_csv_path"),
                ("Qualidade por K", "k_quality_csv_path"),
                ("Estabilidade por Seed", "stability_csv_path"),
            ],
            "heatmap": [("Pares Associativos", "top_pairs_csv_path"), ("Matriz", "association_matrix_csv_path")],
            "associative_heatmap": [("Pares Associativos", "top_pairs_csv_path"), ("Matriz", "association_matrix_csv_path")],
            "thematic_map": [
                ("Comunidades Temáticas", "communities_csv_path"),
                ("Mapa Estratégico", "strategic_map_csv_path"),
                ("Frases Representativas", "representative_sentences_csv_path"),
                ("Nós", "nodes_csv_path"),
                ("Arestas", "edges_csv_path"),
            ],
            "thematic_chd": [("Classe-Topico", "class_topic_mix_csv_path")],
        }
        for label, attr in attr_map.get(analysis_type_key, []):
            add(label, self._result_attr(result, attr))

        if not gallery:
            primary = self._get_table_csv(analysis_type_key, result)
            if primary is not None:
                add("Tabela", primary)

        return gallery

    def _generate_wordcloud_csv(self, result: Any) -> Optional[Path]:
        """Gera CSV temporário com frequências do wordcloud."""
        word_frequencies = self._result_attr(result, "word_frequencies")
        if not isinstance(word_frequencies, dict) or not word_frequencies:
            return None
        output_dir = self._get_analysis_output_dir("wordcloud")
        csv_path = Path(output_dir) / "word_frequencies.csv"
        try:
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Palavra", "Frequência"])
                for word, freq in sorted(word_frequencies.items(), key=lambda item: -int(item[1])):
                    writer.writerow([word, int(freq)])
            return csv_path if csv_path.exists() else None
        except Exception as exc:
            log.warning("Falha ao gerar CSV de wordcloud: %s", exc)
            return None

    def _generate_prototypical_csv(self, result: Any) -> Optional[Path]:
        """Gera CSV temporário com quadrantes da análise prototípica."""
        core = list(self._result_attr(result, "core", []) or [])
        first_periphery = list(self._result_attr(result, "first_periphery", []) or [])
        contrast_zone = list(self._result_attr(result, "contrast_zone", []) or [])
        second_periphery = list(self._result_attr(result, "second_periphery", []) or [])
        if not any([core, first_periphery, contrast_zone, second_periphery]):
            return None

        output_dir = self._get_analysis_output_dir("prototypical")
        csv_path = Path(output_dir) / "prototypical_quadrants.csv"
        try:
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Palavra", "Quadrante"])
                for word in core:
                    writer.writerow([word, "Núcleo Central"])
                for word in first_periphery:
                    writer.writerow([word, "1ª Periferia"])
                for word in contrast_zone:
                    writer.writerow([word, "Zona de Contraste"])
                for word in second_periphery:
                    writer.writerow([word, "2ª Periferia"])
            return csv_path if csv_path.exists() else None
        except Exception as exc:
            log.warning("Falha ao gerar CSV prototípico: %s", exc)
            return None

    def _generate_labbe_csv(self, result: Any) -> Optional[Path]:
        """Gera CSV temporário com matriz de distância Labbé."""
        distance_matrix = self._result_attr(result, "distance_matrix")
        if distance_matrix is None or not hasattr(distance_matrix, "shape"):
            return None
        output_dir = self._get_analysis_output_dir("labbe")
        csv_path = Path(output_dir) / "labbe_distance.csv"
        try:
            n_rows = int(distance_matrix.shape[0])
            headers = [""] + [f"doc_{idx + 1}" for idx in range(n_rows)]
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(headers)
                for row_idx in range(n_rows):
                    row = [f"doc_{row_idx + 1}"]
                    row.extend(float(distance_matrix[row_idx, col_idx]) for col_idx in range(n_rows))
                    writer.writerow(row)
            return csv_path if csv_path.exists() else None
        except Exception as exc:
            log.warning("Falha ao gerar CSV Labbé: %s", exc)
            return None

    def _populate_all_tabs(
        self,
        analysis_type_key: str,
        result: Any,
        artifact_path: Optional[Path],
        report_path: Optional[Path],
        skip_statistics: bool = False,
    ) -> None:
        """Popula as abas de conteúdo na ordem: Estatísticas -> Tabela -> Gráfico."""
        analysis_type_key = str(analysis_type_key or "").lower()
        self._ensure_results_workspace()
        viewer = self.results_viewer
        if hasattr(viewer, "set_data_export_source"):
            export_sources = self._get_data_export_sources(
                analysis_type_key=analysis_type_key,
                result=result,
            )
            viewer.set_data_export_source(
                export_sources if export_sources else None
            )
        elif hasattr(viewer, "set_network_net_path"):
            if analysis_type_key == "network_text":
                viewer.set_network_net_path(self._result_attr(result, "net_path"))
            else:
                viewer.set_network_net_path(None)

        if not skip_statistics:
            try:
                if analysis_type_key == "statistics":
                    stats_payload = self._result_attr(result, "stats", {})
                    if isinstance(stats_payload, dict) and stats_payload:
                        viewer.show_statistics(stats_payload)
                    else:
                        stats_text = self._build_statistics_summary(analysis_type_key, result)
                        if stats_text:
                            viewer.show_text(
                                stats_text,
                                title=f"Estatísticas - {analysis_type_key.upper()}",
                            )
                else:
                    stats_text = self._build_statistics_summary(analysis_type_key, result)
                    if stats_text:
                        viewer.show_text(
                            stats_text,
                            title=f"Estatísticas - {analysis_type_key.upper()}",
                        )
            except Exception:
                log.exception("Falha ao renderizar aba de estatísticas (%s)", analysis_type_key)

        voyant_rendered = False
        if analysis_type_key == "voyant_suite" and hasattr(viewer, "show_voyant_suite"):
            payload = self._extract_voyant_payload(result=result)
            if payload:
                try:
                    viewer.show_voyant_suite(payload)
                    voyant_rendered = True
                except Exception:
                    log.exception("Falha no render dedicado da suíte Voyant; aplicando fallback padrão.")

        # Fluxo especial CHD: tabela rica (show_chd_profiles) + galeria de imagens.
        if analysis_type_key == "chd" and result is not None:
            try:
                profiles = getattr(result, "profiles", None)
                class_sizes = getattr(result, "class_sizes", None)
                if profiles and class_sizes and hasattr(viewer, "show_chd_profiles"):
                    viewer.show_chd_profiles(profiles, class_sizes, result=result)
            except Exception:
                log.exception("Falha ao renderizar perfis CHD.")
            try:
                chd_gallery = self._get_image_gallery(
                    analysis_type_key="chd",
                    result=result,
                    artifact_path=artifact_path,
                )
                if chd_gallery:
                    if hasattr(viewer, "show_image_gallery"):
                        viewer.show_image_gallery(chd_gallery, default_label="Dendrograma")
                    else:
                        self._show_image_gallery(chd_gallery)
                    self._apply_graph_default_zoom_for_analysis("chd")
            except Exception:
                log.exception("Falha ao renderizar galeria CHD.")
            try:
                if hasattr(viewer, "set_data_export_source"):
                    export_sources = self._get_data_export_sources(
                        analysis_type_key="chd",
                        result=result,
                    )
                    viewer.set_data_export_source(
                        export_sources if export_sources else None
                    )
            except Exception:
                log.exception("Falha ao configurar exportação de dados CHD.")

        if not voyant_rendered and analysis_type_key != "chd":
            try:
                table_gallery = self._get_table_gallery(
                    analysis_type_key=analysis_type_key,
                    result=result,
                )
                if table_gallery:
                    if hasattr(viewer, "show_table_gallery"):
                        viewer.show_table_gallery(table_gallery)
                    else:
                        first_table = next(iter(table_gallery.values()))
                        viewer.show_table(first_table)
            except Exception:
                log.exception("Falha ao renderizar aba de tabelas (%s)", analysis_type_key)

            try:
                image_gallery = self._get_image_gallery(
                    analysis_type_key=analysis_type_key,
                    result=result,
                    artifact_path=artifact_path,
                )
                if image_gallery:
                    self._show_image_gallery(image_gallery)
                    self._apply_graph_default_zoom_for_analysis(analysis_type_key)
            except Exception:
                log.exception("Falha ao renderizar aba de gráficos (%s)", analysis_type_key)

        if report_path and hasattr(viewer, "set_report_path"):
            try:
                viewer.set_report_path(report_path)
            except Exception:
                log.exception("Falha ao renderizar aba de relatório (%s)", analysis_type_key)

    def _populate_tabs_from_history_metadata(
        self,
        entry: Any,
        artifact_path: Optional[Path],
        report_path: Optional[Path],
        skip_statistics: bool = False,
    ) -> None:
        """Popula abas usando metadados quando o objeto resultado não está disponível."""
        analysis_type_key = str(getattr(entry, "analysis_type", "")).lower()
        raw_metadata = getattr(entry, "metadata", {})
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        if isinstance(raw_metadata, str):
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}

        viewer = self.results_viewer
        if hasattr(viewer, "set_data_export_source"):
            export_sources = self._get_data_export_sources(
                analysis_type_key=analysis_type_key,
                result=None,
                metadata=metadata,
            )
            viewer.set_data_export_source(
                export_sources if export_sources else None
            )
        elif hasattr(viewer, "set_network_net_path"):
            if analysis_type_key == "network_text":
                viewer.set_network_net_path(metadata.get("net_path"))
            else:
                viewer.set_network_net_path(None)

        if not skip_statistics:
            try:
                lines = [f"Tipo de análise: {analysis_type_key.upper()}"]
                backend = metadata.get("backend_used")
                if backend:
                    lines.append(f"Backend: {backend}")
                n_classes = metadata.get("n_classes")
                if n_classes:
                    lines.append(f"Número de classes: {n_classes}")
                index_type = metadata.get("index_type")
                if index_type:
                    lines.append(f"Índice: {index_type}")
                min_freq = metadata.get("min_freq")
                if min_freq:
                    lines.append(f"Frequência mínima: {min_freq}")
                if analysis_type_key == "network_text":
                    n_communities = metadata.get("n_communities")
                    if n_communities is not None:
                        lines.append(f"Comunidades: {n_communities}")
                    modularity_score = metadata.get("modularity_score")
                    if modularity_score is not None:
                        lines.append(f"Modularidade: {modularity_score}")
                if analysis_type_key == "voyant_suite":
                    lines.append(f"Documentos: {metadata.get('n_documents', '?')}")
                    lines.append(f"Segmentos: {metadata.get('n_segments', '?')}")
                    lines.append(f"Contextos KWIC: {metadata.get('n_contexts', '?')}")
                    selected_terms = metadata.get("selected_terms", [])
                    if isinstance(selected_terms, list) and selected_terms:
                        preview = ", ".join(str(term) for term in selected_terms[:15])
                        lines.append(f"Top termos: {preview}")
                viewer.show_text(
                    "\n".join(lines),
                    title=f"Estatísticas - {analysis_type_key.upper()}",
                )
            except Exception:
                log.exception("Falha ao restaurar estatísticas do histórico (%s)", analysis_type_key)

        voyant_rendered = False
        if analysis_type_key == "voyant_suite" and hasattr(viewer, "show_voyant_suite"):
            payload = self._extract_voyant_payload(result=None, metadata=metadata)
            if payload:
                try:
                    viewer.show_voyant_suite(payload)
                    voyant_rendered = True
                except Exception:
                    log.exception("Falha ao restaurar visualização dedicada Voyant do histórico.")

        if not voyant_rendered:
            try:
                table_gallery = self._get_table_gallery(
                    analysis_type_key=analysis_type_key,
                    result=None,
                    metadata=metadata,
                )
                if table_gallery:
                    if hasattr(viewer, "show_table_gallery"):
                        viewer.show_table_gallery(table_gallery)
                    else:
                        first_table = next(iter(table_gallery.values()))
                        viewer.show_table(first_table)
            except Exception:
                log.exception("Falha ao restaurar tabela do histórico (%s)", analysis_type_key)

            try:
                image_gallery = self._get_image_gallery(
                    analysis_type_key=analysis_type_key,
                    result=None,
                    artifact_path=artifact_path,
                    metadata=metadata,
                )
                if image_gallery:
                    self._show_image_gallery(image_gallery)
                    self._apply_graph_default_zoom_for_analysis(analysis_type_key)
            except Exception:
                log.exception("Falha ao restaurar gráfico do histórico (%s)", analysis_type_key)

        if report_path and hasattr(viewer, "set_report_path"):
            try:
                viewer.set_report_path(report_path)
            except Exception:
                log.exception("Falha ao restaurar relatório do histórico (%s)", analysis_type_key)

    def _apply_graph_default_zoom_for_analysis(self, analysis_type_key: str) -> None:
        """Aplica zoom padrão por tipo de análise após render da aba Gráfico."""
        key = str(analysis_type_key or "").lower()
        if key != "network_text":
            return
        viewer = getattr(self, "results_viewer", None)
        if viewer is None:
            return
        try:
            if hasattr(viewer, "set_graph_zoom_percent"):
                viewer.set_graph_zoom_percent(60, sync=False, persist=True)
                return
            if hasattr(viewer, "_set_zoom"):
                viewer._set_zoom("Gráfico", 60, sync=False)
            if hasattr(viewer, "_sync_active_tab_state"):
                viewer._sync_active_tab_state()
        except Exception:
            log.exception("Falha ao aplicar zoom padrão de rede (60%%).")

    def _run_chd(self):
        """Abre dialogo de CHD."""
        from .dialogs.analysis_dialog import CHDDialog  # lazy import
        if not self.corpus:
            return

        dialog = CHDDialog(self, initial_params=self._get_initial_analysis_params("chd"))
        params = dialog.get_result()
        
        if params:
            self._remember_analysis_params("chd", params)
            self._execute_analysis_async('CHD', params)

    def _run_similarity(self):
        """Abre dialogo de similaridade."""
        from .dialogs.analysis_dialog import SimilarityDialog  # lazy import
        from .dialogs.word_selector_dialog import WordSelectorDialog  # lazy import
        if not self.corpus:
            return

        dialog = SimilarityDialog(self, initial_params=self._get_initial_analysis_params("similarity"))
        params = dialog.get_result()
        
        if params:
            use_lemmas = bool(params.get("use_lemmas", True))
            selector = WordSelectorDialog(
                self,
                self.corpus,
                max_words=int(params.get("max_words", 50)),
                min_freq=int(params.get("min_freq", 3)),
                use_lemmas=use_lemmas,
            )
            selected_words = selector.get_result()
            if selected_words is None:
                return
            params["selected_words"] = selected_words
            params["selected_words_explicit"] = bool(selected_words)
            self._remember_analysis_params("similarity", params)
            self._execute_analysis_async('Similitude', params)

    def _run_wordcloud(self):
        """Abre dialogo de word cloud."""
        from .dialogs.analysis_dialog import WordCloudDialog  # lazy import
        if not self.corpus:
            return

        dialog = WordCloudDialog(self, initial_params=self._get_initial_analysis_params("wordcloud"))
        params = dialog.get_result()
        
        if params:
            self._remember_analysis_params("wordcloud", params)
            self._execute_analysis_async('Nuvem de Palavras', params)

    def _run_specificities(self):
        """Abre dialogo de especificidades lexicais."""
        from .dialogs.specificities_dialog import SpecificitiesDialog  # lazy import
        if not self.corpus:
            return

        metadata_tokens = sorted(self.corpus.make_etoiles())
        dialog = SpecificitiesDialog(
            self,
            metadata_tokens=metadata_tokens,
            initial_params=self._get_initial_analysis_params("specificities"),
        )
        params = dialog.get_result()

        if params:
            self._remember_analysis_params("specificities", params)
            self._execute_analysis_async('Especificidades', params)

    def _run_concordance(self):
        """Abre dialogo de concordancia (KWIC)."""
        from .dialogs.concordance_dialog import ConcordanceDialog  # lazy import
        if not self.corpus:
            return

        try:
            self._set_status("Abrindo concordância...", 0.2)
            ConcordanceDialog(self, self.corpus)
            self._set_status("Concordância pronta", 1.0)
        except Exception as exc:
            log.exception("Erro ao abrir concordancia")
            show_error(self, error=exc)
            self._set_status("Erro na concordância", 0)

    def _run_voyant_suite(self):
        """Abre dialogo do pacote lexical inspirado no Voyant."""
        from .dialogs.analysis_dialog import VoyantSuiteDialog  # lazy import
        if not self.corpus:
            return
        if not self._voyant_suite_enabled:
            show_error(
                self,
                what="Pacote Voyant desativado na configuração.",
                why="A flag features.voyant_suite.enabled está desligada.",
                how="Ative a flag em config.json para executar a suíte Voyant.",
            )
            return

        dialog = VoyantSuiteDialog(
            self,
            initial_params=self._get_initial_analysis_params("voyant_suite"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("voyant_suite", params)
            self._execute_analysis_async("Pacote Voyant", params)

    def _run_prototypical(self):
        """Abre dialogo da analise prototipica."""
        from .dialogs.analysis_dialog import PrototypicalDialog  # lazy import
        if not self.corpus:
            return

        dialog = PrototypicalDialog(
            self,
            initial_params=self._get_initial_analysis_params("prototypical"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("prototypical", params)
            self._execute_analysis_async("Prototípica", params)

    def _run_labbe(self):
        """Abre dialogo da distancia de Labbe."""
        from .dialogs.analysis_dialog import LabbeDialog  # lazy import
        if not self.corpus:
            return

        dialog = LabbeDialog(
            self,
            initial_params=self._get_initial_analysis_params("labbe"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("labbe", params)
            self._execute_analysis_async("Dist. Labbé", params)

    def _run_keyness_extra(self):
        """Abre dialogo da análise Keyness extra."""
        from .dialogs.analysis_dialog import KeynessExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = KeynessExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("keyness_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("keyness_extra", params)
            self._execute_analysis_async("Keyness (Extra)", params)

    def _run_bigram_network_extra(self):
        """Abre dialogo da rede de coocorrência por bigramas."""
        from .dialogs.analysis_dialog import BigramNetworkExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = BigramNetworkExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("bigram_network_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("bigram_network_extra", params)
            self._execute_analysis_async("Rede Bigramas (Extra)", params)

    def _run_trigram_network_extra(self):
        """Abre dialogo da rede de coocorrência por trigramas."""
        from .dialogs.analysis_dialog import TrigramNetworkExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = TrigramNetworkExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("trigram_network_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("trigram_network_extra", params)
            self._execute_analysis_async("Rede Trigramas (Extra)", params)

    def _run_word_tree_extra(self):
        """Abre dialogo da árvore de palavras."""
        from .dialogs.analysis_dialog import WordTreeExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = WordTreeExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("word_tree_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("word_tree_extra", params)
            self._execute_analysis_async("Word Tree (Extra)", params)

    def _run_network_text_analysis(self):
        """Abre dialogo da analise de rede textual."""
        from .dialogs.network_analysis_dialog import NetworkAnalysisDialog  # lazy import
        if not self.corpus:
            return
        dialog = NetworkAnalysisDialog(
            self,
            initial_params=self._get_initial_analysis_params("network_text"),
            default_params=self._get_original_analysis_defaults("network_text"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("network_text", params)
            self._execute_analysis_async("Rede Textual (Extra)", params)

    def _run_cca_analysis(self):
        """Abre o diálogo de Connected Concept Analysis (Textometrica)."""
        from .dialogs.cca_dialog import CCADialog  # lazy import
        if not self.corpus:
            messagebox.showinfo(
                "Nenhum corpus",
                "Importe um corpus antes de executar a CCA.",
                parent=self,
            )
            return

        corpus_text = getattr(self, "_last_corpus_text", "") or ""
        if not corpus_text.strip():
            try:
                corpus_text = self._build_corpus_snapshot_text()
            except Exception:
                corpus_text = ""

        if not corpus_text.strip():
            messagebox.showinfo(
                "Corpus vazio",
                "O corpus atual não tem texto para analisar.",
                parent=self,
            )
            return

        output_dir = None
        if self._analysis_output_root:
            output_dir = Path(self._analysis_output_root) / "cca"

        CCADialog(self, corpus_text=corpus_text, output_dir=output_dir)

    def _run_rolling_window(self):
        """Abre diálogo de Rolling Window Analysis (Lexos-inspired)."""
        from .dialogs.rolling_window_dialog import RollingWindowDialog  # lazy import
        if not self.corpus:
            messagebox.showinfo(
                "Nenhum corpus",
                "Importe um corpus antes de executar o Rolling Window.",
                parent=self,
            )
            return

        corpus_text = getattr(self, "_last_corpus_text", "") or ""
        if not corpus_text.strip():
            try:
                corpus_text = self._build_corpus_snapshot_text()
            except Exception:
                corpus_text = ""

        if not corpus_text.strip():
            messagebox.showinfo(
                "Corpus vazio",
                "O corpus atual não tem texto para analisar.",
                parent=self,
            )
            return

        output_dir = None
        if self._analysis_output_root:
            output_dir = Path(self._analysis_output_root) / "rolling_window"

        RollingWindowDialog(self, corpus_text=corpus_text, output_dir=output_dir)

    def _run_keyness(self):
        """Abre o diálogo de Keyness / Comparação de corpora."""
        from .dialogs.keyness_dialog import KeynessDialog  # lazy import
        corpus_text = getattr(self, "_last_corpus_text", "") or ""
        if not corpus_text.strip() and self.corpus:
            try:
                corpus_text = self._build_corpus_snapshot_text()
            except Exception:
                corpus_text = ""

        name_a = "Corpus atual"
        if self._last_import_file_path:
            name_a = self._last_import_file_path.stem

        KeynessDialog(
            self,
            corpus_text_a=corpus_text or None,
            corpus_name_a=name_a,
        )

    def _run_wordfish_extra(self):
        """Abre dialogo do escalonamento 1D (Wordfish extra)."""
        from .dialogs.analysis_dialog import WordfishExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = WordfishExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("wordfish_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("wordfish_extra", params)
            self._execute_analysis_async("Wordfish (Extra)", params)

    def _run_xray_extra(self):
        """Abre dialogo da dispersão x-ray extra."""
        from .dialogs.analysis_dialog import XRayExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = XRayExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("xray_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("xray_extra", params)
            self._execute_analysis_async("X-Ray (Extra)", params)

    def _run_sentiment_extra(self):
        """Abre dialogo da análise de sentimentos extra."""
        from .dialogs.analysis_dialog import SentimentExtraDialog  # lazy import
        if not self.corpus:
            return
        dialog = SentimentExtraDialog(
            self,
            initial_params=self._get_initial_analysis_params("sentiment_extra"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("sentiment_extra", params)
            self._execute_analysis_async("Sentimentos (Extra)", params)

    def _run_emotions(self):
        """Abre dialogo da análise de emoções (NRC / syuzhet)."""
        from .dialogs.emotions_dialog import EmotionsDialog  # lazy import
        if not self.corpus:
            return
        dialog = EmotionsDialog(
            self,
            initial_params=self._get_initial_analysis_params("emotions"),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params("emotions", params)
            self._execute_analysis_async("Emoções (NRC)", params)

    def _run_semantic_analysis(self, registry_key: str):
        """Abre dialogo e executa uma analise da suite semantica."""
        if not self.corpus:
            return
        entry = SEMANTIC_REGISTRY.get(registry_key)
        if not entry:
            return
        dialog = entry.dialog_class(
            self,
            initial_params=self._get_initial_analysis_params(registry_key),
        )
        params = dialog.get_result()
        if params:
            self._remember_analysis_params(registry_key, params)
            self._execute_semantic_analysis_async(registry_key, params, entry)

    def _corpus_has_multiword_expressions(self) -> bool:
        metadata = dict(getattr(self, "_last_import_metadata", {}) or {})
        if int(metadata.get("multiword_selected_count", 0) or 0) > 0:
            return True
        formes = getattr(getattr(self, "corpus", None), "formes", {}) or {}
        try:
            return any("_" in str(key) for key in formes.keys())
        except Exception:
            return False

    def _execute_semantic_analysis_async(self, registry_key: str, params: dict, entry: SemanticAnalysisEntry):
        """Executa analise semantica em background usando a registry."""
        self._set_status(f"Executando {entry.display_name}...", 0.3)
        self._enable_analysis_buttons(False)
        self._prepare_new_analysis_run()
        request_params = dict(params or {})
        request_params.pop("analysis_type", None)

        def run():
            try:
                output_dir = self._get_analysis_output_dir(registry_key)
                log.info(
                    "Semantic analysis '%s': output_dir=%s (type=%s, exists=%s), "
                    "corpus=%s, params_keys=%s",
                    registry_key, output_dir, type(output_dir).__name__,
                    output_dir.exists() if output_dir else "N/A",
                    type(self.corpus).__name__ if self.corpus else "None",
                    list(request_params.keys()),
                )

                result = entry.runner_factory(
                    corpus=self.corpus,
                    output_dir=output_dir,
                    **request_params
                )
                
                self._last_analysis_context = {
                    "name": entry.display_name,
                    "analysis_type": registry_key,
                    "params": request_params,
                    "output_dir": str(output_dir),
                }
                self._last_analysis_result = result
                
                # Prepara metadados pro historico via adapter
                base_metadata = {
                    "analysis_name": entry.display_name,
                    "has_visualization": True  # Assumimos que a suite sempre gera views
                }
                if entry.history_metadata_adapter:
                    extra_meta = entry.history_metadata_adapter(result)
                    if isinstance(extra_meta, dict):
                        base_metadata.update(extra_meta)
                        
                saved_entry = self.analysis_history.save_result(
                    analysis_type=entry.report_mode,
                    params=request_params,
                    result_path=str(output_dir),
                    metadata=base_metadata,
                )
                self._last_saved_history_entry_id = saved_entry.entry_id
                
                self.after(0, lambda: self._on_analysis_complete(
                    entry.report_mode, str(output_dir)
                ))
            except Exception as e:
                log.exception(f"Erro em _execute_semantic_analysis_async ({registry_key}):")
                from ..analysis.semantic_contracts import SemanticAnalysisError
                err_msg = str(e)
                if isinstance(e, SemanticAnalysisError):
                    err_msg = f"{e.what}\n{e.why}\n\n{e.how}"
                self.after(0, lambda: self._on_analysis_error(entry.display_name, Exception(err_msg)))

        threading.Thread(target=run, daemon=True).start()

    def _execute_analysis_async(self, name: str, params: dict):
        """Executa analise em thread separada."""
        self._set_status(f"Executando {name}...", 0.3)
        self._enable_analysis_buttons(False)
        self._prepare_new_analysis_run()
        request_params = dict(params or {})
        analysis_type_key = str(request_params.get("analysis_type", "")).lower()
        
        def run():
            try:
                def include_if_present(target: Dict[str, Any], *keys: str) -> Dict[str, Any]:
                    for key in keys:
                        if key in request_params and request_params.get(key) is not None:
                            target[key] = request_params.get(key)
                    return target

                analysis_type = analysis_type_key
                requested_typegraph = request_params.get("typegraph", "png")
                display_typegraph = self._normalize_display_typegraph(requested_typegraph)
                request_params["typegraph"] = display_typegraph
                context_params = dict(request_params)
                result_path = None
                output_dir = None
                runner = None
                
                if analysis_type == 'chd':
                    from ..analysis import CHDAnalysis
                    output_dir = self._get_analysis_output_dir('chd')
                    analysis = self._build_analysis_runner(
                        CHDAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    strict_flag = bool(request_params.get('strict_iramuteq_clone', True))
                    analysis_mode = str(request_params.get('analysis_mode', 'strict' if strict_flag else 'legacy')).strip().lower()
                    if analysis_mode not in {'strict', 'legacy'}:
                        analysis_mode = 'strict' if strict_flag else 'legacy'
                    target_classes = int(request_params.get('n_classes', 5) or 5)
                    chd_params = {
                        'analysis_mode': analysis_mode,
                        'nb_classes': target_classes,
                        # Floor guard, not the target: default 2 so a legitimate
                        # native run with fewer-than-target classes is not rejected.
                        'min_classes': request_params.get('min_classes', 2),
                        'min_freq': request_params.get('min_freq', 2),
                        'min_uce': request_params.get('min_uce', 0),
                        'method': request_params.get('method', 'ward.D2'),
                        'classif_mode': request_params.get('classif_mode', 1),
                        'tailleuc1': request_params.get('tailleuc1', 12),
                        'tailleuc2': request_params.get('tailleuc2', 14),
                        'max_actives': request_params.get('max_actives', 20000),
                        'stopword_policy': request_params.get('stopword_policy', 'aggressive_pt'),
                        'strict_stopword_filter': request_params.get('strict_stopword_filter', True),
                        'prefer_portuguese_br': request_params.get('prefer_portuguese_br', False),
                        'strict_iramuteq_clone': analysis_mode == 'strict',
                        'use_native_chd': request_params.get('use_native_chd', True),
                        'native_fallback_legacy': request_params.get('native_fallback_legacy', True),
                        # Phase-1 over-segmentation DECOUPLED from the desired count.
                        # Coupling nbcl_p1 to n_classes starved the split tree and
                        # produced too few final classes. Default max(10, 2*target).
                        'nbcl_p1': int(request_params.get('nbcl_p1', max(10, 2 * target_classes))),
                        'svd_method': request_params.get('svd_method', 'irlba'),
                        'prefer_readable_afc_profiles': request_params.get('prefer_readable_afc_profiles', False),
                        'nb_per_class': request_params.get('nb_per_class', 80),
                        'max_words': request_params.get('max_words', 600),
                        'min_visible_words': request_params.get('min_visible_words', 120),
                        'typegraph': request_params.get('typegraph', 'png'),
                        'width': request_params.get('width', 1400),
                        'height': request_params.get('height', 1000),
                        'dendro_type': request_params.get('dendro_type', 'profile'),
                        'type_dendro': request_params.get('type_dendro', 'phylogram'),
                        'nb_words': request_params.get('nb_words', 60),
                        'bw': request_params.get('bw', False),
                        'lab': request_params.get('lab'),
                        'direction': request_params.get('direction', 'downwards'),
                    }
                    include_if_present(chd_params, 'width', 'height')
                    result = analysis.run(chd_params)
                    context_params = dict(chd_params)
                    result_path = (
                        getattr(result, 'dendrogram_path', None)
                        or getattr(result, 'afc_graph_path', None)
                        or getattr(result, 'profile_afc_path', None)
                    )
                elif analysis_type == 'similarity':
                    from ..analysis import SimilarityAnalysis

                    coefficient = request_params.get('coefficient', 0)
                    if isinstance(coefficient, str):
                        coefficient = coefficient.strip()

                    output_dir = self._get_analysis_output_dir('similarity')
                    analysis = self._build_analysis_runner(
                        SimilarityAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    similarity_params_raw = {
                        'analysis_mode': request_params.get('analysis_mode', 'strict' if request_params.get('strict_iramuteq_style', True) else 'legacy'),
                        'min_freq': request_params.get('min_freq', 3),
                        'coefficient': coefficient,
                        'layout': request_params.get('layout', 'frutch'),
                        'parity_profile': request_params.get('parity_profile'),
                        'render_profile': request_params.get('render_profile'),
                        'use_lemmas': request_params.get('use_lemmas', True),
                        'active_only': request_params.get('active_only', True),
                        'vertex_scaling': request_params.get('vertex_scaling', 'frequency'),
                        'grayscale': request_params.get('grayscale', False),
                        'min_edge': request_params.get('min_edge', 0),
                        'arbremax': request_params.get('arbremax', True),
                        'detect_communities': request_params.get('detect_communities', False),
                        'community_method': request_params.get('community_method', 'edge_betweenness'),
                        'show_halo': request_params.get('show_halo', False),
                        'show_edge_labels': request_params.get('show_edge_labels', False),
                        'cexalpha': request_params.get('cexalpha', False),
                        'strict_iramuteq_style': request_params.get('strict_iramuteq_style', True),
                        'graph_word': request_params.get('graph_word'),
                        'gexf_output': request_params.get('gexf_output', ''),
                        'renderer_backend': request_params.get('renderer_backend', 'iramuteq_r'),
                        'stopword_policy': request_params.get('stopword_policy', 'aggressive_pt'),
                        'typegraph': request_params.get('typegraph', 'png'),
                        'selected_words': request_params.get('selected_words'),
                        'selected_words_explicit': request_params.get('selected_words_explicit', False),
                    }
                    include_if_present(similarity_params_raw, 'width', 'height')
                    similarity_params = SimilarityAnalysis.sanitize_params(similarity_params_raw)
                    result = analysis.run(similarity_params)
                    context_params = dict(similarity_params)
                    result_path = getattr(result, 'graph_path', None)
                    
                elif analysis_type == 'wordcloud':
                    from ..analysis import WordCloudAnalysis
                    output_dir = self._get_analysis_output_dir('wordcloud')
                    analysis = self._build_analysis_runner(
                        WordCloudAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run(request_params)
                    result_path = getattr(result, 'image_path', None)
                elif analysis_type == 'specificities':
                    from ..analysis import SpecificitiesAnalysis
                    output_dir = self._get_analysis_output_dir('specificities')
                    analysis = self._build_analysis_runner(
                        SpecificitiesAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'index_type': request_params.get('index_type', 'chi2'),
                        'min_freq': request_params.get('min_freq', 3),
                        'gram_type': request_params.get('gram_type', 0),
                        'metadata_tokens': request_params.get('metadata_tokens', []),
                        'run_afc': request_params.get('run_afc', False),
                        'backend': request_params.get('backend', 'python'),
                        'allow_python_fallback': request_params.get('allow_python_fallback', True),
                        'generate_plot': request_params.get('generate_plot', True),
                        'plot_top_n': request_params.get('plot_top_n', 30),
                        'plot_bw': request_params.get('plot_bw', False),
                        'plot_width': request_params.get('plot_width', 1200),
                        'plot_height': request_params.get('plot_height', 800),
                        'plot_typegraph': request_params.get(
                            'plot_typegraph',
                            request_params.get('typegraph', 'png'),
                        ),
                    })
                    result_path = (
                        getattr(result, 'specificities_plot_path', None)
                        or getattr(result, 'afc_graph_path', None)
                        or getattr(result, 'scores_csv_path', None)
                    )
                elif analysis_type == 'prototypical':
                    from ..analysis import PrototypicalAnalysis
                    output_dir = self._get_analysis_output_dir('prototypical')
                    analysis = self._build_analysis_runner(
                        PrototypicalAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'freq_rank': self._build_prototypical_freq_rank(),
                        'mfreq': request_params.get('freq_threshold'),
                        'mrank': request_params.get('rank_threshold'),
                    })
                    result_path = getattr(result, 'graph_path', None)
                elif analysis_type == 'labbe':
                    from ..analysis import LabbeAnalysis
                    output_dir = self._get_analysis_output_dir('labbe')
                    analysis = self._build_analysis_runner(
                        LabbeAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'min_freq': request_params.get('min_freq', 3),
                    })
                    result_path = (
                        getattr(result, 'dendrogram_path', None)
                        or getattr(result, 'heatmap_path', None)
                    )
                elif analysis_type == 'keyness_extra':
                    from ..analysis import KeynessExtraAnalysis
                    output_dir = self._get_analysis_output_dir('keyness_extra')
                    analysis = self._build_analysis_runner(
                        KeynessExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'variable': request_params.get('variable', ''),
                        'target_value': request_params.get('target_value', ''),
                        'min_freq': request_params.get('min_freq', 3),
                        'top_n': request_params.get('top_n', 20),
                        'measure': request_params.get('measure', 'lr'),
                        'remove_stopwords': request_params.get('remove_stopwords', True),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'table_path', None)
                    )
                elif analysis_type == 'bigram_network_extra':
                    from ..analysis import BigramNetworkExtraAnalysis
                    output_dir = self._get_analysis_output_dir('bigram_network_extra')
                    analysis = self._build_analysis_runner(
                        BigramNetworkExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'min_bigram_freq': request_params.get('min_bigram_freq', 2),
                        'top_edges': request_params.get('top_edges', 120),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'edges_path', None)
                    )
                elif analysis_type == 'trigram_network_extra':
                    from ..analysis import TrigramNetworkExtraAnalysis
                    output_dir = self._get_analysis_output_dir('trigram_network_extra')
                    analysis = self._build_analysis_runner(
                        TrigramNetworkExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'min_trigram_freq': request_params.get('min_trigram_freq', 2),
                        'top_edges': request_params.get('top_edges', 120),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'edges_path', None)
                    )
                elif analysis_type == 'word_tree_extra':
                    from ..analysis import WordTreeExtraAnalysis
                    output_dir = self._get_analysis_output_dir('word_tree_extra')
                    analysis = self._build_analysis_runner(
                        WordTreeExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'keyword': request_params.get('keyword', ''),
                        'min_freq': request_params.get('min_freq', 3),
                        'max_depth': request_params.get('max_depth', 4),
                        'min_branch_freq': request_params.get('min_branch_freq', 2),
                        'top_branches': request_params.get('top_branches', 120),
                        'use_lemmas': request_params.get('use_lemmas', True),
                        'active_only': request_params.get('active_only', True),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'table_path', None)
                    )
                elif analysis_type == 'network_text':
                    from ..analysis import NetworkTextAnalysis

                    output_dir = self._get_analysis_output_dir('network_text')
                    analysis = self._build_analysis_runner(
                        NetworkTextAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    network_params = dict(request_params)
                    network_params["typegraph"] = str(requested_typegraph or "png").strip().lower()
                    result = analysis.run(network_params)
                    effective_params = dict(getattr(result, "layout_params", {}) or {})
                    if effective_params:
                        # Persist only stable config keys; runtime internals start with "_".
                        effective_params = {
                            str(key): value
                            for key, value in effective_params.items()
                            if str(key) and not str(key).startswith("_")
                        }
                        effective_params["analysis_type"] = "network_text"
                        request_params.clear()
                        request_params.update(effective_params)
                    else:
                        request_params["typegraph"] = network_params["typegraph"]
                    result_path = (
                        getattr(result, 'graph_image_path', None)
                        or getattr(result, 'graph_svg_path', None)
                        or getattr(result, 'nodes_csv_path', None)
                    )
                elif analysis_type == 'voyant_suite':
                    from ..analysis import VoyantSuiteAnalysis

                    output_dir = self._get_analysis_output_dir('voyant_suite')
                    analysis = self._build_analysis_runner(
                        VoyantSuiteAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'query': request_params.get('query', ''),
                        'num_initial_terms': request_params.get('num_initial_terms', 20),
                        'context': request_params.get('context', 5),
                        'bins': request_params.get('bins', 10),
                        'max_docs': request_params.get('max_docs', 50),
                        'min_freq': request_params.get('min_freq', 2),
                        'use_lemmas': request_params.get('use_lemmas', True),
                        'active_only': request_params.get('active_only', True),
                        'remove_stopwords': request_params.get('remove_stopwords', True),
                        'max_context_rows': request_params.get('max_context_rows', 800),
                        'mode': request_params.get('mode', 'top'),
                        'width': request_params.get('width', 1400),
                        'height': request_params.get('height', 900),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'table_path', None)
                        or getattr(result, 'summary_json_path', None)
                    )
                elif analysis_type == 'wordfish_extra':
                    from ..analysis import WordfishExtraAnalysis
                    output_dir = self._get_analysis_output_dir('wordfish_extra')
                    analysis = self._build_analysis_runner(
                        WordfishExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'group_variable': request_params.get('group_variable', ''),
                        'min_freq': request_params.get('min_freq', 3),
                        'max_features': request_params.get('max_features', 1200),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'scores_path', None)
                    )
                elif analysis_type == 'xray_extra':
                    from ..analysis import XRayExtraAnalysis
                    output_dir = self._get_analysis_output_dir('xray_extra')
                    analysis = self._build_analysis_runner(
                        XRayExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'patterns': request_params.get('patterns', ''),
                        'max_docs': request_params.get('max_docs', 200),
                    })
                    result_path = (
                        getattr(result, 'graph_path', None)
                        or getattr(result, 'points_path', None)
                    )
                elif analysis_type == 'sentiment_extra':
                    from ..analysis import SentimentExtraAnalysis
                    output_dir = self._get_analysis_output_dir('sentiment_extra')
                    analysis = self._build_analysis_runner(
                        SentimentExtraAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'with_timeline': request_params.get('with_timeline', True),
                        'top_words': request_params.get('top_words', 25),
                    })
                    result_path = (
                        getattr(result, 'distribution_graph_path', None)
                        or getattr(result, 'distribution_csv_path', None)
                    )
                elif analysis_type == 'emotions':
                    from ..analysis import EmotionsAnalysis
                    output_dir = self._get_analysis_output_dir('emotions')
                    analysis = self._build_analysis_runner(
                        EmotionsAnalysis,
                        self.corpus,
                        output_dir,
                    )
                    runner = analysis
                    result = analysis.run({
                        'width':  request_params.get('width',  1200),
                        'height': request_params.get('height',  900),
                    })
                    result_path = (
                        getattr(result, 'bar_graph_path', None)
                        or getattr(result, 'stats_csv_path', None)
                    )
                else:
                    raise ValueError(f"Tipo de analise desconhecido: {analysis_type}")

                self._last_analysis_result = result
                self._last_analysis_runner = runner
                self._last_analysis_context = {
                    "name": name,
                    "analysis_type": analysis_type,
                    "params": context_params,
                    "result_path": str(result_path) if result_path else "",
                    "output_dir": str(output_dir) if output_dir else "",
                }
                
                # Atualizar UI na thread principal
                self.after(0, lambda path=result_path: self._on_analysis_complete(name, path))
                
            except Exception as e:
                log.exception(f"Erro na análise {name}")
                self.after(0, lambda err=e: self._on_analysis_error(name, err))
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _build_prototypical_freq_rank(self) -> list:
        """Monta lista (palavra, frequencia, rank) para analise prototipica."""
        if not self.corpus:
            return []
        import re

        items = [
            (word.forme, int(word.freq))
            for word in self.corpus.formes.values()
            if getattr(word, "act", 1) == 1 and int(getattr(word, "freq", 0)) > 0
        ]
        items.sort(key=lambda item: (-item[1], item[0]))
        if not items:
            return []

        token_pattern = re.compile(r"\b[a-zA-ZÀ-ÿ]+\b")
        tracked_words = {word for word, _ in items}
        position_sum: Dict[str, float] = {}
        occurrence_count: Dict[str, int] = {}

        # Rank médio de evocação: posição média da palavra dentro das UCEs.
        for _uce_id, uce_text in self.corpus.get_uces():
            position = 0
            for token in token_pattern.findall((uce_text or "").lower()):
                if len(token) <= 2:
                    continue
                position += 1
                if token not in tracked_words:
                    continue
                position_sum[token] = position_sum.get(token, 0.0) + float(position)
                occurrence_count[token] = occurrence_count.get(token, 0) + 1

        fallback_rank = {
            word: float(idx + 1)
            for idx, (word, _freq) in enumerate(items)
        }
        rows = []
        for word, freq in items:
            occ = occurrence_count.get(word, 0)
            if occ > 0:
                rank = position_sum[word] / occ
            else:
                rank = fallback_rank[word]
            rows.append((word, freq, float(rank)))
        return rows

    @staticmethod
    def _format_prototypical_summary(result: Any) -> str:
        """Gera resumo textual da analise prototipica."""
        if result is None:
            return ""
        core = getattr(result, "core", []) or []
        first = getattr(result, "first_periphery", []) or []
        contrast = getattr(result, "contrast_zone", []) or []
        second = getattr(result, "second_periphery", []) or []
        lines = [
            f"Núcleo central ({len(core)}): {', '.join(core[:20]) or 'vazio'}",
            f"1ª periferia ({len(first)}): {', '.join(first[:20]) or 'vazio'}",
            f"Zona de contraste ({len(contrast)}): {', '.join(contrast[:20]) or 'vazio'}",
            f"2ª periferia ({len(second)}): {', '.join(second[:20]) or 'vazio'}",
        ]
        return "\n\n".join(lines)

    @staticmethod
    def _format_labbe_summary(result: Any) -> str:
        """Gera resumo textual da distancia de Labbe."""
        if result is None:
            return ""
        matrix = getattr(result, "distance_matrix", None)
        if matrix is None:
            return "Resultado Labbe sem matriz de distância."
        try:
            shape = getattr(matrix, "shape", ())
            if len(shape) == 2 and shape[0] and shape[1]:
                return f"Matriz de distância Labbé: {shape[0]} x {shape[1]}."
        except Exception:
            pass
        return "Matriz de distância Labbé calculada."

    def _generate_report_for_current_result(self, name: str, result_path: Optional[Path]) -> Optional[Path]:
        """Gera relatório HTML para o resultado atual e registra no ResultsViewer."""
        try:
            context = self._last_analysis_context if isinstance(self._last_analysis_context, dict) else {}
            analysis_type = str(context.get("analysis_type", "")).lower()
            params = context.get("params", {}) if isinstance(context.get("params", {}), dict) else {}
            result = self._last_analysis_result

            report_dir = self._get_analysis_output_dir("reports")
            generator = ReportGenerator(Path(report_dir))
            report_path: Optional[Path] = None

            if analysis_type == "statistics":
                stats_payload = {}
                graphs_payload = {}
                if isinstance(result, dict):
                    stats_payload = result.get("stats", {}) if isinstance(result.get("stats", {}), dict) else {}
                    raw_graphs = result.get("graphs", {})
                    if isinstance(raw_graphs, dict):
                        graphs_payload = {
                            str(label): Path(path)
                            for label, path in raw_graphs.items()
                            if path
                        }
                report_path = generator.generate_statistics_report(
                    stats=stats_payload,
                    graphs=graphs_payload,
                    analysis_name=name,
                    params=params,
                )
            elif analysis_type in {"matrix_chi2"}:
                report_path = generator.generate_chi2_report(
                    result=result,
                    analysis_name=name,
                    params=params,
                )
            elif analysis_type == "chd":
                report_path = generator.generate_chd_report(
                    result=result,
                    analysis_name=name,
                    params=params,
                    result_path=Path(result_path) if result_path else None,
                )
            elif analysis_type == "network_text":
                report_path = generator.generate_generic_report(
                    analysis_name=name,
                    analysis_type="network_text",
                    params=params,
                    result=result,
                    result_path=Path(result_path) if result_path else None,
                )
            elif analysis_type == "voyant_suite":
                report_path = generator.generate_voyant_suite_report(
                    result=result,
                    analysis_name=name,
                    params=params,
                )
            else:
                report_path = generator.generate_generic_report(
                    analysis_name=name,
                    analysis_type=analysis_type or name.lower(),
                    params=params,
                    result=result,
                    result_path=Path(result_path) if result_path else None,
                )

            if (
                analysis_type == "voyant_suite"
                and report_path
                and result is not None
                and hasattr(result, "voyant_suite_payload_v1")
            ):
                payload = getattr(result, "voyant_suite_payload_v1", None)
                if isinstance(payload, dict):
                    report_section = payload.get("report")
                    if not isinstance(report_section, dict):
                        report_section = {}
                        payload["report"] = report_section
                    report_section["html_path"] = str(report_path)

            self._last_report_path = report_path if report_path and Path(report_path).exists() else None
            viewer = self.__dict__.get("results_viewer")
            if viewer is not None and hasattr(viewer, "set_report_path"):
                viewer.set_report_path(self._last_report_path)
            return self._last_report_path
        except Exception as exc:
            self._last_report_path = None
            viewer = self.__dict__.get("results_viewer")
            if viewer is not None and hasattr(viewer, "set_report_path"):
                viewer.set_report_path(None)
            log.warning("Falha ao gerar relatório de %s: %s", name, exc)
            return None

    def _get_report_path_from_history_entry(self, entry: Any) -> Optional[Path]:
        """Obtém caminho de relatório de uma entrada do histórico."""
        metadata = getattr(entry, "metadata", {}) if isinstance(getattr(entry, "metadata", {}), dict) else {}
        candidate = metadata.get("report_path")
        if not candidate:
            return None
        path = Path(str(candidate))
        if path.exists() and path.is_file():
            return path
        return None


    def _get_reconstructed_chd_result(self, entry: Any) -> Any:
        try:
            result_path = Path(entry.result_path) if getattr(entry, "result_path", "") else None
            if not result_path:
                return None
            
            # Se for arquivo (ex: dendrograma), pegar diretório pai
            result_dir = result_path.parent if result_path.is_file() else result_path
            
            # Verificar arquivos essenciais
            chi2_path = result_dir / "chd_profile_chi2.csv"
            matrix_path = result_dir / "chd_profile_matrix.csv"
            sizes_path = result_dir / "chd_class_sizes.csv"
            
            if not (chi2_path.exists() and matrix_path.exists() and sizes_path.exists()):
                return None
                
            # Ler tamanhos das classes
            class_sizes = {}
            with sizes_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        class_id = int(row["class_id"])
                        count = int(row["count"])
                    except (ValueError, KeyError):
                        continue
                    if class_id <= 0 or count <= 0:
                        continue
                    class_sizes[class_id] = count
                        
            if not class_sizes:
                return None

            # Carregar matrizes para memoria
            # Precisamos ler CSVs variando delimitador (R usa as vezes , ou ;)
            def read_csv_matrix(path):
                data = {}
                with path.open("r", encoding="utf-8") as f:
                    # Detectar delimitador
                    line = f.readline()
                    delimiter = ";" if ";" in line else ","
                    f.seek(0)
                    reader = csv.reader(f, delimiter=delimiter)
                    headers = next(reader, None)
                    if not headers:
                        return None, None
                        
                    # Mapear colunas para class_ids (headers: "", "class_1", "class_2"...)
                    class_col_map = {}
                    for idx, h in enumerate(headers):
                        if "class_" in h:
                            try:
                                cid = int(h.split("_")[1])
                                class_col_map[idx] = cid
                            except (ValueError, KeyError, IndexError):
                                pass
                                
                    if not class_col_map:
                        # Tentar mapear por indice se headers forem apenas numeros ou vazios
                        pass
                        
                    for row in reader:
                        if not row: continue
                        word = row[0]
                        row_vals = {}
                        for idx, val in enumerate(row):
                            if idx in class_col_map:
                                try:
                                    row_vals[class_col_map[idx]] = float(val)
                                except (ValueError, TypeError):
                                    row_vals[class_col_map[idx]] = 0.0
                        data[word] = row_vals
                return data, class_col_map.values()

            chi2_data, class_ids = read_csv_matrix(chi2_path)
            freq_data, _ = read_csv_matrix(matrix_path)
            
            if not chi2_data or not freq_data:
                return None
                
            profiles = {}
            for cid in class_sizes:
                class_profile = []
                for word, chi_vals in chi2_data.items():
                    signed_chi = chi_vals.get(cid, 0.0)
                    if abs(signed_chi) < 0.0001: # Ignorar zeros
                        continue
                        
                    freq = int(freq_data.get(word, {}).get(cid, 0))
                    class_size = class_sizes.get(cid, 1)
                    pct = (freq / class_size) * 100.0 if class_size > 0 else 0.0
                    marker = "+" if signed_chi >= 0 else "-"
                    
                    # (word, chi2, freq, pct, sign)
                    class_profile.append((word, signed_chi, freq, pct, marker))
                
                # Ordenar por chi2 absoluto
                class_profile.sort(key=lambda x: abs(x[1]), reverse=True)
                profiles[cid] = class_profile

            # Construir objeto dummy
            from types import SimpleNamespace
            result = SimpleNamespace()
            result.class_sizes = class_sizes
            result.profiles = profiles
            result.typical_segments = {} # Nao recuperavel facilmente dos CSVs atuais
            result.antiprofiles = {} # Poderia ser derivado dos perfis negativos
            result.repeated_segments = {}
            
            # Tentar recuperar caminhos extras do metadata ou diretorio
            metadata = getattr(entry, "metadata", {}) or {}
            if isinstance(metadata, str):
                try: metadata = json.loads(metadata)
                except (json.JSONDecodeError, ValueError, TypeError): metadata = {}
                
            result.afc_graph_path = metadata.get("chd_afc_graph_path") or None
            result.profile_afc_path = (
                metadata.get("chd_profile_afc_path")
                or metadata.get("profile_afc_path")
                or metadata.get("chd_afc_graph_path")
            )
            if not result.profile_afc_path:
                profile_potentials = (
                    list(result_dir.glob("AFC2DL.*"))
                    + list(result_dir.glob("chd_profiles_afc.*"))
                )
                if profile_potentials:
                    result.profile_afc_path = str(profile_potentials[0])

            result.dendrogram_path = metadata.get("dendrogram_path")
            if not result.dendrogram_path:
                if result_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg"} and result_path.exists():
                    result.dendrogram_path = str(result_path)
                else:
                    dendro_candidates = list(result_dir.glob("dendrogram*.png")) + list(result_dir.glob("dendrogram*.svg"))
                    if dendro_candidates:
                        result.dendrogram_path = str(dendro_candidates[0])
                    
            result.colored_corpus_path = metadata.get("chd_colored_corpus_path")
            if not result.colored_corpus_path:
                colored = result_dir / "colored_corpus.html"
                if colored.exists():
                     result.colored_corpus_path = str(colored)

            return result
        except Exception as exc:
            log.warning("Falha ao ler arquivos da CHD: %s", exc)
            return None

    def _reconstruct_chd_from_files(self, entry: Any) -> bool:
        """Tenta reconstruir resultado CHD a partir dos arquivos gerados."""
        try:
            result = self._get_reconstructed_chd_result(entry)
            if not result:
                return False

            self.results_viewer.show_chd_profiles(
                result.profiles,
                result.class_sizes,
                result=result
            )
            return True
        except Exception as e:
            log.error("Erro ao reconstruir CHD: %s", e)
            return False

    def _show_chd_detail(self, entry: Any, detail: str) -> None:
        """Exibe detalhe específico de uma análise CHD (dendrograma, perfis, etc)."""
        # Primeiro garantir que o resultado está carregado
        log.info("Exibindo detalhe CHD '%s' para entrada %s", detail, getattr(entry, "entry_id", "DESCONHECIDO"))
        
        # Tenta carregar se ainda não estiver (ou se for diferente)
        # Assumindo que _open_history_entry vai lidar com isso
        self._open_history_entry(entry)
        
        # Mapeia 'detail' para aba do ResultsViewer
        # Abas padrão: "Dendrograma", "Tabela", "Gráfico", "Segmentos", "Variáveis"
        tab_map = {
            "dendrogram": "Dendrograma",
            "profiles": "Tabela",
            "afc": "Gráfico",
            "segments": "Segmentos",
            "antiprofiles": "Segmentos", # Ambos em segmentos
        }
        
        target_tab = tab_map.get(detail)
        if target_tab and hasattr(self.results_viewer, "tabview"):
            try:
                # Força update antes de mudar aba para garantir que widget existe
                self.results_viewer.update_idletasks()
                self.results_viewer.tabview.set(target_tab)
            except Exception as e:
                log.warning("Não foi possível mudar para aba '%s': %s", target_tab, e)

    def _on_results_tab_clicked(self, tab_key: str) -> None:
        """XRedirecionador de clique em aba superior de análise.

        Quando o usuário clica em uma aba correspondente a um item do histórico
        (chave no formato 'history_<entry_id>'), reabre a entrada completa do
        histórico a partir do disco, igualando o comportamento da barra lateral.
        Para abas não-históricas (ex: 'inicio'), cai no fallback interno do viewer.
        """
        self._ensure_results_workspace()
        HISTORY_PREFIX = "history_"
        if not tab_key.startswith(HISTORY_PREFIX):
            # Não é aba de histórico: delega para restauração local de snapshot
            if hasattr(self.results_viewer, "_activate_analysis_tab"):
                self.results_viewer._activate_analysis_tab(tab_key)
            return

        entry_id = tab_key[len(HISTORY_PREFIX):]
        entry = None
        try:
            entry = self.analysis_history.get_result(entry_id)
        except Exception:
            log.warning(
                "Não foi possível localizar entrada de histórico para chave '%s' (id='%s').",
                tab_key,
                entry_id,
            )

        if entry is not None:
            log.info(
                "Aba superior clicada: navegando para histórico id='%s' tipo='%s'.",
                entry_id,
                getattr(entry, "analysis_type", "?"),
            )
            self._open_history_entry(entry)
        else:
            # Fallback: nenhuma entrada encontrada — usa restauração local de snapshot
            log.warning(
                "Entrada de histórico não encontrada para aba '%s'; usando snapshot local.",
                tab_key,
            )
            if hasattr(self.results_viewer, "_activate_analysis_tab"):
                self.results_viewer._activate_analysis_tab(tab_key)

    def _open_history_entry(self, entry: Any) -> None:
        """Exibe um item do historico no visualizador de resultados."""
        if entry is None:
            return
        self._ensure_results_workspace()
        entry_key = f"history_{getattr(entry, 'entry_id', '?')}"
        viewer = getattr(self, "results_viewer", None)
        if (
            viewer is not None
            and hasattr(viewer, "has_analysis_tab")
            and viewer.has_analysis_tab(entry_key)
            and hasattr(viewer, "focus_analysis_tab")
        ):
            viewer.focus_analysis_tab(entry_key)
            self._refresh_results_sidebar_context()
            return
            
        analysis_type_raw = str(getattr(entry, "analysis_type", "desconhecido"))
        analysis_type = analysis_type_raw.upper()
        analysis_type_key = analysis_type_raw.lower()
        entry_id = getattr(entry, "entry_id", "?")
        log.info("Abrindo histórico: ID=%s Tipo=%s", entry_id, analysis_type)
        
        if hasattr(self.results_viewer, "set_analysis_tab"):
            entry_label = str(getattr(entry, "analysis_type", "histórico")).upper()
            try:
                self.results_viewer.set_analysis_tab(entry_label, key=entry_key, closable=True)
            except Exception:
                log.exception("Falha ao preparar aba de histórico para entrada %s.", entry_id)
        if hasattr(self.results_viewer, "clear"):
            try:
                self.results_viewer.clear(sync=False, force=True)
            except Exception:
                log.exception("Falha ao limpar visualizador antes de abrir histórico %s.", entry_id)

        report_path = self._get_report_path_from_history_entry(entry)
        result_path_str = getattr(entry, "result_path", "")
        artifact_path = Path(result_path_str) if result_path_str else None
        entry_params = getattr(entry, "params", {}) if isinstance(getattr(entry, "params", {}), dict) else {}
        if analysis_type_key == "similarity":
            similarity_output_dir = (
                artifact_path.parent
                if artifact_path is not None and artifact_path.exists()
                else Path(str(result_path_str or ".")).parent
            )
            self._set_similarity_halo_toggle_context(
                enabled=True,
                params=entry_params,
                output_dir=similarity_output_dir,
                show_halo=bool(entry_params.get("show_halo", False)),
            )
        else:
            self._set_similarity_halo_toggle_context(enabled=False)
        statistics_restored = False
        if analysis_type_key == "statistics":
            statistics_restored = self._restore_statistics_from_history(entry, artifact_path)
        
        log.info("Caminho do artefato: %s", artifact_path)

        # Fluxo especial CHD: preserva tabela rica (show_chd_profiles) e complementa demais abas.
        if analysis_type_key == "chd":
            runtime_chd = self._get_runtime_chd_result(entry)
            reconstructed_chd = runtime_chd or self._get_reconstructed_chd_result(entry)
            if reconstructed_chd is not None:
                gallery_metadata: Dict[str, Any]
                if runtime_chd is not None:
                    # Quando há resultado da sessão em memória, evitar mesclar
                    # galeria persistida do histórico (paths copiados) para
                    # não criar botões duplicados com o mesmo rótulo.
                    gallery_metadata = {}
                else:
                    raw_metadata = getattr(entry, "metadata", {})
                    gallery_metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                self.results_viewer.show_chd_profiles(
                    reconstructed_chd.profiles,
                    reconstructed_chd.class_sizes,
                    result=reconstructed_chd,
                )
                chd_stats = self._build_statistics_summary("chd", reconstructed_chd)
                if chd_stats:
                    self.results_viewer.show_text(chd_stats, title="Estatísticas - CHD")
                chd_gallery = self._get_image_gallery(
                    analysis_type_key="chd",
                    result=reconstructed_chd,
                    artifact_path=artifact_path,
                    metadata=gallery_metadata,
                )
                if chd_gallery:
                    if hasattr(self.results_viewer, "show_image_gallery"):
                        self.results_viewer.show_image_gallery(chd_gallery, default_label="Dendrograma")
                    else:
                        self._show_image_gallery(chd_gallery)
                if hasattr(self.results_viewer, "set_data_export_source"):
                    export_sources = self._get_data_export_sources(
                        analysis_type_key="chd",
                        result=reconstructed_chd,
                        metadata=gallery_metadata,
                    )
                    self.results_viewer.set_data_export_source(
                        export_sources if export_sources else None
                    )
                self._last_report_path = report_path
                if hasattr(self.results_viewer, "set_report_path"):
                    self.results_viewer.set_report_path(report_path)
                self._set_status("Resultado CHD restaurado do histórico", 1.0)
                return
            log.warning("Falha ao reconstruir CHD para entrada %s", entry_id)

        current_context = self.__dict__.get("_last_analysis_context", {})
        if not isinstance(current_context, dict):
            current_context = {}
        current_analysis_type = str(current_context.get("analysis_type", "")).lower()
        result_is_current = (
            self._last_analysis_result is not None
            and str(self._last_saved_history_entry_id or "") == str(entry_id)
            and current_analysis_type == analysis_type_key
        )
        result_obj = self._last_analysis_result if result_is_current else None

        if result_is_current:
            self._populate_all_tabs(
                analysis_type_key=analysis_type_key,
                result=result_obj,
                artifact_path=artifact_path,
                report_path=report_path,
                skip_statistics=statistics_restored,
            )
        else:
            self._populate_tabs_from_history_metadata(
                entry=entry,
                artifact_path=artifact_path,
                report_path=report_path,
                skip_statistics=statistics_restored,
            )

        has_content_after_populate = (
            bool(getattr(self.results_viewer, "_current_image_path", None))
            or bool(getattr(self.results_viewer, "_has_table_content", False))
            or bool(str(getattr(self.results_viewer, "_current_text", "")).strip())
            or bool(getattr(self.results_viewer, "_current_report_path", None))
        )
        if not has_content_after_populate:
            log.warning(
                "Reabertura de histórico sem conteúdo visível (entry=%s, tipo=%s). Forçando fallback por metadata.",
                entry_id,
                analysis_type_key,
            )
            self._populate_tabs_from_history_metadata(
                entry=entry,
                artifact_path=artifact_path,
                report_path=report_path,
                skip_statistics=statistics_restored,
            )

        if artifact_path and artifact_path.exists():
            suffix = artifact_path.suffix.lower()
            log.info("Abrindo artefato com sufixo: %s", suffix)
            if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg"}:
                if not bool(getattr(self.results_viewer, "_current_image_path", None)):
                    self.results_viewer.show_image(artifact_path)
                    self._apply_graph_default_zoom_for_analysis(analysis_type_key)
            elif suffix == ".csv":
                if not bool(getattr(self.results_viewer, "_has_table_content", False)):
                    self.results_viewer.show_table(artifact_path)
            elif suffix in {".txt", ".log"}:
                if not statistics_restored:
                    text = artifact_path.read_text(encoding="utf-8", errors="replace")
                    self.results_viewer.show_text(text, title=f"Resultado ({entry.analysis_type})")
            self._last_report_path = report_path
            if hasattr(self.results_viewer, "set_report_path"):
                self.results_viewer.set_report_path(report_path)
            self._set_status(f"Resultado reaberto: {entry.analysis_type}", 1.0)
            return

        has_content = (
            bool(getattr(self.results_viewer, "_current_image_path", None))
            or bool(getattr(self.results_viewer, "_has_table_content", False))
            or bool(str(getattr(self.results_viewer, "_current_text", "")).strip())
        )
        if has_content or statistics_restored:
            self._last_report_path = report_path
            if hasattr(self.results_viewer, "set_report_path"):
                self.results_viewer.set_report_path(report_path)
            self._set_status(f"Resultado reaberto: {entry.analysis_type}", 1.0)
            return

        log.warning("Artefato não encontrado ou inválido: %s", artifact_path)
        fallback = json.dumps(getattr(entry, "params", {}), indent=2, ensure_ascii=False)
        self.results_viewer.show_text(
            f"Artefato indisponível.\n\nParâmetros da execução:\n{fallback}",
            title=f"Histórico ({getattr(entry, 'analysis_type', 'analise')})",
        )
        self._last_report_path = report_path
        if hasattr(self.results_viewer, "set_report_path"):
            self.results_viewer.set_report_path(report_path)
        self._set_status("Resultado sem artefato persistido", 1.0)

    def _open_history_report(self, entry: Any) -> None:
        """Abre o relatório HTML associado a uma entrada do histórico."""
        if entry is None:
            return
        report_path = self._get_report_path_from_history_entry(entry)
        if report_path is None:
            show_error(
                self,
                what="Relatório indisponível para esta análise.",
                why="A entrada selecionada não possui caminho de relatório salvo ou o arquivo foi removido.",
                how="Reabra o resultado e gere novamente a análise para criar um novo relatório.",
            )
            return
        self._last_report_path = report_path
        if hasattr(self.results_viewer, "set_report_path"):
            self.results_viewer.set_report_path(report_path)
        try:
            if hasattr(self.results_viewer, "open_report"):
                self.results_viewer.open_report()
            else:
                import webbrowser

                webbrowser.open(report_path.resolve().as_uri(), new=2)
            self._set_status("Relatório aberto no navegador", 1.0)
        except Exception as exc:
            show_error(self, error=exc)


    def _delete_history_entry(self, entry: Any) -> None:
        """Remove entrada do histórico."""
        if not entry:
            return
        
        confirm = messagebox.askyesno(
            "Excluir Histórico",
            f"Tem certeza que deseja excluir o item '{getattr(entry, 'analysis_type', 'Análise')}' do histórico?",
            parent=self
        )
        if not confirm:
            return

        try:
            self.analysis_history.delete_entry(entry.entry_id)
            self.corpus_tree.load_history(
                self.analysis_history,
                on_select=self._open_history_entry,
                on_action=self._handle_corpus_tree_action,
            )
            self._set_status("Item removido do histórico", 1.0)
        except Exception as e:
            show_error(self, error=e)

    def _export_history_entry_artifact(self, entry: Any) -> None:
        """Exporta artefato (arquivo) de uma entrada do histórico."""
        path = getattr(entry, "result_path", None)
        if not path:
             messagebox.showinfo("Exportar", "Esta entrada não possui arquivo de resultado associado.")
             return
             
        src = Path(path)
        if not src.exists():
             messagebox.showerror("Erro", "Arquivo original não encontrado.")
             return
             
        dest = filedialog.asksaveasfilename(
            title="Exportar Resultado",
            initialfile=src.name,
            initialdir=src.parent,
        )
        if not dest:
            return
            
        try:
            shutil.copy2(src, dest)
            self._set_status("Arquivo exportado com sucesso", 1.0)
        except Exception as e:
            show_error(self, error=e)


    def _run_similarity_from_chd(self, entry: Any) -> None:
        """Executa similtude a partir de uma classe da CHD."""
        show_error(
            self,
            what="Funcionalidade em manutenção.",
            why="A execução de Similitude a partir de classes da CHD está sendo refatorada.",
            how="Exporte a classe como sub-corpus e execute a Similitude normalmente."
        )

    def _export_dictionary(self, *args, **kwargs) -> None:
        """Exporta dicionario do corpus."""
        show_error(self, what="Exportação de dicionário não implementada.")

    def _export_segmented_corpus(self, *args, **kwargs) -> None:
        """Exporta corpus segmentado."""
        show_error(self, what="Exportação de corpus segmentado não implementada.")

    def _open_corpus_navigator(self, *args, **kwargs) -> None:
        """Abre navegador do corpus."""
        show_error(self, what="Navegador de corpus não implementado.")
        
    def _export_chd_classes(self, *args, **kwargs) -> None:
        """Exporta classes da CHD."""
        show_error(self, what="Exportação de classes não implementada.")

    def _export_chd_colored(self, *args, **kwargs) -> None:
        """Exporta corpus colorido da CHD."""
        show_error(self, what="Exportação de corpus colorido não implementada.")

    def _handle_corpus_tree_action(self, action: str, payload: Dict[str, Any]) -> None:
        """Executa ações de menu de contexto da árvore do corpus."""
        entry = payload.get("entry")
        try:
            if action == "open_result":
                if entry is not None:
                    self._open_history_entry(entry)
                return
            if action == "open_report":
                if entry is not None:
                    self._open_history_report(entry)
                return
            if action == "view_dendrogram":
                self._show_chd_detail(entry, detail="dendrogram")
                return
            if action == "view_profiles":
                self._show_chd_detail(entry, detail="profiles")
                return
            if action == "view_afc":
                self._show_chd_detail(entry, detail="afc")
                return
            if action == "view_segments":
                self._show_chd_detail(entry, detail="segments")
                return
            if action == "view_antiprofiles":
                self._show_chd_detail(entry, detail="antiprofiles")
                return
            if action == "view_graph":
                if entry is not None:
                    self._open_history_entry(entry)
                return
            if action == "export_result":
                if entry is not None:
                    self._export_history_entry_artifact(entry)
                return
            if action == "delete_history":
                if entry is not None:
                    self._delete_history_entry(entry)
                return
            if action == "reconfigure_similarity":
                self._run_similarity()
                return
            if action == "show_stats":
                self._run_statistics()
                return
            if action == "export_dictionary":
                self._export_dictionary()
                return
            if action == "export_segmented":
                self._export_segmented_corpus()
                return
            if action == "export_corpus_txt":
                self._export_corpus_to_txt()
                return
            if action == "export_iramuteq":
                self._export_corpus_to_iramuteq()
                return
            if action == "create_subcorpus":
                self._create_subcorpus()
                return
            if action == "open_navigator":
                self._open_corpus_navigator(entry=entry)
                return
            if action == "export_classes":
                self._export_chd_classes(entry)
                return
            if action == "export_colored_corpus":
                self._export_chd_colored(entry)
                return
            if action == "wordcloud_by_class":
                self._run_wordcloud_from_chd(entry)
                return
            if action == "similarity_by_class":
                self._run_similarity_from_chd(entry)
                return
        except Exception as exc:
            log.exception("Falha ao executar acao de contexto '%s'", action)
            show_error(self, error=exc)

    def _create_subcorpus(self) -> None:
        """Cria sub-corpus filtrando por variável de metadado."""
        if not self.corpus:
            show_error(
                self,
                what="Nenhum corpus carregado.",
                why="A criação de sub-corpus requer um corpus ativo.",
                how="Importe um corpus antes de usar esta ação.",
            )
            return

        etoiles = sorted(self.corpus.make_etoiles())
        if not etoiles:
            show_error(
                self,
                what="Corpus sem variáveis de metadado.",
                why="Nenhuma etoile foi encontrada no corpus atual.",
                how="Use um corpus com linhas de metadado como *variavel_valor.",
            )
            return

        var_values: Dict[str, set[str]] = {}
        for token in etoiles:
            clean = str(token).strip().lstrip("*")
            if "_" not in clean:
                continue
            var_name, value = clean.split("_", 1)
            var_name = var_name.strip()
            value = value.strip()
            if not var_name or not value:
                continue
            var_values.setdefault(var_name, set()).add(value)

        if not var_values:
            show_error(
                self,
                what="Variáveis não reconhecidas.",
                why="As etoiles não seguem o formato *variavel_valor.",
                how="Verifique o formato de metadados no corpus de entrada.",
            )
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Criar Sub-corpus")
        dialog.geometry("420x520")
        dialog.transient(self)
        dialog.grab_set()

        def _close_dialog() -> None:
            try:
                cleanup_widget_menus(dialog)
            except Exception:
                pass
            try:
                dialog.grab_release()
            except Exception:
                pass
            try:
                dialog.destroy()
            except Exception:
                pass

        dialog.protocol("WM_DELETE_WINDOW", _close_dialog)

        ctk.CTkLabel(
            dialog,
            text="Selecionar Variável e Valores",
            font=FONTS["heading"],
        ).pack(pady=10)

        var_list = sorted(var_values.keys())
        selected_var = ctk.StringVar(value=var_list[0])

        ctk.CTkLabel(
            dialog,
            text="Variável:",
            font=FONTS["body"],
        ).pack(anchor="w", padx=20, pady=(4, 0))

        value_vars: Dict[str, ctk.BooleanVar] = {}
        values_frame = ctk.CTkScrollableFrame(dialog, height=280)
        values_frame.pack(fill="both", expand=True, padx=20, pady=10)

        def _refresh_values() -> None:
            for widget in values_frame.winfo_children():
                widget.destroy()
            value_vars.clear()
            current_var = selected_var.get()
            for value in sorted(var_values.get(current_var, set())):
                bool_var = ctk.BooleanVar(value=True)
                value_vars[value] = bool_var
                ctk.CTkCheckBox(
                    values_frame,
                    text=value,
                    variable=bool_var,
                    font=FONTS["body"],
                ).pack(anchor="w", pady=2)

        ctk.CTkOptionMenu(
            dialog,
            values=var_list,
            variable=selected_var,
            command=lambda _value: _refresh_values(),
        ).pack(fill="x", padx=20, pady=5)

        _refresh_values()

        def _confirm() -> None:
            var_name = selected_var.get()
            selected_values = [
                value for value, bool_var in value_vars.items() if bool(bool_var.get())
            ]
            if not selected_values:
                messagebox.showwarning("Sub-corpus", "Selecione pelo menos um valor.")
                return

            subcorpus = self.corpus.extract_subcorpus(var_name, selected_values)
            if subcorpus is None:
                messagebox.showwarning("Sub-corpus", "Nenhuma UCI encontrada com os filtros.")
                return

            self.corpus = subcorpus
            self._corpus_db_path = None
            self._last_analysis_result = None
            self._last_analysis_runner = None
            self._last_saved_history_entry_id = None
            self._last_analysis_context = {}
            self._last_report_path = None

            self.corpus_tree.load_corpus(subcorpus)
            self.corpus_tree.load_history(
                self.analysis_history,
                on_select=self._open_history_entry,
                on_action=self._handle_corpus_tree_action,
            )
            self._enable_analysis_buttons(True)

            n_ucis = len(subcorpus.ucis)
            n_uces = sum(len(uci.uces) for uci in subcorpus.ucis)
            n_formes = len(subcorpus.formes)
            self._set_status(
                f"Sub-corpus criado: {n_ucis} UCIs, {n_uces} UCEs, {n_formes} formas",
                1.0,
            )
            _close_dialog()
            messagebox.showinfo(
                "Sub-corpus",
                (
                    "Sub-corpus criado com sucesso!\n\n"
                    f"UCIs: {n_ucis}\n"
                    f"UCEs: {n_uces}\n"
                    f"Formas: {n_formes}"
                ),
            )

        ctk.CTkButton(
            dialog,
            text="Criar Sub-corpus",
            command=_confirm,
        ).pack(pady=(0, 14))

    def _show_chd_detail(self, entry: Any, detail: str) -> None:
        """Exibe um detalhe de CHD priorizando resultado em memória."""
        result = self._get_runtime_chd_result(entry)
        if result is None:
            if detail == "afc":
                metadata = getattr(entry, "metadata", {}) if isinstance(getattr(entry, "metadata", {}), dict) else {}
                profile_afc_path = (
                    metadata.get("chd_profile_afc_path")
                    or metadata.get("profile_afc_path")
                    or metadata.get("chd_afc_graph_path")
                )
                if profile_afc_path and Path(profile_afc_path).exists():
                    self.results_viewer.show_image(Path(profile_afc_path))
                    return
            self._open_history_entry(entry)
            return

        if detail == "dendrogram":
            image_path = getattr(result, "dendrogram_path", None)
            if image_path and Path(image_path).exists():
                self.results_viewer.show_image(image_path)
                return
        elif detail == "afc":
            image_path = (
                getattr(result, "profile_afc_path", None)
                or getattr(result, "afc_graph_path", None)
            )
            if image_path and Path(image_path).exists():
                self.results_viewer.show_image(image_path)
                return
        elif detail == "profiles":
            self.results_viewer.show_chd_profiles(
                getattr(result, "profiles", {}) or {},
                getattr(result, "class_sizes", {}) or {},
                result=result,
            )
            return
        elif detail == "segments":
            text = self._format_chd_segments_text(getattr(result, "typical_segments", {}) or {})
            self.results_viewer.show_text(text, title="Segmentos Típicos CHD")
            return
        elif detail == "antiprofiles":
            text = self._format_chd_antiprofiles_text(getattr(result, "antiprofiles", {}) or {})
            self.results_viewer.show_text(text, title="Antiperfis CHD")
            return

        self._open_history_entry(entry)

    def _get_runtime_chd_result(self, entry: Any) -> Optional[Any]:
        """Retorna resultado CHD da sessão quando compatível com entrada selecionada."""
        context = self._last_analysis_context if isinstance(self._last_analysis_context, dict) else {}
        if str(context.get("analysis_type", "")).lower() != "chd":
            return None
        if self._last_analysis_result is None:
            return None
        entry_id = getattr(entry, "entry_id", None)
        if entry_id and self._last_saved_history_entry_id and entry_id != self._last_saved_history_entry_id:
            return None
        return self._last_analysis_result

    @staticmethod
    def _format_chd_segments_text(segments_by_class: Dict[int, Any]) -> str:
        """Converte segmentos típicos para texto legível."""
        lines = []
        for class_id in sorted(segments_by_class.keys()):
            lines.append(f"[Classe {class_id}]")
            segments = segments_by_class.get(class_id, [])
            if not segments:
                lines.append("  (sem segmentos)")
                lines.append("")
                continue
            for idx, item in enumerate(segments[:15], start=1):
                text, score = item
                preview = str(text).replace("\n", " ").strip()
                if len(preview) > 220:
                    preview = preview[:220] + "..."
                lines.append(f"  {idx:>2}. score={float(score):.3f} | {preview}")
            lines.append("")
        return "\n".join(lines).strip() or "Segmentos típicos indisponíveis."

    @staticmethod
    def _format_chd_antiprofiles_text(antiprofiles: Dict[int, Any]) -> str:
        """Converte antiperfis para texto legível."""
        lines = []
        for class_id in sorted(antiprofiles.keys()):
            lines.append(f"[Classe {class_id}]")
            rows = antiprofiles.get(class_id, [])
            if not rows:
                lines.append("  (sem antiperfis)")
                lines.append("")
                continue
            for word, chi2, freq, pct, sign in rows[:30]:
                lines.append(f"  {word:<22} {chi2:>8.3f}  freq={int(freq):>4}  pct={pct:>6.2f}%  {sign}")
            lines.append("")
        return "\n".join(lines).strip() or "Antiperfis indisponíveis."

    def _export_history_entry_artifact(self, entry: Any) -> None:
        """Exporta artefato primário de uma entrada do histórico."""
        result_path = str(getattr(entry, "result_path", "")).strip()
        if not result_path:
            show_error(
                self,
                what="Entrada sem artefato para exportação.",
                why="O histórico não possui caminho de arquivo associado.",
                how="Execute a análise novamente para gerar um artefato exportável.",
            )
            return
        source = Path(result_path)
        if not source.exists():
            show_error(
                self,
                what="Arquivo de resultado não encontrado.",
                why=f"O caminho salvo não existe: {source}",
                how="Reexecute a análise para regenerar o resultado.",
            )
            return

        target = filedialog.asksaveasfilename(
            title="Exportar Resultado",
            defaultextension=source.suffix or ".dat",
            filetypes=[("Todos", "*.*")],
        )
        if not target:
            return
        shutil.copy2(source, Path(target))
        self._set_status("Resultado exportado", 1.0)

    def _delete_history_entry(self, entry: Any) -> None:
        """Remove entrada selecionada do histórico."""
        entry_id = str(getattr(entry, "entry_id", "")).strip()
        if not entry_id:
            return
        if not messagebox.askyesno("Excluir Histórico", "Remover esta análise do histórico?"):
            return
        removed = self.analysis_history.delete_result(entry_id)
        if removed:
            self.corpus_tree.load_history(
                self.analysis_history,
                on_select=self._open_history_entry,
                on_action=self._handle_corpus_tree_action,
            )
            self._set_status("Entrada removida do histórico", 1.0)

    def _export_dictionary(self) -> None:
        """Exporta dicionário lexical do corpus."""
        if not self.corpus:
            return
        target = filedialog.asksaveasfilename(
            title="Exportar Dicionário",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not target:
            return
        self.corpus.export_dictionary(Path(target))
        self._set_status("Dicionário exportado", 1.0)

    def _export_segmented_corpus(self) -> None:
        """Exporta corpus segmentado em formato textual IRaMuTeQ."""
        if not self.corpus:
            return
        target = filedialog.asksaveasfilename(
            title="Exportar Corpus Segmentado",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not target:
            return
        Path(target).write_text(self._build_corpus_snapshot_text(), encoding="utf-8")
        self._set_status("Corpus segmentado exportado", 1.0)

    def _converter_para_ansi(self, texto: str) -> bytes:
        """
        Converte texto para Windows-1252 (ANSI) com fallback seguro.
        
        O IRaMuTeQ no Windows espera arquivos em CP1252. Caracteres
        que não podem ser representados em CP1252 são substituídos
        por caracteres seguros (ex: aspas tipográficas -> aspas simples).
        
        Args:
            texto: Texto em UTF-8
            
        Returns:
            Bytes em Windows-1252
        """
        # Mapeamento de caracteres Unicode para CP1252 ou substitutos
        substituicoes = {
            # Aspas tipográficas -> aspas simples
            '\u2018': "'",  # '
            '\u2019': "'",  # '
            '\u201a': "'",  # ‚
            '\u201b': "'",  # ‛
            '\u201c': '"',  # "
            '\u201d': '"',  # "
            '\u201e': '"',  # „
            '\u201f': '"',  # ‟
            # Travessões -> hífen
            '\u2010': '-',  # ‐
            '\u2011': '-',  # ‑
            '\u2012': '-',  # ‒
            '\u2013': '-',  # –
            '\u2014': '-',  # —
            '\u2015': '-',  # ―
            # Espaços especiais -> espaço normal
            '\u00a0': ' ',  # NBSP
            '\u2000': ' ',  # En quad
            '\u2001': ' ',  # Em quad
            '\u2002': ' ',  # En space
            '\u2003': ' ',  # Em space
            '\u2004': ' ',  # Three-per-em space
            '\u2005': ' ',  # Four-per-em space
            '\u2006': ' ',  # Six-per-em space
            '\u2007': ' ',  # Figure space
            '\u2008': ' ',  # Punctuation space
            '\u2009': ' ',  # Thin space
            '\u200a': ' ',  # Hair space
            '\u202f': ' ',  # Narrow no-break space
            '\u205f': ' ',  # Medium mathematical space
            # Outros
            '\u2026': '...',  # …
            '\u00ad': '',     # Soft hyphen (remove)
            '\ufeff': '',     # BOM (remove)
            '\u200b': '',     # Zero-width space (remove)
            '\u200c': '',     # Zero-width non-joiner (remove)
            '\u200d': '',     # Zero-width joiner (remove)
        }
        
        # Aplica substituições
        for char, substituto in substituicoes.items():
            texto = texto.replace(char, substituto)
        
        # Tenta codificar em Windows-1252
        # Caracteres restantes que não são mapeáveis viram '?'
        return texto.encode('windows-1252', errors='replace')

    def _export_corpus_to_txt(self) -> None:
        """Exporta corpus tratado em formato TXT (IRaMuTeQ)."""
        if not self.corpus:
            from tkinter import messagebox
            messagebox.showwarning("Aviso", "Nenhum corpus carregado.")
            return
        target = filedialog.asksaveasfilename(
            title="Exportar Corpus Tratado (TXT)",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not target:
            return
        try:
            content = self._build_corpus_snapshot_text()
            # Windows-1252 (ANSI) para compatibilidade com IRaMuTeQ
            content_ansi = self._converter_para_ansi(content)
            Path(target).write_bytes(content_ansi)
            self._set_status(f"Corpus exportado: {Path(target).name}", 1.0)
        except Exception as exc:
            log.exception("Falha ao exportar corpus")
            show_error(
                self,
                what="Falha ao exportar corpus.",
                why=str(exc),
                how="Verifique permissões da pasta de destino e tente novamente.",
            )

    def _export_corpus_to_iramuteq(self) -> None:
        """
        Exporta corpus em formato textual estruturado.

        O objetivo aqui é maximizar compatibilidade com o parser textual
        usado pelos fluxos estatisticos classicos, garantindo marcadores validos,
        conteúdo textual em cada UCI e encoding Windows-1252.
        """
        if not self.corpus:
            from tkinter import messagebox
            messagebox.showwarning("Aviso", "Nenhum corpus carregado.")
            return
        
        target = filedialog.asksaveasfilename(
            title="Exportar corpus estruturado",
            defaultextension=".txt",
            filetypes=[("Texto estruturado", "*.txt"), ("Todos", "*.*")],
        )
        if not target:
            return
        
        try:
            self._set_status("Preparando exportação do corpus...", 0.3)

            from ..importers.corpus_cleaner import CorpusCleaner
            from ..importers.corpus_validator import CorpusValidator
            cleaner = CorpusCleaner(
                converter_minusculas=False,
                remover_numeros=False,
                remover_acentos=False,
                usar_expressoes_padrao=False,
            )
            validator = CorpusValidator()

            def build_export_blocks(use_safe_markers: bool = False) -> List[str]:
                blocks: List[str] = []
                for idx, uci in enumerate(self.corpus.ucis, start=1):
                    marker = (
                        f"**** *doc_{idx} *fonte_lexianalyst"
                        if use_safe_markers
                        else self._build_iramuteq_marker(uci=uci, idx=idx)
                    )
                    uce_ids = [uce.ident for uce in uci.uces]
                    chunks: List[str] = []
                    for _uce_id, text in self.corpus.getconcorde(uce_ids):
                        segment = str(text or "").strip()
                        if segment:
                            chunks.append(segment)
                    if not chunks:
                        # Nao exporta UCI vazia para evitar erro fatal no IRaMuTeQ.
                        continue
                    blocks.append(marker)
                    # Um único bloco por UCI melhora estabilidade de segmentação no IRaMuTeQ.
                    blocks.append(" ".join(chunks))
                    blocks.append("")
                return blocks

            lines = build_export_blocks(use_safe_markers=False)
            if not lines:
                raise ValueError("Nao ha documentos textuais validos para exportacao IRaMuTeQ.")

            raw_text = "\n".join(lines).strip() + "\n"
            cleaned_text = cleaner.limpar(raw_text)

            self._set_status("Validando formato estruturado...", 0.7)
            report = validator.validate(cleaned_text)
            fallback_used = False

            if report.errors:
                # Fallback automatico para formato estritamente conservador.
                fallback_used = True
                log.warning(
                    "Exportacao IRaMuTeQ com %s erro(s). Aplicando fallback de marcadores padrao.",
                    len(report.errors),
                )
                fallback_lines = build_export_blocks(use_safe_markers=True)
                if not fallback_lines:
                    raise ValueError("Falha ao gerar fallback da exportacao IRaMuTeQ.")
                cleaned_text = cleaner.limpar("\n".join(fallback_lines).strip() + "\n")
                report = validator.validate(cleaned_text)

            if report.errors:
                why = "\n".join(
                    f"Linha {issue.line_number}: {issue.what}"
                    for issue in report.errors[:5]
                )
                if len(report.errors) > 5:
                    why += f"\n... e mais {len(report.errors) - 5} erro(s)."
                how = "\n".join(report.suggestions[:4]) if report.suggestions else (
                    "Revise os metadados das UCIs e remova blocos vazios antes de exportar."
                )
                show_error(
                    self,
                    what="Nao foi possivel gerar um corpus estruturado valido.",
                    why=why,
                    how=how,
                )
                return

            normalized = cleaned_text.replace("\r\n", "\n").replace("\r", "\n")
            normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip() + "\r\n"

            self._set_status("Gravando arquivo...", 0.9)
            Path(target).write_bytes(self._converter_para_ansi(normalized))

            if report.warnings:
                log.warning("Exportacao IRaMuTeQ com avisos: %s", report.warnings)
            if fallback_used:
                log.info("Exportacao IRaMuTeQ concluida com fallback seguro de marcadores.")

            self._set_status(f"Corpus exportado: {Path(target).name}", 1.0)
            
        except Exception as exc:
            log.exception("Falha ao exportar para IRaMuTeQ")
            show_error(
                self,
                what="Falha ao exportar o corpus estruturado.",
                why=str(exc),
                how="Verifique permissões da pasta de destino e tente novamente.",
            )

    def _export_chd_classes(self, entry: Any) -> None:
        """Exporta textos por classe CHD."""
        result = self._get_runtime_chd_result(entry)
        class_text_paths = {}
        if result is not None:
            class_text_paths = getattr(result, "class_text_paths", {}) or {}
        if not class_text_paths:
            metadata = getattr(entry, "metadata", {}) if isinstance(getattr(entry, "metadata", {}), dict) else {}
            raw_paths = metadata.get("chd_class_text_paths", {}) if isinstance(metadata.get("chd_class_text_paths", {}), dict) else {}
            class_text_paths = {
                int(class_id): Path(path)
                for class_id, path in raw_paths.items()
                if str(path).strip()
            }
        if not class_text_paths:
            show_error(
                self,
                what="Textos de classe indisponíveis.",
                why="A execução selecionada não possui exportação de classes armazenada.",
                how="Execute CHD novamente e tente exportar em seguida.",
            )
            return

        target_dir = filedialog.askdirectory(title="Selecionar pasta para exportar classes")
        if not target_dir:
            return
        folder = Path(target_dir)
        for class_id, source in class_text_paths.items():
            if source.exists():
                shutil.copy2(source, folder / f"class_{class_id}.txt")
        self._set_status("Classes CHD exportadas", 1.0)

    def _export_chd_colored(self, entry: Any) -> None:
        """Exporta HTML do corpus colorido de uma execução CHD."""
        result = self._get_runtime_chd_result(entry)
        colored_path = None
        if result is not None:
            colored_path = getattr(result, "colored_corpus_path", None)
        if not colored_path:
            metadata = getattr(entry, "metadata", {}) if isinstance(getattr(entry, "metadata", {}), dict) else {}
            colored_path = metadata.get("chd_colored_corpus_path")
        if not colored_path:
            show_error(
                self,
                what="Corpus colorido indisponível.",
                why="A execução selecionada não possui arquivo HTML associado.",
                how="Execute CHD novamente para gerar o corpus colorido.",
            )
            return
        source = Path(colored_path)
        if not source.exists():
            show_error(
                self,
                what="Arquivo de corpus colorido não encontrado.",
                why=f"O caminho salvo não existe: {source}",
                how="Reexecute a análise CHD para regenerar o HTML.",
            )
            return
        target = filedialog.asksaveasfilename(
            title="Exportar Corpus Colorido",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("Todos", "*.*")],
        )
        if not target:
            return
        shutil.copy2(source, Path(target))
        self._set_status("Corpus colorido exportado", 1.0)

    def _run_wordcloud_from_chd(self, entry: Any) -> None:
        """Gera nuvem por classe a partir do resultado CHD em memória."""
        if not self.corpus:
            return
        result = self._get_runtime_chd_result(entry)
        if result is None:
            show_error(
                self,
                what="Nuvem por classe indisponível fora da sessão atual.",
                why="Esta ação depende dos perfis CHD carregados em memória.",
                how="Selecione o CHD mais recente da sessão atual e tente novamente.",
            )
            return
        from ..analysis import WordCloudAnalysis

        output_dir = self._get_analysis_output_dir("wordcloud_from_chd")
        analysis = self._build_analysis_runner(
            WordCloudAnalysis,
            self.corpus,
            output_dir,
        )
        generated = analysis.run_per_class(getattr(result, "profiles", {}) or {}, output_dir=output_dir)
        if not generated:
            show_error(
                self,
                what="Nenhuma nuvem por classe foi gerada.",
                why="Os perfis CHD não contêm termos suficientes para montar nuvens.",
                how="Reduza filtros de frequência ou execute CHD com outro corpus.",
            )
            return
        first_class = sorted(generated.keys())[0]
        image_path = generated[first_class]
        self.results_viewer.show_image(image_path)
        self._last_analysis_result = type("GeneratedWordcloudResult", (), {"image_path": image_path})()
        self._last_analysis_context = {
            "name": "Nuvem por Classe",
            "analysis_type": "wordcloud",
            "params": {"source": "chd", "class_count": len(generated)},
            "result_path": str(image_path),
            "output_dir": str(output_dir),
        }
        self._generate_report_for_current_result("Nuvem por Classe", image_path)
        self._save_analysis_to_history("Nuvem por Classe", image_path)
        self._set_status("Nuvens por classe geradas", 1.0)

    def _run_similarity_from_chd(self, entry: Any) -> None:
        """Executa similaridade em uma classe CHD selecionada."""
        runner = self._last_analysis_runner
        result = self._get_runtime_chd_result(entry)
        if result is None or runner is None or not hasattr(runner, "run_similarity_from_class"):
            show_error(
                self,
                what="Similaridade por classe indisponível fora da sessão atual.",
                why="A ação requer o objeto de análise CHD ativo em memória.",
                how="Selecione o CHD mais recente da sessão atual e tente novamente.",
            )
            return

        class_ids = sorted((getattr(result, "class_sizes", {}) or {}).keys())
        if not class_ids:
            return
        default_class = class_ids[0]
        selected = simpledialog.askinteger(
            "Classe CHD",
            f"Informe a classe para Similaridade ({', '.join(map(str, class_ids))}):",
            initialvalue=default_class,
            parent=self,
        )
        if selected is None:
            return
        if selected not in class_ids:
            show_error(
                self,
                what=f"Classe {selected} inválida.",
                why="A classe informada não existe no CHD selecionado.",
                how=f"Escolha uma das classes disponíveis: {', '.join(map(str, class_ids))}.",
            )
            return

        sim_result = runner.run_similarity_from_class(
            selected,
            {"min_freq": 1, "graph_out": f"similarity_class_{selected}.png"},
        )
        self.results_viewer.show_image(sim_result.graph_path)
        self._last_analysis_result = sim_result
        self._last_analysis_runner = None
        self._last_analysis_context = {
            "name": "Similitude por Classe",
            "analysis_type": "similarity",
            "params": {"source": "chd", "class_id": selected},
            "result_path": str(sim_result.graph_path),
            "output_dir": str(Path(sim_result.graph_path).parent),
        }
        self._generate_report_for_current_result("Similitude por Classe", sim_result.graph_path)
        self._save_analysis_to_history("Similitude por Classe", sim_result.graph_path)
        self._set_status(f"Similaridade da classe {selected} concluída", 1.0)

    def _open_corpus_navigator(self, entry: Any = None) -> None:
        """Abre janela de navegação do corpus (com cores CHD quando disponível)."""
        if not self.corpus:
            return

        assignments: Dict[int, int] = {}
        result = self._get_runtime_chd_result(entry) if entry is not None else self._last_analysis_result
        runner = self._last_analysis_runner
        if result is not None and runner is not None and hasattr(runner, "_effective_class_uce_map"):
            class_map = getattr(runner, "_effective_class_uce_map", {}) or {}
            for class_id, uce_ids in class_map.items():
                for uce_id in uce_ids:
                    assignments[int(uce_id)] = int(class_id)
        CorpusNavigator(self, self.corpus, cluster_assignments=assignments)

    def _on_analysis_complete(self, name: str, result_path):
        """Callback quando analise completa."""
        self._enable_analysis_buttons(True)
        context = self.__dict__.get("_last_analysis_context", {})
        if not isinstance(context, dict):
            context = {}
        analysis_type = str(context.get("analysis_type", "")).lower()
        params_for_memory = context.get("params", {}) if isinstance(context.get("params", {}), dict) else {}
        if analysis_type and params_for_memory:
            self._remember_analysis_params(analysis_type, params_for_memory)
        if analysis_type == "similarity":
            params = context.get("params", {}) if isinstance(context.get("params", {}), dict) else {}
            output_dir_raw = str(context.get("output_dir", "") or "").strip()
            output_dir = Path(output_dir_raw) if output_dir_raw else None
            self._set_similarity_halo_toggle_context(
                enabled=True,
                params=params,
                output_dir=output_dir,
                show_halo=bool(params.get("show_halo", False)),
            )
        else:
            self._set_similarity_halo_toggle_context(enabled=False)

        artifact_path = Path(result_path) if result_path else None

        # 1. Renderizar imediatamente na UI atual para evitar tela vazia
        try:
            result_obj = self._last_analysis_result
            if result_obj is not None:
                self._generate_report_for_current_result(name, artifact_path)
                self._populate_all_tabs(
                    analysis_type_key=analysis_type,
                    result=result_obj,
                    artifact_path=artifact_path,
                    report_path=self._last_report_path,
                )
                try:
                    self.results_viewer.tabview.set("Gráfico")
                except Exception:
                    pass
        except Exception:
            log.exception("Falha ao renderizar resultado imediato de %s", name)

        # 2. Persistir para garantir histórico
        # Analises semanticas ja foram salvas por _execute_semantic_analysis_async;
        # evitar entrada duplicada verificando se _last_saved_history_entry_id foi setado.
        if not self._last_report_path:
            self._generate_report_for_current_result(name, artifact_path)
        saved_entry = None
        if not self.__dict__.get('_last_saved_history_entry_id'):
            saved_entry = self._save_analysis_to_history(name, result_path)

        # 3. Tenta recuperar a entrada recem-criada no historico
        try:
            if not hasattr(self.analysis_history, "load_results"):
                log.warning("analysis_history nao implementa load_results; pulando auto-abertura.")
                self._set_status(f"Análise '{name}' concluída", 1.0)
                return

            entries = self.analysis_history.load_results()
            if entries:
                latest_entry = (
                    saved_entry
                    or self._resolve_history_entry_by_id(
                        self.__dict__.get("_last_saved_history_entry_id"),
                        entries,
                    )
                    or entries[0]
                )
                history_label = f"{analysis_type.upper() or str(getattr(latest_entry, 'analysis_type', name)).upper()} · {datetime.now().strftime('%H:%M')}"
                self._bind_completed_run_to_history_entry(
                    getattr(self, "_pending_result_run_key", None),
                    getattr(latest_entry, "entry_id", None),
                    history_label,
                )
                
                log.info("Auto-abrindo resultado recém-gerado: %s", latest_entry.entry_id)
                self._open_or_focus_result_entry(latest_entry, source="completed")

                has_content_after_reopen = (
                    bool(getattr(self.results_viewer, "_current_image_path", None))
                    or bool(getattr(self.results_viewer, "_has_table_content", False))
                    or bool(str(getattr(self.results_viewer, "_current_text", "")).strip())
                    or bool(getattr(self.results_viewer, "_current_report_path", None))
                )
                if not has_content_after_reopen:
                    log.warning("Reabertura automática vazia; reaplicando renderização direta para %s", analysis_type)
                    result_obj = self._last_analysis_result
                    if result_obj is not None:
                        self._populate_all_tabs(
                            analysis_type_key=analysis_type,
                            result=result_obj,
                            artifact_path=artifact_path,
                            report_path=self._last_report_path,
                        )
                
                # Forca atualizacao da arvore
                self.corpus_tree.load_history(
                    self.analysis_history,
                    on_select=self._open_history_entry,
                    on_action=self._handle_corpus_tree_action,
                )
                self._refresh_results_sidebar_context()
            else:
                log.warning("Analise completou mas nao encontrou entrada no historico para abrir.")
        except Exception as e:
            log.error("Falha ao auto-abrir resultado: %s", e)
            self._mark_pending_result_tab_error(str(e))
            # Fallback defensivo: mantém resultado recém-gerado na UI mesmo
            # quando a restauração via histórico falhar.
            try:
                result_obj = self._last_analysis_result
                if result_obj is not None:
                    self._populate_all_tabs(
                        analysis_type_key=analysis_type,
                        result=result_obj,
                        artifact_path=artifact_path,
                        report_path=self._last_report_path,
                    )
            except Exception:
                log.exception("Falha no fallback de renderização direta após erro de auto-abertura.")
            # Evita pop-up bloqueante em contextos sem loop de UI (ex.: testes)
            self._set_status(f"Análise '{name}' concluída", 1.0)

    def _save_analysis_to_history(self, name: str, result_path):
        """Persist one completed analysis into JSON history."""
        state = getattr(self, "__dict__", {})
        context = state.get("_last_analysis_context", {}) or {}
        params = context.get("params", {})
        analysis_type = str(context.get("analysis_type") or name).lower()
        result = state.get("_last_analysis_result")
        persisted_result_path = result_path
        if analysis_type == "chd":
            output_dir_raw = str(context.get("output_dir", "") or "").strip()
            if output_dir_raw:
                persisted_result_path = output_dir_raw

        metadata: Dict[str, Any] = {
            "analysis_name": name,
            "has_visualization": bool(persisted_result_path and Path(persisted_result_path).exists()),
        }
        last_report_path = state.get("_last_report_path")
        if last_report_path and Path(last_report_path).exists():
            metadata["report_path"] = str(last_report_path)
        if result is not None:
            for field_name in (
                "backend_used",
                "n_classes",
                "index_type",
                "min_freq",
            ):
                value = getattr(result, field_name, None)
                if value is not None:
                    metadata[field_name] = value
            if analysis_type == "statistics" and isinstance(result, dict):
                stats_json_path = str(result.get("stats_json_path", "")).strip()
                if stats_json_path:
                    metadata["statistics_json_path"] = stats_json_path
                report_txt_path = str(result.get("report_txt", "")).strip()
                if report_txt_path:
                    metadata["statistics_report_txt_path"] = report_txt_path
                backend_used = str(result.get("backend_used", "")).strip()
                if backend_used:
                    metadata["backend_used"] = backend_used
                raw_graphs = result.get("graphs", {})
                if isinstance(raw_graphs, dict):
                    stats_graphs: Dict[str, str] = {}
                    for graph_key, graph_path in raw_graphs.items():
                        resolved_graph = self._resolve_existing_file_path(graph_path)
                        if resolved_graph is not None:
                            stats_graphs[str(graph_key)] = str(resolved_graph)
                    if stats_graphs:
                        metadata["statistics_graphs"] = stats_graphs
            elif analysis_type == "chd":
                metadata["chd_afc_graph_path"] = str(getattr(result, "afc_graph_path", None) or "")
                metadata["chd_profile_afc_path"] = str(
                    getattr(result, "profile_afc_path", None) or ""
                )
                metadata["chd_alternative_profile_afc_path"] = str(
                    getattr(result, "alternate_profile_afc_path", None) or ""
                )
                metadata["chd_metadata_profiles_path"] = str(
                    getattr(result, "metadata_profiles_path", None) or ""
                )
                metadata["chd_colored_corpus_path"] = str(
                    getattr(result, "colored_corpus_path", None) or ""
                )
                metadata["chd_manifest_path"] = str(
                    getattr(result, "manifest_path", None) or ""
                )
                metadata["chd_profile_ca_coords_path"] = str(
                    getattr(result, "profile_ca_coords_path", None) or ""
                )
                metadata["chd_profile_matrix_path"] = str(
                    getattr(result, "profile_matrix_path", None) or ""
                )
                metadata["chd_profile_chi2_path"] = str(
                    getattr(result, "profile_chi2_path", None) or ""
                )
                metadata["chd_vocabulary_path"] = str(
                    getattr(result, "vocabulary_path", None) or ""
                )
                metadata["chd_matrix_uce_term_path"] = str(
                    getattr(result, "matrix_uce_term_path", None) or ""
                )
                metadata["chd_uce_table_path"] = str(
                    getattr(result, "uce_table_path", None) or ""
                )
                for attr_name, metadata_key in (
                    ("chistable_path", "chd_chistable_path"),
                    ("afc_row_path", "chd_afc_row_path"),
                    ("afc_col_path", "chd_afc_col_path"),
                    ("row_coords_path", "chd_row_coords_path"),
                    ("col_coords_path", "chd_col_coords_path"),
                    ("afc_facteur_path", "chd_afc_facteur_path"),
                    ("afc2dl_notplotted_path", "chd_afc2dl_notplotted_path"),
                    ("eigenvalues_path", "chd_eigenvalues_path"),
                ):
                    metadata[metadata_key] = str(getattr(result, attr_name, None) or "")
                class_text_paths = getattr(result, "class_text_paths", {}) or {}
                metadata["chd_class_text_paths"] = {
                    str(class_id): str(path)
                    for class_id, path in class_text_paths.items()
                }
            elif analysis_type == "specificities":
                metadata["specificities_plot_path"] = str(
                    getattr(result, "specificities_plot_path", None) or ""
                )
                metadata["specificities_plot_data_path"] = str(
                    getattr(result, "specificities_plot_data_path", None) or ""
                )
                metadata["specificities_scores_csv_path"] = str(
                    getattr(result, "scores_csv_path", None) or ""
                )
                metadata["specificities_relative_csv_path"] = str(
                    getattr(result, "relative_csv_path", None) or ""
                )
                metadata["specificities_afc_graph_path"] = str(
                    getattr(result, "afc_graph_path", None) or ""
                )
            elif analysis_type == "network_text":
                metadata["nodes_csv_path"] = str(getattr(result, "nodes_csv_path", None) or "")
                metadata["edges_csv_path"] = str(getattr(result, "edges_csv_path", None) or "")
                metadata["gexf_path"] = str(getattr(result, "gexf_path", None) or "")
                metadata["net_path"] = str(getattr(result, "net_path", None) or "")
                metadata["graph_image_path"] = str(getattr(result, "graph_image_path", None) or "")
                metadata["graph_svg_path"] = str(getattr(result, "graph_svg_path", None) or "")
                metadata["layout_backend_used"] = str(getattr(result, "layout_backend_used", "") or "")
                metadata["diagnostics_path"] = str(getattr(result, "diagnostics_path", None) or "")
                metadata["n_communities"] = int(getattr(result, "n_communities", 0) or 0)
                metadata["modularity_score"] = float(getattr(result, "modularity_score", 0.0) or 0.0)
            elif analysis_type == "voyant_suite":
                metadata["termsberry_graph_path"] = str(getattr(result, "termsberry_graph_path", None) or "")
                metadata["trends_graph_path"] = str(getattr(result, "trends_graph_path", None) or "")
                metadata["document_terms_chart_path"] = str(getattr(result, "document_terms_chart_path", None) or "")
                metadata["bubblelines_graph_path"] = str(getattr(result, "bubblelines_graph_path", None) or "")
                metadata["cooccurrences_graph_path"] = str(getattr(result, "cooccurrences_graph_path", None) or "")
                metadata["document_terms_csv_path"] = str(getattr(result, "document_terms_csv_path", None) or "")
                metadata["contexts_csv_path"] = str(getattr(result, "contexts_csv_path", None) or "")
                metadata["cooccurrences_csv_path"] = str(getattr(result, "cooccurrences_csv_path", None) or "")
                metadata["trends_csv_path"] = str(getattr(result, "trends_csv_path", None) or "")
                metadata["termsberry_nodes_csv_path"] = str(getattr(result, "termsberry_nodes_csv_path", None) or "")
                metadata["termsberry_edges_csv_path"] = str(getattr(result, "termsberry_edges_csv_path", None) or "")
                metadata["bubblelines_points_csv_path"] = str(getattr(result, "bubblelines_points_csv_path", None) or "")
                metadata["summary_json_path"] = str(getattr(result, "summary_json_path", None) or "")
                metadata["selected_terms"] = list(getattr(result, "selected_terms", []) or [])
                metadata["query_terms"] = list(getattr(result, "query_terms", []) or [])
                metadata["n_documents"] = int(getattr(result, "n_documents", 0) or 0)
                metadata["n_segments"] = int(getattr(result, "n_segments", 0) or 0)
                metadata["n_contexts"] = int(getattr(result, "n_contexts", 0) or 0)
                payload = getattr(result, "voyant_suite_payload_v1", {})
                if isinstance(payload, dict):
                    try:
                        metadata["voyant_suite_payload_v1"] = json.loads(
                            json.dumps(payload, ensure_ascii=False)
                        )
                    except Exception:
                        metadata["voyant_suite_payload_v1"] = dict(payload)

            def _store_path(meta_key: str, candidate: Any) -> None:
                resolved = self._resolve_existing_file_path(candidate)
                if resolved is not None:
                    metadata[meta_key] = str(resolved)

            _store_path(
                "adjacency_matrix_path",
                getattr(result, "adjacency_matrix", None) or getattr(result, "adjacency_matrix_path", None),
            )
            _store_path(
                "table_csv_path",
                getattr(result, "table_path", None) or getattr(result, "summary_csv_path", None),
            )
            _store_path("nodes_csv_path", getattr(result, "nodes_csv_path", None))
            _store_path(
                "edges_csv_path",
                getattr(result, "edges_path", None) or getattr(result, "edges_csv_path", None),
            )
            _store_path("scores_csv_path", getattr(result, "scores_path", None))
            _store_path("distribution_csv_path", getattr(result, "distribution_csv_path", None))
            _store_path("word_sentiment_csv_path", getattr(result, "word_sentiment_csv_path", None))
            _store_path("points_csv_path", getattr(result, "points_path", None))
            _store_path("timeline_csv_path", getattr(result, "timeline_csv_path", None))
            _store_path("contingency_csv_path", getattr(result, "contingency_csv_path", None))
            _store_path("expected_csv_path", getattr(result, "expected_csv_path", None))
            _store_path("residuals_csv_path", getattr(result, "residuals_csv_path", None))
            _store_path("matrix_clusters_path", getattr(result, "clusters_path", None))
            _store_path("graph_path", getattr(result, "graph_path", None))
            _store_path("graph_image_path", getattr(result, "graph_image_path", None))
            _store_path("graph_svg_path", getattr(result, "graph_svg_path", None))
            _store_path("dendrogram_path", getattr(result, "dendrogram_path", None))
            _store_path("heatmap_path", getattr(result, "heatmap_path", None))
            _store_path("distribution_graph_path", getattr(result, "distribution_graph_path", None))
            _store_path("timeline_graph_path", getattr(result, "timeline_graph_path", None))
            _store_path("gexf_path", getattr(result, "gexf_path", None))
            _store_path("net_path", getattr(result, "net_path", None))
            _store_path("diagnostics_path", getattr(result, "diagnostics_path", None))
            _store_path("termsberry_graph_path", getattr(result, "termsberry_graph_path", None))
            _store_path("trends_graph_path", getattr(result, "trends_graph_path", None))
            _store_path("document_terms_chart_path", getattr(result, "document_terms_chart_path", None))
            _store_path("bubblelines_graph_path", getattr(result, "bubblelines_graph_path", None))
            _store_path("cooccurrences_graph_path", getattr(result, "cooccurrences_graph_path", None))
            _store_path("document_terms_csv_path", getattr(result, "document_terms_csv_path", None))
            _store_path("contexts_csv_path", getattr(result, "contexts_csv_path", None))
            _store_path("cooccurrences_csv_path", getattr(result, "cooccurrences_csv_path", None))
            _store_path("trends_csv_path", getattr(result, "trends_csv_path", None))
            _store_path("termsberry_nodes_csv_path", getattr(result, "termsberry_nodes_csv_path", None))
            _store_path("termsberry_edges_csv_path", getattr(result, "termsberry_edges_csv_path", None))
            _store_path("bubblelines_points_csv_path", getattr(result, "bubblelines_points_csv_path", None))
            _store_path("summary_json_path", getattr(result, "summary_json_path", None))
            # emotions
            _store_path("bar_graph_path", getattr(result, "bar_graph_path", None))
            _store_path("radar_graph_path", getattr(result, "radar_graph_path", None))
            _store_path("polarity_graph_path", getattr(result, "polarity_graph_path", None))
            _store_path("stats_csv_path", getattr(result, "stats_csv_path", None))
            _store_path("words_csv_path", getattr(result, "words_csv_path", None))
            _store_path("words_summary_csv_path", getattr(result, "words_summary_csv_path", None))

            artifact_candidate = self._resolve_existing_file_path(result_path)
            gallery = self._get_image_gallery(
                analysis_type_key=analysis_type,
                result=result,
                artifact_path=artifact_candidate,
                metadata=metadata,
            )
            if gallery:
                metadata["graph_gallery"] = {
                    str(label): str(path)
                    for label, path in gallery.items()
                    if path is not None
                }

            table_gallery = self._get_table_gallery(
                analysis_type_key=analysis_type,
                result=result,
                metadata=metadata,
            )
            if table_gallery:
                metadata["table_gallery"] = {
                    str(label): str(path)
                    for label, path in table_gallery.items()
                    if path is not None
                }

        manifest_path = self._write_analysis_manifest(
            analysis_type=analysis_type,
            params=params,
            result_path=persisted_result_path,
            metadata=metadata,
        )
        if manifest_path is not None:
            metadata["run_manifest_path"] = str(manifest_path)

        try:
            entry = self.analysis_history.save_result(
                analysis_type=analysis_type,
                params=params,
                result_path=persisted_result_path,
                metadata=metadata,
            )
            self._last_saved_history_entry_id = getattr(entry, "entry_id", None)
            corpus_tree = self.__dict__.get("corpus_tree")
            if corpus_tree is not None and hasattr(corpus_tree, "load_history"):
                corpus_tree.load_history(
                    self.analysis_history,
                    on_select=self._open_history_entry,
                    on_action=self._handle_corpus_tree_action,
                )
            pending_result_run_key = state.get("_pending_result_run_key")
            if pending_result_run_key:
                history_label = f"{str(getattr(entry, 'analysis_type', name)).upper()} · {datetime.now().strftime('%H:%M')}"
                self._bind_completed_run_to_history_entry(
                    pending_result_run_key,
                    getattr(entry, "entry_id", None),
                    history_label,
                )
            self._refresh_results_sidebar_context()
            log.info("Historico atualizado para analise %s (%s)", name, analysis_type)
            return entry
        except Exception:
            log.exception("Falha ao salvar historico para analise %s", name)
            return None

    @staticmethod
    def _json_compatible_manifest_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {
                str(key): MainWindow._json_compatible_manifest_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [
                MainWindow._json_compatible_manifest_value(item)
                for item in value
            ]
        return str(value)

    @staticmethod
    def _iter_manifest_file_candidates(value: Any) -> List[Path]:
        paths: List[Path] = []
        if isinstance(value, dict):
            for item in value.values():
                paths.extend(MainWindow._iter_manifest_file_candidates(item))
            return paths
        if isinstance(value, (list, tuple, set)):
            for item in value:
                paths.extend(MainWindow._iter_manifest_file_candidates(item))
            return paths
        if isinstance(value, Path):
            candidate = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                candidate = Path(text)
            except Exception:
                return []
        else:
            return []
        if candidate.exists() and candidate.is_file():
            paths.append(candidate)
        return paths

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()

    def _collect_r_script_hashes(
        self,
        analysis_type: str,
        params: Dict[str, Any],
        output_dir: Path,
    ) -> Dict[str, str]:
        script_paths: Dict[str, Path] = {}
        parity_profile = str(params.get("parity_profile", "") or "").strip().lower()
        strict_similarity = bool(params.get("strict_iramuteq_style", False))
        strict_clone = bool(params.get("strict_iramuteq_clone", False))
        rscripts_dir = (
            PathManager.official_rscripts_dir()
            if analysis_type != "chd" and parity_profile == "official_0_8a7"
            else PathManager.rscripts_dir()
        )
        if analysis_type == "similarity":
            script_paths["generated_script"] = output_dir / "similarity_script.R"
            script_paths["simi.R"] = Path(params.get("script_simi") or (rscripts_dir / "simi.R"))
            script_paths["Rgraph.R"] = Path(params.get("script_rgraph") or (rscripts_dir / "Rgraph.R"))
        elif analysis_type == "chd":
            script_paths["generated_script"] = output_dir / "chd_script.R"
            if strict_clone:
                script_paths["CHD.R"] = Path(params.get("script_chd") or (rscripts_dir / "CHD.R"))
                script_paths["chdtxt.R"] = Path(params.get("script_chdtxt") or (rscripts_dir / "chdtxt.R"))
                script_paths["anacor.R"] = Path(params.get("script_anacor") or (rscripts_dir / "anacor.R"))
                script_paths["Rgraph.R"] = Path(params.get("script_rgraph") or (rscripts_dir / "Rgraph.R"))
        if strict_similarity:
            script_paths.setdefault("Rgraph.R", Path(params.get("script_rgraph") or (rscripts_dir / "Rgraph.R")))
            script_paths.setdefault("simi.R", Path(params.get("script_simi") or (rscripts_dir / "simi.R")))
        hashes: Dict[str, str] = {}
        for label, path in script_paths.items():
            if path.exists() and path.is_file():
                hashes[label] = self._sha256_file(path)
        return hashes

    def _write_analysis_manifest(
        self,
        analysis_type: str,
        params: Dict[str, Any],
        result_path: Any,
        metadata: Dict[str, Any],
    ) -> Optional[Path]:
        context = getattr(self, "_last_analysis_context", {}) or {}
        output_dir_raw = str(context.get("output_dir", "") or "").strip()
        if output_dir_raw:
            output_dir = Path(output_dir_raw)
        elif result_path:
            output_dir = Path(result_path).resolve().parent
        else:
            return None
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None

        artifact_hashes: Dict[str, str] = {}
        file_candidates = self._iter_manifest_file_candidates(metadata)
        if result_path:
            file_candidates.extend(self._iter_manifest_file_candidates(result_path))
        for candidate in file_candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            key = str(resolved)
            if key in artifact_hashes:
                continue
            try:
                artifact_hashes[key] = self._sha256_file(resolved)
            except OSError:
                continue

        corpus_text = self.__dict__.get("_last_corpus_text", "") or self._build_corpus_snapshot_text()
        corpus_info: Dict[str, Any] = {
            "source_path": str(self.__dict__.get("_last_import_file_path")) if self.__dict__.get("_last_import_file_path") else "",
            "snapshot_sha256": self._sha256_text(corpus_text),
            "snapshot_length": len(corpus_text or ""),
        }
        corpus_obj = self.__dict__.get("corpus")
        if corpus_obj:
            try:
                corpus_info["uci_count"] = int(corpus_obj.getucinb())
                corpus_info["uce_count"] = int(corpus_obj.getucenb())
                corpus_info["word_count"] = int(corpus_obj.getwordnb())
            except Exception:
                pass

        manifest = {
            "manifest_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_type": analysis_type,
            "analysis_mode": str(
                params.get(
                    "analysis_mode",
                    "strict"
                    if (
                        bool(params.get("strict_iramuteq_clone", False))
                        or bool(params.get("strict_iramuteq_style", False))
                    )
                    else "legacy",
                )
            ),
            "parity_profile": str(params.get("parity_profile", "") or ""),
            "render_profile": str(params.get("render_profile", "") or ""),
            "params_effective": self._json_compatible_manifest_value(params),
            "corpus": corpus_info,
            "artifacts": {
                "result_path": str(result_path) if result_path else "",
                "artifact_hashes": artifact_hashes,
            },
            "r_scripts": {
                "hashes": self._collect_r_script_hashes(
                    analysis_type=analysis_type,
                    params=params,
                    output_dir=output_dir,
                ),
            },
            "environment": {
                "app_version": APP_VERSION,
                "platform": platform.platform(),
                "official_rscripts_dir": str(PathManager.official_rscripts_dir()),
                "official_configuration_dir": str(PathManager.official_configuration_dir()),
            },
        }
        manifest_path = output_dir / f"{analysis_type}_manifest.json"
        try:
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            log.exception("Falha ao gravar manifesto da analise %s", analysis_type)
            return None
        return manifest_path

    @staticmethod
    def _format_specificities_summary(result) -> str:
        """Build a compact textual summary for specificities result."""
        if result is None:
            return ""

        plot_path = getattr(result, "specificities_plot_path", None)
        lines = [
            f"Índice: {getattr(result, 'index_type', 'n/d')}",
            f"Frequência mínima: {getattr(result, 'min_freq', 'n/d')}",
            f"Backend: {getattr(result, 'backend_used', 'n/d')}",
            f"Plot específico: {'sim' if plot_path else 'não'}",
        ]
        fallback_reason = getattr(result, "fallback_reason", None)
        if fallback_reason:
            lines.append(f"Fallback: {fallback_reason}")
        lines.append("")
        lines.append("Top termos por metadado:")

        scores_by_variable = getattr(result, "scores_by_variable", {}) or {}
        for variable in sorted(scores_by_variable.keys()):
            entries = scores_by_variable[variable][:5]
            if not entries:
                continue
            lines.append(f"- {variable}")
            for entry in entries:
                lines.append(
                    f"  {entry.word}: {entry.score:.3f} "
                    f"(freq={entry.frequency}, rel={entry.relative_per_thousand:.2f}‰)"
                )
        return "\n".join(lines)

    def _on_analysis_error(self, name: str, error: Exception):
        """Callback quando analise falha."""
        self._enable_analysis_buttons(True)
        self._mark_pending_result_tab_error(str(error))
        self._set_status(f"Erro em {name}", 0)
        show_error(self, error=error)

    def _get_widget_rect(self, widget: tk.Widget) -> Optional[Tuple[int, int, int, int]]:
        if not widget or not widget.winfo_ismapped():
            return None
        self.update_idletasks()
        try:
            x = widget.winfo_rootx() - self.winfo_rootx()
            y = widget.winfo_rooty() - self.winfo_rooty()
            w = widget.winfo_width()
            h = widget.winfo_height()
            return (x, y, x + w, y + h)
        except Exception:
            return None


    def _on_close(self):
        """Fecha aplicacao."""
        if self._guided_tour and self._guided_tour.is_active:
            self._guided_tour.close("closed")
        try:
            if hasattr(self, "_messagebox_bridge") and self._messagebox_bridge is not None:
                self._messagebox_bridge.uninstall()
        except Exception:
            pass
        self._enforce_main_pane_limits(persist=True)
        self._cleanup_corpus_storage()
        self._cleanup_analysis_storage()
        self.destroy()


def run_app():
    """Ponto de entrada da aplicacao."""
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    run_app()
    _icon_photo_ref: Optional[tk.PhotoImage] = None
