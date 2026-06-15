import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.history import AnalysisHistory
from src.ui.main_window import MainWindow, SEMANTIC_REGISTRY


@pytest.fixture
def mock_history(tmp_path):
    """Cria um historico mock isolado."""
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    history_file = history_dir / "analysis_history.json"
    artifacts_dir = history_dir / "artifacts"
    artifacts_dir.mkdir()
    
    return AnalysisHistory(history_path=history_file, artifacts_dir=artifacts_dir)


@pytest.fixture
def mock_main_window(mock_history, tmp_path):
    """Cria uma MainWindow mockada injetando o historico isolado."""
    window = MainWindow.__new__(MainWindow)
    window.analysis_history = mock_history
    window._last_analysis_result = None
    window._last_saved_history_entry_id = None
    window._last_report_path = None
    window._last_analysis_context = {}

    window._ensure_results_workspace = MagicMock()
    window._refresh_results_sidebar_context = MagicMock()
    window._set_similarity_halo_toggle_context = MagicMock()
    window._restore_statistics_from_history = MagicMock(return_value=False)
    window._get_runtime_chd_result = MagicMock(return_value=None)
    window._get_reconstructed_chd_result = MagicMock(return_value=None)
    window._populate_all_tabs = MagicMock()
    window._populate_tabs_from_history_metadata = MagicMock()
    window._apply_graph_default_zoom_for_analysis = MagicMock()
    window._get_report_path_from_history_entry = MagicMock(return_value=None)
    window._set_status = MagicMock()

    window.results_viewer = MagicMock()
    window.results_viewer.has_analysis_tab.return_value = False
    window.results_viewer.focus_analysis_tab.return_value = None
    window.results_viewer.set_analysis_tab.return_value = None
    window.results_viewer.clear.return_value = None
    window.results_viewer.show_image.return_value = None
    window.results_viewer.show_table.return_value = None
    window.results_viewer.show_text.return_value = None
    window.results_viewer.set_report_path.return_value = None
    window.results_viewer._current_image_path = None
    window.results_viewer._has_table_content = False
    window.results_viewer._current_text = ""
    window.results_viewer._current_report_path = None
    return window


def test_semantic_history_restoration_all_types(mock_main_window, mock_history, tmp_path):
    """
    Testa a restauracao de todas as entradas sinteticas para as novas analises NLP.
    
    Criteria:
    - O visualizador resolve o artefato primario correto de cada analysis_type
    """
    sample_img = tmp_path / "fake_img.png"
    sample_img.write_bytes(b"fake image data")
    
    sample_csv = tmp_path / "fake_data.csv"
    sample_csv.write_text("a,b\n1,2", encoding="utf-8")
    
    for key, entry in SEMANTIC_REGISTRY.items():
        if key == "associative_heatmap":
            continue  # testado em separado (legado vs novo)
            
        mock_main_window.results_viewer.reset_mock()
        mock_main_window.results_viewer._current_image_path = None
        mock_main_window.results_viewer._has_table_content = False
        
        # Simula salvamento
        metadata = {
            "analysis_type": key,
            "output_dir": str(tmp_path),
            "primary_image": str(sample_img),
            "primary_table": str(sample_csv),
            "secondary_images": [str(sample_img)],
            "secondary_tables": [str(sample_csv)],
        }
        
        saved_entry = mock_history.save_result(
            analysis_type=key,
            params={"test": True},
            result_path=sample_img,
            metadata=metadata
        )
        
        # Restaura a entrada pela UI
        mock_main_window._open_history_entry(saved_entry)
        
        # O _open_history_entry de artifacts nativos resolve imagens pelo result_path
        # se existir e for .png 
        assert mock_main_window.results_viewer.show_image.called
        assert mock_main_window.results_viewer.set_analysis_tab.called


def test_associative_heatmap_legacy_fallback(mock_main_window, mock_history, tmp_path):
    """
    Garante que o associative_heatmap abra com label de legado para 'heatmap' original
    e como novo se tiver o metadado adequado.
    """
    sample_img = tmp_path / "fake_img.png"
    sample_img.write_bytes(b"fake image data")
    
    # 1. Antigo "heatmap" sem metadata rica
    legacy_entry = mock_history.save_result(
        analysis_type="heatmap",
        params={"size": 10},
        result_path=sample_img,
        metadata={}
    )
    
    mock_main_window.results_viewer.reset_mock()
    mock_main_window.results_viewer._current_image_path = None
    
    mock_main_window._open_history_entry(legacy_entry)
    # Tem que conseguir abrir a aba
    assert mock_main_window.results_viewer.set_analysis_tab.called
    assert mock_main_window.results_viewer.show_image.called

    # 2. Novo "associative_heatmap"
    new_entry = mock_history.save_result(
        analysis_type="associative_heatmap",
        params={"min_freq": 2},
        result_path=sample_img,
        metadata={"analysis_type": "associative_heatmap"}
    )
    
    mock_main_window.results_viewer.reset_mock()
    mock_main_window.results_viewer._current_image_path = None
    
    mock_main_window._open_history_entry(new_entry)
    assert mock_main_window.results_viewer.set_analysis_tab.called
    assert mock_main_window.results_viewer.show_image.called


def test_semantic_html_reports_generation(mock_main_window, mock_history, tmp_path):
    """
    Testa que ReportGenerator.generate_generic_report processa as 
    dataclasses das novas analises usando fallback genérico reflexivo.
    """
    from src.core.report_generator import ReportGenerator
    from src.analysis.yake_analysis import YAKEResult
    from src.analysis.semantic_contracts import KeyphraseCandidate

    generator = ReportGenerator(tmp_path)

    sample_csv = tmp_path / "kwd.csv"
    sample_csv.write_text("palavra;score\nteste;1.0", encoding="utf-8")

    sample_img = tmp_path / "yake_ranking.png"
    sample_img.write_bytes(b"fake image data")

    kp = KeyphraseCandidate(
        phrase="teste",
        normalized_phrase="teste",
        score=1.0,
        frequency=3,
        degree=1,
    )

    result = YAKEResult(
        analysis_type="yake",
        output_dir=tmp_path,
        keyphrases=[kp],
        keyphrases_csv_path=sample_csv,
        ranking_image_path=sample_img,
    )

    report_path = generator.generate_generic_report(
        analysis_name="YAKE",
        analysis_type="yake",
        params={"lang": "pt"},
        result=result,
    )

    assert report_path.exists()
    html_content = report_path.read_text(encoding="utf-8")
    assert "YAKE - Relatório" in html_content
    assert "teste" in html_content
    assert "1.0" in html_content
