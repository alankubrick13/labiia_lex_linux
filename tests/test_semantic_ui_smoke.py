"""
Smoke tests para a registry e dialogos da Suite Semantica Classica (Task 4).
Garante que a arquitetura da UI esta pronta para receber as analises das Tasks 5-11.
"""

from __future__ import annotations

import pytest

from src.ui.main_window import SEMANTIC_REGISTRY, SemanticAnalysisEntry
from src.ui.dialogs.semantic_analysis_dialogs import (
    YAKEDialog,
    LDADialog,
    AssociativeHeatmapDialog,
    ThematicMapDialog,
    ThematicCHDDialog,
)


class TestSemanticRegistrySmoke:

    def test_registry_has_all_entries(self):
        """Registry deve conter apenas as analises semanticas ativas."""
        expected_keys = {
            "yake", "lda", "associative_heatmap", "thematic_map", "thematic_chd"
        }
        assert set(SEMANTIC_REGISTRY.keys()) == expected_keys

    @pytest.mark.parametrize("key,expected_class,expected_image,expected_table,fallback", [
        ("yake", YAKEDialog, "yake_ranking.png", "yake_keyphrases.csv", None),
        ("lda", LDADialog, "lda_distribution.png", "lda_terms_beta.csv", None),
        ("associative_heatmap", AssociativeHeatmapDialog, "heatmap.png", "association_matrix.csv", "heatmap"),
        ("thematic_map", ThematicMapDialog, "strategic_map.png", "thematic_communities.csv", None),
        ("thematic_chd", ThematicCHDDialog, "thematic_chd_class_topic_heatmap.png", "class_topic_mix.csv", None),
    ])
    def test_registry_entry_contracts(self, key, expected_class, expected_image, expected_table, fallback):
        """As entradas da registry devem estar corretamente tipadas e mapeadas."""
        entry = SEMANTIC_REGISTRY[key]
        assert isinstance(entry, SemanticAnalysisEntry)
        assert entry.analysis_type == key
        assert entry.dialog_class is expected_class
        assert entry.primary_image_field == expected_image
        assert entry.primary_table_field == expected_table
        assert entry.legacy_fallback_analysis_type == fallback

    def test_heatmap_fallback_presenced(self):
        """Heatmap Associativo tem compatibilidade legada com a view antiga."""
        heatmap_entry = SEMANTIC_REGISTRY["associative_heatmap"]
        assert heatmap_entry.legacy_fallback_analysis_type == "heatmap"

    def test_runner_factory_is_callable(self):
        for entry in SEMANTIC_REGISTRY.values():
            assert callable(entry.runner_factory)
            assert callable(entry.history_metadata_adapter)

    def test_lda_dialog_declares_help_for_all_visible_options(self):
        expected = {
            "k",
            "method",
            "seed",
            "min_freq",
            "max_features",
            "n_iter",
            "gibbs_burnin",
            "gibbs_iter",
            "gibbs_thin",
            "enable_k_tuning",
            "k_range",
            "use_lemmas",
            "enable_advanced_diagnostics",
            "stability_n_seeds",
        }

        assert expected.issubset(set(LDADialog.HELP_TEXTS))
        assert all(str(LDADialog.HELP_TEXTS[key]).strip() for key in expected)
