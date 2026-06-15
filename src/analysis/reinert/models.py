"""Data contracts for the Reinert/CHD engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import sparse


@dataclass(frozen=True)
class ReinertRunConfig:
    """Configuration for the Python Reinert engine."""

    min_docfreq: int = 3
    max_classes: int = 10
    min_child_size: int = 5
    min_characteristic_terms: int = 2
    characteristic_chi2_threshold: float = 3.84
    max_profile_terms: int = 80
    max_plot_terms: int = 240
    max_typical_segments: int = 10
    preparation_level: str = "minimal_default"


@dataclass(frozen=True)
class PreparedUce:
    """Prepared representation of a single UCE."""

    row_index: int
    uce_id: int
    uci_id: int
    para_id: int
    raw_text: str
    prepared_text: str
    tokens: Tuple[str, ...]
    metadata_tokens: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedCorpus:
    """Prepared corpus ready for lexical matrix construction."""

    uces: Tuple[PreparedUce, ...]


@dataclass(frozen=True)
class LexicalMatrix:
    """Binary UCE x term matrix and associated metadata."""

    matrix: sparse.csr_matrix
    terms: Tuple[str, ...]
    docfreq: np.ndarray
    prepared_corpus: PreparedCorpus


@dataclass(frozen=True)
class ProfileRow:
    """Characteristic term or metadata profile row."""

    term: str
    chi2: float
    freq: int
    pct_in_class: float
    sign: str


@dataclass(frozen=True)
class RepeatedSegmentRow:
    """Repeated segment summary for a class."""

    text: str
    count: int
    score: float


@dataclass(frozen=True)
class ProfileCAResult:
    """Correspondence analysis result for class profiles."""

    row_labels: Tuple[str, ...]
    row_coords: np.ndarray
    col_labels: Tuple[str, ...]
    col_coords: np.ndarray
    singular_values: np.ndarray


@dataclass
class CHDNode:
    """Tree node for the divisive CHD process."""

    node_id: int
    row_indices: Tuple[int, ...]
    depth: int
    parent_id: Optional[int] = None
    left_id: Optional[int] = None
    right_id: Optional[int] = None
    split_chi2: Optional[float] = None
    class_id: Optional[int] = None
    left_profile_terms: Tuple[str, ...] = ()
    right_profile_terms: Tuple[str, ...] = ()

    @property
    def is_terminal(self) -> bool:
        return self.left_id is None and self.right_id is None


@dataclass(frozen=True)
class ReinertAnalysisResult:
    """Complete result from the Python Reinert engine."""

    n_classes: int
    class_sizes: Dict[int, int]
    term_profiles: Dict[int, List[ProfileRow]]
    anti_profiles: Dict[int, List[ProfileRow]]
    typical_segments: Dict[int, List[Tuple[str, float]]]
    repeated_segments: Dict[int, List[RepeatedSegmentRow]]
    metadata_profiles: Dict[int, List[ProfileRow]]
    class_assignments: Dict[int, int]
    tree_newick: str
    tree_root_id: int
    tree_nodes: Dict[int, CHDNode]
    lexical_matrix: LexicalMatrix
    profile_ca: Optional[ProfileCAResult]
    manifest_path: Path
    tree_json_path: Path
    tree_newick_path: Path
    assignments_path: Path
    term_profiles_path: Path
    metadata_profiles_path: Path
    profile_ca_coords_path: Optional[Path]
    dendrogram_path: Optional[Path]
    profile_afc_path: Optional[Path]
    prepared_corpus_path: Optional[Path] = None
    vocabulary_path: Optional[Path] = None
    matrix_path: Optional[Path] = None
    uce_table_path: Optional[Path] = None
    profile_matrix_path: Optional[Path] = None
    profile_chi2_path: Optional[Path] = None
    class_text_paths: Dict[int, Path] = field(default_factory=dict)
    colored_corpus_path: Optional[Path] = None
