"""Fix B — coerência n1 / Contout / clnb no pós-processamento CHD.

Cobre os helpers puros (sem R):
- _write_n1_from_ucecl gera n1 com classes 1..clnb alinhadas às colunas de Contout;
- _validate_n1_consistency falha quando n1 e clnb divergem (causa do AFC em branco);
- _clear_stale_iramuteq_artifacts remove só artefatos da família IRaMuTeQ.

Ver planejamentofable.md, Fase 2.
"""

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.chd_reinert import CHDAnalysis, CHDAnalysisError


class _StubCHD(CHDAnalysis):
    """Bypass __init__ to exercise pure helpers with a controlled output_dir."""

    def __init__(self, output_dir):
        import logging

        self.output_dir = Path(output_dir)
        self._logger = logging.getLogger("test_chd_coherence")


def _read_n1(path):
    classes = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader, None)
        for row in reader:
            if row:
                classes.append(int(row[-1]))
    return classes


def test_write_n1_from_ucecl_relabels_to_contiguous_classes(tmp_path):
    chd = _StubCHD(tmp_path)
    n1 = tmp_path / "n1.csv"
    # ucecl: class positions 1,2,3 with arbitrary uce ids
    ucecl = [[10, 11], [20], [30, 31, 32]]
    chd._write_n1_from_ucecl(n1, ucecl, sorted_class_ids=[1, 2, 3])
    classes = _read_n1(n1)
    assert sorted(set(classes)) == [1, 2, 3]
    assert classes.count(1) == 2
    assert classes.count(2) == 1
    assert classes.count(3) == 3
    assert len(classes) == 6  # total UCEs


def test_validate_n1_consistency_passes_when_aligned(tmp_path):
    chd = _StubCHD(tmp_path)
    n1 = tmp_path / "n1.csv"
    ucecl = [[1, 2], [3, 4], [5]]
    chd._write_n1_from_ucecl(n1, ucecl, sorted_class_ids=[1, 2, 3])
    # clnb=3 matches; should not raise
    chd._validate_n1_consistency(n1, clnb=3, ucecl=ucecl)


def test_validate_n1_consistency_raises_on_class_mismatch(tmp_path):
    """Stale n1 with 3 classes but Contout expects clnb=5 -> raise."""
    chd = _StubCHD(tmp_path)
    n1 = tmp_path / "n1.csv"
    # n1 has only classes 1,2,3
    ucecl3 = [[1], [2], [3]]
    chd._write_n1_from_ucecl(n1, ucecl3, sorted_class_ids=[1, 2, 3])
    with pytest.raises(CHDAnalysisError) as exc:
        chd._validate_n1_consistency(n1, clnb=5, ucecl=[[1], [2], [3], [4], [5]])
    assert "inconsistente" in (exc.value.what or "").lower()


def test_validate_n1_consistency_raises_on_row_count_mismatch(tmp_path):
    chd = _StubCHD(tmp_path)
    n1 = tmp_path / "n1.csv"
    ucecl = [[1, 2], [3, 4], [5]]  # 5 UCEs
    chd._write_n1_from_ucecl(n1, ucecl, sorted_class_ids=[1, 2, 3])
    # same classes (1..3) but a different UCE count
    with pytest.raises(CHDAnalysisError):
        chd._validate_n1_consistency(n1, clnb=3, ucecl=[[1, 2], [3, 4], [5, 6, 7]])


def test_native_n1_with_class_zero_rows_is_accepted(tmp_path):
    """Regression for the real-corpus run of 2026-06-12: the NATIVE n1.csv keeps
    class-0 (unclassified) rows, so its row count never matches ucecl (which has
    classified UCEs only). With check_row_count=False it must validate fine —
    rejecting it sent a perfectly good 5-class native run into the ported
    fallback and the overlapped matplotlib AFC."""
    import csv as _csv

    chd = _StubCHD(tmp_path)
    n1 = tmp_path / "n1.csv"
    # Mimic the native file: 12 rows, classes {0,0,0, 1,1, 2,2, 3,3, 4,4, 5}
    rows = [0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5]
    with n1.open("w", encoding="utf-8", newline="") as f:
        writer = _csv.writer(f, delimiter=";")
        writer.writerow(["", "V1"])
        for idx, cls in enumerate(rows, start=1):
            writer.writerow([idx, cls])

    # ucecl holds only the 9 classified UCEs (12 rows - 3 class-0).
    ucecl = [[10, 11], [20, 21], [30, 31], [40, 41], [50]]

    # Native path (check_row_count=False): must NOT raise.
    chd._validate_n1_consistency(n1, clnb=5, ucecl=ucecl, check_row_count=False)

    # And the class-set guard still works on the native path: a stale n1 with
    # only 3 classes against clnb=5 keeps raising even without the row check.
    with n1.open("w", encoding="utf-8", newline="") as f:
        writer = _csv.writer(f, delimiter=";")
        writer.writerow(["", "V1"])
        for idx, cls in enumerate([0, 1, 1, 2, 2, 3], start=1):
            writer.writerow([idx, cls])
    with pytest.raises(CHDAnalysisError):
        chd._validate_n1_consistency(n1, clnb=5, ucecl=ucecl, check_row_count=False)


def test_clear_stale_artifacts_removes_only_family(tmp_path):
    chd = _StubCHD(tmp_path)
    # IRaMuTeQ family (should be removed)
    removed = ["n1.csv", "Contout.csv", "chistable.csv", "afc_row.csv",
               "eigenvalues.csv", "RData.RData", "AFC2DL.png",
               "AFC2DL.png_notplotted.csv", "afc2dl_error.txt"]
    # Unrelated inputs/files (must be kept)
    kept = ["TableUc1.csv", "listuce1.csv", "chd_script.R", "manifest.json"]
    for name in removed + kept:
        (tmp_path / name).write_text("x", encoding="utf-8")

    chd._clear_stale_iramuteq_artifacts()

    for name in removed:
        assert not (tmp_path / name).exists(), f"{name} deveria ter sido removido"
    for name in kept:
        assert (tmp_path / name).exists(), f"{name} não deveria ser removido"


def test_clear_stale_artifacts_is_safe_when_missing(tmp_path):
    chd = _StubCHD(tmp_path)
    # No files present — must not raise
    chd._clear_stale_iramuteq_artifacts()
