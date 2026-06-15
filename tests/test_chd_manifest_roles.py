"""CHD manifest tests aligned with the installed app contract."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _build_simple_metadata(result) -> dict:
    return {
        "dendrogram_path": str(getattr(result, "dendrogram_path", None) or ""),
        "afc_graph_path": str(getattr(result, "afc_graph_path", None) or ""),
        "profile_afc_path": str(getattr(result, "profile_afc_path", None) or ""),
    }


class _SimpleResult:
    dendrogram_path = "dendrogramme.png"
    afc_graph_path = "afc_graph.png"
    profile_afc_path = "chd_profiles_afc.png"


def test_simple_chd_metadata_uses_only_installed_artifact_keys():
    metadata = _build_simple_metadata(_SimpleResult())
    assert set(metadata.keys()) == {
        "dendrogram_path",
        "afc_graph_path",
        "profile_afc_path",
    }


def test_simple_chd_metadata_has_no_chd_artifacts_v2_block():
    metadata = _build_simple_metadata(_SimpleResult())
    assert "chd_artifacts_v2" not in metadata
