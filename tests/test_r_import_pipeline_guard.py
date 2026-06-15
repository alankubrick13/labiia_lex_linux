"""Guards for the unified R import pipeline (Python orchestrator only)."""

from __future__ import annotations

from types import SimpleNamespace


class _DummyConfig:
    def __init__(self) -> None:
        self._store = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value) -> None:
        self._store[key] = value

    def save(self) -> None:
        return None


class _DummyCorpus:
    def __init__(self) -> None:
        self.parametres = {}
        self.formes = {}

    def getucinb(self) -> int:
        return 1

    def getucenb(self) -> int:
        return 1

    def getwordnb(self) -> int:
        return len(self.formes)


def _make_window_stub(module):
    window = module.MainWindow.__new__(module.MainWindow)
    window.config = _DummyConfig()
    window._project_custom_stopwords = []
    window._analysis_output_root = None
    window.analysis_history = []
    window._open_history_entry = lambda *args, **kwargs: None
    window._handle_corpus_tree_action = lambda *args, **kwargs: None
    window._cleanup_analysis_storage = lambda: None
    window._cleanup_corpus_storage = lambda: None
    window._set_status = lambda *args, **kwargs: None
    window._enable_analysis_buttons = lambda *args, **kwargs: None
    window.results_viewer = SimpleNamespace(
        reset_analysis_tabs=lambda: None,
        show_text=lambda *args, **kwargs: None,
    )
    window.corpus_tree = SimpleNamespace(
        load_corpus=lambda *args, **kwargs: None,
        load_history=lambda *args, **kwargs: None,
    )
    window._last_corpus_text = ""
    window._last_import_file_path = None
    window._loaded_lexicon = None
    window.corpus = None
    return window


def test_load_corpus_prefers_r_pipeline_for_text_processing(monkeypatch, tmp_path):
    import src.ui.main_window as mw
    import src.importers.corpus_cleaner as corpus_cleaner_module

    run_calls = {}

    class _FakePipeline:
        def run(self, **kwargs):
            run_calls["kwargs"] = kwargs
            return SimpleNamespace(
                prepared_text="**** *doc_1\ntexto_limpo_pipeline_r",
                preview_text="",
                bigram_candidates=[],
                diagnostics={"engine": "r"},
                warnings=[],
            )

    class _ForbiddenCleaner:
        def __init__(self, *args, **kwargs):
            raise AssertionError("CorpusCleaner nao deve rodar quando o pipeline R ja foi aplicado.")

    errors = []
    monkeypatch.setattr(mw, "RTextPipeline", lambda: _FakePipeline())
    monkeypatch.setattr(corpus_cleaner_module, "CorpusCleaner", _ForbiddenCleaner)
    monkeypatch.setattr(mw, "show_error", lambda *args, **kwargs: errors.append((args, kwargs)))

    window = _make_window_stub(mw)
    dummy_corpus = _DummyCorpus()
    captured = {}

    window._create_corpus_with_temp_db = lambda uce_size=40: dummy_corpus

    def _capture_build(text: str, remove_numbers: bool = False):
        captured["text"] = text
        captured["remove_numbers"] = remove_numbers
        dummy_corpus.formes = {"texto": object()}

    window._build_corpus_from_text = _capture_build

    import_result = {
        "text": "fallback_python_path_should_not_run",
        "mode": "traditional",
        "file_path": str(tmp_path / "amostra.txt"),
        "metadata": {
            "r_pipeline_source_text": "**** *doc_1\nTexto bruto 2025 the off",
        },
        "options": {
            "lowercase": True,
            "remove_numbers": True,
            "remove_accents": False,
            "clean_web_data": True,
            "selected_bigrams": [{"expression": "setor publico", "replacement": "setor_publico"}],
            "session_stopwords": ["manual_stop"],
            "persist_project_stopwords": True,
            "persist_global_stopwords": False,
            "uce_size": 40,
        },
    }

    window._load_corpus(import_result)

    assert errors == []
    assert captured["text"] == "**** *doc_1\ntexto_limpo_pipeline_r"
    assert captured["remove_numbers"] is True
    assert "kwargs" in run_calls
    assert run_calls["kwargs"]["mode"] == "traditional"
    assert run_calls["kwargs"]["selected_bigrams"] == import_result["options"]["selected_bigrams"]
    assert "manual_stop" in run_calls["kwargs"]["extra_stopwords"]
    assert "the" in run_calls["kwargs"]["extra_stopwords"]
    assert window._project_custom_stopwords == ["manual_stop"]


