"""CHD installed-path resolution tests."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chd_reinert import CHDResult


def _make_result(**overrides) -> CHDResult:
    defaults = dict(
        n_classes=3,
        profiles={1: [("term1", 5.0, 10, 50.0, "+")]},
        class_sizes={1: 10},
    )
    defaults.update(overrides)
    return CHDResult(**defaults)


def test_dendrogram_path_is_primary_visual_path(tmp_path):
    dendrogram = tmp_path / "dendrogramme.png"
    result = _make_result(dendrogram_path=dendrogram)
    assert result.dendrogram_path == dendrogram


def test_profile_afc_path_is_independent_from_afc_graph_path(tmp_path):
    afc_graph = tmp_path / "afc_graph.png"
    profile_afc = tmp_path / "chd_profiles_afc.png"
    result = _make_result(afc_graph_path=afc_graph, profile_afc_path=profile_afc)
    assert result.afc_graph_path == afc_graph
    assert result.profile_afc_path == profile_afc


def test_chd_result_has_no_publication_aliases():
    result = _make_result()
    assert not hasattr(result, "publication_dendrogram_path")
    assert not hasattr(result, "polished_dendrogram_path")
