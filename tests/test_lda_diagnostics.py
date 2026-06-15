from __future__ import annotations

import json

import numpy as np

from src.analysis.topic_modeling import DocTopicRow, LDAModelResult, TopicTerms


def _model_result() -> LDAModelResult:
    return LDAModelResult(
        topic_terms=[
            TopicTerms(topic_id=0, label="T0", terms=[("inteligencia_artificial", 0.5), ("dados", 0.3)]),
            TopicTerms(topic_id=1, label="T1", terms=[("saude_publica", 0.5), ("politica", 0.3)]),
            TopicTerms(topic_id=2, label="T2", terms=[("saude_publica", 0.45), ("politica", 0.25)]),
        ],
        doc_topic_rows=[
            DocTopicRow(doc_id=0, doc_label="d0", topic_probabilities=[0.9, 0.05, 0.05]),
            DocTopicRow(doc_id=1, doc_label="d1", topic_probabilities=[0.34, 0.33, 0.33]),
            DocTopicRow(doc_id=2, doc_label="d2", topic_probabilities=[0.1, 0.8, 0.1]),
        ],
        perplexity=123.0,
        n_topics=3,
        topic_labels=["T0", "T1", "T2"],
        doc_topic_matrix=np.array(
            [
                [0.9, 0.05, 0.05],
                [0.34, 0.33, 0.33],
                [0.1, 0.8, 0.1],
            ]
        ),
    )


def test_lda_topic_diagnostics_flags_small_and_similar_topics() -> None:
    from src.analysis.lda_diagnostics import compute_topic_diagnostics

    rows = compute_topic_diagnostics(_model_result(), small_threshold=0.17, similar_threshold=0.5)
    by_topic = {row["topic_id"]: row for row in rows}

    assert by_topic[2]["is_small_topic"] is True
    assert by_topic[1]["most_similar_topic_id"] == 2
    assert by_topic[1]["max_topic_similarity"] >= 0.5


def test_lda_document_mixing_flags_low_confidence_documents() -> None:
    from src.analysis.lda_diagnostics import compute_document_mixing

    rows = compute_document_mixing(_model_result(), mixed_threshold=0.2)
    by_doc = {row["doc_id"]: row for row in rows}

    assert by_doc[0]["is_mixed"] is False
    assert by_doc[1]["is_mixed"] is True
    assert by_doc[1]["margin"] < 0.2


def test_lda_advanced_diagnostics_writes_artifacts(tmp_path) -> None:
    from src.analysis.lda_diagnostics import write_advanced_lda_diagnostics

    paths, payload = write_advanced_lda_diagnostics(
        _model_result(),
        output_dir=tmp_path,
        k_quality_rows=[{"k": 2, "perplexity": 150.0}, {"k": 3, "perplexity": 123.0}],
        stability_rows=[
            {"seed": 42, "mean_similarity": 1.0, "min_similarity": 1.0},
            {"seed": 43, "mean_similarity": 0.8, "min_similarity": 0.6},
        ],
    )

    assert paths["topic_diagnostics_csv"].exists()
    assert paths["document_mixing_csv"].exists()
    assert paths["k_quality_csv"].exists()
    assert paths["stability_csv"].exists()
    assert paths["diagnostics_png"].exists()
    summary = json.loads(paths["stability_summary_json"].read_text(encoding="utf-8"))
    assert summary["stability_n_seeds"] == 2
    assert payload["multiword_features_count"] == 2
