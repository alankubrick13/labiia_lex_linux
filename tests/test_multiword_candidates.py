from __future__ import annotations


def test_extract_multiword_candidates_returns_only_2_to_3_grams() -> None:
    from src.importers.multiword_candidates import extract_multiword_candidates

    text = """
    **** *doc_1
    inteligencia artificial generativa aplicada cresce
    inteligencia artificial generativa aplicada cresce
    inteligencia artificial generativa aplicada cresce
    redes neurais profundas explicaveis ajudam
    redes neurais profundas explicaveis ajudam
    """

    candidates = extract_multiword_candidates(text, top_n=20, min_freq=2, ngram_max=5)
    by_expr = {item["expression"]: item for item in candidates}

    assert by_expr["inteligencia artificial"]["n_tokens"] == 2
    assert by_expr["inteligencia artificial generativa"]["n_tokens"] == 3
    assert "artificial generativa aplicada" not in by_expr
    assert "generativa aplicada cresce" not in by_expr
    assert "inteligencia artificial generativa aplicada" not in by_expr
    assert all(2 <= int(item["n_tokens"]) <= 3 for item in candidates)


def test_extract_multiword_candidates_rejects_stopword_edges_and_noise() -> None:
    from src.importers.multiword_candidates import extract_multiword_candidates

    text = """
    **** *doc_1
    de inteligencia artificial de
    de inteligencia artificial de
    1234 5678 1234 5678
    politica publica nacional
    politica publica nacional
    """

    expressions = {
        item["expression"]
        for item in extract_multiword_candidates(text, top_n=20, min_freq=2, ngram_max=4)
    }

    assert "de inteligencia" not in expressions
    assert "artificial de" not in expressions
    assert "1234 5678" not in expressions
    assert "politica publica" in expressions


def test_extract_multiword_candidates_ranking_prefers_dense_frequent_terms() -> None:
    from src.importers.multiword_candidates import extract_multiword_candidates

    text = """
    **** *doc_1
    inteligencia artificial generativa
    inteligencia artificial generativa
    inteligencia artificial generativa
    inteligencia artificial generativa
    agenda comum
    agenda comum
    """

    candidates = extract_multiword_candidates(text, top_n=5, min_freq=2, ngram_max=3)

    assert candidates[0]["expression"] == "inteligencia artificial generativa"
    assert candidates[0]["method"] == "is_index"
    assert 0.0 <= candidates[0]["is_norm"] <= 1.0
    assert candidates[0]["selected_default"] is True


def test_multiword_candidates_include_doc_count_and_context_examples() -> None:
    from src.importers.multiword_candidates import extract_multiword_candidates

    text = """
    **** *doc_1
    inteligencia artificial generativa muda a pesquisa aplicada.
    inteligencia artificial generativa muda a pesquisa aplicada.
    **** *doc_2
    A pesquisa sobre inteligencia artificial generativa cresceu.
    """

    candidates = extract_multiword_candidates(text, top_n=10, min_freq=2, ngram_max=3)
    by_expr = {item["expression"]: item for item in candidates}

    candidate = by_expr["inteligencia artificial generativa"]
    assert candidate["doc_count"] == 2
    assert candidate["context_examples"]
    assert candidate["context_examples"][0]["doc_label"]
    assert "inteligencia artificial generativa" in candidate["context_examples"][0]["context"].lower()


def test_multiword_candidates_filter_single_document_noise_when_corpus_has_multiple_docs() -> None:
    from src.importers.multiword_candidates import extract_multiword_candidates

    text = """
    **** *doc_1
    revista foco impacto produtividade
    revista foco impacto produtividade
    revista foco impacto produtividade
    **** *doc_2
    inteligencia artificial generativa aplicada
    inteligencia artificial generativa aplicada
    **** *doc_3
    inteligencia artificial generativa aplicada
    """

    expressions = {
        item["expression"]
        for item in extract_multiword_candidates(text, top_n=20, min_freq=2, ngram_max=5)
    }

    assert "revista foco" not in expressions
    assert "foco impacto produtividade" not in expressions
    assert "inteligencia artificial" in expressions
    assert "inteligencia artificial generativa" in expressions


