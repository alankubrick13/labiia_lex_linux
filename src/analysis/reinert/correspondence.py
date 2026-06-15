"""Correspondence analysis helpers for Reinert CHD."""

from __future__ import annotations

from typing import Tuple

import numpy as np
from scipy import sparse


def correspondence_analysis(
    table: sparse.spmatrix | np.ndarray,
    n_components: int = 2,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute row and column principal coordinates for CA."""
    if sparse.issparse(table):
        dense = np.asarray(table.toarray(), dtype=float)
    else:
        dense = np.asarray(table, dtype=float)

    if dense.ndim != 2 or dense.size == 0:
        return (
            np.zeros((0, 0), dtype=float),
            np.zeros((0, 0), dtype=float),
            np.zeros((0,), dtype=float),
        )

    total = float(dense.sum())
    if total <= 0:
        return (
            np.zeros((dense.shape[0], 0), dtype=float),
            np.zeros((dense.shape[1], 0), dtype=float),
            np.zeros((0,), dtype=float),
        )

    probability = dense / total
    row_mass = probability.sum(axis=1)
    col_mass = probability.sum(axis=0)

    valid_rows = row_mass > 0
    valid_cols = col_mass > 0
    if valid_rows.sum() == 0 or valid_cols.sum() == 0:
        return (
            np.zeros((dense.shape[0], 0), dtype=float),
            np.zeros((dense.shape[1], 0), dtype=float),
            np.zeros((0,), dtype=float),
        )

    reduced = probability[np.ix_(valid_rows, valid_cols)]
    reduced_row_mass = row_mass[valid_rows]
    reduced_col_mass = col_mass[valid_cols]
    expected = np.outer(reduced_row_mass, reduced_col_mass)
    standardized = (reduced - expected) / np.sqrt(expected)

    u, singular_values, vt = np.linalg.svd(standardized, full_matrices=False)
    keep = min(
        max(1, int(n_components)),
        singular_values.shape[0],
        max(1, reduced.shape[0] - 1),
        max(1, reduced.shape[1] - 1),
    )
    singular_values = singular_values[:keep]
    u = u[:, :keep]
    vt = vt[:keep, :]

    row_coords_reduced = (u * singular_values) / np.sqrt(reduced_row_mass[:, None])
    col_coords_reduced = (vt.T * singular_values) / np.sqrt(reduced_col_mass[:, None])

    row_coords = np.zeros((dense.shape[0], keep), dtype=float)
    col_coords = np.zeros((dense.shape[1], keep), dtype=float)
    row_coords[valid_rows, :] = row_coords_reduced
    col_coords[valid_cols, :] = col_coords_reduced
    return row_coords, col_coords, singular_values
