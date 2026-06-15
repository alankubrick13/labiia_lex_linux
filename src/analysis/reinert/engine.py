"""Python-first implementation of the Reinert/CHD workflow."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse

from ...core.chart_theme import apply_theme, ggplot_hue, save_figure
from ...core.corpus import Corpus
from ...core.stopword_policy import is_chd_visual_content_term
from ...importers.minimal_text_preparator import MinimalTextPreparator
from ..chd_visualization import render_chd_dendrogram
from .correspondence import correspondence_analysis
from .models import (
    CHDNode,
    LexicalMatrix,
    PreparedCorpus,
    ProfileCAResult,
    ProfileRow,
    ReinertAnalysisResult,
    ReinertRunConfig,
    RepeatedSegmentRow,
)
from .preparation import build_lexical_matrix, class_term_counts, metadata_row_lookup, prepare_corpus


class ReinertEngine:
    """Execute the Reinert CHD pipeline in pure Python."""

    def __init__(
        self,
        corpus: Corpus,
        output_dir: Path,
        config: ReinertRunConfig | None = None,
        preparator: MinimalTextPreparator | None = None,
    ) -> None:
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or ReinertRunConfig()
        self.preparator = preparator or MinimalTextPreparator()
        self._terms: Tuple[str, ...] = ()

    def run(self) -> ReinertAnalysisResult:
        prepared = prepare_corpus(self.corpus, self.config, self.preparator)
        lexical_matrix = build_lexical_matrix(prepared, self.config)
        if lexical_matrix.matrix.shape[0] < max(2, self.config.min_child_size * 2):
            raise ValueError("Corpus com UCEs insuficientes para CHD.")
        if lexical_matrix.matrix.shape[1] == 0:
            raise ValueError("Nenhum termo restou apos o filtro minimo de frequencia.")

        root_id, nodes, class_assignments = self._build_tree(lexical_matrix)
        class_sizes = dict(sorted(Counter(class_assignments.values()).items()))
        term_profiles = self._compute_term_profiles(lexical_matrix, class_assignments, class_sizes)
        anti_profiles = {
            class_id: [row for row in rows if row.sign == "-"][: self.config.max_profile_terms]
            for class_id, rows in term_profiles.items()
        }
        metadata_profiles = self._compute_metadata_profiles(prepared, class_assignments, class_sizes)
        typical_segments = self._compute_typical_segments(lexical_matrix, class_assignments, term_profiles)
        repeated_segments = self._compute_repeated_segments(prepared, class_assignments)
        profile_ca = self._compute_profile_ca(lexical_matrix, class_assignments, class_sizes)
        tree_newick = f"{self._build_newick(root_id, nodes)};"

        paths = self._write_outputs(
            lexical_matrix=lexical_matrix,
            nodes=nodes,
            root_id=root_id,
            class_assignments=class_assignments,
            class_sizes=class_sizes,
            term_profiles=term_profiles,
            metadata_profiles=metadata_profiles,
            profile_ca=profile_ca,
            tree_newick=tree_newick,
        )

        return ReinertAnalysisResult(
            n_classes=len(class_sizes),
            class_sizes=class_sizes,
            term_profiles=term_profiles,
            anti_profiles=anti_profiles,
            typical_segments=typical_segments,
            repeated_segments=repeated_segments,
            metadata_profiles=metadata_profiles,
            class_assignments=class_assignments,
            tree_newick=tree_newick,
            tree_root_id=root_id,
            tree_nodes=nodes,
            lexical_matrix=lexical_matrix,
            profile_ca=profile_ca,
            manifest_path=paths["manifest"],
            tree_json_path=paths["tree_json"],
            tree_newick_path=paths["tree_newick"],
            assignments_path=paths["assignments"],
            term_profiles_path=paths["term_profiles"],
            metadata_profiles_path=paths["metadata_profiles"],
            profile_ca_coords_path=paths.get("profile_ca_coords"),
            dendrogram_path=paths.get("dendrogram"),
            profile_afc_path=paths.get("profile_afc"),
            prepared_corpus_path=paths.get("prepared_corpus"),
            vocabulary_path=paths.get("vocabulary"),
            matrix_path=paths.get("matrix_uce_term"),
            uce_table_path=paths.get("uce_table"),
            profile_matrix_path=paths.get("profile_matrix"),
            profile_chi2_path=paths.get("profile_chi2"),
            class_text_paths=paths["class_text_paths"],
            colored_corpus_path=paths.get("colored_corpus"),
        )

    def _build_tree(
        self,
        lexical_matrix: LexicalMatrix,
    ) -> Tuple[int, Dict[int, CHDNode], Dict[int, int]]:
        matrix = lexical_matrix.matrix
        root = CHDNode(node_id=1, row_indices=tuple(range(matrix.shape[0])), depth=0)
        nodes: Dict[int, CHDNode] = {1: root}
        terminal_ids = {1}
        next_node_id = 2

        while len(terminal_ids) < max(2, int(self.config.max_classes)):
            best_split: Optional[dict] = None
            best_node_id: Optional[int] = None
            for node_id in sorted(terminal_ids):
                proposal = self._propose_split(lexical_matrix.matrix, nodes[node_id].row_indices, lexical_matrix.terms)
                if proposal is None:
                    continue
                if best_split is None or float(proposal["chi2"]) > float(best_split["chi2"]):
                    best_split = proposal
                    best_node_id = node_id
            if best_split is None or best_node_id is None:
                break

            parent = nodes[best_node_id]
            left_id = next_node_id
            right_id = next_node_id + 1
            next_node_id += 2
            left_node = CHDNode(
                node_id=left_id,
                row_indices=tuple(best_split["left_rows"]),
                depth=parent.depth + 1,
                parent_id=parent.node_id,
            )
            right_node = CHDNode(
                node_id=right_id,
                row_indices=tuple(best_split["right_rows"]),
                depth=parent.depth + 1,
                parent_id=parent.node_id,
            )
            parent.left_id = left_id
            parent.right_id = right_id
            parent.split_chi2 = float(best_split["chi2"])
            parent.left_profile_terms = tuple(best_split["left_terms"])
            parent.right_profile_terms = tuple(best_split["right_terms"])
            nodes[left_id] = left_node
            nodes[right_id] = right_node
            terminal_ids.remove(parent.node_id)
            terminal_ids.add(left_id)
            terminal_ids.add(right_id)

        prepared = lexical_matrix.prepared_corpus
        ordered_terminal_ids = self._terminal_nodes_in_order(root.node_id, nodes)
        class_assignments: Dict[int, int] = {}
        for class_id, node_id in enumerate(ordered_terminal_ids, start=1):
            nodes[node_id].class_id = class_id
            for row_index in nodes[node_id].row_indices:
                uce = prepared.uces[int(row_index)]
                class_assignments[int(uce.uce_id)] = class_id
        return root.node_id, nodes, class_assignments

    def _propose_split(
        self,
        matrix: sparse.csr_matrix,
        row_indices: Sequence[int],
        terms: Sequence[str],
    ) -> Optional[dict]:
        if len(row_indices) < max(2, self.config.min_child_size * 2):
            return None

        subset = matrix[np.asarray(list(row_indices), dtype=int)]
        if subset.shape[1] == 0:
            return None
        row_coords, _col_coords, singular_values = correspondence_analysis(subset, n_components=1)
        if row_coords.shape[1] == 0 or singular_values.size == 0:
            return None

        order = np.argsort(row_coords[:, 0], kind="mergesort")
        ordered_rows = np.asarray(list(row_indices), dtype=int)[order]
        ordered_matrix = np.asarray(subset[order].toarray(), dtype=float)
        prefix = np.cumsum(ordered_matrix, axis=0)
        total_counts = prefix[-1]

        best_cut = None
        best_chi2 = None
        for cut in range(self.config.min_child_size - 1, len(ordered_rows) - self.config.min_child_size):
            left_counts = prefix[cut]
            right_counts = total_counts - left_counts
            chi2_value = self._global_split_chi2(left_counts, right_counts)
            if chi2_value is None:
                continue
            if best_chi2 is None or chi2_value > best_chi2:
                best_chi2 = chi2_value
                best_cut = cut
        if best_cut is None or best_chi2 is None:
            return None

        membership = np.zeros(len(ordered_rows), dtype=bool)
        membership[: best_cut + 1] = True
        membership = self._refine_membership(ordered_matrix, membership)
        if membership.sum() < self.config.min_child_size or (~membership).sum() < self.config.min_child_size:
            return None

        left_rows = ordered_rows[membership].tolist()
        right_rows = ordered_rows[~membership].tolist()
        left_counts = ordered_matrix[membership].sum(axis=0)
        right_counts = ordered_matrix[~membership].sum(axis=0)
        left_terms = self._characteristic_terms(terms, left_counts, int(membership.sum()), right_counts, int((~membership).sum()), sign="+")
        right_terms = self._characteristic_terms(terms, left_counts, int(membership.sum()), right_counts, int((~membership).sum()), sign="-")
        if len(left_terms) < int(self.config.min_characteristic_terms):
            left_terms = self._ranked_side_terms(
                terms,
                left_counts,
                int(membership.sum()),
                right_counts,
                int((~membership).sum()),
                sign="+",
            )
        if len(right_terms) < int(self.config.min_characteristic_terms):
            right_terms = self._ranked_side_terms(
                terms,
                left_counts,
                int(membership.sum()),
                right_counts,
                int((~membership).sum()),
                sign="-",
            )
        if not left_terms and not right_terms:
            return None

        return {
            "chi2": float(self._global_split_chi2(left_counts, right_counts) or 0.0),
            "left_rows": left_rows,
            "right_rows": right_rows,
            "left_terms": left_terms[:10],
            "right_terms": right_terms[:10],
        }

    def _refine_membership(self, ordered_matrix: np.ndarray, membership: np.ndarray) -> np.ndarray:
        current = membership.copy()
        improved = True
        while improved:
            improved = False
            left_counts = ordered_matrix[current].sum(axis=0)
            right_counts = ordered_matrix[~current].sum(axis=0)
            current_score = self._global_split_chi2(left_counts, right_counts) or 0.0

            for idx in range(len(current)):
                if current[idx] and int(current.sum()) <= self.config.min_child_size:
                    continue
                if (not current[idx]) and int((~current).sum()) <= self.config.min_child_size:
                    continue
                trial = current.copy()
                trial[idx] = not trial[idx]
                trial_left = ordered_matrix[trial].sum(axis=0)
                trial_right = ordered_matrix[~trial].sum(axis=0)
                trial_score = self._global_split_chi2(trial_left, trial_right)
                if trial_score is None:
                    continue
                if trial_score > current_score:
                    current = trial
                    improved = True
                    break
        return current

    @staticmethod
    def _global_split_chi2(left_counts: np.ndarray, right_counts: np.ndarray) -> Optional[float]:
        row_totals = np.asarray([left_counts.sum(), right_counts.sum()], dtype=float)
        grand_total = float(row_totals.sum())
        if grand_total <= 0:
            return None
        col_totals = left_counts + right_counts
        if np.all(col_totals <= 0):
            return None

        expected_left = (row_totals[0] * col_totals) / grand_total
        expected_right = (row_totals[1] * col_totals) / grand_total
        chi2_left = np.divide(
            np.square(left_counts - expected_left),
            expected_left,
            out=np.zeros_like(expected_left, dtype=float),
            where=expected_left > 0,
        )
        chi2_right = np.divide(
            np.square(right_counts - expected_right),
            expected_right,
            out=np.zeros_like(expected_right, dtype=float),
            where=expected_right > 0,
        )
        return float(chi2_left.sum() + chi2_right.sum())

    def _characteristic_terms(
        self,
        terms: Sequence[str],
        left_counts: np.ndarray,
        left_size: int,
        right_counts: np.ndarray,
        right_size: int,
        sign: str,
    ) -> List[str]:
        selected: List[Tuple[str, float]] = []
        for term, left_present, right_present in zip(terms, left_counts.tolist(), right_counts.tolist()):
            signed = self._signed_chi2(
                float(left_present),
                float(left_size - left_present),
                float(right_present),
                float(right_size - right_present),
            )
            if sign == "+" and signed >= self.config.characteristic_chi2_threshold:
                selected.append((str(term), float(signed)))
            elif sign == "-" and signed <= -self.config.characteristic_chi2_threshold:
                selected.append((str(term), abs(float(signed))))
        selected.sort(key=lambda item: item[1], reverse=True)
        return [term for term, _score in selected]

    def _ranked_side_terms(
        self,
        terms: Sequence[str],
        left_counts: np.ndarray,
        left_size: int,
        right_counts: np.ndarray,
        right_size: int,
        sign: str,
    ) -> List[str]:
        """Return top signed terms even before the mixed side becomes a final class."""
        ranked: List[Tuple[str, float]] = []
        for term, left_present, right_present in zip(terms, left_counts.tolist(), right_counts.tolist()):
            signed = self._signed_chi2(
                float(left_present),
                float(left_size - left_present),
                float(right_present),
                float(right_size - right_present),
            )
            if sign == "+" and signed > 0:
                ranked.append((str(term), float(signed)))
            elif sign == "-" and signed < 0:
                ranked.append((str(term), abs(float(signed))))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [term for term, _score in ranked[:10]]

    @staticmethod
    def _signed_chi2(obs11: float, obs12: float, obs21: float, obs22: float) -> float:
        total = obs11 + obs12 + obs21 + obs22
        if total <= 0:
            return 0.0
        row1 = obs11 + obs12
        row2 = obs21 + obs22
        col1 = obs11 + obs21
        col2 = obs12 + obs22
        exp11 = (row1 * col1) / total if total else 0.0
        exp12 = (row1 * col2) / total if total else 0.0
        exp21 = (row2 * col1) / total if total else 0.0
        exp22 = (row2 * col2) / total if total else 0.0
        chi2 = 0.0
        for obs, exp in ((obs11, exp11), (obs12, exp12), (obs21, exp21), (obs22, exp22)):
            if exp > 0:
                chi2 += ((obs - exp) ** 2) / exp
        return chi2 if obs11 >= exp11 else -chi2

    def _terminal_nodes_in_order(self, node_id: int, nodes: Dict[int, CHDNode]) -> List[int]:
        node = nodes[node_id]
        if node.is_terminal:
            return [node_id]
        return self._terminal_nodes_in_order(node.left_id, nodes) + self._terminal_nodes_in_order(node.right_id, nodes)

    def _compute_term_profiles(
        self,
        lexical_matrix: LexicalMatrix,
        class_assignments: Dict[int, int],
        class_sizes: Dict[int, int],
    ) -> Dict[int, List[ProfileRow]]:
        self._terms = lexical_matrix.terms
        matrix = lexical_matrix.matrix
        prepared = lexical_matrix.prepared_corpus
        row_lookup = {uce.uce_id: uce.row_index for uce in prepared.uces}
        total_rows = int(matrix.shape[0])
        total_term_presence = np.asarray(matrix.sum(axis=0)).ravel().astype(float)
        profiles: Dict[int, List[ProfileRow]] = {}

        for class_id, class_size in class_sizes.items():
            row_indices = [row_lookup[uce_id] for uce_id, cid in class_assignments.items() if cid == class_id]
            class_counts = class_term_counts(matrix, row_indices)
            class_rows: List[ProfileRow] = []
            for term, present_in_class, present_total in zip(self._terms, class_counts.tolist(), total_term_presence.tolist()):
                signed = self._signed_chi2(
                    float(present_in_class),
                    float(class_size - present_in_class),
                    float(present_total - present_in_class),
                    float((total_rows - class_size) - (present_total - present_in_class)),
                )
                pct = (float(present_in_class) / float(class_size)) * 100.0 if class_size else 0.0
                class_rows.append(
                    ProfileRow(
                        term=term,
                        chi2=float(signed),
                        freq=int(present_in_class),
                        pct_in_class=float(pct),
                        sign="+" if signed >= 0 else "-",
                    )
                )
            class_rows.sort(key=lambda row: abs(float(row.chi2)), reverse=True)
            profiles[class_id] = class_rows[: self.config.max_profile_terms]
        return profiles

    def _compute_metadata_profiles(
        self,
        prepared: PreparedCorpus,
        class_assignments: Dict[int, int],
        class_sizes: Dict[int, int],
    ) -> Dict[int, List[ProfileRow]]:
        lookup = metadata_row_lookup(prepared)
        total_rows = len(prepared.uces)
        uce_by_id = {uce.uce_id: uce for uce in prepared.uces}
        class_row_ids = {
            class_id: {uce_by_id[uce_id].row_index for uce_id, cid in class_assignments.items() if cid == class_id}
            for class_id in class_sizes
        }

        profiles: Dict[int, List[ProfileRow]] = {}
        for class_id, row_ids in class_row_ids.items():
            rows: List[ProfileRow] = []
            class_size = class_sizes[class_id]
            for token, token_rows in lookup.items():
                token_set = set(token_rows)
                present_in_class = len(token_set.intersection(row_ids))
                present_total = len(token_set)
                signed = self._signed_chi2(
                    float(present_in_class),
                    float(class_size - present_in_class),
                    float(present_total - present_in_class),
                    float((total_rows - class_size) - (present_total - present_in_class)),
                )
                rows.append(
                    ProfileRow(
                        term=token,
                        chi2=float(signed),
                        freq=int(present_in_class),
                        pct_in_class=(float(present_in_class) / float(class_size) * 100.0) if class_size else 0.0,
                        sign="+" if signed >= 0 else "-",
                    )
                )
            rows.sort(key=lambda item: abs(float(item.chi2)), reverse=True)
            profiles[class_id] = rows[: self.config.max_profile_terms]
        return profiles

    def _compute_typical_segments(
        self,
        lexical_matrix: LexicalMatrix,
        class_assignments: Dict[int, int],
        term_profiles: Dict[int, List[ProfileRow]],
    ) -> Dict[int, List[Tuple[str, float]]]:
        prepared = lexical_matrix.prepared_corpus
        by_class: Dict[int, List[Tuple[str, float]]] = {}
        for class_id, rows in term_profiles.items():
            positive_weights = {
                row.term: float(row.chi2)
                for row in rows
                if row.sign == "+" and float(row.chi2) > 0
            }
            ranked: List[Tuple[str, float]] = []
            for uce in prepared.uces:
                if class_assignments.get(uce.uce_id) != class_id:
                    continue
                score = sum(positive_weights.get(token, 0.0) for token in set(uce.tokens))
                ranked.append((uce.raw_text.strip() or uce.prepared_text, float(score)))
            ranked.sort(key=lambda item: item[1], reverse=True)
            by_class[class_id] = ranked[: self.config.max_typical_segments]
        return by_class

    def _compute_repeated_segments(
        self,
        prepared: PreparedCorpus,
        class_assignments: Dict[int, int],
    ) -> Dict[int, List[RepeatedSegmentRow]]:
        repeated: Dict[int, List[RepeatedSegmentRow]] = {}
        class_ids = sorted(set(class_assignments.values()))
        for class_id in class_ids:
            counts: Counter[str] = Counter(
                (uce.prepared_text or uce.raw_text).strip()
                for uce in prepared.uces
                if class_assignments.get(uce.uce_id) == class_id
            )
            rows = [
                RepeatedSegmentRow(text=text, count=count, score=float(count))
                for text, count in counts.items()
                if count > 1 and text
            ]
            rows.sort(key=lambda item: (item.count, item.text), reverse=True)
            repeated[class_id] = rows[: self.config.max_typical_segments]
        return repeated

    def _compute_profile_ca(
        self,
        lexical_matrix: LexicalMatrix,
        class_assignments: Dict[int, int],
        class_sizes: Dict[int, int],
    ) -> Optional[ProfileCAResult]:
        if len(class_sizes) < 2 or lexical_matrix.matrix.shape[1] < 2:
            return None

        prepared = lexical_matrix.prepared_corpus
        row_lookup = {uce.uce_id: uce.row_index for uce in prepared.uces}
        class_ids = sorted(class_sizes.keys())
        class_rows = [
            class_term_counts(
                lexical_matrix.matrix,
                [row_lookup[uce_id] for uce_id, cid in class_assignments.items() if cid == class_id],
            )
            for class_id in class_ids
        ]
        table = np.vstack(class_rows)
        row_coords, col_coords, singular_values = correspondence_analysis(table, n_components=2)
        if row_coords.shape[1] < 2:
            row_coords = _pad_columns(row_coords, 2)
        if col_coords.shape[1] < 2:
            col_coords = _pad_columns(col_coords, 2)
        return ProfileCAResult(
            row_labels=tuple(f"class_{class_id}" for class_id in class_ids),
            row_coords=row_coords[:, :2],
            col_labels=lexical_matrix.terms,
            col_coords=col_coords[:, :2],
            singular_values=singular_values,
        )

    def _build_newick(self, node_id: int, nodes: Dict[int, CHDNode]) -> str:
        node = nodes[node_id]
        if node.is_terminal:
            return f"class_{node.class_id}"
        return (
            f"({self._build_newick(node.left_id, nodes)},{self._build_newick(node.right_id, nodes)})"
            if node.left_id is not None and node.right_id is not None
            else f"class_{node.class_id or node.node_id}"
        )

    def _write_outputs(
        self,
        lexical_matrix: LexicalMatrix,
        nodes: Dict[int, CHDNode],
        root_id: int,
        class_assignments: Dict[int, int],
        class_sizes: Dict[int, int],
        term_profiles: Dict[int, List[ProfileRow]],
        metadata_profiles: Dict[int, List[ProfileRow]],
        profile_ca: Optional[ProfileCAResult],
        tree_newick: str,
    ) -> Dict[str, Path]:
        prepared = lexical_matrix.prepared_corpus
        prepared_path = self.output_dir / "prepared_corpus.json"
        vocabulary_path = self.output_dir / "vocabulary.csv"
        matrix_path = self.output_dir / "matrix_uce_term.npz"
        uce_table_path = self.output_dir / "uce_table.csv"
        assignments_path = self.output_dir / "class_assignments.csv"
        term_profiles_path = self.output_dir / "profiles_terms.csv"
        metadata_profiles_path = self.output_dir / "profiles_metadata.csv"
        profile_ca_coords_path = self.output_dir / "profile_ca_coords.csv"
        tree_json_path = self.output_dir / "tree.json"
        tree_newick_path = self.output_dir / "tree.newick"
        manifest_path = self.output_dir / "manifest.json"

        prepared_payload = {
            "uces": [
                {
                    "row_index": uce.row_index,
                    "uce_id": uce.uce_id,
                    "uci_id": uce.uci_id,
                    "para_id": uce.para_id,
                    "raw_text": uce.raw_text,
                    "prepared_text": uce.prepared_text,
                    "tokens": list(uce.tokens),
                    "metadata_tokens": list(uce.metadata_tokens),
                }
                for uce in prepared.uces
            ]
        }
        prepared_path.write_text(json.dumps(prepared_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with vocabulary_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["term", "docfreq"])
            for term, freq in zip(lexical_matrix.terms, lexical_matrix.docfreq.tolist()):
                writer.writerow([term, int(freq)])

        sparse.save_npz(matrix_path, lexical_matrix.matrix)

        with uce_table_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["uce_id", "uci_id", "para_id", "class_id", "raw_text", "prepared_text", "metadata_tokens"])
            for uce in prepared.uces:
                writer.writerow(
                    [
                        uce.uce_id,
                        uce.uci_id,
                        uce.para_id,
                        class_assignments.get(uce.uce_id, 0),
                        uce.raw_text,
                        uce.prepared_text,
                        " ".join(uce.metadata_tokens),
                    ]
                )

        with assignments_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["uce_id", "class_id"])
            for uce_id, class_id in sorted(class_assignments.items()):
                writer.writerow([uce_id, class_id])

        self._write_profiles_csv(term_profiles_path, term_profiles)
        self._write_profiles_csv(metadata_profiles_path, metadata_profiles)

        if profile_ca is not None:
            with profile_ca_coords_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["kind", "label", "x", "y"])
                for label, coords in zip(profile_ca.row_labels, profile_ca.row_coords.tolist()):
                    writer.writerow(["class", label, coords[0], coords[1]])
                for label, coords in zip(profile_ca.col_labels, profile_ca.col_coords.tolist()):
                    writer.writerow(["term", label, coords[0], coords[1]])

        tree_payload = {
            "root_id": root_id,
            "nodes": {
                str(node_id): {
                    "node_id": node.node_id,
                    "parent_id": node.parent_id,
                    "left_id": node.left_id,
                    "right_id": node.right_id,
                    "depth": node.depth,
                    "class_id": node.class_id,
                    "split_chi2": node.split_chi2,
                    "row_indices": list(node.row_indices),
                    "left_profile_terms": list(node.left_profile_terms),
                    "right_profile_terms": list(node.right_profile_terms),
                }
                for node_id, node in nodes.items()
            },
        }
        tree_json_path.write_text(json.dumps(tree_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tree_newick_path.write_text(tree_newick, encoding="utf-8")

        class_text_paths = self._write_class_texts(prepared, class_assignments)
        colored_corpus_path = self._write_colored_corpus(prepared, class_assignments)
        profile_matrix_path, profile_chi2_path = self._write_profile_matrices(
            lexical_matrix=lexical_matrix,
            class_assignments=class_assignments,
            class_sizes=class_sizes,
            term_profiles=term_profiles,
        )
        dendrogram_path = self._write_dendrogram_plot(
            root_id,
            nodes,
            class_sizes=class_sizes,
            term_profiles=term_profiles,
            tree_newick=tree_newick,
        )
        profile_afc_path = self._write_profile_ca_plot(profile_ca, term_profiles)
        afc_points_path = self.output_dir / "chd_profiles_afc_points.csv"
        afc_labeled_path = self.output_dir / "chd_profiles_afc_labeled_terms.csv"
        afc_hidden_path = self.output_dir / "chd_profiles_afc_hidden_terms.csv"

        manifest = {
            "summary": {
                "n_classes": len(class_sizes),
                "class_sizes": class_sizes,
                "n_uces": len(prepared.uces),
                "n_terms": len(lexical_matrix.terms),
            },
            "files": {
                "prepared_corpus": str(prepared_path),
                "vocabulary": str(vocabulary_path),
                "matrix_uce_term": str(matrix_path),
                "uce_table": str(uce_table_path),
                "class_assignments": str(assignments_path),
                "profiles_terms": str(term_profiles_path),
                "profiles_metadata": str(metadata_profiles_path),
                "profile_matrix": str(profile_matrix_path),
                "profile_chi2": str(profile_chi2_path),
                "profile_ca_coords": str(profile_ca_coords_path) if profile_ca is not None else None,
                "tree_json": str(tree_json_path),
                "tree_newick": str(tree_newick_path),
                "dendrogram": str(dendrogram_path) if dendrogram_path else None,
                "profile_afc": str(profile_afc_path) if profile_afc_path else None,
                "profile_afc_points": str(afc_points_path) if afc_points_path.exists() else None,
                "profile_afc_labeled_terms": str(afc_labeled_path) if afc_labeled_path.exists() else None,
                "profile_afc_hidden_terms": str(afc_hidden_path) if afc_hidden_path.exists() else None,
                "colored_corpus": str(colored_corpus_path) if colored_corpus_path else None,
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        paths: Dict[str, Path] = {
            "manifest": manifest_path,
            "prepared_corpus": prepared_path,
            "vocabulary": vocabulary_path,
            "matrix_uce_term": matrix_path,
            "uce_table": uce_table_path,
            "tree_json": tree_json_path,
            "tree_newick": tree_newick_path,
            "assignments": assignments_path,
            "term_profiles": term_profiles_path,
            "metadata_profiles": metadata_profiles_path,
            "profile_matrix": profile_matrix_path,
            "profile_chi2": profile_chi2_path,
            "class_text_paths": class_text_paths,
        }
        if profile_ca is not None:
            paths["profile_ca_coords"] = profile_ca_coords_path
        if dendrogram_path is not None:
            paths["dendrogram"] = dendrogram_path
        if profile_afc_path is not None:
            paths["profile_afc"] = profile_afc_path
        if afc_points_path.exists():
            paths["profile_afc_points"] = afc_points_path
        if afc_labeled_path.exists():
            paths["profile_afc_labeled_terms"] = afc_labeled_path
        if afc_hidden_path.exists():
            paths["profile_afc_hidden_terms"] = afc_hidden_path
        if colored_corpus_path is not None:
            paths["colored_corpus"] = colored_corpus_path
        return paths

    @staticmethod
    def _write_profiles_csv(path: Path, profiles: Dict[int, List[ProfileRow]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["class_id", "term", "chi2", "freq", "pct_in_class", "sign"])
            for class_id, rows in sorted(profiles.items()):
                for row in rows:
                    writer.writerow([class_id, row.term, row.chi2, row.freq, row.pct_in_class, row.sign])

    def _write_profile_matrices(
        self,
        *,
        lexical_matrix: LexicalMatrix,
        class_assignments: Dict[int, int],
        class_sizes: Dict[int, int],
        term_profiles: Dict[int, List[ProfileRow]],
    ) -> Tuple[Path, Path]:
        """Write dense profile inputs without pre-cutting AFC vocabulary."""
        prepared = lexical_matrix.prepared_corpus
        row_lookup = {uce.uce_id: uce.row_index for uce in prepared.uces}
        class_ids = sorted(int(cid) for cid in class_sizes.keys())
        counts_by_class: Dict[int, np.ndarray] = {}
        for class_id in class_ids:
            rows = [
                row_lookup[uce_id]
                for uce_id, cid in class_assignments.items()
                if int(cid) == int(class_id) and uce_id in row_lookup
            ]
            counts_by_class[class_id] = class_term_counts(lexical_matrix.matrix, rows)

        chi2_by_class: Dict[int, Dict[str, float]] = {}
        for class_id, rows in term_profiles.items():
            chi2_by_class[int(class_id)] = {
                str(row.term): float(row.chi2)
                for row in rows
                if str(row.term)
            }

        matrix_path = self.output_dir / "chd_profile_matrix.csv"
        with matrix_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow([""] + [f"class_{cid}" for cid in class_ids])
            for term_idx, term in enumerate(lexical_matrix.terms):
                row = [int(counts_by_class[cid][term_idx]) for cid in class_ids]
                if sum(row) <= 0:
                    continue
                writer.writerow([term] + row)

        chi2_path = self.output_dir / "chd_profile_chi2.csv"
        with chi2_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([""] + [f"class_{cid}" for cid in class_ids])
            for term in lexical_matrix.terms:
                writer.writerow(
                    [term] + [float(chi2_by_class.get(cid, {}).get(term, 0.0)) for cid in class_ids]
                )

        return matrix_path, chi2_path

    def _write_class_texts(
        self,
        prepared: PreparedCorpus,
        class_assignments: Dict[int, int],
    ) -> Dict[int, Path]:
        class_dir = self.output_dir / "classes"
        class_dir.mkdir(parents=True, exist_ok=True)
        grouped: Dict[int, List[str]] = {}
        for uce in prepared.uces:
            class_id = class_assignments.get(uce.uce_id)
            if class_id is None:
                continue
            grouped.setdefault(class_id, []).append(uce.raw_text.strip() or uce.prepared_text)

        paths: Dict[int, Path] = {}
        for class_id, texts in grouped.items():
            path = class_dir / f"class_{class_id}.txt"
            path.write_text("\n".join(texts).strip() + "\n", encoding="utf-8")
            paths[class_id] = path
        return paths

    def _write_colored_corpus(
        self,
        prepared: PreparedCorpus,
        class_assignments: Dict[int, int],
    ) -> Path:
        path = self.output_dir / "colored_corpus.txt"
        lines = []
        for uce in prepared.uces:
            class_id = class_assignments.get(uce.uce_id, 0)
            lines.append(f"[class_{class_id}] {uce.raw_text.strip() or uce.prepared_text}")
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return path

    def _write_dendrogram_plot(
        self,
        root_id: int,
        nodes: Dict[int, CHDNode],
        *,
        class_sizes: Dict[int, int],
        term_profiles: Dict[int, List[ProfileRow]],
        tree_newick: str,
    ) -> Optional[Path]:
        _ = root_id, nodes
        output_path = self.output_dir / "dendrogramme.png"
        layout_path = self.output_dir / "chd_dendrogram_layout.json"
        converted_profiles = {
            int(class_id): [
                (row.term, row.chi2, row.freq, row.pct_in_class, row.sign)
                for row in rows
            ]
            for class_id, rows in term_profiles.items()
        }
        try:
            return render_chd_dendrogram(
                profiles=converted_profiles,
                class_sizes=class_sizes,
                output_path=output_path,
                layout_path=layout_path,
                newick=tree_newick,
                max_terms_per_class=36,
            )
        except Exception:
            return None

    def _write_profile_ca_plot(
        self,
        profile_ca: Optional[ProfileCAResult],
        term_profiles: Dict[int, List[ProfileRow]],
    ) -> Optional[Path]:
        if profile_ca is None:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            return None

        apply_theme()
        fig, ax = plt.subplots(figsize=(13.5, 8.6))
        row_coords = profile_ca.row_coords
        col_coords = profile_ca.col_coords
        class_ids = [
            int(str(label).split("_")[-1])
            for label in profile_ca.row_labels
            if str(label).split("_")[-1].isdigit()
        ]
        colors = ggplot_hue(max(1, len(class_ids)))
        color_by_class = {
            class_id: colors[idx % len(colors)]
            for idx, class_id in enumerate(class_ids)
        }
        class_color_default = colors[0] if colors else "#2D2D2D"

        term_class: Dict[str, Tuple[int, float]] = {}
        ranked_terms: List[Tuple[str, int, float]] = []
        for class_id, rows in term_profiles.items():
            for row in rows:
                if not is_chd_visual_content_term(row.term):
                    continue
                score = abs(float(row.chi2))
                previous = term_class.get(row.term)
                if previous is None or score > previous[1]:
                    term_class[row.term] = (int(class_id), score)
                ranked_terms.append((row.term, int(class_id), score))
        ranked_terms.sort(key=lambda item: (item[2], item[0]), reverse=True)

        coord_by_term = {
            str(label): (float(coords[0]), float(coords[1]))
            for label, coords in zip(profile_ca.col_labels, col_coords.tolist())
            if is_chd_visual_content_term(label)
        }
        valid_terms = set(coord_by_term)
        max_total_labels = max(160, min(360, int(self.config.max_plot_terms or 240)))
        candidates: List[Tuple[str, int, float, float, float]] = []
        seen_candidate_terms: set[str] = set()
        for term, class_id, _score in ranked_terms:
            if term not in valid_terms:
                continue
            if term in seen_candidate_terms:
                continue
            x_value, y_value = coord_by_term[term]
            candidates.append((term, class_id, _score, x_value, y_value))
            seen_candidate_terms.add(term)
            if len(candidates) >= max_total_labels:
                break
        if len(candidates) < max_total_labels:
            for term in sorted(valid_terms):
                if term in seen_candidate_terms:
                    continue
                x_value, y_value = coord_by_term[term]
                class_id, score = term_class.get(term, (class_ids[0] if class_ids else 1, 0.0))
                candidates.append((term, int(class_id), float(score), x_value, y_value))
                seen_candidate_terms.add(term)
                if len(candidates) >= max_total_labels:
                    break

        selected_terms = candidates[:max_total_labels]
        placed_terms = self._spread_afc_label_positions(selected_terms)
        selected_lookup = {term for term, _class_id, _score, _x_value, _y_value in selected_terms}

        points_path = self.output_dir / "chd_profiles_afc_points.csv"
        labeled_path = self.output_dir / "chd_profiles_afc_labeled_terms.csv"
        hidden_path = self.output_dir / "chd_profiles_afc_hidden_terms.csv"
        filtered_path = self.output_dir / "chd_profiles_afc_filtered_terms.csv"
        layout_path = self.output_dir / "chd_profiles_afc_layout.json"

        hidden_terms: List[Tuple[str, int, float, float, float]] = []
        filtered_terms: List[str] = []
        point_rows: List[Tuple[str, int, float, float, float, bool]] = []
        for label, coords in zip(profile_ca.col_labels, col_coords.tolist()):
            if not is_chd_visual_content_term(label):
                filtered_terms.append(str(label))
                continue
            term = str(label)
            class_id, score = term_class.get(term, (class_ids[0] if class_ids else 1, 1.0))
            x_value = float(coords[0])
            y_value = float(coords[1])
            is_labeled = term in selected_lookup
            point_rows.append((term, int(class_id), float(score), x_value, y_value, is_labeled))
            if not is_labeled:
                hidden_terms.append((term, int(class_id), float(score), x_value, y_value))

        for term, class_id, score, x_value, y_value, display_x, display_y in placed_terms:
            color = color_by_class.get(class_id, class_color_default)
            ax.text(
                display_x,
                display_y,
                term,
                color=color,
                ha="left",
                va="bottom",
                fontsize=6.8 if len(placed_terms) > 90 else 7.4,
                alpha=0.96,
                zorder=3,
            )

        with points_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["term", "class_id", "chi2", "x", "y", "labeled"])
            for term, class_id, score, x_value, y_value, is_labeled in point_rows:
                writer.writerow([term, class_id, score, x_value, y_value, int(is_labeled)])

        with labeled_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["term", "class_id", "chi2", "x", "y", "display_x", "display_y"])
            for term, class_id, score, x_value, y_value, display_x, display_y in placed_terms:
                writer.writerow([term, class_id, score, x_value, y_value, display_x, display_y])

        with hidden_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["term", "class_id", "chi2", "x", "y"])
            for term, class_id, score, x_value, y_value in hidden_terms:
                writer.writerow([term, class_id, score, x_value, y_value])

        legacy_hidden_path = self.output_dir / "chd_profiles_afc.png_notplotted.csv"
        with legacy_hidden_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["term"])
            for term, _class_id, _score, _x_value, _y_value in hidden_terms:
                writer.writerow([term])

        with filtered_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["term"])
            for term in filtered_terms:
                writer.writerow([term])

        layout_payload = {
            "renderer": "labiialex_chd_profile_afc_words_only_1.0.9",
            "class_markers_drawn": False,
            "class_labels_drawn": False,
            "term_points_drawn": False,
            "visible_label_count": len(selected_terms),
            "hidden_label_count": len(hidden_terms),
            "filtered_label_count": len(filtered_terms),
            "visible_terms": [term for term, *_rest in selected_terms],
        }
        layout_path.write_text(json.dumps(layout_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        ax.axhline(0.0, color="#BDBDBD", linewidth=0.8, linestyle="--", zorder=0)
        ax.axvline(0.0, color="#BDBDBD", linewidth=0.8, linestyle="--", zorder=0)
        if placed_terms:
            selected_x = [float(item[5]) for item in placed_terms]
            selected_y = [float(item[6]) for item in placed_terms]
            min_x, max_x = min(selected_x), max(selected_x)
            min_y, max_y = min(selected_y), max(selected_y)
            x_pad = max((max_x - min_x) * 0.14, 0.15)
            y_pad = max((max_y - min_y) * 0.14, 0.15)
            ax.set_xlim(min_x - x_pad, max_x + x_pad)
            ax.set_ylim(min_y - y_pad, max_y + y_pad)
        inertia = profile_ca.singular_values ** 2
        inertia = inertia / inertia.sum() if inertia.size and inertia.sum() > 0 else inertia
        x_label = f"Eixo 1 ({inertia[0] * 100:.1f}%)" if inertia.size > 0 else "Eixo 1"
        y_label = f"Eixo 2 ({inertia[1] * 100:.1f}%)" if inertia.size > 1 else "Eixo 2"
        ax.set_title("AFC Perfis pós-CHD", pad=14)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.grid(True, color="#E5E5E5", linewidth=0.6, alpha=0.75)
        path = self.output_dir / "chd_profiles_afc.png"
        fig.subplots_adjust(left=0.08, right=0.98, top=0.91, bottom=0.10)
        save_figure(fig, path, dpi=180)
        plt.close(fig)
        return path

    @staticmethod
    def _spread_afc_label_positions(
        candidates: Sequence[Tuple[str, int, float, float, float]],
    ) -> List[Tuple[str, int, float, float, float, float, float]]:
        """Keep dense AFC word maps readable without drawing points.

        The raw x/y values remain exported.  ``display_x``/``display_y`` are
        deterministic visual positions for the PNG, chosen as close as possible
        to each AFC coordinate while avoiding coarse label collisions.
        """
        if not candidates:
            return []
        xs = [float(item[3]) for item in candidates]
        ys = [float(item[4]) for item in candidates]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        x_span = max(max_x - min_x, 1e-9)
        y_span = max(max_y - min_y, 1e-9)

        x_margin = x_span * 0.14
        y_margin = y_span * 0.14
        min_bound_x = min_x - x_margin
        max_bound_x = max_x + x_margin
        min_bound_y = min_y - y_margin
        max_bound_y = max_y + y_margin
        step_x = max(x_span * 0.018, 0.030)
        step_y = max(y_span * 0.030, 0.038)
        placed_boxes: List[Tuple[float, float, float, float]] = []
        placed: List[Tuple[str, int, float, float, float, float, float]] = []

        def estimate_box(term: str, x_value: float, y_value: float) -> Tuple[float, float, float, float]:
            width = max(x_span * 0.032, min(x_span * 0.20, len(term) * x_span * 0.0095))
            height = max(y_span * 0.024, y_span * 0.035)
            return (x_value, y_value - height * 0.15, x_value + width, y_value + height)

        def intersects(box: Tuple[float, float, float, float]) -> bool:
            left, bottom, right, top = box
            pad_x = x_span * 0.004
            pad_y = y_span * 0.006
            for other_left, other_bottom, other_right, other_top in placed_boxes:
                if right + pad_x <= other_left or left >= other_right + pad_x:
                    continue
                if top + pad_y <= other_bottom or bottom >= other_top + pad_y:
                    continue
                return True
            return False

        offsets: List[Tuple[float, float]] = [(0.0, 0.0)]
        for ring in range(1, 18):
            for dx in range(-ring, ring + 1):
                offsets.append((dx * step_x, -ring * step_y))
                offsets.append((dx * step_x, ring * step_y))
            for dy in range(-ring + 1, ring):
                offsets.append((-ring * step_x, dy * step_y))
                offsets.append((ring * step_x, dy * step_y))

        for term, class_id, score, x_value, y_value in candidates:
            raw_x = float(x_value)
            raw_y = float(y_value)
            chosen_x = raw_x
            chosen_y = raw_y
            chosen_box = estimate_box(term, chosen_x, chosen_y)
            for dx, dy in offsets:
                trial_x = min(max(raw_x + dx, min_bound_x), max_bound_x)
                trial_y = min(max(raw_y + dy, min_bound_y), max_bound_y)
                trial_box = estimate_box(term, trial_x, trial_y)
                if not intersects(trial_box):
                    chosen_x = trial_x
                    chosen_y = trial_y
                    chosen_box = trial_box
                    break
            placed_boxes.append(chosen_box)
            placed.append((term, class_id, score, raw_x, raw_y, chosen_x, chosen_y))
        return placed


def _pad_columns(array: np.ndarray, n_columns: int) -> np.ndarray:
    if array.shape[1] >= n_columns:
        return array
    padded = np.zeros((array.shape[0], n_columns), dtype=float)
    if array.shape[1] > 0:
        padded[:, : array.shape[1]] = array
    return padded
