"""
Layer 2: Graph construction, MST, communities, and metrics.

Builds a NetworkX graph from the association matrix, applies
optional MST pruning and community detection, computes structural
metrics, and determines layout positions.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]

from .models import SimilitudeConfig, SimilitudeGraph, SimilitudeMatrix

import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Community detection methods
# ---------------------------------------------------------------------------

_COMMUNITY_METHODS = {
    "louvain": "louvain",
    "multilevel": "louvain",
    "greedy": "greedy_modularity",
    "fastgreedy": "greedy_modularity",
    "label_propagation": "label_propagation",
    "edge_betweenness": "edge_betweenness",
    "walktrap": "walktrap",
}


def _detect_communities_nx(
    G: "nx.Graph",
    method: str = "louvain",
) -> Dict[str, int]:
    """Detect communities using NetworkX algorithms."""
    resolved = _COMMUNITY_METHODS.get(method.lower(), "louvain")

    try:
        if resolved == "louvain":
            parts = nx.community.louvain_communities(G, seed=42, weight="weight")
        elif resolved == "greedy_modularity":
            parts = nx.community.greedy_modularity_communities(G, weight="weight")
        elif resolved == "label_propagation":
            parts = nx.community.label_propagation_communities(G)
        elif resolved == "edge_betweenness":
            # Girvan-Newman: take first split that gives >=2 communities
            comp = nx.community.girvan_newman(G)
            parts = next(comp)
            if len(parts) < 2:
                parts = next(comp, parts)
        elif resolved == "walktrap":
            # NetworkX doesn't have walktrap natively; fallback to Louvain
            parts = nx.community.louvain_communities(G, seed=42, weight="weight")
        else:
            parts = nx.community.louvain_communities(G, seed=42, weight="weight")

        # Sort communities by size (largest first) for stable coloring
        parts_list = sorted(parts, key=len, reverse=True)

        # Merge tiny communities (< 3 members) into nearest larger community
        min_community_size = 3
        large_parts = [p for p in parts_list if len(p) >= min_community_size]
        small_parts = [p for p in parts_list if len(p) < min_community_size]

        communities: Dict[str, int] = {}
        for cid, members in enumerate(large_parts):
            for node in members:
                communities[str(node)] = cid

        # Assign orphan nodes to the community of their nearest neighbor
        for small_part in small_parts:
            for node in small_part:
                # Find which large community has the strongest edge connection
                best_cid = 0
                best_weight = -1
                for neighbor in G.neighbors(node):
                    n_str = str(neighbor)
                    if n_str in communities:
                        w = G[node][neighbor].get("weight", 1.0)
                        if w > best_weight:
                            best_weight = w
                            best_cid = communities[n_str]
                communities[str(node)] = best_cid

        return communities

    except Exception as exc:
        log.warning(f"Community detection failed ({method}): {exc}. Assigning all to 0.")
        return {str(n): 0 for n in G.nodes()}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(
    matrix: SimilitudeMatrix,
    config: SimilitudeConfig,
) -> SimilitudeGraph:
    """
    Build the complete similitude graph from the association matrix.

    Steps:
      1. Create weighted graph from association matrix
      2. Apply MST if requested
      3. Detect communities
      4. Compute metrics
      5. Compute layout

    Returns:
        SimilitudeGraph with all computed data.
    """
    if nx is None:
        raise ImportError("networkx is required for graph construction")

    association = matrix.association
    vocabulary = matrix.vocabulary
    n = len(vocabulary)

    # Step 1: Build weighted graph
    G = nx.Graph()
    for i in range(n):
        G.add_node(vocabulary[i], frequency=float(matrix.term_frequencies[i]))

    for i in range(n):
        for j in range(i + 1, n):
            w = float(association[i, j])
            if w > config.min_edge:
                G.add_edge(vocabulary[i], vocabulary[j], weight=w)

    # Remove isolated nodes
    isolates = list(nx.isolates(G))
    G.remove_nodes_from(isolates)
    if isolates:
        log.info(f"Removed {len(isolates)} isolated nodes")

    if G.number_of_nodes() < 2:
        raise ValueError(
            f"Graph has only {G.number_of_nodes()} nodes after filtering. "
            f"Try lowering min_freq or min_edge."
        )

    # Step 2: MST (maximum spanning tree)
    is_mst = False
    if config.arbremax:
        G = _apply_mst(G, matrix.coefficient_name)
        is_mst = True

    # Step 3: Communities
    if config.detect_communities:
        communities = _detect_communities_nx(G, config.community_method)
    else:
        communities = {str(n): 0 for n in G.nodes()}

    # Step 4: Metrics
    metrics = _compute_metrics(G)

    # Step 5: Term frequencies for remaining nodes
    vocab_idx = {v: i for i, v in enumerate(vocabulary)}
    remaining_nodes = list(G.nodes())
    term_freqs = np.array([
        float(matrix.term_frequencies[vocab_idx[n]])
        if n in vocab_idx else 1.0
        for n in remaining_nodes
    ])

    # Step 6: Layout
    positions = _compute_layout(G, config.layout, communities)

    log.info(
        f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
        f"{len(set(communities.values()))} communities"
    )

    return SimilitudeGraph(
        graph=G,
        vocabulary=remaining_nodes,
        communities=communities,
        metrics=metrics,
        term_frequencies=term_freqs,
        n_edges=G.number_of_edges(),
        is_mst=is_mst,
        positions=positions,
        config=config,
    )


def _apply_mst(G: "nx.Graph", coefficient: str) -> "nx.Graph":
    """
    Compute the maximum spanning tree.

    For co-occurrence (higher = stronger), we negate weights for MST.
    For normalized indices in [0,1], we use 1-w.
    """
    coeff_lower = coefficient.lower()
    use_raw_inversion = coeff_lower in ("cooccurrence", "cooc", "raw")

    G_neg = G.copy()
    for u, v, data in G_neg.edges(data=True):
        w = data.get("weight", 1.0)
        if use_raw_inversion:
            data["weight"] = (1.0 / w) if w > 0 else float("inf")
        else:
            data["weight"] = 1.0 - w

    mst = nx.minimum_spanning_tree(G_neg)

    # Restore original weights
    for u, v in mst.edges():
        if G.has_edge(u, v):
            mst[u][v]["weight"] = G[u][v]["weight"]

    # Copy node attributes
    for node in mst.nodes():
        if node in G.nodes:
            mst.nodes[node].update(G.nodes[node])

    log.info(
        f"MST: {G.number_of_edges()} edges -> {mst.number_of_edges()} edges"
    )
    return mst


def _compute_metrics(G: "nx.Graph") -> Dict[str, Dict[str, float]]:
    """Compute structural metrics for all nodes."""
    metrics: Dict[str, Dict[str, float]] = {}

    degrees = dict(G.degree())
    w_degrees = dict(G.degree(weight="weight"))

    try:
        betweenness = nx.betweenness_centrality(G, weight="weight")
    except Exception:
        betweenness = {n: 0.0 for n in G.nodes()}

    try:
        closeness = nx.closeness_centrality(G, distance=None)
    except Exception:
        closeness = {n: 0.0 for n in G.nodes()}

    for node in G.nodes():
        metrics[str(node)] = {
            "degree": float(degrees.get(node, 0)),
            "weighted_degree": float(w_degrees.get(node, 0.0)),
            "betweenness": float(betweenness.get(node, 0.0)),
            "closeness": float(closeness.get(node, 0.0)),
        }

    return metrics


def _compute_layout(
    G: "nx.Graph",
    layout_name: str,
    communities: Dict[str, int],
) -> Dict[str, Tuple[float, float]]:
    """Compute node positions using the specified layout algorithm."""
    n = G.number_of_nodes()

    if layout_name in ("forceatlas2", "fa2"):
        # For MST/tree graphs, Kamada-Kawai provides good initial spread.
        # Then we refine with spring_layout for better separation.
        try:
            init_pos = nx.kamada_kawai_layout(G, weight=None, scale=5.0)
            pos = nx.spring_layout(
                G, pos=init_pos, weight=None, seed=42,
                k=30.0 / max(1, n ** 0.35), iterations=500,
                scale=8.0,
            )
            pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}
        except Exception:
            pos = nx.spring_layout(
                G, weight=None, seed=42,
                k=25.0 / max(1, n ** 0.35), iterations=2000,
                scale=5.0,
            )
            pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}

    elif layout_name in ("frutch", "fruchterman", "fr"):
        pos = nx.spring_layout(
            G, weight=None, seed=42,
            k=8.0 / max(1, n ** 0.35), iterations=1000,
        )
        pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}
    elif layout_name in ("kawa", "kamada", "kk"):
        try:
            pos = nx.kamada_kawai_layout(G, weight="weight")
            pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}
        except Exception:
            pos = nx.spring_layout(G, weight=None, seed=42,
                                   k=8.0 / max(1, n ** 0.35), iterations=1000)
            pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}
    elif layout_name in ("circle", "circular"):
        pos = nx.circular_layout(G)
        pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}
    elif layout_name == "random":
        pos = nx.random_layout(G, seed=42)
        pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}
    else:
        pos = nx.spring_layout(G, weight=None, seed=42, iterations=800)
        pos = {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}

    pos = _normalize_positions(pos, target_range=50.0)
    return _expand_communities(pos, communities, expansion=5.0)


def _expand_communities(
    pos: Dict[str, Tuple[float, float]],
    communities: Dict[str, int],
    expansion: float = 4.0,
) -> Dict[str, Tuple[float, float]]:
    """
    Push community centroids apart to create petal-like layout.

    Creates the IRaMuTeQ-style flower petal layout by:
    1. Computing each community's centroid
    2. Pushing entire communities outward from the global center
    3. Elongating within-community spread along the radial axis (petal shape)
    """
    if len(pos) < 3:
        return pos

    # Global centroid
    all_x = [p[0] for p in pos.values()]
    all_y = [p[1] for p in pos.values()]
    gcx = sum(all_x) / len(all_x)
    gcy = sum(all_y) / len(all_y)

    # Compute community centroids
    comm_members: Dict[int, List[str]] = {}
    for node, cid in communities.items():
        if node in pos:
            comm_members.setdefault(cid, []).append(node)

    comm_centroids: Dict[int, Tuple[float, float]] = {}
    for cid, members in comm_members.items():
        cx = sum(pos[n][0] for n in members) / len(members)
        cy = sum(pos[n][1] for n in members) / len(members)
        comm_centroids[cid] = (cx, cy)

    # Compute global spread for reference
    global_spread = max(max(all_x) - min(all_x), max(all_y) - min(all_y), 1.0)

    # Find the most central community (closest to global centroid)
    central_cid = 0
    min_dist = float("inf")
    for cid, (cx, cy) in comm_centroids.items():
        d = math.sqrt((cx - gcx) ** 2 + (cy - gcy) ** 2)
        if d < min_dist:
            min_dist = d
            central_cid = cid

    # Push each community outward with elongation
    new_pos = {}
    for node, (x, y) in pos.items():
        cid = communities.get(node, 0)
        if cid not in comm_centroids:
            new_pos[node] = (x, y)
            continue

        ccx, ccy = comm_centroids[cid]
        # Direction from global center to community centroid
        dx = ccx - gcx
        dy = ccy - gcy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 0.01:
            # Truly central node: keep near center
            new_pos[node] = (x, y)
            continue

        # Unit direction vector from center to community
        ux = dx / dist
        uy = dy / dist

        if cid == central_cid:
            # Central community: light push outward for breathing room
            light_push = global_spread * 0.15
            new_pos[node] = (x + ux * light_push, y + uy * light_push)
            continue

        # Push the entire community outward (translation)
        push_strength = expansion * global_spread * 0.6
        push_x = ux * push_strength
        push_y = uy * push_strength

        # Elongate within-community: stretch along radial axis (petal effect)
        # Decompose node offset from community centroid into radial and tangential
        node_dx = x - ccx
        node_dy = y - ccy
        # Radial component (along ux, uy)
        radial = node_dx * ux + node_dy * uy
        # Tangential component (perpendicular)
        tang = node_dx * (-uy) + node_dy * ux

        # Elongate: stretch radial by 2.5x, keep tangential for breathing room
        radial *= 2.5
        tang *= 1.0

        # Reconstruct position
        new_x = ccx + radial * ux + tang * (-uy) + push_x
        new_y = ccy + radial * uy + tang * ux + push_y

        new_pos[node] = (new_x, new_y)

    return new_pos


def _normalize_positions(
    pos: Dict[str, Tuple[float, float]],
    target_range: float = 10.0,
) -> Dict[str, Tuple[float, float]]:
    """Normalize positions to fill a target range centered at origin."""
    if len(pos) < 2:
        return pos
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    rx = max(xs) - min(xs)
    ry = max(ys) - min(ys)
    scale = target_range / max(rx, ry, 1e-6)
    return {
        k: ((v[0] - cx) * scale, (v[1] - cy) * scale)
        for k, v in pos.items()
    }
