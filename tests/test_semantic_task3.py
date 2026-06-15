"""
Testes para Task 3: YAKE e exportacoes de grafo.

Cobre:
- keyphrase_yake: extrai keyphrases via YAKE, ranqueia, deduplicacao automatica
- semantic_graph_exports: escreve nodes.csv, edges.csv, summary.json, diagnostics.json
"""

from __future__ import annotations

import csv
import json
import sys
import types
from pathlib import Path

import pytest

from src.analysis.keyphrase_yake import extract_ranked_keyphrases
from src.analysis.semantic_contracts import (
    KeyphraseCandidate,
    SemanticAnalysisError,
)
from src.analysis.semantic_graph_exports import (
    GraphEdge,
    GraphNode,
    write_diagnostics_json,
    write_edges_csv,
    write_nodes_csv,
    write_summary_json,
)
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEXTS = [
    "governo federal aprovou a medida e o governo federal fez analise textual do tema",
    "analise textual do governo e da economia com crescimento do mercado de trabalho",
    "governo federal de educacao e o professor do aluno com analise textual",
    "saude publica e a vacina do hospital para o governo com analise",
]


# ---------------------------------------------------------------------------
# Tests: keyphrase_yake
# ---------------------------------------------------------------------------

class TestYakeExtraction:

    def test_extracts_keyphrases(self):
        candidates = extract_ranked_keyphrases(
            TEXTS, min_freq=1, min_tokens=1, max_tokens=4, top_n=50
        )
        assert len(candidates) > 0
        for c in candidates:
            assert isinstance(c, KeyphraseCandidate)
            assert c.score > 0
            assert c.frequency >= 1

    def test_respects_min_freq(self):
        candidates = extract_ranked_keyphrases(
            TEXTS, min_freq=100, min_tokens=1, max_tokens=4, top_n=50
        )
        assert len(candidates) == 0

    def test_respects_top_n(self):
        candidates = extract_ranked_keyphrases(
            TEXTS, min_freq=1, min_tokens=1, max_tokens=4, top_n=3
        )
        assert len(candidates) <= 3

    def test_deduplication(self):
        """Keyphrases devem ser unicas (normalizadas)."""
        candidates = extract_ranked_keyphrases(
            TEXTS, min_freq=1, min_tokens=1, max_tokens=4, top_n=50
        )
        norms = [c.normalized_phrase for c in candidates]
        assert len(norms) == len(set(norms))

    def test_scores_are_ordered(self):
        """Resultados devem estar em ordem decrescente de score."""
        candidates = extract_ranked_keyphrases(
            TEXTS, min_freq=1, min_tokens=1, max_tokens=4, top_n=50
        )
        if len(candidates) > 1:
            for i in range(len(candidates) - 1):
                assert candidates[i].score >= candidates[i + 1].score

    def test_empty_corpus_raises(self):
        with pytest.raises(SemanticAnalysisError):
            extract_ranked_keyphrases(
                [], min_freq=1, min_tokens=1, max_tokens=4, top_n=50
            )

    def test_filters_conversational_noise_keyphrases(self, monkeypatch):
        class _FakeExtractor:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def extract_keywords(self, full_text):
                return [
                    ("entrevistador", 0.01),
                    ("então", 0.02),
                    ("saude publica", 0.03),
                    ("politica de saude", 0.04),
                ]

        fake_yake = types.SimpleNamespace(KeywordExtractor=_FakeExtractor)
        monkeypatch.setitem(sys.modules, "yake", fake_yake)

        candidates = extract_ranked_keyphrases(
            ["entrevistador então saude publica politica de saude"],
            min_freq=1,
            min_tokens=1,
            max_tokens=3,
            top_n=10,
        )
        norms = [candidate.normalized_phrase for candidate in candidates]
        assert "entrevistador" not in norms
        assert "então" not in norms
        assert "saude publica" in norms
        assert "politica de saude" in norms


# ---------------------------------------------------------------------------
# Tests: semantic_graph_exports
# ---------------------------------------------------------------------------

class TestGraphExports:

    def test_write_nodes_csv(self, tmp_path):
        nodes = [
            GraphNode(node_id="n1", label="Governo", frequency=10, community_id=0),
            GraphNode(node_id="n2", label="Economia", frequency=8, community_id=1),
        ]
        path = tmp_path / "nodes.csv"
        result = write_nodes_csv(nodes, path)
        assert result.exists()

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["node_id"] == "n1"
        assert rows[0]["label"] == "Governo"

    def test_write_edges_csv(self, tmp_path):
        edges = [
            GraphEdge(source="n1", target="n2", cooccurrence=5, association_weight=1.5),
        ]
        path = tmp_path / "edges.csv"
        result = write_edges_csv(edges, path)
        assert result.exists()

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["source"] == "n1"

    def test_write_summary_json(self, tmp_path):
        data = {"analysis_type": "network_text", "n_nodes": 10}
        path = tmp_path / "summary.json"
        result = write_summary_json(data, path)
        assert result.exists()

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["analysis_type"] == "network_text"

    def test_write_diagnostics_json(self, tmp_path):
        data = {"spacy_available": True, "warnings": []}
        path = tmp_path / "diagnostics.json"
        result = write_diagnostics_json(data, path)
        assert result.exists()

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["spacy_available"] is True
