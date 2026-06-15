"""CHDResult simple contract tests aligned with the installed app."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chd_reinert import CHDResult


def _minimal_result(**overrides) -> CHDResult:
    defaults = dict(
        n_classes=3,
        profiles={
            1: [("term1", 5.0, 10, 50.0, "+")],
            2: [("term2", 3.0, 8, 40.0, "+")],
            3: [("term3", 2.0, 6, 30.0, "+")],
        },
        class_sizes={1: 10, 2: 8, 3: 6},
    )
    defaults.update(overrides)
    return CHDResult(**defaults)


EXPECTED_SIMPLE_FIELDS = [
    "n_classes",
    "profiles",
    "class_sizes",
    "dendrogram_path",
    "contingency_table",
    "profile_afc_path",
    "afc_graph_path",
    "afc_row_coords",
    "afc_col_coords",
    "metadata_profiles_path",
    "typical_segments",
    "antiprofiles",
    "repeated_segments",
    "colored_corpus_path",
    "class_text_paths",
    "newick",
]

REMOVED_PUBLICATION_FIELDS = [
    "polished_dendrogram_path",
    "polished_profile_afc_path",
    "native_dendrogram_path",
    "native_profile_afc_path",
    "publication_dendrogram_path",
    "publication_phylogram_path",
    "publication_profile_afc_path",
    "tree_newick_path",
    "tree_json_path",
    "class_assignments_path",
    "profiles_terms_path",
    "profiles_metadata_path_export",
    "profile_ca_coords_path",
    "artifact_metrics_path",
    "tree_source",
]


def test_chd_result_matches_simple_installed_shape():
    result = _minimal_result()
    for field_name in EXPECTED_SIMPLE_FIELDS:
        assert hasattr(result, field_name), f"missing simple CHD field: {field_name}"


def test_chd_result_does_not_expose_publication_fields():
    result = _minimal_result()
    for field_name in REMOVED_PUBLICATION_FIELDS:
        assert not hasattr(result, field_name), f"unexpected publication field: {field_name}"
