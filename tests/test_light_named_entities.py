from __future__ import annotations


def test_light_named_entities_detects_institutions_acronyms_and_mixed_names() -> None:
    from src.importers.light_named_entities import extract_light_named_entities

    text = """
    **** *doc_1
    O Supremo Tribunal Federal analisou pedido do Ministerio da Saude sobre OpenAI.
    O STF citou ChatGPT no debate.
    **** *doc_2
    O Supremo Tribunal Federal voltou a citar o Ministerio da Saude.
    """

    candidates = extract_light_named_entities(text, top_n=20, min_freq=1)
    by_entity = {item["entity"]: item for item in candidates}

    assert by_entity["Supremo Tribunal Federal"]["doc_count"] == 2
    assert by_entity["Ministerio da Saude"]["replacement"] == "Ministerio_da_Saude"
    assert by_entity["STF"]["entity_type"] == "acronym"
    assert by_entity["OpenAI"]["entity_type"] == "mixed_case_name"
    assert by_entity["ChatGPT"]["entity_type"] == "mixed_case_name"


def test_light_named_entities_rejects_common_sentence_start_words() -> None:
    from src.importers.light_named_entities import extract_light_named_entities

    text = """
    Hoje a politica publica foi discutida.
    Hoje a politica publica voltou ao debate.
    """

    entities = {item["entity"] for item in extract_light_named_entities(text, top_n=20, min_freq=1)}

    assert "Hoje" not in entities