def test_load_corpus_reuses_prepared_text_without_rerunning_pipeline(monkeypatch, tmp_path):
    import src.ui.main_window as mw

    class _ForbiddenPipeline:
        def run(self, **_kwargs):
            raise AssertionError("Pipeline R nao deve rodar quando prepared_text ja existe.")

    monkeypatch.setattr(mw, "RTextPipeline", lambda: _ForbiddenPipeline())
    monkeypatch.setattr(mw, "show_error", lambda *args, **kwargs: None)

    window = _make_window_stub(mw)
    dummy_corpus = _DummyCorpus()
    captured = {}

    window._create_corpus_with_temp_db = lambda uce_size=40: dummy_corpus

    def _capture_build(text: str, remove_numbers: bool = False):
        captured["text"] = text
        captured["remove_numbers"] = remove_numbers
        dummy_corpus.formes = {"texto": object()}

    window._build_corpus_from_text = _capture_build

    import_result = {
        "text": "**** *doc_1\ntexto_limpo_pipeline_r",
        "mode": "traditional",
        "file_path": str(tmp_path / "amostra.txt"),
        "metadata": {
            "r_pipeline_source_text": "**** *doc_1\nTexto bruto",
            "r_pipeline_prepared_text": "**** *doc_1\ntexto_limpo_pipeline_r",
        },
        "options": {
            "uce_size": 40,
        },
    }

    window._load_corpus(import_result)

    assert captured["text"] == "**** *doc_1\ntexto_limpo_pipeline_r"
    assert captured["remove_numbers"] is False


def test_prepare_corpus_with_phase2_options_runs_r_pipeline_and_reloads(monkeypatch, tmp_path):
    import src.ui.main_window as mw

    run_calls = {}

    class _FakePipeline:
        def script_hash(self):
            return "pipeline-hash"

        def run(self, **kwargs):
            run_calls["kwargs"] = kwargs
            return SimpleNamespace(
                prepared_text="**** *doc_1\ntexto_limpo_fase_2",
                preview_text="texto_limpo_fase_2",
                bigram_candidates=[],
                diagnostics={"phase": "phase2"},
                warnings=[],
            )

    monkeypatch.setattr(mw, "RTextPipeline", lambda: _FakePipeline())
    monkeypatch.setattr(mw, "show_error", lambda *args, **kwargs: None)

    window = _make_window_stub(mw)
    source_path = tmp_path / "amostra.txt"
    source_path.write_text("Texto BRUTO 123 https://exemplo.com", encoding="utf-8")
    window._last_import_file_path = source_path
    window._last_import_metadata = {
        "r_pipeline_source_text": "**** *doc_1\nTexto BRUTO 123 https://exemplo.com",
        "selected_files": [str(source_path)],
    }
    window._last_import_mode = "traditional"
    window._last_import_options = {"uce_size": 40, "session_stopwords": ["manual_stop"]}

    captured = {}
    window._load_corpus = lambda import_result: captured.setdefault("import_result", import_result)

    MainWindow = mw.MainWindow
    MainWindow._apply_corpus_preparation(
        window,
        {
            "lowercase": True,
            "remove_numbers": True,
            "remove_accents": True,
            "clean_web_data": True,
            "detect_bigrams": False,
            "ngram_max": 5,
            "min_is_norm": 0.25,
            "selected_bigrams": [{"expression": "texto bruto", "replacement": "texto_bruto"}],
        },
    )

    assert run_calls["kwargs"]["lowercase"] is True
    assert run_calls["kwargs"]["remove_numbers"] is True
    assert run_calls["kwargs"]["remove_accents"] is True
    assert run_calls["kwargs"]["clean_web_data"] is True
    assert run_calls["kwargs"]["detect_bigrams"] is False
    assert run_calls["kwargs"]["ngram_max"] == 3
    assert run_calls["kwargs"]["min_is_norm"] == 0.25
    assert run_calls["kwargs"]["selected_bigrams"] == [
        {"expression": "texto bruto", "replacement": "texto_bruto"}
    ]
    assert "manual_stop" in run_calls["kwargs"]["extra_stopwords"]

    prepared = captured["import_result"]
    assert prepared["text"] == "**** *doc_1\ntexto_limpo_fase_2"
    assert prepared["metadata"]["r_pipeline_prepared_text"] == "**** *doc_1\ntexto_limpo_fase_2"
    assert prepared["metadata"]["r_pipeline_diagnostics"] == {"phase": "phase2"}
    assert prepared["metadata"]["phase2_version"] == "1.0.9"
    assert prepared["metadata"]["multiword_selected_count"] == 1
    assert prepared["metadata"]["multiword_detection_method"] == "is_index_tall_inspired"
    assert prepared["options"]["lowercase"] is True
    assert prepared["options"]["selected_bigrams"] == [
        {"expression": "texto bruto", "replacement": "texto_bruto"}
    ]


def test_load_corpus_does_not_fallback_silently_when_r_pipeline_fails(monkeypatch, tmp_path):
    import src.ui.main_window as mw

    class _ExplodingPipeline:
        def run(self, **kwargs):
            raise mw.RTextPipelineError("pipeline r indisponivel")

    errors = []
    monkeypatch.setattr(mw, "RTextPipeline", lambda: _ExplodingPipeline())
    monkeypatch.setattr(mw, "show_error", lambda *args, **kwargs: errors.append((args, kwargs)))

    window = _make_window_stub(mw)
    window._create_corpus_with_temp_db = lambda uce_size=40: _DummyCorpus()
    window._build_corpus_from_text = (
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Nao deve cair em processamento textual Python quando o pipeline R falha.")
        )
    )

    import_result = {
        "text": "fallback_python_path_should_not_run",
        "mode": "traditional",
        "file_path": str(tmp_path / "amostra.txt"),
        "metadata": {"r_pipeline_source_text": "**** *doc_1\ntexto"},
        "options": {"uce_size": 40},
    }

    window._load_corpus(import_result)
    assert len(errors) == 1
