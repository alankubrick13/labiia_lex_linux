from __future__ import annotations

import csv
import json


def test_corpus_preparation_audit_writes_csv_and_summary(tmp_path) -> None:
    from src.importers.corpus_preparation_audit import write_corpus_preparation_audit

    candidates = [
        {
            "expression": "inteligencia artificial",
            "replacement": "inteligencia_artificial",
            "n_tokens": 2,
            "frequency": 4,
            "doc_count": 2,
            "is_score": 2.5,
            "is_norm": 1.0,
            "method": "is_index",
            "context_examples": [
                {"doc_id": 1, "doc_label": "Doc 1", "context": "uso de inteligencia artificial no setor publico"}
            ],
        }
    ]
    selected = [dict(candidates[0])]

    paths = write_corpus_preparation_audit(
        tmp_path,
        source_paths=[tmp_path / "corpus.txt"],
        options={"detect_bigrams": True, "ngram_max": 5},
        candidates=candidates,
        selected=selected,
        diagnostics={"engine": "r"},
        pipeline_hash="abc123",
    )

    assert paths["multiword_candidates_csv"].exists()
    assert paths["multiword_decisions_csv"].exists()
    assert paths["multiword_contexts_csv"].exists()
    assert paths["corpus_preparation_summary_json"].exists()

    with paths["multiword_decisions_csv"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["expression"] == "inteligencia artificial"
    assert rows[0]["doc_count"] == "2"
    assert rows[0]["selected"] == "true"

    with paths["multiword_contexts_csv"].open(encoding="utf-8", newline="") as handle:
        context_rows = list(csv.DictReader(handle))
    assert context_rows[0]["expression"] == "inteligencia artificial"
    assert "setor publico" in context_rows[0]["context"]

    summary = json.loads(paths["corpus_preparation_summary_json"].read_text(encoding="utf-8"))
    assert summary["version"] == "1.0.9"
    assert summary["candidate_count"] == 1
    assert summary["selected_count"] == 1
    assert summary["pipeline_hash"] == "abc123"


def test_corpus_preparation_audit_writes_entity_artifacts(tmp_path) -> None:
    from src.importers.corpus_preparation_audit import write_corpus_preparation_audit

    entity = {
        "entity": "Supremo Tribunal Federal",
        "replacement": "Supremo_Tribunal_Federal",
        "entity_type": "institution_or_group",
        "frequency": 3,
        "doc_count": 2,
        "score": 1.0,
        "selected_default": True,
        "context_examples": [
            {"doc_id": 1, "doc_label": "Doc 1", "context": "O Supremo Tribunal Federal decidiu."}
        ],
    }

    paths = write_corpus_preparation_audit(
        tmp_path,
        source_paths=[],
        options={"detect_bigrams": False, "detect_entities": True},
        candidates=[],
        selected=[],
        diagnostics={},
        pipeline_hash="abc123",
        entity_candidates=[entity],
        selected_entities=[entity],
    )

    assert paths["entity_candidates_csv"].exists()
    assert paths["entity_decisions_csv"].exists()
    assert paths["entity_contexts_csv"].exists()

    with paths["entity_decisions_csv"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["entity"] == "Supremo Tribunal Federal"
    assert rows[0]["selected"] == "true"


def test_corpus_preparation_audit_skips_without_multiword_detection(tmp_path) -> None:
    from src.importers.corpus_preparation_audit import write_corpus_preparation_audit

    paths = write_corpus_preparation_audit(
        tmp_path,
        source_paths=[],
        options={"detect_bigrams": False},
        candidates=[],
        selected=[],
        diagnostics={},
        pipeline_hash="abc123",
    )

    assert paths == {}
