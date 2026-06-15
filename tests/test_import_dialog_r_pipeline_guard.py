"""Guards that preview import processing stays on the unified R pipeline."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


class _Flag:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def test_import_dialog_preview_worker_uses_r_pipeline(monkeypatch, tmp_path):
    from src.ui.dialogs.import_dialog import ImportDialog
    import src.importers as importers_module
    import src.importers.corpus_validator as corpus_validator_module
    import src.importers.iramuteq_adapter as iramuteq_adapter_module
    import src.core.r_text_pipeline as r_text_pipeline_module

    sample_file = Path(tmp_path) / "amostra.txt"
    sample_file.write_text("Texto bruto da importacao", encoding="utf-8")

    dialog = ImportDialog.__new__(ImportDialog)
    dialog._source_mode = "file"
    dialog._file_paths = [sample_file]
    dialog._file_path = sample_file
    dialog.mode_var = _Flag("traditional")
    dialog.lowercase_var = _Flag(True)
    dialog.remove_numbers_var = _Flag(True)
    dialog.remove_accents_var = _Flag(False)
    dialog.clean_web_data_var = _Flag(True)
    dialog._session_stopwords = ["manual_stop"]
    dialog._project_stopwords = []
    dialog._global_stopwords = []
    dialog._get_stopword_layers = lambda: {
        "global": [],
        "project": [],
        "session": ["manual_stop"],
    }
    dialog._build_traditional_collection_text = (
        lambda extracted_text, metadata: f"**** *doc_1\n{extracted_text}"
    )

    state = {"progress": [], "success": None, "error": None}
    dialog._set_preview_progress = lambda progress, message="": state["progress"].append((progress, message))
    dialog._safe_after = lambda callback: callback()
    dialog._finish_preview_success = lambda **kwargs: state.__setitem__("success", kwargs)
    dialog._finish_preview_error = lambda message: state.__setitem__("error", message)

    class _FakeImporter:
        def set_progress_callback(self, callback):
            self._callback = callback

        def extract(self, path):
            return SimpleNamespace(
                text="Texto 2025 the off para limpeza",
                metadata={},
            )

    monkeypatch.setattr(importers_module, "get_importer_for_file", lambda _path: _FakeImporter())
    monkeypatch.setattr(
        corpus_validator_module,
        "CorpusValidator",
        lambda: SimpleNamespace(
            validate=lambda _text: SimpleNamespace(errors=[], warnings=[], suggestions=[])
        ),
    )
    monkeypatch.setattr(
        iramuteq_adapter_module,
        "IramuteqAutoAdapter",
        lambda: SimpleNamespace(to_iramuteq=lambda text, **_kwargs: text),
    )

    run_calls = {}

    class _FakePipeline:
        def run(self, **kwargs):
            run_calls["kwargs"] = kwargs
            return SimpleNamespace(
                prepared_text="**** *doc_1\ntexto_limpo_r",
                preview_text="preview vindo do pipeline R",
                bigram_candidates=[{"expression": "texto limpo", "replacement": "texto_limpo", "frequency": 2}],
                diagnostics={"engine": "r"},
                warnings=[],
            )

    monkeypatch.setattr(r_text_pipeline_module, "RTextPipeline", lambda: _FakePipeline())

    dialog._preview_worker()

    assert state["error"] is None
    assert state["success"] is not None
    assert run_calls["kwargs"]["mode"] == "traditional"
    assert run_calls["kwargs"]["lowercase"] is False
    assert run_calls["kwargs"]["remove_numbers"] is False
    assert run_calls["kwargs"]["remove_accents"] is False
    assert run_calls["kwargs"]["clean_web_data"] is False
    assert run_calls["kwargs"]["detect_bigrams"] is False
    assert run_calls["kwargs"]["aggressive_noise_filter"] is True
    assert "manual_stop" in run_calls["kwargs"]["extra_stopwords"]
    assert "the" in run_calls["kwargs"]["extra_stopwords"]
