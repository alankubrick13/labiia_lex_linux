"""Tests for optional semantic resource loading used by CCA auto mode."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.cca_analysis import AutoConceptConfig, CCAAnalyzer
from src.analysis.semantic_resources import SemanticResourceLoader
from src.utils.paths import PathManager


def test_semantic_loader_parses_pairs_morphology_and_ttl(tmp_path):
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    (semantic_dir / "pairs.tsv").write_text(
        "escrita\tredacao\nartigo\tpaper\n",
        encoding="utf-8",
    )
    (semantic_dir / "morphobr_sample.txt").write_text(
        "escritas,escrita.N+f+p\nredacoes,redacao.N+f+p\n",
        encoding="utf-8",
    )
    (semantic_dir / "openwordnet_sample.ttl").write_text(
        """
own:synset-001 wn:label "academico"@pt .
own:synset-001 wn:label "cientifico"@pt .
""".strip(),
        encoding="utf-8",
    )

    loader = SemanticResourceLoader(min_word_length=3, max_pairs=2000)
    bundle = loader.load(semantic_dir)

    assert bundle.lemma_by_form.get("escritas") == "escrita"
    assert ("escrita", "redacao") in bundle.semantic_pairs
    assert ("academico", "cientifico") in bundle.semantic_pairs
    assert int(bundle.diagnostics.get("files_used", 0) or 0) >= 3


def test_cca_auto_reports_semantic_resources_in_diagnostics(tmp_path, monkeypatch):
    resources_dir = tmp_path / "resources"
    semantic_dir = resources_dir / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    dictionaries_dir = tmp_path / "dictionaries"
    dictionaries_dir.mkdir(parents=True, exist_ok=True)

    (semantic_dir / "pairs.tsv").write_text(
        "metodologia\tmetodologico\nescrita\tredacao\n",
        encoding="utf-8",
    )
    (semantic_dir / "portilexicon_ud.tsv").write_text(
        "form\tlemma\tupos\nmetodologicos\tmetodologico\tADJ\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(PathManager, "resources_dir", staticmethod(lambda: resources_dir))
    monkeypatch.setattr(PathManager, "dictionaries_dir", staticmethod(lambda: dictionaries_dir))

    corpus = "\n".join(
        [
            "**** *doc_1",
            "metodologicos escrita redacao metodologia",
            "**** *doc_2",
            "metodologico escrita metodologia redacao",
            "**** *doc_3",
            "metodologicos redacao escrita metodologia",
        ]
    )
    analyzer = CCAAnalyzer(corpus, remove_stopwords=True, min_word_length=3)
    result = analyzer.suggest_concepts_hybrid(
        AutoConceptConfig(
            top_n=80,
            min_freq=1,
            window_size=4,
            min_edge_weight=1,
            min_cluster_size=2,
            confidence_threshold=0.78,
            max_concepts=8,
            adaptive_relaxation=False,
            lemma_bridge_weight=1.0,
            external_pair_weight=0.9,
            semantic_bonus_weight=0.12,
        )
    )

    semantic_diag = dict(result.diagnostics.get("semantic_resources", {}) or {})
    assert int(result.diagnostics.get("external_pairs_loaded", 0) or 0) >= 2
    assert int(semantic_diag.get("lemma_entries_loaded", 0) or 0) >= 1
    assert result.suggestions

