"""CHD tree helper tests retained for the simple installed contract."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.analysis.chd_reinert import CHDAnalysis


def _is_valid_newick(s: str) -> bool:
    if not s or not s.strip().endswith(";"):
        return False
    core = s.strip().rstrip(";")
    depth = 0
    for ch in core:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


class TestNewickValidity:
    @pytest.mark.parametrize("newick", [
        "((1,2),3);",
        "(1,2);",
        "((1,2),(3,4));",
    ])
    def test_known_valid_newicks(self, newick):
        assert _is_valid_newick(newick)

    @pytest.mark.parametrize("newick", [
        "((1,2),3)",
        "((1,2),3;",
        "",
        None,
    ])
    def test_known_invalid_newicks(self, newick):
        assert not _is_valid_newick(newick)


class TestBuildBalancedNewick:
    def test_produces_valid_newick(self):
        newick = CHDAnalysis._build_balanced_newick([1, 2, 3, 4])
        assert _is_valid_newick(f"{newick};")
