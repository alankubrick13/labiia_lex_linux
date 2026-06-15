"""Structural parity checks against the installed LabiiaLex CHD contract."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chd_reinert import CHDAnalysis, CHDResult
from src.core.config_manager import ConfigManager


def test_chd_defaults_match_installed_baseline():
    defaults = ConfigManager.DEFAULT_ANALYSIS_DEFAULTS["chd"]
    assert defaults["n_classes"] == 5
    # min_classes is a FLOOR (degenerate guard), not the target. The installed
    # baseline ran with no explicit min_classes and nbcl_p1=10; coupling the
    # floor to the target was the WIP regression that broke the dense AFC.
    assert defaults["min_classes"] == 2
    assert defaults["nbcl_p1"] == 10
    assert defaults["use_native_chd"] is True
    assert defaults["native_fallback_legacy"] is True
    assert defaults["strict_iramuteq_clone"] is True
    assert "parity_profile" not in defaults
    assert "render_profile" not in defaults


def test_chd_runtime_defaults_match_installed_baseline():
    defaults = CHDAnalysis.DEFAULT_PARAMS
    assert defaults["nb_classes"] == 5
    # Floor of 2 + phase-1 over-segmentation of 10 (IRaMuTeQ convention).
    assert defaults["min_classes"] == 2
    assert defaults["nbcl_p1"] == 10
    assert defaults["native_fallback_legacy"] is True
    assert defaults["width"] == 1400
    assert defaults["height"] == 1000
    assert "parity_profile" not in defaults
    assert "render_profile" not in defaults


def test_chd_result_has_no_publication_contract():
    field_names = set(CHDResult.__dataclass_fields__.keys())
    assert "publication_dendrogram_path" not in field_names
    assert "tree_source" not in field_names
