from __future__ import annotations


def test_textrank_summary_returns_literal_representative_sentences() -> None:
    from src.analysis.extractive_summary import rank_representative_sentences

    sentences = [
        {
            "sentence_id": 1,
            "text": "A inteligencia artificial ajuda a pesquisa publica.",
            "doc_id": 1,
            "doc_label": "Doc 1",
            "tokens": ["inteligencia", "artificial", "pesquisa", "publica"],
        },
        {
            "sentence_id": 2,
            "text": "O hospital ampliou o atendimento de saude publica.",
            "doc_id": 2,
            "doc_label": "Doc 2",
            "tokens": ["hospital", "saude", "publica"],
        },
    ]

    ranked = rank_representative_sentences(
        sentences,
        targets=[{"target_type": "topic", "target_id": 0, "terms": ["inteligencia", "artificial"]}],
        per_target=1,
    )

    assert len(ranked) == 1
    assert ranked[0]["sentence"] == "A inteligencia artificial ajuda a pesquisa publica."
    assert ranked[0]["target_type"] == "topic"
    assert ranked[0]["target_id"] == 0
    assert "inteligencia" in ranked[0]["matched_terms"]
