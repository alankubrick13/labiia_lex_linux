"""
Testes de interface grafica (UI).

Usa mocks para evitar dependencia de GUI real.
Pula testes se CustomTkinter nao estiver disponivel.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Verificar se customtkinter esta disponivel
try:
    import customtkinter
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

# Marcar todos os testes como UI tests que podem ser pulados
pytestmark = pytest.mark.skipif(not HAS_CTK, reason="CustomTkinter nao disponivel")


class TestStyles:
    """Testes para modulo de estilos."""
    
    def test_colors_defined(self):
        """Verifica que cores estao definidas."""
        from src.ui.styles import COLORS
        
        assert 'primary' in COLORS
        assert 'secondary' in COLORS
        assert 'success' in COLORS
        assert 'warning' in COLORS
        assert 'danger' in COLORS
        assert 'background' in COLORS
        assert 'text' in COLORS
    
    def test_fonts_defined(self):
        """Verifica que fontes estao definidas."""
        from src.ui.styles import FONTS
        
        assert 'title' in FONTS
        assert 'heading' in FONTS
        assert 'body' in FONTS
        assert 'small' in FONTS
        assert 'mono' in FONTS
    
    def test_sizes_defined(self):
        """Verifica que tamanhos estao definidos."""
        from src.ui.styles import SIZES
        
        assert 'button_width' in SIZES
        assert 'dialog_width' in SIZES
        assert 'sidebar_width' in SIZES
    
    def test_get_font_helper(self):
        """Testa funcao helper get_font."""
        from src.ui.styles import get_font
        
        font = get_font('body')
        assert font is not None
        assert isinstance(font, tuple)
    
    def test_get_color_helper(self):
        """Testa funcao helper get_color."""
        from src.ui.styles import get_color
        
        color = get_color('primary')
        assert color is not None
        assert isinstance(color, str)


class TestDialogImports:
    """Testa que modulos de dialog podem ser importados."""
    
    def test_import_error_dialog(self):
        """ErrorDialog pode ser importado."""
        from src.ui.dialogs.error_dialog import ErrorDialog
        assert ErrorDialog is not None
    
    def test_import_import_dialog(self):
        """ImportDialog pode ser importado."""
        from src.ui.dialogs.import_dialog import ImportDialog
        assert ImportDialog is not None

    def test_import_dialog_defaults_to_traditional_mode(self):
        """ImportDialog deve abrir com Análise tradicional como padrão."""
        from src.ui.dialogs.import_dialog import ImportDialog

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        try:
            root.withdraw()
            with patch.object(ImportDialog, "wait_window", lambda _self: None):
                dialog = ImportDialog(root)
                try:
                    assert dialog.mode_var.get() == "traditional"
                    assert bool(dialog.clean_web_data_var.get()) is False
                    assert hasattr(dialog, "source_card_buttons")
                    assert hasattr(dialog, "advanced_section_expanded_var")
                    assert bool(dialog.advanced_section_expanded_var.get()) is False
                finally:
                    dialog.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass
    
    def test_import_analysis_dialogs(self):
        """Analysis dialogs podem ser importados."""
        from src.ui.dialogs.analysis_dialog import (
            CHDDialog, SimilarityDialog,
            WordCloudDialog, StatisticsDialog, PrototypicalDialog, LabbeDialog,
            KeynessExtraDialog, BigramNetworkExtraDialog,
            WordTreeExtraDialog,
            WordfishExtraDialog,
            XRayExtraDialog, SentimentExtraDialog,
        )
        assert CHDDialog is not None
        assert SimilarityDialog is not None
        assert WordCloudDialog is not None
        assert StatisticsDialog is not None
        assert PrototypicalDialog is not None
        assert LabbeDialog is not None
        assert KeynessExtraDialog is not None
        assert BigramNetworkExtraDialog is not None
        assert WordTreeExtraDialog is not None
        assert WordfishExtraDialog is not None
        assert XRayExtraDialog is not None
        assert SentimentExtraDialog is not None

    def test_import_concordance_dialog(self):
        """ConcordanceDialog pode ser importado."""
        from src.ui.dialogs.concordance_dialog import ConcordanceDialog
        assert ConcordanceDialog is not None

    def test_import_specificities_dialog(self):
        """SpecificitiesDialog pode ser importado."""
        from src.ui.dialogs.specificities_dialog import SpecificitiesDialog
        assert SpecificitiesDialog is not None

    def test_import_cca_auto_preview_dialog(self):
        """CCAAutoPreviewDialog pode ser importado."""
        from src.ui.dialogs.cca_auto_preview_dialog import CCAAutoPreviewDialog
        assert CCAAutoPreviewDialog is not None
    
    def test_import_settings_dialog(self):
        """SettingsDialog pode ser importado."""
        from src.ui.dialogs.settings_dialog import SettingsDialog
        assert SettingsDialog is not None

    def test_settings_dialog_exposes_visual_theme_tiles(self):
        from src.ui.dialogs.settings_dialog import SettingsDialog

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        dialog = None
        try:
            root.withdraw()
            dialog = SettingsDialog(root)
            assert hasattr(dialog, "theme_preview_cards")
            assert set(dialog.theme_preview_cards.keys()) == {"light", "dark", "system"}
            assert hasattr(dialog, "advanced_section_frame")
        finally:
            try:
                if dialog is not None:
                    dialog.destroy()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass


class TestWidgetImports:
    """Testa que modulos de widgets podem ser importados."""
    
    def test_import_corpus_tree(self):
        """CorpusTree pode ser importado."""
        from src.ui.widgets.corpus_tree import CorpusTree
        assert CorpusTree is not None
        assert hasattr(CorpusTree, "load_history")
    
    def test_import_results_viewer(self):
        """ResultsViewer pode ser importado."""
        from src.ui.widgets.results_viewer import ResultsViewer
        assert ResultsViewer is not None
        assert hasattr(ResultsViewer, "configure_similarity_halo_toggle")
    
    def test_import_graph_viewer(self):
        """GraphViewer pode ser importado."""
        from src.ui.widgets.graph_viewer import GraphViewer
        assert GraphViewer is not None

    def test_import_corpus_navigator(self):
        """CorpusNavigator pode ser importado."""
        from src.ui.widgets.corpus_navigator import CorpusNavigator
        assert CorpusNavigator is not None


class TestMainWindowImports:
    """Testa que MainWindow pode ser importado."""
    
    def test_import_main_window(self):
        """MainWindow pode ser importado."""
        from src.ui.main_window import MainWindow
        assert MainWindow is not None
    
    def test_import_run_app(self):
        """run_app pode ser importado."""
        from src.ui.main_window import run_app
        assert run_app is not None

    def test_build_traditional_collection_text_preserves_documents(self):
        """Colecao multi-arquivo em modo tradicional deve manter uma UCI por arquivo."""
        from src.ui.main_window import MainWindow

        metadata = {
            "collection_mode": True,
            "documents": [
                {"name": "Doc A", "text": "primeiro texto"},
                {"name": "Doc B", "text": "segundo texto"},
                {"name": "Doc C", "text": "terceiro texto"},
            ],
        }
        built = MainWindow._build_traditional_collection_text(
            text="fallback",
            metadata=metadata,
        )

        assert built.count("**** *doc_") == 3
        assert "primeiro texto" in built
        assert "segundo texto" in built
        assert "terceiro texto" in built

    def test_build_traditional_collection_text_keeps_original_when_invalid(self):
        """Sem metadata valido de colecao, deve manter texto original."""
        from src.ui.main_window import MainWindow

        original = "texto original"
        built = MainWindow._build_traditional_collection_text(
            text=original,
            metadata={"collection_mode": False},
        )
        assert built == original

    def test_build_corpus_from_text_uses_global_para_counter(self, tmp_path):
        """Para IDs devem continuar globais entre UCIs (sem reset por documento)."""
        from src.core.corpus import Corpus
        from src.ui.main_window import MainWindow

        corpus = Corpus()
        corpus.connect(tmp_path / "mw_para.db")
        try:
            window = MainWindow.__new__(MainWindow)
            window.corpus = corpus
            window._loaded_lexicon = None

            text = "\n".join(
                [
                    "**** *doc_a",
                    "primeiro segmento do documento a",
                    "",
                    "**** *doc_b",
                    "segundo segmento do documento b",
                ]
            )
            window._build_corpus_from_text(text)

            para_ids = [int(uce.para) for uci in corpus.ucis for uce in uci.uces]
            assert para_ids
            assert para_ids == sorted(para_ids)
            assert len(set(para_ids)) == len(para_ids)
        finally:
            corpus.close()


class TestUIPackageExports:
    """Testa exports do pacote UI."""
    
    def test_ui_init_exports(self):
        """Verifica exports do __init__.py."""
        from src.ui import (
            apply_theme, COLORS, FONTS, SIZES,
            get_font, get_color, MainWindow, run_app
        )
        assert apply_theme is not None
        assert COLORS is not None
        assert FONTS is not None
        assert SIZES is not None
        assert MainWindow is not None
        assert run_app is not None
    
    def test_dialogs_init_exports(self):
        """Verifica exports de dialogs/__init__.py."""
        from src.ui.dialogs import (
            ImportDialog, CHDDialog, SimilarityDialog,
            WordCloudDialog, StatisticsDialog,
            ConcordanceDialog,
            SpecificitiesDialog,
            PrototypicalDialog,
            LabbeDialog,
            KeynessExtraDialog,
            BigramNetworkExtraDialog,
            WordTreeExtraDialog,
            WordfishExtraDialog,
            XRayExtraDialog,
            SentimentExtraDialog,
            WordSelectorDialog,
            CCAAutoPreviewDialog,
            ErrorDialog, SettingsDialog
        )
        assert ImportDialog is not None
        assert CHDDialog is not None
        assert ConcordanceDialog is not None
        assert SpecificitiesDialog is not None
        assert PrototypicalDialog is not None
        assert LabbeDialog is not None
        assert KeynessExtraDialog is not None
        assert BigramNetworkExtraDialog is not None
        assert WordTreeExtraDialog is not None
        assert WordfishExtraDialog is not None
        assert XRayExtraDialog is not None
        assert SentimentExtraDialog is not None
        assert WordSelectorDialog is not None
        assert CCAAutoPreviewDialog is not None
        assert ErrorDialog is not None
    
    def test_widgets_init_exports(self):
        """Verifica exports de widgets/__init__.py."""
        from src.ui.widgets import (
            CorpusTree, ResultsViewer, GraphViewer, CorpusNavigator, AnalysisCatalogView
        )
        assert CorpusTree is not None
        assert ResultsViewer is not None
        assert GraphViewer is not None
        assert CorpusNavigator is not None
        assert AnalysisCatalogView is not None


class TestErrorDialogLogic:
    """Testa logica do ErrorDialog sem GUI."""
    
    def test_error_message_format(self):
        """Verifica que ErrorDialog aceita formato what/why/how."""
        from src.ui.dialogs.error_dialog import ErrorDialog
        
        # Verificar que a classe existe e tem os metodos esperados
        assert hasattr(ErrorDialog, '__init__')
        assert hasattr(ErrorDialog, '_create_widgets')
        assert hasattr(ErrorDialog, '_center_on_parent')


class TestAnalysisDialogParameters:
    """Testa parametros dos dialogos de analise."""
    
    def test_chd_dialog_has_build_result(self):
        """CHDDialog tem metodo _build_result."""
        from src.ui.dialogs.analysis_dialog import CHDDialog
        assert hasattr(CHDDialog, '_build_result')
    
    def test_similarity_dialog_has_build_result(self):
        """SimilarityDialog tem metodo _build_result."""
        from src.ui.dialogs.analysis_dialog import SimilarityDialog
        assert hasattr(SimilarityDialog, '_build_result')
    
    def test_wordcloud_dialog_has_build_result(self):
        """WordCloudDialog tem metodo _build_result."""
        from src.ui.dialogs.analysis_dialog import WordCloudDialog
        assert hasattr(WordCloudDialog, '_build_result')


class TestGuidedTourLayout:
    """Regressões de layout do tutorial guiado."""

    def test_guided_tour_keeps_buttons_before_message_area(self):
        from src.ui.widgets.guided_tour import GuidedTour, TourStep

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        tour = None
        try:
            root.geometry("1024x768")
            root.update_idletasks()
            root.deiconify()
            root.update()

            tour = GuidedTour(
                root,
                steps=[
                    TourStep(
                        title="Teste",
                        message="Mensagem longa\n" * 20,
                        target_getter=lambda: (100, 100, 300, 200),
                    )
                ],
            )
            tour.start()
            root.update_idletasks()

            assert tour._buttons_frame is not None
            assert tour._message_scroll is not None
            assert tour._buttons_frame.winfo_manager() == "pack"

            btn_y = int(tour._buttons_frame.winfo_rooty())
            msg_y = int(tour._message_scroll.winfo_rooty())
            assert btn_y <= msg_y
        finally:
            try:
                if tour is not None:
                    tour.close("test_done")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass

    def test_guided_tour_runs_before_enter_and_uses_fallback_rect(self):
        from src.ui.widgets.guided_tour import GuidedTour, TourStep

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        executed = []
        tour = None
        try:
            root.geometry("900x640")
            root.update_idletasks()
            root.deiconify()
            root.update()

            tour = GuidedTour(
                root,
                steps=[
                    TourStep(
                        title="Teste",
                        message="Conteudo",
                        target_getter=lambda: None,
                        before_enter=lambda: executed.append("ran"),
                        anchor_padding=0,
                        fallback_rect=(40, 40, 280, 180),
                    )
                ],
            )
            tour.start()
            root.update_idletasks()

            assert executed == ["ran"]
            assert tour._current_target_rect == (40, 40, 280, 180)
        finally:
            try:
                if tour is not None:
                    tour.close("test_done")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass

    def test_guided_tour_keeps_card_inside_small_viewport(self):
        from src.ui.widgets.guided_tour import GuidedTour, TourStep

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        tour = None
        try:
            root.withdraw()
            root.geometry("1280x720")
            root.update_idletasks()

            tour = GuidedTour(
                root,
                steps=[
                    TourStep(
                        title="Teste",
                        message=("Mensagem longa " * 100).strip(),
                        target_getter=lambda: (980, 520, 1240, 690),
                        preferred_placement="right",
                    )
                ],
            )
            tour.start()
            root.update_idletasks()

            assert tour._card is not None
            x = int(tour._card.winfo_x())
            y = int(tour._card.winfo_y())
            width = int(tour._card.winfo_width())
            height = int(tour._card.winfo_height())
            viewport_w = max(int(root.winfo_width()), 1280)
            viewport_h = max(int(root.winfo_height()), 720)

            assert x >= 0
            assert y >= 0
            assert x + width <= viewport_w
            assert y + height <= viewport_h
        finally:
            try:
                if tour is not None:
                    tour.close("test_done")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass

    def test_guided_tour_uses_in_window_overlay_not_toplevel(self):
        import tkinter as tk
        from src.ui.widgets.guided_tour import GuidedTour, TourStep

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        tour = None
        try:
            root.geometry("1024x768")
            root.update_idletasks()

            tour = GuidedTour(
                root,
                steps=[
                    TourStep(
                        title="Teste",
                        message="Conteudo",
                        target_getter=lambda: (80, 80, 240, 180),
                    )
                ],
            )
            tour.start()
            root.update_idletasks()

            assert tour._overlay is not None
            assert isinstance(tour._overlay, tk.Frame)
            assert not isinstance(tour._overlay, tk.Toplevel)
            assert tour._overlay.master is root
            assert tour._card is not None
            assert tour._card.master is root
        finally:
            try:
                if tour is not None:
                    tour.close("test_done")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass

    def test_guided_tour_repeated_start_does_not_create_duplicate_overlay(self):
        from src.ui.widgets.guided_tour import GuidedTour, TourStep

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        tour = None
        try:
            root.geometry("1024x768")
            root.update_idletasks()
            tour = GuidedTour(
                root,
                steps=[
                    TourStep(
                        title="Teste",
                        message="Conteudo",
                        target_getter=lambda: (80, 80, 240, 180),
                    )
                ],
            )
            tour.start()
            first_overlay = tour._overlay
            first_card = tour._card

            tour.start()
            tour.bring_to_front(reset_to_first=True)
            root.update_idletasks()

            assert tour._overlay is first_overlay
            assert tour._card is first_card
            assert len(tour._shade_regions) == 4
            assert len(tour._spotlight_border) == 4
        finally:
            try:
                if tour is not None:
                    tour.close("test_done")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass

    def test_guided_tour_configure_sync_keeps_card_geometry_stable(self):
        from src.ui.widgets.guided_tour import GuidedTour, TourStep

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        executed = []
        tour = None
        try:
            root.geometry("1366x768")
            root.update_idletasks()
            tour = GuidedTour(
                root,
                steps=[
                    TourStep(
                        title="Teste",
                        message="Conteudo",
                        target_getter=lambda: (100, 100, 320, 220),
                        before_enter=lambda: executed.append("entered"),
                    )
                ],
            )
            tour.start()
            root.update_idletasks()
            assert executed == ["entered"]

            first_geometry = tour._last_card_geometry
            for _ in range(5):
                tour._do_configure_sync()
                root.update_idletasks()

            assert tour._last_card_geometry == first_geometry
            assert executed == ["entered"]
        finally:
            try:
                if tour is not None:
                    tour.close("test_done")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass

    def test_guided_tour_source_has_no_window_manager_overlay_code(self):
        source = (PROJECT_ROOT / "src" / "ui" / "widgets" / "guided_tour.py").read_text(encoding="utf-8")

        forbidden = [
            "Toplevel",
            "overrideredirect",
            "transparentcolor",
            "transient",
            "topmost",
            "ctypes",
            "GetForegroundWindow",
            "_run_visibility_guard",
            "_master_is_foreground_window",
        ]
        for token in forbidden:
            assert token not in source


class TestStylesHelperFunctions:
    """Testa funcoes auxiliares de estilos."""
    
    def test_get_font_returns_default_for_unknown(self):
        """get_font retorna body para chave desconhecida."""
        from src.ui.styles import get_font, FONTS
        
        font = get_font('nonexistent_key')
        assert font == FONTS.get('body')
    
    def test_get_color_returns_default_for_unknown(self):
        """get_color retorna text para chave desconhecida."""
        from src.ui.styles import get_color, COLORS
        
        color = get_color('nonexistent_key')
        assert color == COLORS.get('text')


class TestResultsViewerVoyant:
    """Testes de robustez da renderização Voyant no ResultsViewer."""

    def test_show_table_gallery_repack_is_stable(self, tmp_path):
        from src.ui.widgets.results_viewer import ResultsViewer

        csv_a = tmp_path / "a.csv"
        csv_b = tmp_path / "b.csv"
        csv_a.write_text("col1;col2\n1;2\n", encoding="utf-8")
        csv_b.write_text("col1;col2\n3;4\n", encoding="utf-8")

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        try:
            root.withdraw()
            try:
                viewer = ResultsViewer(root)
            except Exception as exc:
                pytest.skip(f"ResultsViewer indisponível no ambiente atual: {exc}")
            viewer.pack(fill="both", expand=True)
            viewer.show_table_gallery(
                {
                    "Tabela A": csv_a,
                    "Tabela B": csv_b,
                }
            )
            assert viewer._has_table_content is True
            assert viewer._current_table_path is not None
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_graph_finalize_preserves_fit_instead_of_forcing_default_zoom(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        class _DummyTabView:
            def __init__(self):
                self._value = "Gráfico"

            def set(self, value):
                self._value = value

            def get(self):
                return self._value

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer._pending_graph_finalize_job = "job-id"
        viewer._current_image_source = object()
        viewer.tabview = _DummyTabView()
        viewer._current_content_tab = lambda: "Gráfico"
        viewer.update_idletasks = lambda: None
        calls = []
        viewer._fit_image_to_view = lambda sync=False, allow_below_min=False, allow_upscale=False: calls.append(
            ("fit", sync, allow_below_min, allow_upscale)
        )
        viewer._render_current_image = lambda sync=False: calls.append(("render", sync))
        viewer._update_zoom_label = lambda tab=None: calls.append(("label", tab))
        viewer._sync_active_tab_state = lambda: calls.append(("sync",))
        viewer._set_zoom = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("_set_zoom não deve ser chamado no finalize")
        )

        ResultsViewer._run_graph_finalize(viewer)

        assert viewer._pending_graph_finalize_job is None
        assert ("fit", False, True, False) in calls
        assert ("render", False) in calls
        assert ("label", "Gráfico") in calls

    def test_ctk_image_display_size_compensates_windows_scaling(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer.image_label = object()
        viewer._get_widget_scaling = lambda _widget: 1.5

        assert ResultsViewer._ctk_image_display_size(viewer, (1500, 900)) == (1000, 600)

    def test_ctk_image_display_size_keeps_native_size_at_100_percent(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer.image_label = object()
        viewer._get_widget_scaling = lambda _widget: 1.0

        assert ResultsViewer._ctk_image_display_size(viewer, (1500, 900)) == (1500, 900)

    def test_fit_image_to_view_never_drops_below_interactive_minimum(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        class _DummyImage:
            size = (5000, 3000)

        class _DummyCanvas:
            def winfo_width(self):
                return 1000

            def winfo_height(self):
                return 620

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer._current_image_source = _DummyImage()
        viewer.image_canvas = _DummyCanvas()
        viewer.image_label = object()
        viewer._zoom_min = 30
        viewer._zoom_fit_min = 50
        viewer._zoom_max = 300
        viewer._get_widget_scaling = lambda _widget: 1.0
        calls = []
        viewer._set_zoom = lambda *args, **kwargs: calls.append((args, kwargs))
        viewer.update_idletasks = lambda: None

        ResultsViewer._fit_image_to_view(viewer, sync=False, allow_below_min=True)

        assert calls
        args, kwargs = calls[-1]
        assert args[:2] == ("Gráfico", 20)
        assert kwargs["min_override"] == 50

    def test_drop_empty_iramuteq_uci_blocks_keeps_only_valid_documents(self):
        from src.ui.main_window import MainWindow

        text = "\n**** *doc_1\n\n**** *doc_2\ntexto valido\n\n**** *doc_3\n   \n"

        cleaned = MainWindow._drop_empty_iramuteq_uci_blocks(text)

        assert "**** *doc_1" not in cleaned
        assert "**** *doc_2" in cleaned
        assert "texto valido" in cleaned
        assert "**** *doc_3" not in cleaned


class TestResultsViewerAnalysisTabs:
    """Regressões para troca de abas de análise durante loading."""

    def test_public_analysis_tab_helpers_create_pending_finalize_and_error_states(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer._analysis_tabs = {}
        viewer._analysis_tab_order = []
        viewer._active_analysis_tab_key = None
        viewer._loading_content = False
        viewer._pending_analysis_tab_key = None
        viewer._restoring_analysis_tab = False
        viewer._default_zoom_levels = {"Gráfico": 100, "Tabela": 100, "Estatísticas": 100}
        viewer._new_tab_snapshot = ResultsViewer._new_tab_snapshot.__get__(viewer, ResultsViewer)
        viewer._activate_analysis_tab = ResultsViewer._activate_analysis_tab.__get__(viewer, ResultsViewer)
        viewer._render_analysis_tab_header = lambda: None
        viewer._restore_active_tab_state = lambda: None
        viewer._show_blank_start_state = lambda: None
        viewer.clear = lambda sync=False, force=False: None

        assert ResultsViewer.has_analysis_tab(viewer, "run_1") is False
        ResultsViewer.create_pending_analysis_tab(viewer, "run_1", "Estatísticas")
        assert ResultsViewer.has_analysis_tab(viewer, "run_1") is True
        assert viewer._analysis_tabs["run_1"]["status"] == "pending"
        assert viewer._active_analysis_tab_key == "run_1"

        ResultsViewer.finalize_analysis_tab(viewer, "run_1", label="Estatísticas 10:30")
        assert viewer._analysis_tabs["run_1"]["status"] == "ready"
        assert viewer._analysis_tabs["run_1"]["label"] == "Estatísticas 10:30"

        ResultsViewer.mark_analysis_tab_error(viewer, "run_1", "Falhou")
        assert viewer._analysis_tabs["run_1"]["status"] == "error"
        assert viewer._analysis_tabs["run_1"]["error_message"] == "Falhou"

    def test_tab_switch_during_loading_does_not_change_active_key(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer._analysis_tabs = {
            "wordcloud": {"label": "WORDCLOUD"},
            "network": {"label": "NETWORK_TEXT"},
        }
        viewer._analysis_tab_order = ["wordcloud", "network"]
        viewer._active_analysis_tab_key = "network"
        viewer._pending_analysis_tab_key = None
        viewer._loading_content = True
        viewer.after = lambda _ms, _cb: None

        ResultsViewer._activate_analysis_tab(viewer, "wordcloud")

        assert viewer._active_analysis_tab_key == "network"
        assert viewer._pending_analysis_tab_key == "wordcloud"

    def test_sync_during_loading_does_not_overwrite_other_tab_snapshot(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        class _DummyTabView:
            def get(self):
                return "Gráfico"

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer._restoring_analysis_tab = False
        viewer._loading_content = True
        viewer._active_analysis_tab_key = "network"
        viewer._pending_analysis_tab_key = "wordcloud"
        viewer._analysis_tabs = {
            "wordcloud": {"text": "NUVEM_ANTERIOR"},
            "network": {"text": "REDE_ANTERIOR"},
        }
        viewer._current_image_path = None
        viewer._image_gallery = {}
        viewer._active_image_label = None
        viewer._color_overrides = {}
        viewer._color_tolerance = 20
        viewer._is_voyant_graph_gallery = False
        viewer._current_voyant_payload = {}
        viewer._current_table_path = None
        viewer._table_gallery = {}
        viewer._active_table_label = None
        viewer._current_text = "REDE_ATUAL"
        viewer._current_stats_dict = None
        viewer._current_chd_profiles = None
        viewer._current_chd_class_sizes = {}
        viewer._current_chd_afc_path = None
        viewer._current_chd_metadata_path = None
        viewer._current_chd_colored_path = None
        viewer._current_chd_class_texts = {}
        viewer._current_chd_typical_segments = {}
        viewer._current_chd_antiprofiles = {}
        viewer._current_chd_repeated_segments = {}
        viewer._current_report_path = None
        viewer._current_data_export_path = None
        viewer._current_data_export_sources = []
        viewer._zoom_levels = {"Gráfico": 100, "Estatísticas": 100, "Tabela": 100}
        viewer._has_table_content = False
        viewer.tabview = _DummyTabView()

        ResultsViewer._sync_active_tab_state(viewer)

        assert viewer._analysis_tabs["wordcloud"]["text"] == "NUVEM_ANTERIOR"
        assert viewer._analysis_tabs["network"]["text"] == "REDE_ANTERIOR"

    def test_pending_activation_restores_target_snapshot_after_loading(self):
        from src.ui.widgets.results_viewer import ResultsViewer

        viewer = ResultsViewer.__new__(ResultsViewer)
        viewer._analysis_tabs = {
            "wordcloud": {"label": "WORDCLOUD"},
            "network": {"label": "NETWORK_TEXT"},
        }
        viewer._active_analysis_tab_key = "network"
        viewer._pending_analysis_tab_key = "wordcloud"
        viewer._loading_content = False

        calls = []

        def _activate(key):
            calls.append(key)
            viewer._active_analysis_tab_key = key

        viewer._activate_analysis_tab = _activate

        ResultsViewer._flush_pending_analysis_tab_activation(viewer)

        assert viewer._pending_analysis_tab_key is None
        assert calls == ["wordcloud"]
        assert viewer._active_analysis_tab_key == "wordcloud"


class TestMainWindowResultsNavigation:
    def test_similarity_halo_toggle_downgrades_strict_mode_for_refresh(self, tmp_path):
        from src.ui.main_window import MainWindow

        executed_params = {}
        toggle_calls = []

        class _Thread:
            def __init__(self, target=None, daemon=None):
                self.target = target
                self.daemon = daemon

            def start(self):
                if self.target is not None:
                    self.target()

        class _Viewer:
            def configure_similarity_halo_toggle(self, **kwargs):
                toggle_calls.append(kwargs)

            def show_image(self, _path):
                return None

        class _Runner:
            def run(self, params):
                executed_params.update(dict(params))
                return SimpleNamespace(graph_path=tmp_path / "similarity.png")

        output_dir = tmp_path / "similarity"
        output_dir.mkdir()

        window = MainWindow.__new__(MainWindow)
        window.results_viewer = _Viewer()
        window.corpus = object()
        window._similarity_halo_refresh_running = False
        window._similarity_halo_context = {
            "params": {
                "strict_iramuteq_style": True,
                "renderer_backend": "iramuteq_r",
                "analysis_mode": "strict",
                "show_halo": False,
            },
            "output_dir": str(output_dir),
            "show_halo": False,
        }
        window._enable_analysis_buttons = lambda *_args, **_kwargs: None
        window._set_status = lambda *args, **kwargs: None
        window._last_analysis_result = None
        window._last_analysis_runner = None
        window._last_analysis_context = {}
        window.after = lambda _delay, callback: callback()
        window._build_analysis_runner = lambda *_args, **_kwargs: _Runner()
        window._set_similarity_halo_toggle_context = (
            lambda **kwargs: toggle_calls.append({"context": kwargs})
        )

        with patch("src.ui.main_window.threading.Thread", _Thread):
            MainWindow._on_similarity_halo_toggle(window, True)

        assert executed_params["show_halo"] is True
        assert executed_params["detect_communities"] is True
        assert executed_params["strict_iramuteq_style"] is False
        assert executed_params["analysis_mode"] == "legacy"
        assert executed_params["render_profile"] == "publication_polish"

    def test_execute_analysis_async_resets_previous_history_identity_before_starting_new_run(self):
        from src.ui.main_window import MainWindow

        class _Thread:
            def __init__(self, target=None, daemon=None):
                self.target = target
                self.daemon = daemon

            def start(self):
                return None

        window = MainWindow.__new__(MainWindow)
        window._set_status = lambda *args, **kwargs: None
        window._enable_analysis_buttons = lambda *_args, **_kwargs: None
        window._last_saved_history_entry_id = "history_old"
        window._last_report_path = "old_report.html"

        with patch("src.ui.main_window.threading.Thread", _Thread):
            MainWindow._execute_analysis_async(
                window,
                "Nuvem de Palavras",
                {"analysis_type": "wordcloud"},
            )

        assert window._last_saved_history_entry_id is None
        assert window._last_report_path is None

    def test_on_analysis_complete_prefers_saved_history_entry_instead_of_first_loaded_entry(self):
        from src.ui.main_window import MainWindow

        wrong_entry = SimpleNamespace(entry_id="entry_old", analysis_type="voyant_suite")
        correct_entry = SimpleNamespace(entry_id="entry_new", analysis_type="wordcloud")
        opened = []
        binds = []

        class _TabView:
            def set(self, _name):
                return None

        class _Viewer:
            def __init__(self):
                self.tabview = _TabView()
                self._current_image_path = None
                self._has_table_content = False
                self._current_text = ""
                self._current_report_path = None

        class _CorpusTree:
            def load_history(self, *args, **kwargs):
                return None

        window = MainWindow.__new__(MainWindow)
        window.results_viewer = _Viewer()
        window.corpus_tree = _CorpusTree()
        window.analysis_history = SimpleNamespace(load_results=lambda: [wrong_entry, correct_entry])
        window._last_analysis_context = {"analysis_type": "wordcloud", "params": {}}
        window._last_analysis_result = object()
        window._last_saved_history_entry_id = "entry_new"
        window._last_report_path = None
        window._pending_result_run_key = "run_123"
        window._enable_analysis_buttons = lambda *_args, **_kwargs: None
        window._remember_analysis_params = lambda *_args, **_kwargs: None
        window._set_similarity_halo_toggle_context = lambda *args, **kwargs: None
        window._generate_report_for_current_result = lambda *args, **kwargs: None
        window._populate_all_tabs = lambda *args, **kwargs: None
        window._save_analysis_to_history = lambda *args, **kwargs: pytest.fail("não deveria salvar entrada errada novamente")
        window._bind_completed_run_to_history_entry = lambda run_key, entry_id, label: binds.append((run_key, entry_id, label))
        window._open_or_focus_result_entry = lambda entry, source="": opened.append((entry, source))
        window._refresh_results_sidebar_context = lambda: None
        window._set_status = lambda *args, **kwargs: None

        MainWindow._on_analysis_complete(window, "Nuvem de Palavras", None)

        assert opened == [(correct_entry, "completed")]
        assert binds == [("run_123", "entry_new", "WORDCLOUD · " + binds[0][2].split(" · ", 1)[1])]

    def test_on_analysis_error_marks_pending_tab_and_clears_pending_identity(self):
        from src.ui.main_window import MainWindow

        marked = []

        class _Viewer:
            def mark_analysis_tab_error(self, key, message=None):
                marked.append((key, message))

        window = MainWindow.__new__(MainWindow)
        window.results_viewer = _Viewer()
        window._pending_result_run_key = "run_pending"
        window._pending_result_tab_label = "CHD"
        window._enable_analysis_buttons = lambda *_args, **_kwargs: None
        window._set_status = lambda *args, **kwargs: None
        window._refresh_results_sidebar_context = lambda: None

        with patch("src.ui.main_window.show_error") as show_error:
            MainWindow._on_analysis_error(window, "CHD", RuntimeError("falhou"))

        assert marked == [("run_pending", "falhou")]
        assert window._pending_result_run_key is None
        assert window._pending_result_tab_label is None
        assert show_error.called

    def test_save_analysis_to_history_uses_chd_output_dir_for_persisted_entry(self, tmp_path):
        from src.ui.main_window import MainWindow

        output_dir = tmp_path / "chd_run"
        output_dir.mkdir()
        dendrogram = output_dir / "dendrogram.png"
        dendrogram.write_bytes(b"png")

        saved = {}

        class _History:
            def save_result(self, **kwargs):
                saved.update(kwargs)
                return SimpleNamespace(entry_id="entry_chd")

        window = MainWindow.__new__(MainWindow)
        window.analysis_history = _History()
        window._last_analysis_context = {
            "analysis_type": "chd",
            "params": {"analysis_mode": "strict"},
            "output_dir": str(output_dir),
        }
        window._last_analysis_result = SimpleNamespace(
            dendrogram_path=str(dendrogram),
            afc_graph_path="",
            profile_afc_path="",
            metadata_profiles_path="",
            colored_corpus_path="",
            class_text_paths={},
        )
        window._last_report_path = None
        window._resolve_existing_file_path = lambda value: None
        window._get_image_gallery = lambda **kwargs: {}
        window._get_table_gallery = lambda **kwargs: {}
        window._write_analysis_manifest = lambda **kwargs: None
        window._refresh_results_sidebar_context = lambda: None
        window._handle_corpus_tree_action = lambda *args, **kwargs: None

        entry = MainWindow._save_analysis_to_history(window, "CHD", str(dendrogram))

        assert entry.entry_id == "entry_chd"
        assert saved["result_path"] == str(output_dir)
        assert saved["analysis_type"] == "chd"

    def test_open_history_entry_reuses_existing_history_tab_without_clearing(self):
        from src.ui.main_window import MainWindow

        class _Viewer:
            def __init__(self):
                self.calls = []

            def has_analysis_tab(self, key):
                self.calls.append(("has", key))
                return True

            def focus_analysis_tab(self, key):
                self.calls.append(("focus", key))

            def clear(self, **kwargs):
                self.calls.append(("clear", kwargs))

        entry = SimpleNamespace(entry_id="abc123", analysis_type="statistics")
        window = MainWindow.__new__(MainWindow)
        window.results_viewer = _Viewer()
        window._ensure_results_workspace = lambda: None
        window.analysis_history = SimpleNamespace()

        MainWindow._open_history_entry(window, entry)

        assert ("has", "history_abc123") in window.results_viewer.calls
        assert ("focus", "history_abc123") in window.results_viewer.calls
        assert not any(call[0] == "clear" for call in window.results_viewer.calls)

    def test_decorate_results_viewer_methods_forces_snapshot_sync_after_render(self):
        from src.ui.main_window import MainWindow

        class _Viewer:
            def __init__(self):
                self.calls = []
                self._shell_wrapped = False

            def show_text(self, *args, **kwargs):
                self.calls.append(("show_text", args, kwargs))
                return "ok"

            def _sync_active_tab_state(self):
                self.calls.append(("sync",))

        window = MainWindow.__new__(MainWindow)
        window.results_viewer = _Viewer()
        window._ensure_results_workspace = lambda: window.results_viewer.calls.append(("ensure",))
        window._refresh_results_sidebar_context = lambda: window.results_viewer.calls.append(("refresh_sidebar",))

        MainWindow._decorate_results_viewer_methods(window)
        result = window.results_viewer.show_text("demo")

        assert result == "ok"
        assert window.results_viewer.calls == [
            ("ensure",),
            ("show_text", ("demo",), {}),
            ("sync",),
            ("refresh_sidebar",),
        ]


class TestMainWindowImageGallery:
    """Testes de deduplicação da galeria de imagens no MainWindow."""

    def test_get_image_gallery_avoids_duplicate_suffix_for_same_label(self, tmp_path):
        from PIL import Image
        from src.ui.main_window import MainWindow

        def make_png(path):
            image = Image.new("RGB", (120, 80), color=(210, 210, 210))
            image.save(path, format="PNG")

        dendro_meta = tmp_path / "dendro_meta.png"
        dendro_runtime = tmp_path / "dendro_runtime.png"
        afc_meta = tmp_path / "afc_meta.png"
        afc_runtime = tmp_path / "afc_runtime.png"
        afc_alternate = tmp_path / "afc_alternate.png"
        artifact = tmp_path / "artifact.png"
        for path in (dendro_meta, dendro_runtime, afc_meta, afc_runtime, afc_alternate, artifact):
            make_png(path)

        result = SimpleNamespace(
            dendrogram_path=str(dendro_runtime),
            polished_dendrogram_path=str(dendro_runtime),
            afc_graph_path=str(afc_meta),
            profile_afc_path=str(afc_runtime),
            alternate_profile_afc_path=str(afc_alternate),
        )
        metadata = {
            "graph_gallery": {
                "Dendrograma": str(dendro_meta),
                "AFC Perfis": str(afc_runtime),
            },
            "chd_afc_graph_path": str(afc_meta),
            "chd_profile_afc_path": str(afc_runtime),
            "chd_alternative_profile_afc_path": str(afc_alternate),
            "native_dendrogram_path": str(dendro_meta),
            "polished_dendrogram_path": str(dendro_runtime),
            "dendrogram_path": str(dendro_meta),
        }

        window = MainWindow.__new__(MainWindow)
        gallery = window._get_image_gallery(
            analysis_type_key="chd",
            result=result,
            artifact_path=artifact,
            metadata=metadata,
        )

        assert "Dendrograma" in gallery
        assert "Phylograma" in gallery
        assert "AFC Perfis" in gallery
        assert "AFC Perfis alternativo" in gallery
        assert "AFC" not in gallery
        assert "Principal" not in gallery
        assert "Dendrograma (2)" not in gallery
        assert "AFC Perfis (2)" not in gallery

    def test_apply_graph_default_zoom_for_network_text_uses_60_percent(self):
        from src.ui.main_window import MainWindow

        calls = []

        class _Viewer:
            def set_graph_zoom_percent(self, value, sync=False, persist=True):
                calls.append((value, sync, persist))

        window = MainWindow.__new__(MainWindow)
        window.results_viewer = _Viewer()

        MainWindow._apply_graph_default_zoom_for_analysis(window, "network_text")
        MainWindow._apply_graph_default_zoom_for_analysis(window, "wordcloud")

        assert calls == [(60, False, True)]

    def test_chd_data_export_sources_include_native_afc_artifacts(self, tmp_path):
        from src.ui.main_window import MainWindow

        filenames = [
            "chd_metadata_profiles.csv",
            "colored_corpus.txt",
            "chistable.csv",
            "afc_row.csv",
            "afc_col.csv",
            "row_coords.csv",
            "col_coords.csv",
            "afc_facteur.csv",
            "AFC2DL.png_notplotted.csv",
            "eigenvalues.csv",
            "manifest.json",
        ]
        paths = {}
        for name in filenames:
            path = tmp_path / name
            path.write_text("data", encoding="utf-8")
            paths[name] = path

        result = SimpleNamespace(
            metadata_profiles_path=paths["chd_metadata_profiles.csv"],
            colored_corpus_path=paths["colored_corpus.txt"],
            chistable_path=paths["chistable.csv"],
            afc_row_path=paths["afc_row.csv"],
            afc_col_path=paths["afc_col.csv"],
            row_coords_path=paths["row_coords.csv"],
            col_coords_path=paths["col_coords.csv"],
            afc_facteur_path=paths["afc_facteur.csv"],
            afc2dl_notplotted_path=paths["AFC2DL.png_notplotted.csv"],
            eigenvalues_path=paths["eigenvalues.csv"],
            manifest_path=paths["manifest.json"],
            class_text_paths={},
        )
        window = MainWindow.__new__(MainWindow)
        sources = window._get_data_export_sources("chd", result=result, metadata={})

        exported_names = {source.name for source in sources}
        assert set(filenames).issubset(exported_names)

    def test_get_image_gallery_for_lda_uses_fixed_labels(self, tmp_path):
        from PIL import Image
        from src.ui.main_window import MainWindow

        def make_png(path):
            image = Image.new("RGB", (160, 100), color=(180, 200, 220))
            image.save(path, format="PNG")

        dist = tmp_path / "lda_distribution.png"
        top = tmp_path / "lda_top_terms.png"
        heat = tmp_path / "lda_doc_topic_heatmap.png"
        tune = tmp_path / "lda_tuning_plot.png"
        for path in (dist, top, heat, tune):
            make_png(path)

        result = SimpleNamespace(
            distribution_image_path=str(dist),
            top_terms_image_path=str(top),
            heatmap_image_path=str(heat),
            tuning_image_path=str(tune),
            timeline_image_path=None,
        )
        window = MainWindow.__new__(MainWindow)
        gallery = window._get_image_gallery(
            analysis_type_key="lda",
            result=result,
            artifact_path=None,
            metadata=None,
        )

        assert "Distribuição de Tópicos" in gallery
        assert "Top Termos por Tópico" in gallery
        assert "Heatmap Doc-Tópico" in gallery
        assert "Tuning de k" in gallery

    def test_show_voyant_suite_creates_fixed_graph_subtabs(self, tmp_path):
        from PIL import Image
        from src.ui.widgets.results_viewer import ResultsViewer

        def make_png(path):
            image = Image.new("RGB", (160, 90), color=(240, 240, 240))
            image.save(path, format="PNG")

        graph_paths = {
            "termsberry": tmp_path / "termsberry.png",
            "trends": tmp_path / "trends.png",
            "document_terms": tmp_path / "document_terms.png",
            "bubblelines": tmp_path / "bubblelines.png",
            "cooccurrences": tmp_path / "cooccurrences.png",
        }
        for path in graph_paths.values():
            make_png(path)

        csv_common = tmp_path / "panel.csv"
        csv_common.write_text("a;b\n1;2\n", encoding="utf-8")
        payload = {
            "version": "voyant_suite_payload_v1",
            "graph_tabs": [
                "termsberry",
                "trends",
                "document_terms",
                "bubblelines",
                "cooccurrences",
            ],
            "graphs": {
                "termsberry": {"title_pt": "TermsBerry", "image_path": str(graph_paths["termsberry"])},
                "trends": {"title_pt": "Tendências", "image_path": str(graph_paths["trends"])},
                "document_terms": {"title_pt": "Termos do documento", "image_path": str(graph_paths["document_terms"])},
                "bubblelines": {"title_pt": "Gráfico de bolhas", "image_path": str(graph_paths["bubblelines"])},
                "cooccurrences": {"title_pt": "Co-ocorrências", "image_path": str(graph_paths["cooccurrences"])},
            },
            "tables": {
                "termsberry": {"title_pt": "TermsBerry", "csv_path": str(csv_common)},
                "trends": {"title_pt": "Tendências", "csv_path": str(csv_common)},
                "document_terms": {"title_pt": "Termos do documento", "csv_path": str(csv_common)},
                "bubblelines": {"title_pt": "Gráfico de bolhas", "csv_path": str(csv_common)},
                "cooccurrences": {"title_pt": "Co-ocorrências", "csv_path": str(csv_common)},
            },
            "meta": {"doc_count": 1},
        }

        try:
            root = customtkinter.CTk()
        except Exception as exc:
            pytest.skip(f"Tk indisponível no ambiente atual: {exc}")

        try:
            root.withdraw()
            try:
                viewer = ResultsViewer(root)
            except Exception as exc:
                pytest.skip(f"ResultsViewer indisponível no ambiente atual: {exc}")
            viewer.pack(fill="both", expand=True)
            viewer.show_voyant_suite(payload)
            assert viewer._is_voyant_graph_gallery is True
            assert len(viewer._image_gallery) == 5
            assert viewer._has_table_content is True
        finally:
            try:
                root.destroy()
            except Exception:
                pass
