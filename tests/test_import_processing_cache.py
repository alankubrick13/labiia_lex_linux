from __future__ import annotations

from pathlib import Path


def test_import_processing_cache_reuses_entry_for_same_file_options(tmp_path, monkeypatch):
    from src.core.import_processing_cache import ImportProcessingCache

    monkeypatch.setattr(
        "src.core.import_processing_cache.PathManager.user_data_dir",
        lambda: tmp_path,
    )

    source = tmp_path / "sample.txt"
    source.write_text("Texto de teste", encoding="utf-8")

    cache = ImportProcessingCache()
    key = cache.build_key(
        source_paths=[source],
        mode="traditional",
        options={"lowercase": False, "detect_bigrams": False},
        stopwords=["manual"],
        pipeline_hash="abc",
    )
    payload = {
        "extracted_text": "Texto de teste",
        "source_text": "**** *doc_1\nTexto de teste",
        "prepared_text": "**** *doc_1\ntexto de teste",
        "metadata": {"source": "unit"},
    }

    cache.put(key, payload)

    loaded = cache.get(key)
    assert loaded is not None
    assert loaded["prepared_text"] == payload["prepared_text"]
    assert loaded["metadata"]["source"] == "unit"


def test_import_processing_cache_invalidates_when_options_change(tmp_path, monkeypatch):
    from src.core.import_processing_cache import ImportProcessingCache

    monkeypatch.setattr(
        "src.core.import_processing_cache.PathManager.user_data_dir",
        lambda: tmp_path,
    )

    source = tmp_path / "sample.txt"
    source.write_text("Texto de teste", encoding="utf-8")

    cache = ImportProcessingCache()
    key_a = cache.build_key(
        source_paths=[source],
        mode="traditional",
        options={"lowercase": False},
        stopwords=[],
        pipeline_hash="abc",
    )
    key_b = cache.build_key(
        source_paths=[source],
        mode="traditional",
        options={"lowercase": True},
        stopwords=[],
        pipeline_hash="abc",
    )

    assert key_a != key_b


def test_import_processing_cache_keys_include_multiword_phase2_options(tmp_path, monkeypatch):
    from src.core.import_processing_cache import ImportProcessingCache

    monkeypatch.setattr(
        "src.core.import_processing_cache.PathManager.user_data_dir",
        lambda: tmp_path,
    )

    source = tmp_path / "sample.txt"
    source.write_text("Texto de teste", encoding="utf-8")

    cache = ImportProcessingCache()
    base_options = {
        "detect_bigrams": True,
        "bigram_top_n": 50,
        "bigram_min_freq": 2,
        "ngram_max": 5,
        "min_is_norm": 0.25,
        "selected_bigrams": [],
    }
    key_base = cache.build_key(
        source_paths=[source],
        mode="traditional",
        options=base_options,
        stopwords=[],
        pipeline_hash="abc",
    )

    for changed in (
        {**base_options, "ngram_max": 4},
        {**base_options, "bigram_min_freq": 3},
        {
            **base_options,
            "selected_bigrams": [
                {"expression": "inteligencia artificial", "replacement": "inteligencia_artificial"}
            ],
        },
    ):
        assert cache.build_key(
            source_paths=[source],
            mode="traditional",
            options=changed,
            stopwords=[],
            pipeline_hash="abc",
        ) != key_base
