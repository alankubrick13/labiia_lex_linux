#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Data Exchange - Handles data serialization between Python and R

This module provides functions to export analysis results to formats
that R scripts can read, and import R results back to Python.
"""

import os
import tempfile
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

from ...utils.logger import get_logger

logger = get_logger('data_exchange')


class DataExchange:
    """
    Handles data serialization between Python and R.

    Provides methods to:
    - Export AFC data (coordinates, chi-square tables)
    - Export CHD data (tree structure, class assignments, words)
    - Export Similarity data (co-occurrence matrix, frequencies)
    """

    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize DataExchange.

        Args:
            temp_dir: Directory for temporary files (default: system temp)
        """
        if temp_dir:
            self.temp_dir = Path(temp_dir)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.temp_dir = Path(tempfile.gettempdir()) / 'textanalyzer_r'
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self):
        """Remove temporary files."""
        import shutil
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.warning(f"Could not cleanup temp dir: {e}")

    # =========================================================================
    # AFC Data Export
    # =========================================================================

    def export_afc_data(self, afc_result: Dict[str, Any],
                        chd_result=None) -> Dict[str, str]:
        """
        Export AFC analysis data for R visualization.

        Args:
            afc_result: AFC analysis result dictionary
            chd_result: Optional CHD result for class coloring

        Returns:
            Dictionary with paths to exported files:
            - coords_file: Word coordinates CSV
            - chi2_file: Chi-square values CSV
            - inertia_file: Explained inertia JSON
        """
        files = {}

        # Export coordinates
        coords_file = self.temp_dir / 'afc_coords.csv'
        row_coords = afc_result.get('row_coordinates')

        if row_coords is not None and not row_coords.empty:
            # Ensure we have at least 2 dimensions
            if len(row_coords.columns) >= 2:
                export_df = row_coords.copy()
                # Standardize column names for R
                export_df.columns = [f'Dim{i+1}' for i in range(len(export_df.columns))]
                export_df.index.name = 'word'
                export_df.to_csv(coords_file, encoding='utf-8-sig')
                files['coords_file'] = str(coords_file)
                logger.debug(f"Exported AFC coordinates: {len(export_df)} words")

        # Export column coordinates when available (for AFC col=TRUE mode)
        col_coords = afc_result.get('col_coordinates')
        if col_coords is None:
            col_coords = afc_result.get('column_coordinates')
        if col_coords is not None and hasattr(col_coords, "empty") and not col_coords.empty:
            if len(col_coords.columns) >= 2:
                col_coords_file = self.temp_dir / 'afc_col_coords.csv'
                col_df = col_coords.copy()
                col_df.columns = [f'Dim{i+1}' for i in range(len(col_df.columns))]
                col_df.index.name = 'item'
                col_df.to_csv(col_coords_file, encoding='utf-8-sig')
                files['col_coords_file'] = str(col_coords_file)
                logger.debug(f"Exported AFC column coordinates: {len(col_df)} items")

        # Export chi-square values if CHD result is available
        if chd_result is not None:
            chi2_file = self.temp_dir / 'afc_chi2.csv'
            chi2_data = self._build_chi2_table(afc_result, chd_result)
            if chi2_data is not None and not chi2_data.empty:
                chi2_data.to_csv(chi2_file, encoding='utf-8-sig')
                files['chi2_file'] = str(chi2_file)
                logger.debug(f"Exported chi-square table: {len(chi2_data)} words")

        # Export debsup hint (where supplementary forms start), when available
        debsup = self._infer_debsup(afc_result, chd_result)
        if debsup is not None:
            files['debsup'] = str(debsup)

        # Export inertia values
        inertia_file = self.temp_dir / 'afc_inertia.json'
        inertia = afc_result.get('explained_inertia', [])
        with open(inertia_file, 'w', encoding='utf-8') as f:
            json.dump({'inertia': [float(x) for x in inertia]}, f)
        files['inertia_file'] = str(inertia_file)

        return files

    def _build_chi2_table(self, afc_result: Dict, chd_result) -> Optional[pd.DataFrame]:
        """Build chi-square table mapping words to classes."""
        row_coords = afc_result.get('row_coordinates')
        if row_coords is None:
            return None

        words = list(row_coords.index)

        # CHD result can expose classes either as:
        # 1) classes[class_id].characteristic_forms (legacy object)
        # 2) profiles[class_id] = [(word, chi2, ...), ...] (new CHDResult dataclass)
        classes = getattr(chd_result, 'classes', None)
        profiles = getattr(chd_result, 'profiles', None)

        if classes is not None:
            class_ids = sorted(classes.keys())
        elif isinstance(profiles, dict):
            class_ids = sorted(int(cid) for cid in profiles.keys())
        else:
            class_ids = []

        num_classes = len(class_ids)

        if num_classes == 0:
            return None

        # Initialize chi2 matrix with class IDs as column names
        chi2_data = pd.DataFrame(
            0.0,
            index=words,
            columns=[str(cid) for cid in class_ids]
        )

        if classes is not None:
            # Fill with chi-square values from legacy CHD class object
            for class_id, cls in classes.items():
                col = str(class_id)
                if col in chi2_data.columns:
                    for form_data in getattr(cls, 'characteristic_forms', []):
                        if len(form_data) >= 2:
                            word = form_data[0]
                            chi2 = float(form_data[1])
                            if word in chi2_data.index:
                                chi2_data.loc[word, col] = chi2
        else:
            # Fill with chi-square values from profiles mapping
            for class_id, rows in (profiles or {}).items():
                col = str(class_id)
                if col not in chi2_data.columns:
                    continue
                for row in rows:
                    if not row:
                        continue
                    word = str(row[0])
                    try:
                        chi2 = float(row[1]) if len(row) > 1 else 0.0
                    except (TypeError, ValueError):
                        chi2 = 0.0
                    if word in chi2_data.index:
                        chi2_data.loc[word, col] = chi2

        chi2_data.index.name = 'word'
        return chi2_data

    @staticmethod
    def _infer_debsup(afc_result: Dict[str, Any], chd_result: Optional[Any]) -> Optional[int]:
        """Infer debsup index from AFC/CHD metadata when available."""
        candidates: List[Any] = [
            afc_result.get('debsup'),
            afc_result.get('n_active_forms'),
        ]
        if chd_result is not None:
            candidates.extend([
                getattr(chd_result, 'debsup', None),
                getattr(chd_result, 'n_active_forms', None),
            ])

        for value in candidates:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 1:
                return parsed
        return None

    # =========================================================================
    # CHD Data Export
    # =========================================================================

    def export_chd_data(self, chd_result) -> Dict[str, str]:
        """
        Export CHD analysis data for R dendrogram visualization.

        Args:
            chd_result: CHD analysis result

        Returns:
            Dictionary with paths to exported files:
            - tree_file: Tree structure in Newick format
            - classes_file: Class assignments and percentages
            - words_file: Words per class with chi-square values
        """
        files = {}

        # Export tree structure (Newick format)
        tree_file = self.temp_dir / 'chd_tree.txt'
        tree_newick = self._build_newick_from_linkage(chd_result)
        with open(tree_file, 'w', encoding='utf-8') as f:
            f.write(tree_newick)
        files['tree_file'] = str(tree_file)

        # Export class information
        classes_file = self.temp_dir / 'chd_classes.csv'
        classes_df = self._build_classes_table(chd_result)
        classes_df.to_csv(classes_file, encoding='utf-8-sig', index=False)
        files['classes_file'] = str(classes_file)

        # Export words per class
        words_file = self.temp_dir / 'chd_words.csv'
        words_df = self._build_words_table(chd_result)
        if not words_df.empty:
            words_df.to_csv(words_file, encoding='utf-8-sig', index=False)
            files['words_file'] = str(words_file)

        return files

    def _build_newick_from_linkage(self, chd_result) -> str:
        """
        Build Newick tree from scipy linkage matrix in CHD result.

        This creates a tree that reflects the actual hierarchical
        clustering structure, not an artificial balanced tree.
        """
        class_ids = self._extract_class_ids(chd_result)
        num_classes = len(class_ids)

        if num_classes == 0:
            return ';'

        if num_classes == 1:
            return f'({class_ids[0]});'

        # Prefer explicit Newick when available
        dendro_data = getattr(chd_result, 'dendrogram_data', {}) or {}
        newick = dendro_data.get('newick') or getattr(chd_result, 'newick', None)
        if isinstance(newick, str) and newick.strip():
            rendered = newick.strip()
            return rendered if rendered.endswith(';') else f'{rendered};'

        # Try to get linkage matrix from dendrogram_data
        linkage_matrix = dendro_data.get('linkage_matrix')
        segment_classes = (
            dendro_data.get('segment_classes')
            or getattr(chd_result, 'segment_classes', None)
        )

        if linkage_matrix is not None:
            try:
                return self._linkage_to_newick(
                    linkage_matrix=linkage_matrix,
                    class_ids=class_ids,
                    segment_classes=segment_classes,
                )
            except Exception as e:
                logger.warning(f"Could not build tree from linkage: {e}")

        # Fallback: build tree from class parent/children relationships
        classes = getattr(chd_result, 'classes', {})

        # Check if classes have parent/children structure
        has_hierarchy = any(
            getattr(cls, 'parent_id', None) is not None or
            getattr(cls, 'children_ids', [])
            for cls in classes.values()
        )

        if has_hierarchy:
            return self._build_newick_from_hierarchy(classes)

        # Ultimate fallback: balanced tree
        return self._build_balanced_newick(class_ids) + ';'

    def _linkage_to_newick(self,
                           linkage_matrix: List[List[float]],
                           class_ids: List[int],
                           segment_classes: Optional[List[Any]] = None) -> str:
        """
        Convert scipy linkage matrix to Newick format.

        The linkage matrix has format:
        [cluster1, cluster2, distance, size]

        Clusters 0 to n-1 are original leaves.
        Clusters n to 2n-2 are merged clusters.
        """
        linkage = np.array(linkage_matrix)
        n = len(linkage) + 1  # Number of original observations
        num_classes = len(class_ids)

        if n <= 1:
            return f'({class_ids[0]});'

        # Map leaf index -> class id.
        leaf_to_class: Dict[int, int] = {}
        for i in range(n):
            leaf_to_class[i] = int(class_ids[i % num_classes])

        if segment_classes:
            for i, cls in enumerate(segment_classes):
                if i >= n:
                    break
                try:
                    cls_id = int(cls)
                except (TypeError, ValueError):
                    continue
                if cls_id in class_ids:
                    leaf_to_class[i] = cls_id

        # Build tree structure
        def get_subtree(idx: int) -> str:
            if idx < n:
                return str(leaf_to_class.get(int(idx), class_ids[0]))

            row_idx = int(idx - n)
            if row_idx < 0 or row_idx >= len(linkage):
                return str(class_ids[int(idx) % num_classes])

            left_idx = int(linkage[row_idx, 0])
            right_idx = int(linkage[row_idx, 1])

            left = get_subtree(left_idx)
            right = get_subtree(right_idx)

            return f'({left},{right})'

        # Get root (last merge)
        root_idx = n + len(linkage) - 1
        tree = get_subtree(root_idx)

        # Collapse duplicate labels while preserving class set for dendrogram tips.
        tree = self._collapse_duplicate_leaves(tree, class_ids)

        return tree + ';'

    def _collapse_duplicate_leaves(self, tree: str, class_ids: List[int]) -> str:
        """
        Collapse repeated class labels from leaf-level linkage Newick.

        Strategy: preserve original topology order, pruning duplicate leaves.
        """
        class_set = {int(cid) for cid in class_ids}
        text = str(tree or "").strip().rstrip(";")
        if not text:
            return self._build_hierarchical_newick([int(cid) for cid in class_ids])

        # Newick parser (supports nested tuples and optional branch lengths).
        idx = 0
        n = len(text)

        def _skip_space() -> None:
            nonlocal idx
            while idx < n and text[idx].isspace():
                idx += 1

        def _consume_label() -> str:
            nonlocal idx
            start = idx
            while idx < n and text[idx] not in ",():;":
                idx += 1
            label = text[start:idx].strip()
            if idx < n and text[idx] == ":":
                idx += 1
                while idx < n and text[idx] not in ",();":
                    idx += 1
            return label

        def _parse_node() -> Any:
            nonlocal idx
            _skip_space()
            if idx >= n:
                return None
            if text[idx] == "(":
                idx += 1
                children: List[Any] = []
                while idx < n:
                    child = _parse_node()
                    if child is not None:
                        children.append(child)
                    _skip_space()
                    if idx < n and text[idx] == ",":
                        idx += 1
                        continue
                    if idx < n and text[idx] == ")":
                        idx += 1
                    break
                _skip_space()
                _consume_label()
                return children
            label = _consume_label()
            if not label:
                return None
            try:
                return int(label)
            except ValueError:
                return label

        try:
            parsed = _parse_node()
        except Exception:
            parsed = None

        seen: set[int] = set()

        def _prune(node: Any) -> Any:
            if node is None:
                return None
            if isinstance(node, list):
                kept: List[Any] = []
                for child in node:
                    pruned = _prune(child)
                    if pruned is not None:
                        kept.append(pruned)
                if not kept:
                    return None
                if len(kept) == 1:
                    return kept[0]
                return kept
            try:
                cid = int(node)
            except (TypeError, ValueError):
                return None
            if cid not in class_set:
                return None
            if cid in seen:
                return None
            seen.add(cid)
            return cid

        pruned = _prune(parsed)
        missing = [int(cid) for cid in class_ids if int(cid) not in seen]
        for cid in missing:
            if pruned is None:
                pruned = cid
            else:
                pruned = [pruned, cid]

        if pruned is None:
            return self._build_hierarchical_newick([int(cid) for cid in class_ids])

        def _to_newick(node: Any) -> str:
            if isinstance(node, list):
                if len(node) == 1:
                    return _to_newick(node[0])
                return f"({','.join(_to_newick(child) for child in node)})"
            return str(int(node))

        return _to_newick(pruned)

    def _build_hierarchical_newick(self, labels: List[int]) -> str:
        """Build hierarchical Newick tree resembling CHD structure."""
        if len(labels) == 1:
            return str(labels[0])
        elif len(labels) == 2:
            return f'({labels[0]},{labels[1]})'
        else:
            # CHD typically splits into unequal groups
            # Take 2 on left, rest on right
            left = self._build_hierarchical_newick(labels[:2])
            right = self._build_hierarchical_newick(labels[2:])
            return f'({left},{right})'

    def _extract_class_ids(self, chd_result) -> List[int]:
        """Extract sorted class IDs from different CHD result representations."""
        classes = getattr(chd_result, 'classes', None)
        if isinstance(classes, dict) and classes:
            return sorted(int(cid) for cid in classes.keys())

        class_sizes = getattr(chd_result, 'class_sizes', None)
        if isinstance(class_sizes, dict) and class_sizes:
            return sorted(int(cid) for cid in class_sizes.keys())

        profiles = getattr(chd_result, 'profiles', None)
        if isinstance(profiles, dict) and profiles:
            return sorted(int(cid) for cid in profiles.keys())

        return []

    def _build_newick_from_hierarchy(self, classes: Dict) -> str:
        """Build Newick from CHDClass parent/children relationships."""
        # Find root classes (no parent)
        roots = [cid for cid, cls in classes.items()
                 if getattr(cls, 'parent_id', None) is None]

        if not roots:
            # All are roots
            roots = sorted(classes.keys())

        def build_subtree(class_ids: List[int]) -> str:
            if len(class_ids) == 1:
                return str(class_ids[0])
            elif len(class_ids) == 2:
                return f'({class_ids[0]},{class_ids[1]})'
            else:
                mid = len(class_ids) // 2
                left = build_subtree(class_ids[:mid])
                right = build_subtree(class_ids[mid:])
                return f'({left},{right})'

        return build_subtree(sorted(roots)) + ';'

    def _build_balanced_newick(self, labels: List[int]) -> str:
        """Recursively build balanced Newick tree (fallback)."""
        if len(labels) == 1:
            return str(labels[0])
        elif len(labels) == 2:
            return f'({labels[0]},{labels[1]})'
        else:
            mid = len(labels) // 2
            left = self._build_balanced_newick(labels[:mid])
            right = self._build_balanced_newick(labels[mid:])
            return f'({left},{right})'

    def _build_classes_table(self, chd_result) -> pd.DataFrame:
        """Build table with class information."""
        data = []
        classes = getattr(chd_result, 'classes', None)
        if isinstance(classes, dict) and classes:
            for class_id, cls in sorted(classes.items()):
                n_segments = getattr(cls, 'n_segments', None) or getattr(cls, 'size', 0)
                data.append({
                    'class_id': class_id,
                    'percentage': float(getattr(cls, 'percentage', 0.0)),
                    'n_segments': int(n_segments),
                    'color': getattr(cls, 'color', ''),
                })
            return pd.DataFrame(data)

        class_sizes = getattr(chd_result, 'class_sizes', None)
        if isinstance(class_sizes, dict) and class_sizes:
            total = float(sum(max(0, int(v)) for v in class_sizes.values()))
            for class_id, size in sorted(class_sizes.items()):
                n_segments = int(size)
                percentage = (100.0 * n_segments / total) if total > 0 else 0.0
                data.append({
                    'class_id': int(class_id),
                    'percentage': float(percentage),
                    'n_segments': n_segments,
                    'color': '',
                })
            return pd.DataFrame(data)

        return pd.DataFrame(columns=['class_id', 'percentage', 'n_segments', 'color'])

    def _build_words_table(self, chd_result) -> pd.DataFrame:
        """Build table with words per class."""
        data = []
        classes = getattr(chd_result, 'classes', None)
        if isinstance(classes, dict) and classes:
            for class_id, cls in sorted(classes.items()):
                forms = getattr(cls, 'characteristic_forms', [])
                for i, form_data in enumerate(forms):
                    if isinstance(form_data, (list, tuple)) and len(form_data) >= 1:
                        word = str(form_data[0])
                        chi2 = float(form_data[1]) if len(form_data) > 1 else 0.0
                        freq = int(form_data[2]) if len(form_data) > 2 else 0
                        data.append({
                            'class_id': class_id,
                            'word': word,
                            'chi2': chi2,
                            'freq': freq,
                            'rank': i + 1,
                        })
        else:
            profiles = getattr(chd_result, 'profiles', None)
            if isinstance(profiles, dict):
                for class_id, rows in sorted(profiles.items()):
                    for i, row in enumerate(rows):
                        if not isinstance(row, (list, tuple)) or len(row) < 1:
                            continue
                        word = str(row[0])
                        try:
                            chi2 = float(row[1]) if len(row) > 1 else 0.0
                        except (TypeError, ValueError):
                            chi2 = 0.0
                        try:
                            freq = int(row[2]) if len(row) > 2 else 0
                        except (TypeError, ValueError):
                            freq = 0
                        data.append({
                            'class_id': int(class_id),
                            'word': word,
                            'chi2': chi2,
                            'freq': freq,
                            'rank': i + 1,
                        })
        return pd.DataFrame(data) if data else pd.DataFrame()

    # =========================================================================
    # Similarity Data Export
    # =========================================================================

    def export_similarity_data(self, sim_result: Dict[str, Any]) -> Dict[str, str]:
        """
        Export similarity analysis data for R graph visualization.

        Args:
            sim_result: Similarity analysis result

        Returns:
            Dictionary with paths to exported files:
            - matrix_file: Co-occurrence matrix CSV
            - freq_file: Word frequencies CSV
            - edges_file: Edge list CSV
        """
        files = {}

        # Export co-occurrence matrix
        matrix = sim_result.get('cooccurrence_matrix')
        graph = sim_result.get('graph')
        
        # If no matrix but we have a graph, build matrix from graph
        if matrix is None and graph is not None:
            logger.info("Building co-occurrence matrix from NetworkX graph")
            nodes = list(graph.nodes())
            n = len(nodes)
            if n > 0:
                node_idx = {node: i for i, node in enumerate(nodes)}
                matrix_data = np.zeros((n, n))
                for u, v, data in graph.edges(data=True):
                    i, j = node_idx[u], node_idx[v]
                    weight = data.get('weight', data.get('cooccurrence', 1))
                    matrix_data[i, j] = weight
                    matrix_data[j, i] = weight  # Symmetric
                matrix = pd.DataFrame(matrix_data, index=nodes, columns=nodes)
        
        if matrix is not None:
            matrix_file = self.temp_dir / 'sim_matrix.csv'
            if isinstance(matrix, pd.DataFrame):
                matrix.to_csv(matrix_file, encoding='utf-8-sig')
            elif isinstance(matrix, np.ndarray):
                # Need vocabulary for row/column names
                vocab = sim_result.get('vocabulary', [])
                if vocab:
                    df = pd.DataFrame(matrix, index=vocab, columns=vocab)
                else:
                    df = pd.DataFrame(matrix)
                df.to_csv(matrix_file, encoding='utf-8-sig')
            files['matrix_file'] = str(matrix_file)
            logger.info(f"Exported similarity matrix: {matrix.shape if hasattr(matrix, 'shape') else 'unknown size'}")

        # Export word frequencies (try both key names)
        freq = sim_result.get('form_frequencies', sim_result.get('word_frequencies', {}))
        if freq:
            freq_file = self.temp_dir / 'sim_freq.csv'
            freq_df = pd.DataFrame([
                {'word': str(w), 'frequency': int(f)}
                for w, f in freq.items()
            ])
            freq_df.to_csv(freq_file, encoding='utf-8-sig', index=False)
            files['freq_file'] = str(freq_file)
            logger.info(f"Exported {len(freq)} word frequencies")

        # Export graph edges
        graph = sim_result.get('graph')
        if graph is not None:
            edges_file = self.temp_dir / 'sim_edges.csv'
            edges_data = []
            for u, v, data in graph.edges(data=True):
                edges_data.append({
                    'source': str(u),
                    'target': str(v),
                    'weight': float(data.get('weight', 1)),
                })
            if edges_data:
                pd.DataFrame(edges_data).to_csv(edges_file, encoding='utf-8-sig', index=False)
                files['edges_file'] = str(edges_file)

        # Export vocabulary mapping
        vocab = sim_result.get('vocabulary', [])
        if vocab:
            vocab_file = self.temp_dir / 'sim_vocab.csv'
            vocab_df = pd.DataFrame([
                {'index': i, 'word': str(w)}
                for i, w in enumerate(vocab)
            ])
            vocab_df.to_csv(vocab_file, encoding='utf-8-sig', index=False)
            files['vocab_file'] = str(vocab_file)

        return files

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_temp_output_path(self, prefix: str, extension: str = 'png') -> str:
        """
        Get a temporary output file path.

        Args:
            prefix: File prefix
            extension: File extension (default: png)

        Returns:
            Full path to temporary file
        """
        return str(self.temp_dir / f'{prefix}_output.{extension}')

    def read_output_image(self, output_file: str) -> bytes:
        """
        Read output image file as bytes.

        Args:
            output_file: Path to output file

        Returns:
            File contents as bytes
        """
        if os.path.exists(output_file):
            try:
                with open(output_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Could not read output file: {e}")
        return b''