def test_multiword_candidates_filter_weak_predicate_and_adjective_pairs() -> None:
    from src.importers.multiword_candidates import extract_multiword_candidates

    text = """
    **** *doc_1
    inteligencia artificial generativa aplicada cresce
    inteligencia artificial generativa aplicada cresce
    **** *doc_2
    inteligencia artificial generativa aplicada cresce
    inteligencia artificial generativa aplicada cresce
    """

    expressions = {
        item["expression"]
        for item in extract_multiword_candidates(text, top_n=20, min_freq=2, ngram_max=3)
    }

    assert "inteligencia artificial" in expressions
    assert "inteligencia artificial generativa" in expressions
    assert "generativa aplicada" not in expressions
    assert "aplicada cresce" not in expressions


def test_enrich_multiword_candidates_filters_r_candidates_seen_in_one_document_only() -> None:
    from src.importers.multiword_candidates import enrich_multiword_candidates_with_context

    text = """
    **** *doc_1
    revista foco impacto produtividade
    revista foco impacto produtividade
    **** *doc_2
    inteligencia artificial generativa
    **** *doc_3
    inteligencia artificial generativa
    """
    candidates = [
        {"expression": "revista foco", "replacement": "revista_foco", "n_tokens": 2, "frequency": 2},
        {
            "expression": "inteligencia artificial",
            "replacement": "inteligencia_artificial",
            "n_tokens": 2,
            "frequency": 2,
        },
    ]

    enriched = enrich_multiword_candidates_with_context(text, candidates)
    expressions = {item["expression"] for item in enriched}

    assert "revista foco" not in expressions
    assert "inteligencia artificial" in expressions


def test_enrich_multiword_candidates_filters_weak_r_bigrams() -> None:
    from src.importers.multiword_candidates import enrich_multiword_candidates_with_context

    text = """
    **** *doc_1
    inteligencia artificial generativa aplicada cresce
    **** *doc_2
    inteligencia artificial generativa aplicada cresce
    """
    candidates = [
        {
            "expression": "inteligencia artificial",
            "replacement": "inteligencia_artificial",
            "n_tokens": 2,
            "frequency": 2,
        },
        {
            "expression": "generativa aplicada",
            "replacement": "generativa_aplicada",
            "n_tokens": 2,
            "frequency": 2,
        },
        {
            "expression": "aplicada cresce",
            "replacement": "aplicada_cresce",
            "n_tokens": 2,
            "frequency": 2,
        },
    ]

    enriched = enrich_multiword_candidates_with_context(text, candidates)
    expressions = {item["expression"] for item in enriched}

    assert "inteligencia artificial" in expressions
    assert "generativa aplicada" not in expressions
    assert "aplicada cresce" not in expressions


def test_enrich_multiword_candidates_filters_interior_sliding_trigrams() -> None:
    from src.importers.multiword_candidates import enrich_multiword_candidates_with_context

    text = """
    **** *doc_1
    inteligencia artificial generativa aplicada cresce
    **** *doc_2
    inteligencia artificial generativa aplicada cresce
    """
    candidates = [
        {
            "expression": "inteligencia artificial generativa",
            "replacement": "inteligencia_artificial_generativa",
            "n_tokens": 3,
            "frequency": 2,
        },
        {
            "expression": "artificial generativa aplicada",
            "replacement": "artificial_generativa_aplicada",
            "n_tokens": 3,
            "frequency": 2,
        },
    ]

    enriched = enrich_multiword_candidates_with_context(text, candidates)
    expressions = {item["expression"] for item in enriched}

    assert "inteligencia artificial generativa" in expressions
    assert "artificial generativa aplicada" not in expressions


def test_apply_selected_multiwords_supports_trigrams_in_one_pass() -> None:
    from src.importers.bigram_compounds import (
        apply_selected_bigrams_to_text,
        selected_bigrams_to_expressions,
    )

    selected = [
        {
            "expression": "inteligencia artificial generativa",
            "replacement": "inteligencia_artificial_generativa",
            "n_tokens": 3,
        }
    ]

    expressions = selected_bigrams_to_expressions(selected)
    text, count = apply_selected_bigrams_to_text(
        "**** *doc_1\nA inteligencia artificial generativa mudou a pesquisa.",
        expressions,
    )

    assert count == 1
    assert "inteligencia_artificial_generativa" in text
    assert text.startswith("**** *doc_1")
