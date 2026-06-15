"""Testes unitários para lógica pura do AnalysisRibbonView.

Não instanciam widgets CTk — testam apenas as funções de filtragem e
habilitação que podem ser extraídas do contexto de display.
"""

import pytest


# --------------------------------------------------------------------------- #
#  Helpers — replicam a lógica de AnalysisRibbonView sem instanciar CTk       #
# --------------------------------------------------------------------------- #

def items_for_group(registry, group_name):
    """Replica _items_for_group sem instanciar o widget."""
    visible = [(k, v) for k, v in registry.items() if callable(v.get("command"))]
    if group_name == "Todos":
        return visible
    return [(k, v) for k, v in visible if str(v.get("group", "")) == group_name]


def is_enabled(payload, corpus_loaded):
    """Replica _is_enabled sem instanciar o widget."""
    requires = bool(payload.get("requires_corpus", False))
    predicate = payload.get("is_enabled_predicate")
    enabled = not requires or corpus_loaded
    if enabled and callable(predicate):
        try:
            enabled = bool(predicate())
        except Exception:
            enabled = False
    return enabled


# --------------------------------------------------------------------------- #
#  Registry mínimo para os testes                                              #
# --------------------------------------------------------------------------- #

FAKE_REGISTRY = {
    "stats": {"label": "Estatísticas", "group": "Essenciais", "command": lambda: None, "requires_corpus": True},
    "chd":   {"label": "CHD",          "group": "Essenciais", "command": lambda: None, "requires_corpus": True},
    "nuvem": {"label": "Nuvem",        "group": "Essenciais", "command": lambda: None, "requires_corpus": True},
    "yake":  {"label": "YAKE",         "group": "Semânticas", "command": lambda: None, "requires_corpus": True},
    "lda":   {"label": "LDA",          "group": "Semânticas", "command": lambda: None, "requires_corpus": True},
    "bigrams": {"label": "Bigramas",   "group": "Extras",     "command": lambda: None, "requires_corpus": True},
    "no_cmd": {"label": "Sem Comando", "group": "Essenciais"},  # sem command — deve ser filtrado
}


class TestItemsForGroup:
    def test_todos_retorna_todos_com_command(self):
        result = items_for_group(FAKE_REGISTRY, "Todos")
        keys = [k for k, _ in result]
        assert "stats" in keys
        assert "yake" in keys
        assert "bigrams" in keys
        assert "no_cmd" not in keys  # sem command é excluído

    def test_essenciais_retorna_apenas_essenciais(self):
        result = items_for_group(FAKE_REGISTRY, "Essenciais")
        keys = [k for k, _ in result]
        assert set(keys) == {"stats", "chd", "nuvem"}

    def test_semanticas_retorna_apenas_semanticas(self):
        result = items_for_group(FAKE_REGISTRY, "Semânticas")
        keys = [k for k, _ in result]
        assert set(keys) == {"yake", "lda"}

    def test_grupo_inexistente_retorna_vazio(self):
        result = items_for_group(FAKE_REGISTRY, "GrupoFantasma")
        assert result == []

    def test_extras_retorna_apenas_extras(self):
        result = items_for_group(FAKE_REGISTRY, "Extras")
        keys = [k for k, _ in result]
        assert set(keys) == {"bigrams"}


class TestIsEnabled:
    def test_sem_corpus_requires_corpus_true_disabled(self):
        payload = {"requires_corpus": True, "command": lambda: None}
        assert is_enabled(payload, corpus_loaded=False) is False

    def test_com_corpus_requires_corpus_true_enabled(self):
        payload = {"requires_corpus": True, "command": lambda: None}
        assert is_enabled(payload, corpus_loaded=True) is True

    def test_sem_requires_sempre_habilitado(self):
        payload = {"command": lambda: None}
        assert is_enabled(payload, corpus_loaded=False) is True

    def test_predicate_false_desabilita_mesmo_com_corpus(self):
        payload = {
            "requires_corpus": True,
            "command": lambda: None,
            "is_enabled_predicate": lambda: False,
        }
        assert is_enabled(payload, corpus_loaded=True) is False

    def test_predicate_true_mantém_habilitado(self):
        payload = {
            "requires_corpus": True,
            "command": lambda: None,
            "is_enabled_predicate": lambda: True,
        }
        assert is_enabled(payload, corpus_loaded=True) is True

    def test_predicate_que_lanca_excecao_desabilita(self):
        def bad_predicate():
            raise RuntimeError("explodiu")
        payload = {
            "requires_corpus": True,
            "command": lambda: None,
            "is_enabled_predicate": bad_predicate,
        }
        assert is_enabled(payload, corpus_loaded=True) is False
