"""ConfigManager coverage for network_text defaults and legacy sanitization."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_manager import ConfigManager


def test_network_text_defaults_are_explicit():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = ConfigManager(config_path=Path(tmpdir) / "config.json")
        defaults = cfg.get_analysis_defaults("network_text")
        assert defaults["layout_backend"] == "gephi_java"
        assert defaults["strict_layout_backend"] is True
        assert defaults["auto_tune"] is True
        assert defaults["stopword_policy"] == "aggressive_pt"
        assert defaults["strict_stopword_filter"] is True
        assert defaults["fa2_iterations"] == 3000
        assert defaults["label_hide_overlap"] is True
        assert defaults["label_max_count"] >= 20
        assert defaults["render_quality_auto"] is True
        assert defaults["render_quality_passes"] >= 1
        assert defaults["label_overlap_target"] > 0
        assert defaults["edge_use_community_color"] is True
        assert defaults["auto_reconnect_components"] is True
        assert defaults["peripheral_enrichment"] is True
        assert defaults["peripheral_min_degree"] >= 1
        assert defaults["peripheral_quantile"] > 0
        assert defaults["label_anchor_lines"] is True
        assert defaults["edge_min_alpha"] > 0
        assert defaults["width"] >= 3200
        assert defaults["height"] >= 2200
        assert defaults["dpi"] >= 240
        assert defaults["view_trim_quantile"] == 0.05
        assert defaults["view_pad_ratio_initial"] == 0.06
        assert defaults["view_pad_ratio_final"] == 0.03
        assert defaults["label_size_boost"] == 3.0


def test_network_text_export_defaults_include_net_flag():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = ConfigManager(config_path=Path(tmpdir) / "config.json")
        defaults = cfg.get_analysis_defaults("network_text")
        assert defaults["export_gexf"] is True
        assert defaults["export_csv"] is True
        assert defaults["export_net"] is False


def test_network_text_legacy_keys_are_sanitized():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "analysis_defaults": {
                        "network_text": {
                            "label_adjust_enabled": False,
                            "fa2_scaling": 9999,
                            "stopword_policy": "unknown_policy",
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        cfg = ConfigManager(config_path=cfg_path)
        defaults = cfg.get_analysis_defaults("network_text")
        assert "label_adjust_enabled" not in defaults
        assert defaults["label_adjust"] is False
        assert defaults["fa2_scaling"] <= 150.0
        assert defaults["stopword_policy"] == "aggressive_pt"
        assert defaults["layout_backend"] == "gephi_java"


def test_network_text_legacy_render_size_is_migrated_to_modern_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "analysis_defaults": {
                        "network_text": {
                            "width": 1600,
                            "height": 1200,
                            "dpi": 200,
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg = ConfigManager(config_path=cfg_path)
        defaults = cfg.get_analysis_defaults("network_text")
        assert defaults["width"] == 3200
        assert defaults["height"] == 2200
        assert defaults["dpi"] == 240
        assert defaults["view_trim_quantile"] == 0.05
        assert defaults["view_pad_ratio_initial"] == 0.06
        assert defaults["view_pad_ratio_final"] == 0.03
        assert defaults["label_size_boost"] == 3.0


def test_similarity_defaults_keep_iramuteq_clone_profile():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = ConfigManager(config_path=Path(tmpdir) / "config.json")
        defaults = cfg.get_analysis_defaults("similarity")
        assert defaults["use_lemmas"] is True
        assert defaults["active_only"] is True
        assert defaults["renderer_backend"] == "iramuteq_r"
        assert defaults["strict_iramuteq_style"] is True
        assert defaults["analysis_mode"] == "strict"
        assert defaults["parity_profile"] == "official_0_8a7"
        assert defaults["render_profile"] == "native"
        assert defaults["show_halo"] is False
        assert defaults["show_edge_labels"] is False
        assert defaults["selected_words"] == []


def test_similarity_renderer_backend_is_sanitized():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "analysis_defaults": {
                        "similarity": {
                            "renderer_backend": "unknown_backend",
                            "use_lemmas": False,
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg = ConfigManager(config_path=cfg_path)
        defaults = cfg.get_analysis_defaults("similarity")
        assert defaults["renderer_backend"] == "iramuteq_r"
        assert defaults["use_lemmas"] is False


def test_similarity_strict_mode_overrides_legacy_visual_noise():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "analysis_defaults": {
                        "similarity": {
                            "show_halo": True,
                            "show_edge_labels": True,
                            "detect_communities": True,
                            "strict_iramuteq_style": True,
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg = ConfigManager(config_path=cfg_path)
        defaults = cfg.get_analysis_defaults("similarity")
        assert defaults["detect_communities"] is False
        assert defaults["show_halo"] is False
        assert defaults["show_edge_labels"] is False


def test_similarity_defaults_drop_stale_selected_words_without_explicit_opt_in():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "analysis_defaults": {
                        "similarity": {
                            "selected_words": ["hermes", "midiatizacao"],
                            "strict_iramuteq_style": True,
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg = ConfigManager(config_path=cfg_path)
        defaults = cfg.get_analysis_defaults("similarity")
        assert defaults["selected_words"] == []
        assert defaults["selected_words_explicit"] is False


def test_official_native_profiles_use_canonical_dimensions_without_overwriting_explicit_sizes():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = ConfigManager(config_path=Path(tmpdir) / "config.json")

        cfg.set_analysis_defaults(
            "similarity",
            {"parity_profile": "official_0_8a7", "render_profile": "native"},
        )
        similarity = cfg.get_analysis_defaults("similarity")
        assert similarity["width"] == 1000
        assert similarity["height"] == 1000

        cfg.set_analysis_defaults(
            "chd",
            {"parity_profile": "official_0_8a7", "render_profile": "native"},
        )
        chd = cfg.get_analysis_defaults("chd")
        assert chd["strict_iramuteq_clone"] is True
        assert chd["tailleuc1"] == 12
        assert chd["tailleuc2"] == 14

        cfg.set_analysis_defaults(
            "similarity",
            {
                "parity_profile": "official_0_8a7",
                "render_profile": "native",
                "width": 1234,
                "height": 987,
            },
        )
        explicit_similarity = cfg.get_analysis_defaults("similarity")
        assert explicit_similarity["width"] == 1234
        assert explicit_similarity["height"] == 987


def test_voyant_defaults_and_feature_flag_are_sanitized():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "features": {"voyant_suite": {"enabled": 0}},
                    "analysis_defaults": {
                        "voyant_suite": {
                            "bins": 999,
                            "context": -2,
                            "mode": "invalid_mode",
                            "min_freq": -1,
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg = ConfigManager(config_path=cfg_path)

        assert cfg.is_feature_enabled("voyant_suite", default=True) is False

        defaults = cfg.get_analysis_defaults("voyant_suite")
        assert defaults["bins"] <= 30
        assert defaults["context"] >= 2
        assert defaults["min_freq"] >= 1
        assert defaults["mode"] == "top"


def test_wordcloud_last_params_do_not_override_global_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg = ConfigManager(config_path=cfg_path)
        cfg.set_last_analysis_params(
            "wordcloud",
            {
                "colors": "Set1",
                "shape": "square",
                "sizing_mode": "height",
                "eccentricity": 1.0,
                "max_words": 2400,
            },
        )
        cfg.save()

        cfg2 = ConfigManager(config_path=cfg_path)
        defaults = cfg2.get_analysis_defaults("wordcloud")
        last_params = cfg2.get_last_analysis_params("wordcloud", include_defaults=False)

        assert defaults["colors"] == "Dark2"
        assert defaults["shape"] == "square"
        assert defaults["sizing_mode"] == "area"
        assert defaults["eccentricity"] == 0.65
        assert last_params["colors"] == "Set1"
        assert last_params["shape"] == "square"
        assert last_params["max_words"] == 2000


def test_wordcloud_migration_is_one_shot_and_preserves_visual_choices():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "analysis_defaults": {
                        "wordcloud": {
                            "max_words": 80,
                            "min_freq": 5,
                            "colors": "Pastel1",
                            "shape": "triangle-forward",
                            "sizing_mode": "height",
                            "eccentricity": 0.35,
                        }
                    },
                    "last_analysis_params": {
                        "wordcloud": {
                            "max_words": 80,
                            "min_freq": 5,
                            "colors": "Pastel1",
                            "shape": "triangle-forward",
                            "sizing_mode": "height",
                            "eccentricity": 0.35,
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg = ConfigManager(config_path=cfg_path)
        defaults = cfg.get_analysis_defaults("wordcloud")
        last_params = cfg.get_last_analysis_params("wordcloud", include_defaults=False)

        assert defaults["colors"] == "Pastel1"
        assert defaults["shape"] == "triangle-forward"
        assert defaults["sizing_mode"] == "height"
        assert defaults["eccentricity"] == 0.35
        assert last_params["colors"] == "Pastel1"
        assert last_params["shape"] == "triangle-forward"
        assert last_params["sizing_mode"] == "height"
        assert last_params["eccentricity"] == 0.35
        assert cfg.get("migrations", {}).get("wordcloud_v2_applied") is True

        # Depois da migração, escolhas novas do usuário não devem ser reescritas.
        cfg.set_last_analysis_params(
            "wordcloud",
            {
                "colors": "Pastel1",
                "shape": "triangle-forward",
                "sizing_mode": "height",
                "eccentricity": 0.35,
            },
        )
        cfg.save()

        cfg2 = ConfigManager(config_path=cfg_path)
        last_after = cfg2.get_last_analysis_params("wordcloud", include_defaults=False)
        defaults_after = cfg2.get_analysis_defaults("wordcloud")
        assert last_after["colors"] == "Pastel1"
        assert last_after["shape"] == "triangle-forward"
        assert defaults_after["colors"] == "Pastel1"
