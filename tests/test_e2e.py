"""
Testes end-to-end para fluxo real do LabiiaLex.

Objetivo:
- Cobrir importacao -> limpeza -> validacao -> corpus -> estatisticas
- Validar correcoes de runtime que nao eram pegas por unit tests
"""

from __future__ import annotations

import inspect
from pathlib import Path
import re

import pytest

from src.analysis.statistics import CorpusStatistics, StatisticsAnalysis
from src.core.corpus import Corpus
from src.importers import TXTImporter
from src.importers.corpus_cleaner import CorpusCleaner
from src.importers.corpus_validator import (
    CorpusValidationError,
    CorpusValidator,
    validate_iramuteq_corpus,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "exemplo.txt"

try:
    import customtkinter  # noqa: F401

    HAS_CTK = True
except Exception:
    HAS_CTK = False


def _add_words_from_text(corpus: Corpus, text: str) -> None:
    for word in re.findall(r"\b[a-zA-ZÀ-ÿ]+\b", text.lower()):
        if len(word) > 2:
            corpus.add_word(word)


def _build_corpus_from_iramuteq_text(corpus: Corpus, text: str) -> None:
    """Constroi corpus no formato IRaMuTeQ sem mocks."""
    current_uci = None
    current_paragraph = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line.startswith("****"):
            if current_uci is not None and current_paragraph:
                para_text = " ".join(current_paragraph)
                corpus.add_uce(current_uci.ident, 0, para_text)
                _add_words_from_text(corpus, para_text)
                current_paragraph = []
            current_uci = corpus.add_uci(line)
        elif line and current_uci is not None:
            current_paragraph.append(line)
        elif not line and current_uci is not None and current_paragraph:
            para_text = " ".join(current_paragraph)
            corpus.add_uce(current_uci.ident, 0, para_text)
            _add_words_from_text(corpus, para_text)
            current_paragraph = []

    if current_uci is not None and current_paragraph:
        para_text = " ".join(current_paragraph)
        corpus.add_uce(current_uci.ident, 0, para_text)
        _add_words_from_text(corpus, para_text)


class TestE2EImportPipeline:
    """Pipeline real de importacao e analise sem mocks."""

    def test_import_clean_validate_build_statistics(self, tmp_path):
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture de corpus nao encontrada")

        importer = TXTImporter()
        extracted = importer.extract(str(FIXTURE_PATH))

        cleaner = CorpusCleaner()
        cleaned_text = cleaner.limpar(extracted.text)
        validate_iramuteq_corpus(cleaned_text)

        corpus = Corpus()
        db_path = tmp_path / "e2e_pipeline.db"
        corpus.connect(db_path)

        try:
            _build_corpus_from_iramuteq_text(corpus, cleaned_text)

            stats = StatisticsAnalysis(corpus).get_corpus_statistics()
            uces_in_db = corpus.getalluces()

            assert stats.total_ucis > 0
            assert stats.total_uces > 0
            assert stats.total_formes > 0
            assert stats.total_occurrences > 0
            assert len(uces_in_db) == stats.total_uces
        finally:
            corpus.close()

    def test_validator_returns_friendly_error(self):
        invalid_text = (
            "**** *grupo_teste\n"
            "Texto valido.\n\n"
            "**** grupo_sem_asterisco\n"
            "Outro texto.\n"
        )

        with pytest.raises(CorpusValidationError) as exc_info:
            validate_iramuteq_corpus(invalid_text)

        message = str(exc_info.value)
        assert "O que aconteceu:" in message
        assert "Por que aconteceu:" in message
        assert "Como resolver:" in message

    def test_validator_returns_structured_report(self):
        text = "**** *grupo_teste\nTexto da UCI.\n"
        report = CorpusValidator().validate(text)

        assert report.is_valid is True
        assert report.errors == []
        assert "total_ucis" in report.stats
        assert report.stats["total_ucis"] >= 1


@pytest.mark.skipif(not HAS_CTK, reason="CustomTkinter nao disponivel")
class TestE2ERuntimeFixes:
    """Smoke tests para correcoes de runtime na UI."""

    def test_corpus_tree_uses_getucenb(self):
        from src.ui.widgets.corpus_tree import CorpusTree

        source = inspect.getsource(CorpusTree.load_corpus)
        assert "getucenb" in source
        assert "corpus.uces" not in source

    def test_build_corpus_uses_segment_text(self):
        from src.ui.main_window import MainWindow

        source = inspect.getsource(MainWindow._build_corpus_from_text)
        assert "segment_text" in source

    def test_statistics_mapping_uses_total_fields(self):
        from src.ui.main_window import MainWindow

        stats = CorpusStatistics(
            total_ucis=3,
            total_uces=7,
            total_formes=25,
            total_occurrences=80,
            total_hapax=12,
            mean_words_per_uce=11.4,
            vocabulary_richness=0.48,
        )

        mapped = MainWindow._statistics_to_display_dict(stats)

        assert mapped["total_ucis"] == 3
        assert mapped["total_uces"] == 7
        assert mapped["total_occurrences"] == 80
        assert "n_ucis" not in mapped
        assert "n_uces" not in mapped

    def test_main_window_temp_sqlite_persists_uce(self):
        from src.ui.main_window import MainWindow

        window = MainWindow.__new__(MainWindow)
        window.corpus = None
        window._corpus_db_path = None

        corpus = MainWindow._create_corpus_with_temp_db(window)
        db_path = window._corpus_db_path

        try:
            uci = corpus.add_uci("**** *doc_1")
            corpus.add_uce(uci.ident, 0, "texto de teste")

            stored_uces = corpus.getalluces()
            assert len(stored_uces) == 1
            assert stored_uces[0][1] == "texto de teste"
        finally:
            window.corpus = corpus
            MainWindow._cleanup_corpus_storage(window)
            if db_path is not None:
                assert not db_path.exists()

    def test_analysis_dialog_base_injects_analysis_type(self):
        from src.ui.dialogs.analysis_dialog import BaseAnalysisDialog

        class DummyDialog:
            ANALYSIS_TYPE = "dummy"
            _cancelled = True

            def _build_result(self):
                return {"param": 1}

            def destroy(self):
                return None

        dummy = DummyDialog()
        BaseAnalysisDialog._execute(dummy)
        assert dummy._result["analysis_type"] == "dummy"
        assert dummy._result["param"] == 1

    def test_execute_analysis_async_uses_output_dir_and_params_dict(self, monkeypatch, tmp_path):
        import src.analysis as analysis_pkg
        from src.ui import main_window as main_window_module

        captured = {}
        callback_state = {}

        class ImmediateThread:
            def __init__(self, target, daemon=True):
                self._target = target

            def start(self):
                self._target()

        class DummyCHDAnalysis:
            def __init__(self, corpus, output_dir):
                captured["corpus"] = corpus
                captured["output_dir"] = output_dir

            def run(self, params=None):
                captured["params"] = params

                result_path = tmp_path / "dummy_chd.png"
                result_path.write_text("ok", encoding="utf-8")

                class DummyResult:
                    dendrogram_path = result_path

                return DummyResult()

        monkeypatch.setattr(main_window_module.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(analysis_pkg, "CHDAnalysis", DummyCHDAnalysis)

        window = main_window_module.MainWindow.__new__(main_window_module.MainWindow)
        window.corpus = object()
        window._analysis_output_root = None
        window._set_status = lambda *args, **kwargs: None
        window._enable_analysis_buttons = lambda *args, **kwargs: None
        window.after = lambda _delay, callback: callback()
        window._on_analysis_complete = lambda name, path: callback_state.update(
            {"name": name, "path": path}
        )
        window._on_analysis_error = lambda name, error: callback_state.update(
            {"error_name": name, "error": str(error)}
        )

        main_window_module.MainWindow._execute_analysis_async(
            window,
            "CHD",
            {
                "analysis_type": "chd",
                "n_classes": 4,
                "min_freq": 2,
                "method": "ward.D2",
            },
        )

        assert "error" not in callback_state
        assert callback_state["name"] == "CHD"
        assert Path(callback_state["path"]).exists()

        assert isinstance(captured["params"], dict)
        assert captured["params"]["nb_classes"] == 4
        assert captured["params"]["min_freq"] == 2
        assert captured["params"]["method"] == "ward.D2"
        assert Path(captured["output_dir"]).exists()

    def test_prototypical_rank_uses_mean_word_position(self, tmp_path):
        from src.ui.main_window import MainWindow

        corpus = Corpus()
        db_path = tmp_path / "proto_rank.db"
        corpus.connect(db_path)

        try:
            uci = corpus.add_uci("**** *doc_1")
            samples = [
                "beta alpha alpha",
                "alpha beta",
            ]
            for para_id, text in enumerate(samples):
                uce = corpus.add_uce(uci.ident, para_id, text)
                for token in re.findall(r"\b[a-zA-ZÀ-ÿ]+\b", text.lower()):
                    if len(token) > 2:
                        corpus.add_word(token, uce_id=uce.ident)

            window = MainWindow.__new__(MainWindow)
            window.corpus = corpus
            rows = MainWindow._build_prototypical_freq_rank(window)
            data = {word: (freq, rank) for word, freq, rank in rows}

            assert data["alpha"][0] == 3
            assert data["beta"][0] == 2
            assert data["alpha"][1] == pytest.approx(2.0)
            assert data["beta"][1] == pytest.approx(1.5)
        finally:
            corpus.close()

    def test_on_analysis_complete_saves_history_entry(self, tmp_path):
        from src.ui import main_window as main_window_module

        class DummyResultsViewer:
            def show_image(self, _path):
                return None

            def show_chd_profiles(self, _profiles, _class_sizes, result=None):
                return None

            def show_table(self, _path):
                return None

            def show_text(self, _text, title=""):
                return None

        class DummyHistory:
            def __init__(self):
                self.calls = []

            def save_result(self, **kwargs):
                self.calls.append(kwargs)
                return kwargs

        class DummyResult:
            profiles = {}
            class_sizes = {}

        output_path = tmp_path / "history_result.png"
        output_path.write_text("ok", encoding="utf-8")

        window = main_window_module.MainWindow.__new__(main_window_module.MainWindow)
        window._enable_analysis_buttons = lambda *args, **kwargs: None
        window._set_status = lambda *args, **kwargs: None
        window.results_viewer = DummyResultsViewer()
        window.analysis_history = DummyHistory()
        window._last_analysis_result = DummyResult()
        window._last_analysis_context = {
            "analysis_type": "chd",
            "params": {"analysis_type": "chd", "n_classes": 6, "min_freq": 4},
        }

        main_window_module.MainWindow._on_analysis_complete(window, "CHD", output_path)

        assert len(window.analysis_history.calls) == 1
        call = window.analysis_history.calls[0]
        assert call["analysis_type"] == "chd"
        assert call["params"]["n_classes"] == 6
        assert Path(call["result_path"]).exists()

    def test_save_history_includes_report_path_metadata(self, tmp_path):
        from src.ui import main_window as main_window_module

        class DummyHistory:
            def __init__(self):
                self.calls = []

            def save_result(self, **kwargs):
                self.calls.append(kwargs)
                return type("Entry", (), {"entry_id": "id-1"})()

        class DummyTree:
            def load_history(self, *_args, **_kwargs):
                return None

        window = main_window_module.MainWindow.__new__(main_window_module.MainWindow)
        window.analysis_history = DummyHistory()
        window.corpus_tree = DummyTree()
        window._open_history_entry = lambda *_args, **_kwargs: None
        window._handle_corpus_tree_action = lambda *_args, **_kwargs: None
        window._last_analysis_context = {"analysis_type": "matrix_afc", "params": {"n_dim": 2}}
        window._last_analysis_result = object()
        window._last_report_path = tmp_path / "report.html"
        window._last_report_path.write_text("<html></html>", encoding="utf-8")

        result_path = tmp_path / "matrix_afc.png"
        result_path.write_text("img", encoding="utf-8")
        main_window_module.MainWindow._save_analysis_to_history(window, "AFC (Matriz)", result_path)

        assert len(window.analysis_history.calls) == 1
        metadata = window.analysis_history.calls[0]["metadata"]
        assert metadata.get("report_path") == str(window._last_report_path)

    def test_open_history_report_from_tree_action(self, tmp_path):
        from src.ui import main_window as main_window_module

        class DummyViewer:
            def __init__(self):
                self.report_path = None
                self.opened = False

            def set_report_path(self, path):
                self.report_path = path

            def open_report(self):
                self.opened = True

        report_path = tmp_path / "report.html"
        report_path.write_text("<html><body>ok</body></html>", encoding="utf-8")
        entry = type("Entry", (), {"metadata": {"report_path": str(report_path)}})()

        window = main_window_module.MainWindow.__new__(main_window_module.MainWindow)
        window.results_viewer = DummyViewer()
        window._set_status = lambda *_args, **_kwargs: None
        window._last_report_path = None

        main_window_module.MainWindow._handle_corpus_tree_action(
            window, "open_report", {"entry": entry}
        )

        assert window.results_viewer.opened is True
        assert window.results_viewer.report_path == report_path
