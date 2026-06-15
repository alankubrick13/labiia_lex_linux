"""
Dataclasses for the Similitude analysis module.

These models define the contracts between the three layers:
  Matrix -> Graph -> Visualization
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import sparse


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SimilitudeConfig:
    """Full configuration for a similitude analysis run."""

    # Vocabulary filtering
    min_freq: int = 3
    active_only: bool = True
    use_lemmas: bool = True
    stopword_policy: str = "aggressive_pt"

    # Association index
    coefficient: str = "cooccurrence"

    # Graph construction
    arbremax: bool = True
    min_edge: float = 0.0
    max_terms: int = 0  # 0 = no cap
    selected_words: Optional[List[str]] = None
    graph_word: str = ""
    keep_punctuation: bool = False
    strict_iramuteq_style: bool = True
    readability_warning_threshold: int = 200

    # Community detection
    detect_communities: bool = True
    community_method: str = "edge_betweenness"
    show_halo: bool = True

    # Layout
    layout: str = "frutch"

    # Visualization
    width: int = 1200
    height: int = 1000
    typegraph: str = "png"
    show_edge_labels: bool = False
    vertex_scaling: str = "frequency"
    grayscale: bool = False
    font_family: str = "sans-serif"
    edge_curved: bool = True

    # Backend
    renderer_backend: str = "iramuteq_r"


# ---------------------------------------------------------------------------
# Layer 1 outputs: Matrix
# ---------------------------------------------------------------------------

@dataclass
class ContingencyTables:
    """The four contingency counts for all term pairs.

    For binary UCE x term matrix X of shape (n_uces, n_terms):
      a[i,j] = number of UCEs where both term_i and term_j are present
      b[i,j] = number of UCEs where term_i present, term_j absent
      c[i,j] = number of UCEs where term_i absent, term_j present
      d[i,j] = number of UCEs where both are absent

    Invariant: a + b + c + d == n_uces for all (i,j).
    """

    a: np.ndarray  # (n_terms, n_terms) co-presence
    b: np.ndarray  # (n_terms, n_terms)
    c: np.ndarray  # (n_terms, n_terms)
    d: np.ndarray  # (n_terms, n_terms)
    n_uces: int


@dataclass
class SimilitudeMatrix:
    """Output of Layer 1: the association matrix + metadata."""

    association: np.ndarray          # (n_terms, n_terms) symmetric, float64
    vocabulary: List[str]            # ordered term labels
    term_frequencies: np.ndarray     # (n_terms,) absolute freq in corpus
    coefficient_name: str            # which index was used
    binary_matrix: sparse.csr_matrix  # (n_uces, n_terms) int8, the raw input
    contingency: ContingencyTables   # full contingency tables
    n_uces: int
    n_terms: int
    dropped_tokens: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer 2 outputs: Graph
# ---------------------------------------------------------------------------

@dataclass
class SimilitudeGraph:
    """Output of Layer 2: the constructed graph + analysis."""

    # The graph object (networkx)
    graph: Any  # nx.Graph

    # Node info
    vocabulary: List[str]
    communities: Dict[str, int]         # term -> community_id
    metrics: Dict[str, Dict[str, float]]  # term -> {degree, weighted_degree, betweenness, ...}
    term_frequencies: np.ndarray        # (n_nodes,) for sizing

    # Edge info
    n_edges: int
    is_mst: bool

    # Layout positions
    positions: Dict[str, Tuple[float, float]]  # term -> (x, y)

    # Config used
    config: SimilitudeConfig


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

@dataclass
class SimilitudeResult:
    """Final result of the full similitude pipeline.

    Compatible with the existing SimilarityResult contract.
    """

    graph_path: Path
    adjacency_matrix: Optional[Path] = None
    communities: Optional[Dict[str, int]] = None
    centrality: Optional[Dict[str, float]] = None

    # Extended fields (new)
    association_matrix_path: Optional[Path] = None
    vocabulary_path: Optional[Path] = None
    communities_path: Optional[Path] = None
    centrality_path: Optional[Path] = None
    graph_data: Optional[SimilitudeGraph] = None
    matrix_data: Optional[SimilitudeMatrix] = None
    config: Optional[SimilitudeConfig] = None
    artifacts: Dict[str, Path] = field(default_factory=dict)
    backend_used: str = "unknown"
    strict_mode_used: bool = True
    fallback_used: bool = False
    dropped_token_count: int = 0
    r_session_info: Optional[Dict[str, Any]] = None
    community_sensitivity_report: Optional[Dict[str, Any]] = None
    raw_graph_path: Optional[Path] = None
    verified_output: bool = False
    render_metrics: Dict[str, Any] = field(default_factory=dict)
    manifest_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)
