"""
Validation utilities for similitude analysis.

Checks matrix properties, graph integrity, and data consistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import numpy as np
from scipy import sparse

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

try:
    import imagehash
except ImportError:
    imagehash = None  # type: ignore[assignment]

try:
    from skimage.metrics import structural_similarity
except ImportError:
    structural_similarity = None  # type: ignore[assignment]

import logging

log = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Report from matrix/graph validation."""

    is_valid: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        log.warning(f"Validation: {msg}")

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False
        log.error(f"Validation: {msg}")


@dataclass
class VisualRegressionReport:
    """Comparison report for rendered images."""

    ssim: float | None = None
    phash_distance: int | None = None
    warnings: List[str] = field(default_factory=list)


def validate_binary_matrix(
    X: sparse.csr_matrix,
    vocabulary_size: int,
) -> ValidationReport:
    """Validate the binary UCE x term matrix."""
    report = ValidationReport()

    if X.shape[1] != vocabulary_size:
        report.error(
            f"Matrix columns ({X.shape[1]}) != vocabulary size ({vocabulary_size})"
        )

    if X.shape[0] == 0:
        report.error("Matrix has 0 rows (no UCEs)")

    if X.shape[1] == 0:
        report.error("Matrix has 0 columns (no terms)")

    # Check binary: all values should be 0 or 1
    if X.nnz > 0:
        data = X.data
        non_binary = np.sum((data != 0) & (data != 1))
        if non_binary > 0:
            report.error(f"Matrix contains {non_binary} non-binary values")

    # Check for empty rows (UCEs with no terms)
    row_sums = np.asarray(X.sum(axis=1)).ravel()
    empty_rows = np.sum(row_sums == 0)
    if empty_rows > 0:
        report.warn(f"{empty_rows} UCEs have no terms in vocabulary")

    # Check for empty columns (terms not in any UCE)
    col_sums = np.asarray(X.sum(axis=0)).ravel()
    empty_cols = np.sum(col_sums == 0)
    if empty_cols > 0:
        report.warn(f"{empty_cols} terms appear in no UCE (should have been filtered)")

    density = X.nnz / max(1, X.shape[0] * X.shape[1])
    if density > 0.5:
        report.warn(f"Matrix density is high ({density:.3f}), unusual for text data")

    return report


def validate_contingency(a, b, c, d, n_uces: int) -> ValidationReport:
    """Validate contingency tables."""
    report = ValidationReport()

    # Check invariant: a + b + c + d == n_uces
    total = a + b + c + d
    max_deviation = np.max(np.abs(total - n_uces))
    if max_deviation > 1e-6:
        report.error(
            f"Contingency invariant violated: max |a+b+c+d - n| = {max_deviation}"
        )

    # Check non-negative
    for name, arr in [("a", a), ("b", b), ("c", c), ("d", d)]:
        if np.any(arr < -1e-10):
            report.error(f"Contingency table '{name}' contains negative values")

    # Check symmetry of a
    if not np.allclose(a, a.T, atol=1e-10):
        report.error("Co-presence matrix 'a' is not symmetric")

    return report


def validate_association_matrix(matrix: np.ndarray) -> ValidationReport:
    """Validate the association matrix."""
    report = ValidationReport()

    if matrix.ndim != 2:
        report.error(f"Association matrix should be 2D, got {matrix.ndim}D")
        return report

    if matrix.shape[0] != matrix.shape[1]:
        report.error(
            f"Association matrix not square: {matrix.shape[0]} x {matrix.shape[1]}"
        )

    # Check symmetry
    if not np.allclose(matrix, matrix.T, atol=1e-10):
        report.error("Association matrix is not symmetric")

    # Check diagonal
    diag = np.diag(matrix)
    if np.any(np.abs(diag) > 1e-10):
        report.warn("Association matrix has non-zero diagonal values")

    # Check for NaN/Inf
    n_nan = np.sum(np.isnan(matrix))
    n_inf = np.sum(np.isinf(matrix))
    if n_nan > 0:
        report.error(f"Association matrix contains {n_nan} NaN values")
    if n_inf > 0:
        report.error(f"Association matrix contains {n_inf} Inf values")

    # Check sparsity
    n_nonzero = np.count_nonzero(matrix)
    n_total = matrix.shape[0] * (matrix.shape[0] - 1)  # excluding diagonal
    if n_total > 0:
        density = n_nonzero / n_total
        if density > 0.95:
            report.warn(f"Association matrix very dense ({density:.3f})")
        if density < 0.01 and matrix.shape[0] > 10:
            report.warn(f"Association matrix very sparse ({density:.3f})")

    return report


def compare_rendered_images(
    reference_image: str | Path,
    candidate_image: str | Path,
) -> VisualRegressionReport:
    """
    Compare two rendered graph images using optional SSIM and perceptual hash.

    Returns available metrics without failing when optional dependencies
    are missing; warnings explain what could not be computed.
    """
    report = VisualRegressionReport()
    ref_path = Path(reference_image)
    cand_path = Path(candidate_image)

    if not ref_path.exists():
        report.warnings.append(f"Reference image not found: {ref_path}")
        return report
    if not cand_path.exists():
        report.warnings.append(f"Candidate image not found: {cand_path}")
        return report

    if Image is None:
        report.warnings.append("Pillow is not available; visual comparison skipped.")
        return report

    with Image.open(ref_path) as ref_img, Image.open(cand_path) as cand_img:
        ref_rgb = ref_img.convert("RGB")
        cand_rgb = cand_img.convert("RGB")

        if imagehash is None:
            report.warnings.append("ImageHash is not available; pHash distance skipped.")
        else:
            report.phash_distance = int(
                imagehash.phash(ref_rgb) - imagehash.phash(cand_rgb)
            )

        if structural_similarity is None:
            report.warnings.append("scikit-image is not available; SSIM skipped.")
        else:
            ref_gray = np.asarray(ref_rgb.convert("L"))
            cand_gray = np.asarray(cand_rgb.convert("L"))
            if ref_gray.shape != cand_gray.shape:
                report.warnings.append(
                    f"Image shapes differ ({ref_gray.shape} vs {cand_gray.shape}); SSIM skipped."
                )
            else:
                report.ssim = float(structural_similarity(ref_gray, cand_gray))

    return report
