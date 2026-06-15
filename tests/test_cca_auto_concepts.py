"""Tests for hybrid automatic concept creation in CCA."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis import community_detection
from src.analysis.cca_analysis import (
    AutoConceptConfig,
    AutoConceptSuggestion,
    CCAAnalyzer,
)
from src.ui.dialogs.cca_dialog import CCADialog


def _build_synthetic_pt_corpus(include_ambiguous: bool = False) -> str:
    lines = []
    for idx in range(32):
        lines.append(f"**** *doc_{idx}")
        lines.append("educacao escola aluno professor aprendizagem didatica ensino")
        lines.append("professor aluno escola didatica educacao ensino")
        lines.append("saude hospital medico paciente tratamento clinica terapia")
        lines.append("medico paciente hospital saude tratamento clinica")
        lines.append("economia mercado empresa investimento lucro financa crescimento")
        lines.append("mercado empresa investimento economia lucro financa")
        if include_ambiguous:
            lines.append("modelo educacao hospital mercado inteligencia digital")
    return "\n".join(lines)


def _build_homogeneous_academic_corpus() -> str:
    docs = []
    blocks = [
        "escrita academica artigo metodologia revisao literatura citacao referencia",
        "metodo analise dados validacao triangulacao reproducibilidade",
        "autoria coautoria colaboracao orientacao banca avaliacao",
        "etica plagio originalidade integridade cientifica transparencia",
    ]
    for idx in range(32):
        docs.append(f"**** *doc_acad_{idx}")
        docs.append(blocks[idx % len(blocks)])
        docs.append(blocks[(idx + 1) % len(blocks)])
        docs.append("pesquisa universidade periodico publicacao argumento teorico")
    return "\n".join(docs)


def _build_noisy_affiliation_corpus() -> str:
    docs = []
    thematic_blocks = [
        "escrita academica argumentacao metodologia revisao literatura citacao referencia",
        "producao cientifica autoria colaboracao integridade etica plagio",
        "analise textual corpus segmentacao inferencia validade confiabilidade",
        "formacao docente letramento academico genero discursivo avaliacao",
    ]
    for idx in range(10):
        docs.append(f"**** *doc_noise_{idx}")
        docs.append("Universidade Federal de Santa Catarina Florianopolis Candido Elias Stefane")
        docs.append("Departamento Programa de Pos Graduacao ORCID DOI ISSN Revista")
        docs.append(thematic_blocks[idx % len(thematic_blocks)])
        docs.append(thematic_blocks[(idx + 1) % len(thematic_blocks)])
    return "\n".join(docs)


def _default_auto_config(**overrides) -> AutoConceptConfig:
    base = {
        "top_n": 180,
        "min_freq": 2,
        "window_size": 4,
        "min_edge_weight": 2,
        "min_cluster_size": 3,
        "confidence_threshold": 0.80,
        "max_concepts": 15,
        "resolution": 1.0,
        "seed": 42,
    }
    base.update(overrides)
    return AutoConceptConfig(**base)


def test_hybrid_auto_creates_expected_clusters_pt():
    analyzer = CCAAnalyzer(_build_synthetic_pt_corpus(), remove_stopwords=True, min_word_length=3)
    result = analyzer.suggest_concepts_hybrid(_default_auto_config())

    assert len(result.suggestions) >= 3
    word_to_concept = {
        word: suggestion.name
        for suggestion in result.suggestions
        for word in suggestion.words
    }

    assert word_to_concept["aluno"] == word_to_concept["professor"]
    assert word_to_concept["hospital"] == word_to_concept["medico"]
    assert word_to_concept["mercado"] == word_to_concept["empresa"]
    assert word_to_concept["aluno"] != word_to_concept["hospital"]


def test_precision_assigned_above_80():
    analyzer = CCAAnalyzer(_build_synthetic_pt_corpus(), remove_stopwords=True, min_word_length=3)
    result = analyzer.suggest_concepts_hybrid(_default_auto_config())

    truth = {
        "educacao": "edu",
        "escola": "edu",
        "aluno": "edu",
        "professor": "edu",
        "aprendizagem": "edu",
        "didatica": "edu",
        "ensino": "edu",
        "saude": "saude",
        "hospital": "saude",
        "medico": "saude",
        "paciente": "saude",
        "tratamento": "saude",
        "clinica": "saude",
        "terapia": "saude",
        "economia": "eco",
        "mercado": "eco",
        "empresa": "eco",
        "investimento": "eco",
        "lucro": "eco",
        "financa": "eco",
        "crescimento": "eco",
    }

    assigned_labeled = []
    for suggestion in result.suggestions:
        words = [word for word in suggestion.words if word in truth]
        if words:
            assigned_labeled.append((suggestion.name, words))

    assert assigned_labeled, "Nenhuma palavra com rótulo de referência foi atribuída."

    correct = 0
    total = 0
    for _name, words in assigned_labeled:
        counts = {}
        for word in words:
            theme = truth[word]
            counts[theme] = counts.get(theme, 0) + 1
        dominant = max(counts.values())
        correct += dominant
        total += len(words)

    precision = correct / total if total else 0.0
    assert precision >= 0.80


def test_confidence_threshold_filters_ambiguous_terms():
    analyzer = CCAAnalyzer(
        _build_synthetic_pt_corpus(include_ambiguous=True),
        remove_stopwords=True,
        min_word_length=3,
    )
    result = analyzer.suggest_concepts_hybrid(
        _default_auto_config(confidence_threshold=0.90)
    )

    assert result.suggestions
    assert "modelo" in result.unassigned_words


def test_homogeneous_academic_corpus_still_generates_multiple_suggestions():
    analyzer = CCAAnalyzer(
        _build_homogeneous_academic_corpus(),
        remove_stopwords=True,
        min_word_length=3,
    )
    result = analyzer.suggest_concepts_hybrid(
        _default_auto_config(
            top_n=260,
            min_freq=2,
            window_size=6,
            min_edge_weight=2,
            min_cluster_size=3,
            confidence_threshold=0.80,
            adaptive_relaxation=True,
            relaxation_steps=3,
            target_min_concepts=4,
            target_min_assigned_words=14,
        )
    )

    assert len(result.suggestions) >= 4
    assert int(result.diagnostics.get("assigned_words", 0) or 0) >= 14


def test_adaptive_relaxation_recovers_sparse_case():
    sparse_corpus = []
    for idx in range(12):
        sparse_corpus.append(f"**** *doc_{idx}")
        sparse_corpus.append("educacao ensino aluno")
        sparse_corpus.append("saude hospital paciente")
        sparse_corpus.append("economia mercado empresa")
    analyzer = CCAAnalyzer("\n".join(sparse_corpus), remove_stopwords=True, min_word_length=3)

    strict_cfg = _default_auto_config(
        min_edge_weight=4,
        window_size=3,
        adaptive_relaxation=False,
    )
    adaptive_cfg = _default_auto_config(
        min_edge_weight=4,
        window_size=3,
        adaptive_relaxation=True,
        relaxation_steps=2,
        target_min_concepts=2,
        target_min_assigned_words=6,
    )

    strict_result = analyzer.suggest_concepts_hybrid(strict_cfg)
    adaptive_result = analyzer.suggest_concepts_hybrid(adaptive_cfg)

    assert len(adaptive_result.suggestions) >= len(strict_result.suggestions)
    assert bool(adaptive_result.diagnostics.get("adaptive_relaxation_used", False))


def test_noisy_affiliation_terms_do_not_dominate_suggestions():
    analyzer = CCAAnalyzer(
        _build_noisy_affiliation_corpus(),
        remove_stopwords=True,
        min_word_length=3,
    )
    result = analyzer.suggest_concepts_hybrid(
        _default_auto_config(
            top_n=260,
            min_freq=2,
            window_size=7,
            min_edge_weight=2,
            min_cluster_size=3,
            confidence_threshold=0.80,
            adaptive_relaxation=True,
            relaxation_steps=3,
            target_min_concepts=4,
            target_min_assigned_words=16,
        )
    )

    assert len(result.suggestions) >= 3
    assigned = {word for suggestion in result.suggestions for word in suggestion.words}
    thematic_words = {
        "escrita",
        "academica",
        "academico",
        "metodologia",
        "revisao",
        "literatura",
        "autoria",
        "integridade",
        "analise",
        "corpus",
        "avaliacao",
        "letramento",
    }
    noisy_words = {
        "universidade",
        "federal",
        "florianopolis",
        "candido",
        "elias",
        "stefane",
        "orcid",
        "doi",
        "issn",
    }
    assert len(assigned.intersection(thematic_words)) >= 5
    assert len(assigned.intersection(noisy_words)) <= 2


def test_no_louvain_fallback_still_returns_suggestions(monkeypatch):
    analyzer = CCAAnalyzer(_build_synthetic_pt_corpus(), remove_stopwords=True, min_word_length=3)

    def _raise_import_error():
        raise ImportError("community module unavailable")

    monkeypatch.setattr(community_detection, "_load_louvain_module", _raise_import_error)
    result = analyzer.suggest_concepts_hybrid(_default_auto_config())

    assert result.suggestions
    passes = list(result.diagnostics.get("passes", []) or [])
    assert passes
    first_metrics = dict(passes[0].get("community_metrics", {}) or {})
    assert int(first_metrics.get("communities_detected", 0) or 0) >= 1
    assert float(first_metrics.get("modularity", 0.0) or 0.0) == 0.0


def test_manual_assignments_not_overwritten_on_apply():
    manual = {
        "educacao": ["aluno", "professor"],
        "saude": ["hospital", "medico"],
    }
    suggestions = [
        AutoConceptSuggestion(
            name="educacao",
            words=["aluno", "escola", "didatica"],
            mean_confidence=0.91,
            size=3,
            diagnostics={},
        ),
        AutoConceptSuggestion(
            name="mercado",
            words=["empresa", "lucro"],
            mean_confidence=0.92,
            size=2,
            diagnostics={},
        ),
    ]

    merged, created_names, words_added = CCADialog._merge_auto_suggestions(
        concept_map=manual,
        suggestions=suggestions,
    )

    assert merged["educacao"] == ["aluno", "professor"]
    auto_educ_names = [name for name in created_names if name.startswith("educacao (auto")]
    assert auto_educ_names
    assert sorted(merged[auto_educ_names[0]]) == ["didatica", "escola"]
    assert merged["mercado"] == ["empresa", "lucro"]
    assert words_added == 4


def test_auto_mode_anti_noise_uses_more_conservative_config():
    class _DummyVar:
        def __init__(self, value):
            self._value = value

        def get(self):
            return self._value

    dialog = CCADialog.__new__(CCADialog)
    dialog._top_n_var = _DummyVar(100)
    dialog._min_freq_var = _DummyVar(2)

    cfg_default = dialog._build_auto_concept_config("Padrão")
    cfg_anti = dialog._build_auto_concept_config("Anti-ruído")

    assert cfg_anti.top_n >= cfg_default.top_n
    assert cfg_anti.confidence_threshold >= cfg_default.confidence_threshold
    assert cfg_anti.orthographic_bridge_weight <= cfg_default.orthographic_bridge_weight
    assert cfg_anti.orthographic_similarity >= cfg_default.orthographic_similarity
    assert cfg_anti.early_stop_max_dominance <= cfg_default.early_stop_max_dominance


def test_apply_auto_suggestions_uses_runtime_tab_name():
    class _DummyTabs:
        def __init__(self):
            self.last = None

        def set(self, value):
            self.last = value

    dialog = CCADialog.__new__(CCADialog)
    dialog._concept_map = {}
    dialog._concept_colors = {}
    dialog._tabs = _DummyTabs()
    dialog._tab_concepts_name = "Conceitos"
    dialog._refresh_concept_list = lambda: None
    dialog._select_concept = lambda _name: None

    suggestions = [
        AutoConceptSuggestion(
            name="tema",
            words=["analise", "texto"],
            mean_confidence=0.82,
            size=2,
            diagnostics={},
        )
    ]

    concepts_added, words_added = dialog._apply_auto_suggestions(suggestions)
    assert concepts_added == 1
    assert words_added == 2
    assert dialog._tabs.last == "Conceitos"


def test_merge_auto_suggestions_accepts_comma_separated_words_string():
    suggestions = [
        {
            "name": "tema",
            "words": "analise, texto; metodologia\npesquisa",
        }
    ]

    merged, created_names, words_added = CCADialog._merge_auto_suggestions(
        concept_map={},
        suggestions=suggestions,
    )

    assert created_names == ["tema"]
    assert words_added == 4
    assert sorted(merged["tema"]) == ["analise", "metodologia", "pesquisa", "texto"]
