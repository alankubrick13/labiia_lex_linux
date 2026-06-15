"""
Exportadores de grafos semanticos.

Helpers para gravar ``nodes.csv``, ``edges.csv``,
``summary.json`` e ``diagnostics.json`` em formato padrao.

Pertence a ``src/analysis`` — NAO importa ``src/ui``.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registros de nos e arestas
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class GraphNode:
    """No de um grafo semantico."""

    node_id: str
    label: str
    normalized_label: str = ""
    frequency: int = 0
    degree_centrality: float = 0.0
    betweenness_centrality: float = 0.0
    community_id: int = 0
    node_type: str = "concept"
    in_degree: int = 0
    out_degree: int = 0
    segments_count: int = 0
    label_priority: float = 0.0
    is_representative_label: bool = False
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}
        if not self.normalized_label:
            self.normalized_label = self.label.lower().strip()


@dataclass(slots=True, kw_only=True)
class GraphEdge:
    """Aresta de um grafo semantico."""

    source: str
    target: str
    cooccurrence: int = 0
    association_weight: float = 0.0
    edge_type: str = "cooccurrence"
    dominant_verb: str = ""
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


# ---------------------------------------------------------------------------
# Exportadores
# ---------------------------------------------------------------------------

def write_nodes_csv(
    nodes: Sequence[GraphNode],
    path: Path,
) -> Path:
    """Grava nodes.csv no formato padrao."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "node_id", "label", "normalized_label", "frequency",
        "degree_centrality", "betweenness_centrality", "community_id",
        "node_type", "in_degree", "out_degree", "segments_count",
        "label_priority", "is_representative_label",
    ]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for node in nodes:
            writer.writerow({
                "node_id": node.node_id,
                "label": node.label,
                "normalized_label": node.normalized_label,
                "frequency": node.frequency,
                "degree_centrality": f"{node.degree_centrality:.6f}",
                "betweenness_centrality": f"{node.betweenness_centrality:.6f}",
                "community_id": node.community_id,
                "node_type": node.node_type,
                "in_degree": node.in_degree,
                "out_degree": node.out_degree,
                "segments_count": node.segments_count,
                "label_priority": f"{node.label_priority:.6f}",
                "is_representative_label": int(bool(node.is_representative_label)),
            })

    log.info("Wrote %d nodes to %s", len(nodes), path)
    return path


def write_edges_csv(
    edges: Sequence[GraphEdge],
    path: Path,
) -> Path:
    """Grava edges.csv no formato padrao."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "source", "target", "cooccurrence", "association_weight",
        "edge_type", "dominant_verb",
    ]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for edge in edges:
            writer.writerow({
                "source": edge.source,
                "target": edge.target,
                "cooccurrence": edge.cooccurrence,
                "association_weight": f"{edge.association_weight:.6f}",
                "edge_type": edge.edge_type,
                "dominant_verb": edge.dominant_verb,
            })

    log.info("Wrote %d edges to %s", len(edges), path)
    return path


def write_summary_json(
    data: Dict[str, Any],
    path: Path,
) -> Path:
    """Grava summary.json."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    log.info("Wrote summary to %s", path)
    return path


def write_diagnostics_json(
    data: Dict[str, Any],
    path: Path,
) -> Path:
    """Grava diagnostics.json."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    log.info("Wrote diagnostics to %s", path)
    return path
