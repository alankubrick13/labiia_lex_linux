"""Benchmark helpers for comparing Reinert/CHD runs via canonical artifacts."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment


def compare_reinert_manifests(
    reference_manifest: str | Path,
    candidate_manifest: str | Path,
    *,
    top_n_terms: int = 20,
) -> Dict[str, Any]:
    """Compare two Reinert runs through canonical manifest artifacts."""
    reference = _load_manifest_bundle(reference_manifest)
    candidate = _load_manifest_bundle(candidate_manifest)

    common_uce_ids = sorted(set(reference["assignments"].keys()) & set(candidate["assignments"].keys()))
    reference_labels = [int(reference["assignments"][uce_id]) for uce_id in common_uce_ids]
    candidate_labels = [int(candidate["assignments"][uce_id]) for uce_id in common_uce_ids]

    if common_uce_ids:
        assignment_ari = _adjusted_rand_index(reference_labels, candidate_labels)
        assignment_nmi = _normalized_mutual_information(reference_labels, candidate_labels)
    else:
        assignment_ari = 0.0
        assignment_nmi = 0.0

    term_overlap = _compare_term_profiles(
        reference["term_profiles"],
        candidate["term_profiles"],
        top_n_terms=top_n_terms,
    )

    return {
        "reference_manifest": str(reference["manifest_path"]),
        "candidate_manifest": str(candidate["manifest_path"]),
        "n_reference_uces": len(reference["assignments"]),
        "n_candidate_uces": len(candidate["assignments"]),
        "n_common_uces": len(common_uce_ids),
        "assignment_ari": float(assignment_ari),
        "assignment_nmi": float(assignment_nmi),
        "n_reference_classes": len(reference["term_profiles"]),
        "n_candidate_classes": len(candidate["term_profiles"]),
        "term_overlap_macro_jaccard": float(term_overlap["macro_jaccard"]),
        "term_overlap_matches": term_overlap["matches"],
    }


def _load_manifest_bundle(path_like: str | Path) -> Dict[str, Any]:
    manifest_path = _resolve_manifest_path(path_like)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Manifest inválido: {manifest_path}")

    files = payload.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"Manifest sem seção 'files': {manifest_path}")

    assignments_path = _resolve_existing_path(files.get("class_assignments"))
    term_profiles_path = _resolve_existing_path(files.get("profiles_terms"))
    if assignments_path is None:
        raise FileNotFoundError(f"class_assignments não encontrado para {manifest_path}")
    if term_profiles_path is None:
        raise FileNotFoundError(f"profiles_terms não encontrado para {manifest_path}")

    return {
        "manifest_path": manifest_path,
        "assignments": _load_assignments(assignments_path),
        "term_profiles": _load_term_profiles(term_profiles_path),
    }


def _resolve_manifest_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    manifest_path = path / "manifest.json" if path.exists() and path.is_dir() else path
    if not manifest_path.exists() or not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest não encontrado: {manifest_path}")
    return manifest_path


def _resolve_existing_path(path_like: Any) -> Optional[Path]:
    if not path_like:
        return None
    try:
        path = Path(str(path_like))
    except Exception:
        return None
    if path.exists() and path.is_file():
        return path
    return None


def _load_assignments(path: Path) -> Dict[int, int]:
    assignments: Dict[int, int] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                uce_id = int(row.get("uce_id", 0) or 0)
                class_id = int(row.get("class_id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if uce_id <= 0 or class_id <= 0:
                continue
            assignments[uce_id] = class_id
    return assignments


def _load_term_profiles(path: Path) -> Dict[int, List[str]]:
    grouped: Dict[int, List[Tuple[str, float]]] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                class_id = int(row.get("class_id", 0) or 0)
                term = str(row.get("term", "") or "").strip()
                chi2 = abs(float(row.get("chi2", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
            if class_id <= 0 or not term:
                continue
            grouped.setdefault(class_id, []).append((term, chi2))

    term_profiles: Dict[int, List[str]] = {}
    for class_id, rows in grouped.items():
        rows.sort(key=lambda item: item[1], reverse=True)
        term_profiles[class_id] = [term for term, _ in rows]
    return term_profiles


def _adjusted_rand_index(labels_a: Sequence[int], labels_b: Sequence[int]) -> float:
    n = len(labels_a)
    if n != len(labels_b):
        raise ValueError("As sequências de rótulos precisam ter o mesmo tamanho.")
    if n < 2:
        return 1.0

    contingency = _contingency_counts(labels_a, labels_b)
    sum_comb = sum(_comb2(count) for row in contingency.values() for count in row.values())
    row_sums = [sum(row.values()) for row in contingency.values()]
    col_totals: Dict[int, int] = {}
    for row in contingency.values():
        for label, count in row.items():
            col_totals[label] = col_totals.get(label, 0) + count
    col_sums = list(col_totals.values())

    total_pairs = _comb2(n)
    if total_pairs == 0:
        return 1.0

    sum_rows = sum(_comb2(count) for count in row_sums)
    sum_cols = sum(_comb2(count) for count in col_sums)
    expected_index = (sum_rows * sum_cols) / total_pairs
    max_index = 0.5 * (sum_rows + sum_cols)
    denominator = max_index - expected_index
    if denominator == 0:
        return 1.0
    return (sum_comb - expected_index) / denominator


def _normalized_mutual_information(labels_a: Sequence[int], labels_b: Sequence[int]) -> float:
    n = len(labels_a)
    if n != len(labels_b):
        raise ValueError("As sequências de rótulos precisam ter o mesmo tamanho.")
    if n == 0:
        return 0.0

    contingency = _contingency_counts(labels_a, labels_b)
    row_totals = {row_label: sum(cols.values()) for row_label, cols in contingency.items()}
    col_totals: Dict[int, int] = {}
    for cols in contingency.values():
        for col_label, count in cols.items():
            col_totals[col_label] = col_totals.get(col_label, 0) + count

    mutual_information = 0.0
    for row_label, cols in contingency.items():
        for col_label, count in cols.items():
            if count <= 0:
                continue
            p_ij = count / n
            p_i = row_totals[row_label] / n
            p_j = col_totals[col_label] / n
            mutual_information += p_ij * math.log(p_ij / (p_i * p_j))

    entropy_a = -sum((count / n) * math.log(count / n) for count in row_totals.values() if count > 0)
    entropy_b = -sum((count / n) * math.log(count / n) for count in col_totals.values() if count > 0)
    denominator = (entropy_a + entropy_b) / 2.0
    if denominator == 0:
        return 1.0
    return mutual_information / denominator


def _compare_term_profiles(
    reference_profiles: Dict[int, List[str]],
    candidate_profiles: Dict[int, List[str]],
    *,
    top_n_terms: int,
) -> Dict[str, Any]:
    reference_ids = sorted(reference_profiles.keys())
    candidate_ids = sorted(candidate_profiles.keys())
    if not reference_ids or not candidate_ids:
        return {"macro_jaccard": 0.0, "matches": []}

    score_matrix = np.zeros((len(reference_ids), len(candidate_ids)), dtype=float)
    for i, reference_id in enumerate(reference_ids):
        left_terms = set(reference_profiles.get(reference_id, [])[:top_n_terms])
        for j, candidate_id in enumerate(candidate_ids):
            right_terms = set(candidate_profiles.get(candidate_id, [])[:top_n_terms])
            score_matrix[i, j] = _jaccard(left_terms, right_terms)

    row_ind, col_ind = linear_sum_assignment(-score_matrix)
    matches: List[Dict[str, Any]] = []
    total_score = 0.0
    for ref_idx, cand_idx in zip(row_ind.tolist(), col_ind.tolist()):
        score = float(score_matrix[ref_idx, cand_idx])
        total_score += score
        matches.append(
            {
                "reference_class_id": int(reference_ids[ref_idx]),
                "candidate_class_id": int(candidate_ids[cand_idx]),
                "jaccard": score,
            }
        )

    macro_jaccard = total_score / float(max(len(reference_ids), len(candidate_ids)))
    return {"macro_jaccard": macro_jaccard, "matches": matches}


def _contingency_counts(labels_a: Sequence[int], labels_b: Sequence[int]) -> Dict[int, Dict[int, int]]:
    contingency: Dict[int, Dict[int, int]] = {}
    for left, right in zip(labels_a, labels_b):
        row = contingency.setdefault(int(left), {})
        row[int(right)] = row.get(int(right), 0) + 1
    return contingency


def _comb2(value: int) -> int:
    value = int(value)
    return value * (value - 1) // 2 if value >= 2 else 0


def _jaccard(left_terms: set[str], right_terms: set[str]) -> float:
    if not left_terms and not right_terms:
        return 1.0
    union = left_terms | right_terms
    if not union:
        return 0.0
    return len(left_terms & right_terms) / float(len(union))
