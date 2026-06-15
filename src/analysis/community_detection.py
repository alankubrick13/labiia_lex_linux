"""Shared graph community-detection helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict

import networkx as nx

log = logging.getLogger(__name__)


def _load_louvain_module():
    """Load python-louvain lazily to keep optional dependency behavior."""
    import community as community_louvain  # type: ignore

    return community_louvain


def _connected_components_partition(graph: nx.Graph) -> Dict[Any, int]:
    """Fallback partition based on connected components."""
    partition: Dict[Any, int] = {}
    for idx, component in enumerate(nx.connected_components(graph)):
        for node in component:
            partition[node] = idx
    return partition


def detect_louvain_partition(
    graph: nx.Graph,
    resolution: float = 1.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Detect communities with Louvain.

    Returns:
        Dict payload with keys:
          - partition: node -> community_id
          - modularity: float
          - n_communities: int
    """
    if graph is None or graph.number_of_nodes() == 0:
        return {"partition": {}, "modularity": 0.0, "n_communities": 0}

    try:
        community_louvain = _load_louvain_module()
        partition = community_louvain.best_partition(
            graph,
            weight="weight",
            resolution=float(resolution or 1.0),
            random_state=int(seed or 42),
        )

        # Ensure isolated or missing nodes are still represented.
        next_id = max(partition.values(), default=-1) + 1
        for node in graph.nodes():
            if node not in partition:
                partition[node] = next_id
                next_id += 1

        modularity = 0.0
        if graph.number_of_edges() > 0 and len(set(partition.values())) > 1:
            try:
                modularity = float(
                    community_louvain.modularity(partition, graph, weight="weight")
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("Louvain modularity computation failed: %s", exc)

        return {
            "partition": partition,
            "modularity": float(modularity),
            "n_communities": len(set(partition.values())),
        }
    except Exception as exc:
        log.warning("Louvain unavailable/failed; using component fallback: %s", exc)
        partition = _connected_components_partition(graph)
        return {
            "partition": partition,
            "modularity": 0.0,
            "n_communities": len(set(partition.values())),
        }

