"""JSON configuration manager for LabiiaLex."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .iramuteq_defaults import (
    LEGACY_PARITY_PROFILE,
    LEGACY_RENDER_PROFILE,
    OFFICIAL_PARITY_PROFILE,
    OFFICIAL_RENDER_PROFILE,
    official_defaults_for,
)
from ..utils.logger import get_logger
from ..utils.paths import PathManager

_OFFICIAL_SIMILARITY_DEFAULTS = official_defaults_for("similarity")
class ConfigManager:
    """
    Manage LabiiaLex configuration persisted as JSON.
    """

    DEFAULT_ANALYSIS_DEFAULTS: Dict[str, Dict[str, Any]] = {
        "chd": {
            "analysis_mode": "strict",
            "n_classes": 5,
            "min_classes": 2,
            "min_freq": 2,
            "method": "ward.D2",
            "classif_mode": 1,
            "tailleuc1": 12,
            "tailleuc2": 14,
            "max_actives": 20000,
            "stopword_policy": "aggressive_pt",
            "strict_stopword_filter": True,
            "use_native_chd": True,
            "native_fallback_legacy": True,
            "strict_iramuteq_clone": True,
            "nbcl_p1": 10,
            "svd_method": "irlba",
            "auto_expand_actives": True,
            "min_actives_floor": 300,
            "prefer_readable_afc_profiles": False,
            "min_visible_words": 120,
            "nb_per_class": 80,
            "max_words": 600,
        },
        "similarity": {
            "analysis_mode": "strict",
            "parity_profile": OFFICIAL_PARITY_PROFILE,
            "render_profile": OFFICIAL_RENDER_PROFILE,
            "layout": str(_OFFICIAL_SIMILARITY_DEFAULTS.get("layout", "frutch")),
            "min_freq": int(_OFFICIAL_SIMILARITY_DEFAULTS.get("min_freq", 3)),
            "use_lemmas": True,
            "active_only": True,
            "coefficient": int(_OFFICIAL_SIMILARITY_DEFAULTS.get("coefficient", 0)),
            "min_edge": 0,
            "vertex_scaling": "frequency",
            "grayscale": False,
            "arbremax": bool(_OFFICIAL_SIMILARITY_DEFAULTS.get("arbremax", True)),
            "detect_communities": False,
            "community_method": "edge_betweenness",
            "show_halo": False,
            "show_edge_labels": False,
            "cexalpha": False,
            "strict_iramuteq_style": True,
            "typegraph": "png",
            "max_words": 50,
            "gexf_output": "",
            "renderer_backend": "iramuteq_r",
            "width": int(_OFFICIAL_SIMILARITY_DEFAULTS.get("width", 1000)),
            "height": int(_OFFICIAL_SIMILARITY_DEFAULTS.get("height", 1000)),
            "selected_words": [],
            "selected_words_explicit": False,
        },
        "wordcloud": {
            "max_words": 100,
            "min_freq": 3,
            "colors": "Dark2",
            "active_only": True,
            "use_lemmas": True,
            "shape": "square",
            "sizing_mode": "area",
            "eccentricity": 0.65,
            "scale_max": 28,
            "grid_size": 4,
            "max_steps": 60,
            "typegraph": "png",
        },
        "specificities": {
            "index_type": "chi2",
            "min_freq": 3,
            "gram_type": 0,
            "metadata_tokens": [],
            "run_afc": False,
            "backend": "python",
            "allow_python_fallback": True,
            "generate_plot": True,
            "plot_top_n": 30,
            "plot_bw": False,
            "plot_width": 1200,
            "plot_height": 800,
            "plot_typegraph": "png",
        },
        "concordance": {
            "context_size": 50,
            "regex": False,
        },
        "prototypical": {
            "freq_threshold": 5,
            "rank_threshold": 2.5,
        },
        "labbe": {
            "min_freq": 3,
        },
        "keyness_extra": {
            "variable": "",
            "target_value": "",
            "min_freq": 3,
            "top_n": 20,
            "measure": "lr",
            "remove_stopwords": True,
        },
        "bigram_network_extra": {
            "min_bigram_freq": 2,
            "top_edges": 120,
        },
        "word_tree_extra": {
            "keyword": "",
            "min_freq": 3,
            "max_depth": 4,
            "min_branch_freq": 2,
            "top_branches": 120,
            "use_lemmas": True,
            "active_only": True,
        },
        "wordfish_extra": {
            "group_variable": "",
            "min_freq": 3,
            "max_features": 1200,
        },
        "xray_extra": {
            "patterns": "",
            "max_docs": 200,
        },
        "sentiment_extra": {
            "with_timeline": True,
            "top_words": 25,
        },
        "matrix_frequency": {
            "columns": [],
            "top_n": 50,
            "typegraph": "png",
        },
        "matrix_chi2": {
            "row_var": "",
            "col_var": "",
            "typegraph": "png",
        },
        "matrix_afc": {
            "n_dim": 2,
            "typegraph": "png",
        },
        "matrix_chd": {
            "nb_classes": 5,
            "method": "ward.D2",
            "typegraph": "png",
        },
        "matrix_similarity": {
            "layout": "frutch",
            "min_edge": 0,
            "grayscale": False,
            "arbremax": True,
            "detect_communities": False,
            "community_method": "edge_betweenness",
            "typegraph": "png",
        },
        "network_text": {
            "layout": "forceatlas2",
            "layout_backend": "gephi_java",
            "strict_layout_backend": True,
            "auto_tune": True,
            "min_freq": 3,
            "window_size": 5,
            "min_cooc": 2,
            "max_nodes": 300,
            "active_only": True,
            "stopword_policy": "aggressive_pt",
            "strict_stopword_filter": True,
            "fa2_gravity": 0.8,
            "fa2_scaling": 50.0,
            "fa2_iterations": 3000,
            "noverlap_enabled": True,
            "label_adjust": True,
            "edge_weight_quantile": 0.0,
            "candidate_min_cooc": 1.0,
            "show_nodes": False,
            "edge_use_community_color": True,
            "auto_reconnect_components": True,
            "auto_reconnect_max_bridges": 16,
            "peripheral_enrichment": True,
            "peripheral_min_degree": 2,
            "peripheral_quantile": 0.55,
            "peripheral_boost_max_added": 180,
            "label_density": 0.35,
            "label_max_count": 80,
            "label_hide_overlap": True,
            "label_min_keep": 8,
            "label_size_gamma": 1.2,
            "label_size_boost": 3.0,
            "label_overlap_target": 0.16,
            "label_anchor_lines": True,
            "label_anchor_line_alpha": 0.38,
            "label_anchor_line_width": 0.62,
            "render_quality_auto": True,
            "render_quality_passes": 3,
            "width": 3200,
            "height": 2200,
            "dpi": 240,
            "view_trim_quantile": 0.05,
            "view_pad_ratio_initial": 0.06,
            "view_pad_ratio_final": 0.03,
            "edge_min_alpha": 0.13,
            "edge_min_width": 0.34,
            "edge_max_width": 1.4,
            "export_gexf": True,
            "export_csv": True,
            "export_net": False,
        },
        "voyant_suite": {
            "query": "",
            "num_initial_terms": 20,
            "context": 5,
            "bins": 10,
            "max_docs": 50,
            "min_freq": 2,
            "use_lemmas": True,
            "active_only": True,
            "remove_stopwords": True,
            "max_context_rows": 800,
            "mode": "top",
        },
    }

    DEFAULT_CONFIG: Dict[str, Any] = {
        "r_path": "",
        "cran_mirror": "https://cloud.r-project.org",
        "language": "portuguese",
        "analysis_mode": "strict",
        "theme": "light",
        "ui": {
            "v2_enabled": True,
            "v2_scope": ["shell", "results", "feedback"],
            "shell_version": "modern_academic_v1",
            "nav_collapsed": False,
            "density": "comfortable",
            "table_row_mode": "comfortable",
            "enable_compact_toolbar": False,
        },
        "uce_size": 40,
        "features": {
            "voyant_suite": {
                "enabled": True,
            },
        },
        "custom_stopwords_global": [],
        "analysis_defaults": DEFAULT_ANALYSIS_DEFAULTS,
        "last_analysis_params": {},
        "migrations": {},
    }

    def __init__(self, config_path: Optional[Union[str, Path]] = None) -> None:
        """
        Initialize the configuration manager.

        Args:
            config_path: Optional path to the JSON config file.
        """
        self._logger = get_logger(__name__)
        if config_path:
            self._config_path = Path(config_path)
        else:
            if PathManager.is_frozen():
                self._config_path = PathManager.user_data_dir() / "config.json"
            else:
                self._config_path = PathManager.project_root() / "config.json"
        self._data: Dict[str, Any] = {}
        self.load()

    @property
    def path(self) -> Path:
        """
        Return the current configuration file path.

        Returns:
            Path to the configuration JSON file.
        """
        return self._config_path

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from disk or defaults if missing.

        Returns:
            Configuration dictionary.
        """
        if self._config_path.is_file():
            try:
                with self._config_path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                if not isinstance(data, dict):
                    raise ValueError("Config JSON invalido: raiz nao e objeto")
                self._data = self._deep_merge_dicts(self._build_default_config(), data)
                self._sanitize_loaded_config()
            except (json.JSONDecodeError, OSError) as exc:
                self._logger.error(
                    "Falha ao ler config JSON. Usando defaults. Erro tecnico: %s", exc
                )
                self._data = self._build_default_config()
            except ValueError as exc:
                self._logger.error("%s. Usando defaults.", exc)
                self._data = self._build_default_config()
        else:
            self._data = self._build_default_config()

        return self._data

    def save(self) -> None:
        """
        Persist configuration to disk as JSON.
        """
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with self._config_path.open("w", encoding="utf-8") as file:
                json.dump(self._data, file, indent=2, ensure_ascii=False)
        except OSError as exc:
            self._logger.error("Falha ao salvar config JSON: %s", exc)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: Configuration key.
            default: Default value if key is missing.

        Returns:
            Configuration value or default.
        """
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value in memory.

        Args:
            key: Configuration key.
            value: Value to assign.
        """
        self._data[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        """
        Update multiple configuration values.

        Args:
            values: Dictionary of values to merge.
        """
        self._data.update(values)

    def is_feature_enabled(self, feature_key: str, default: bool = True) -> bool:
        """
        Resolve feature flags from config using dot-notation keys.

        Example:
            feature_key="voyant_suite" -> features.voyant_suite.enabled
            feature_key="voyant_suite.enabled" -> features.voyant_suite.enabled
        """
        tokens = [token for token in str(feature_key or "").split(".") if token]
        if not tokens:
            return bool(default)

        if tokens[-1].lower() != "enabled":
            tokens.append("enabled")

        current: Any = self._data.get("features", {})
        for token in tokens:
            if not isinstance(current, dict):
                return bool(default)
            if token not in current:
                return bool(default)
            current = current.get(token)
        return bool(current)

    def get_analysis_defaults(self, analysis_type: str) -> Dict[str, Any]:
        """
        Return default parameters for one analysis type.

        Args:
            analysis_type: Analysis key (e.g., "chd", "matrix_afc").

        Returns:
            Merged defaults for the requested analysis.
        """
        analysis_key = str(analysis_type or "").strip().lower()
        defaults = copy.deepcopy(
            self.DEFAULT_ANALYSIS_DEFAULTS.get(analysis_key, {})
        )
        configured = (
            self._data.get("analysis_defaults", {}).get(analysis_key, {})
            if isinstance(self._data.get("analysis_defaults"), dict)
            else {}
        )
        if isinstance(configured, dict):
            defaults.update(configured)
        defaults = self._sanitize_analysis_params(analysis_key, defaults)
        return defaults

    def set_analysis_defaults(self, analysis_type: str, params: Dict[str, Any]) -> None:
        """
        Persist custom default parameters for one analysis type.

        Args:
            analysis_type: Analysis key (e.g., "chd", "matrix_afc").
            params: Parameters to store as defaults.
        """
        analysis_key = str(analysis_type or "").strip().lower()
        if not analysis_key:
            return
        if not isinstance(self._data.get("analysis_defaults"), dict):
            self._data["analysis_defaults"] = {}
        sanitized = self._sanitize_analysis_params(analysis_key, params or {})
        self._data["analysis_defaults"][analysis_key] = self._to_json_compatible(sanitized)

    def get_last_analysis_params(
        self,
        analysis_type: str,
        include_defaults: bool = True,
    ) -> Dict[str, Any]:
        """
        Return last used parameters for one analysis.

        Args:
            analysis_type: Analysis key.
            include_defaults: Merge with defaults when True.

        Returns:
            Parameters dictionary.
        """
        analysis_key = str(analysis_type or "").strip().lower()
        params: Dict[str, Any] = {}
        if include_defaults:
            params.update(self.get_analysis_defaults(analysis_key))

        last_params_store = self._data.get("last_analysis_params", {})
        if isinstance(last_params_store, dict):
            saved = last_params_store.get(analysis_key, {})
            if isinstance(saved, dict):
                params.update(saved)
        params = self._sanitize_analysis_params(analysis_key, params)
        return params

    def set_last_analysis_params(self, analysis_type: str, params: Dict[str, Any]) -> None:
        """
        Persist last used parameters for one analysis.

        Args:
            analysis_type: Analysis key.
            params: Parameters used in the latest execution.
        """
        analysis_key = str(analysis_type or "").strip().lower()
        if not analysis_key:
            return
        if not isinstance(self._data.get("last_analysis_params"), dict):
            self._data["last_analysis_params"] = {}

        sanitized = self._sanitize_analysis_params(analysis_key, params or {})
        normalized = self._to_json_compatible(sanitized)
        self._data["last_analysis_params"][analysis_key] = normalized
        if analysis_key == "wordcloud":
            migrations = self._data.get("migrations")
            if not isinstance(migrations, dict):
                migrations = {}
                self._data["migrations"] = migrations
            migrations["wordcloud_v2_applied"] = True
        else:
            self.set_analysis_defaults(analysis_key, normalized)

    def as_dict(self) -> Dict[str, Any]:
        """
        Return a shallow copy of the configuration.

        Returns:
            Configuration dictionary copy.
        """
        return dict(self._data)

    @classmethod
    def _build_default_config(cls) -> Dict[str, Any]:
        return {
            "r_path": "",
            "cran_mirror": "https://cloud.r-project.org",
            "language": "portuguese",
            "theme": "light",
            "show_guided_tour_on_startup": True,
            "guided_tour_version_seen": "",
            "ui": {
                "v2_enabled": True,
                "v2_scope": ["shell", "results", "feedback"],
                "shell_version": "modern_academic_v1",
                "nav_collapsed": False,
                "density": "comfortable",
                "table_row_mode": "comfortable",
                "enable_compact_toolbar": False,
            },
            "uce_size": 40,
            "features": {
                "voyant_suite": {
                    "enabled": True,
                },
            },
            "analysis_defaults": copy.deepcopy(cls.DEFAULT_ANALYSIS_DEFAULTS),
            "last_analysis_params": {},
            "migrations": {},
        }

    @classmethod
    def _deep_merge_dicts(cls, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = cls._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    @classmethod
    def _to_json_compatible(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {
                str(key): cls._to_json_compatible(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [cls._to_json_compatible(item) for item in value]
        return str(value)

    def _sanitize_loaded_config(self) -> None:
        # Product policy: PT-BR is the canonical lexical language for analysis.
        self._data["language"] = "portuguese"

        features = self._data.get("features")
        if not isinstance(features, dict):
            features = {}
            self._data["features"] = features
        voyant_features = features.get("voyant_suite")
        if not isinstance(voyant_features, dict):
            voyant_features = {}
            features["voyant_suite"] = voyant_features
        voyant_features["enabled"] = bool(voyant_features.get("enabled", True))

        ui = self._data.get("ui")
        if not isinstance(ui, dict):
            ui = {}
        ui["v2_enabled"] = bool(ui.get("v2_enabled", True))
        raw_scope = ui.get("v2_scope", ["shell", "results", "feedback"])
        allowed_scope = {"shell", "results", "dialogs", "feedback", "icons"}
        if isinstance(raw_scope, (list, tuple, set)):
            scope = [
                str(item).strip().lower()
                for item in raw_scope
                if str(item).strip().lower() in allowed_scope
            ]
        elif isinstance(raw_scope, str):
            parsed = [part.strip().lower() for part in raw_scope.split(",")]
            scope = [item for item in parsed if item in allowed_scope]
        else:
            scope = []
        ui["v2_scope"] = scope or ["shell", "results", "feedback"]
        density = str(ui.get("density", "comfortable") or "comfortable").strip().lower()
        ui["density"] = density if density in {"compact", "comfortable"} else "comfortable"
        row_mode = str(ui.get("table_row_mode", "comfortable") or "comfortable").strip().lower()
        ui["table_row_mode"] = row_mode if row_mode in {"compact", "comfortable"} else "comfortable"
        shell_version = str(ui.get("shell_version", "modern_academic_v1") or "modern_academic_v1").strip().lower()
        ui["shell_version"] = shell_version if shell_version in {"modern_academic_v1"} else "modern_academic_v1"
        ui["nav_collapsed"] = bool(ui.get("nav_collapsed", False))
        ui["enable_compact_toolbar"] = bool(ui.get("enable_compact_toolbar", False))
        self._data["ui"] = ui

        analysis_defaults = self._data.get("analysis_defaults", {})
        if isinstance(analysis_defaults, dict):
            for key, value in list(analysis_defaults.items()):
                if isinstance(value, dict):
                    analysis_defaults[key] = self._sanitize_analysis_params(
                        str(key).strip().lower(),
                        value,
                    )

        last_params = self._data.get("last_analysis_params", {})
        if isinstance(last_params, dict):
            for key, value in list(last_params.items()):
                if isinstance(value, dict):
                    last_params[key] = self._sanitize_analysis_params(
                        str(key).strip().lower(),
                        value,
                    )

        migrations = self._data.get("migrations")
        if not isinstance(migrations, dict):
            migrations = {}
            self._data["migrations"] = migrations
        self._apply_wordcloud_v2_migration()

    def _apply_wordcloud_v2_migration(self) -> None:
        """
        One-shot migration for wordcloud compatibility defaults.

        Historical builds rewrote user-selected visual parameters here.
        That behavior breaks portability when importing projects or moving
        installations to another machine. This migration now only ensures
        sanitized keys and fills missing core fields, preserving valid user
        choices for shape/sizing/colors/eccentricity.
        """
        migrations = self._data.get("migrations")
        if not isinstance(migrations, dict):
            migrations = {}
            self._data["migrations"] = migrations
        if bool(migrations.get("wordcloud_v2_applied", False)):
            return

        targets = ("analysis_defaults", "last_analysis_params")
        for bucket_key in targets:
            bucket = self._data.get(bucket_key)
            if not isinstance(bucket, dict):
                continue
            current = bucket.get("wordcloud")
            if not isinstance(current, dict):
                continue

            normalized = self._sanitize_analysis_params("wordcloud", current)
            missing_core_shape = any(
                key_name not in current
                for key_name in ("shape", "sizing_mode", "eccentricity")
            )
            if missing_core_shape:
                normalized.update(
                    {
                        "colors": "Dark2",
                        "shape": "square",
                        "sizing_mode": "area",
                        "eccentricity": 0.65,
                    }
                )
            bucket["wordcloud"] = self._to_json_compatible(
                self._sanitize_analysis_params("wordcloud", normalized)
            )

        migrations["wordcloud_v2_applied"] = True

    def _sanitize_analysis_params(self, analysis_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        key = str(analysis_key or "").strip().lower()
        if key == "similarity":
            raw = dict(params or {})
            merged = {
                **self.DEFAULT_ANALYSIS_DEFAULTS.get("similarity", {}),
                **raw,
            }
            mode = str(merged.get("analysis_mode", "") or "").strip().lower()
            if "analysis_mode" in raw:
                if mode not in {"strict", "legacy"}:
                    mode = "strict" if bool(merged.get("strict_iramuteq_style", True)) else "legacy"
            elif "strict_iramuteq_style" in raw:
                mode = "strict" if bool(raw.get("strict_iramuteq_style", True)) else "legacy"
            elif mode not in {"strict", "legacy"}:
                mode = "strict" if bool(merged.get("strict_iramuteq_style", True)) else "legacy"
            merged["analysis_mode"] = mode
            if "halo" in raw and "show_halo" not in raw:
                merged["show_halo"] = bool(raw.get("halo"))
            if "label_e" in raw and "show_edge_labels" not in raw:
                merged["show_edge_labels"] = bool(raw.get("label_e"))
            if "com" in raw and "detect_communities" not in raw:
                merged["detect_communities"] = bool(raw.get("com"))
            if "communities" in raw and "community_method" not in raw:
                community_by_idx = {
                    0: "edge_betweenness",
                    1: "fastgreedy",
                    2: "label_propagation",
                    3: "leading_eigenvector",
                    4: "multilevel",
                    5: "optimal",
                    6: "spinglass",
                    7: "walktrap",
                }
                try:
                    idx = int(raw.get("communities"))
                except (TypeError, ValueError):
                    idx = -1
                merged["community_method"] = community_by_idx.get(idx, "edge_betweenness")
            merged["use_lemmas"] = bool(merged.get("use_lemmas", True))
            merged["active_only"] = bool(merged.get("active_only", True))
            merged["arbremax"] = bool(merged.get("arbremax", True))
            merged["detect_communities"] = bool(merged.get("detect_communities", False))
            merged["show_halo"] = bool(merged.get("show_halo", False))
            merged["show_edge_labels"] = bool(merged.get("show_edge_labels", False))
            merged["cexalpha"] = bool(merged.get("cexalpha", False))
            merged["strict_iramuteq_style"] = mode == "strict"
            parity_default = (
                OFFICIAL_PARITY_PROFILE
                if merged["strict_iramuteq_style"]
                else LEGACY_PARITY_PROFILE
            )
            render_default = (
                OFFICIAL_RENDER_PROFILE
                if merged["strict_iramuteq_style"]
                else LEGACY_RENDER_PROFILE
            )
            merged["parity_profile"] = self._normalize_parity_profile(
                merged.get("parity_profile"),
                default=parity_default,
            )
            merged["render_profile"] = self._normalize_render_profile(
                merged.get("render_profile"),
                default=render_default,
            )
            if merged["strict_iramuteq_style"]:
                merged["parity_profile"] = OFFICIAL_PARITY_PROFILE
                merged["render_profile"] = OFFICIAL_RENDER_PROFILE
            renderer_backend = str(merged.get("renderer_backend", "iramuteq_r")).strip().lower()
            if renderer_backend not in {"iramuteq_r", "python"}:
                renderer_backend = "iramuteq_r"
            merged["renderer_backend"] = renderer_backend
            layout = str(merged.get("layout", "frutch")).strip()
            if layout.lower() == "fruchterman":
                layout = "frutch"
            elif layout.lower() == "kamada":
                layout = "kawa"
            elif layout.lower() == "circular":
                layout = "circle"
            if layout not in {"random", "circle", "frutch", "kawa", "graphopt", "spirale", "spirale3D"}:
                layout = "frutch"
            merged["layout"] = layout
            vertex_scaling = str(merged.get("vertex_scaling", "frequency")).strip().lower()
            if vertex_scaling not in {"frequency", "chi2", "degree"}:
                vertex_scaling = "frequency"
            merged["vertex_scaling"] = vertex_scaling
            typegraph = str(merged.get("typegraph", "png")).strip().lower()
            merged["typegraph"] = typegraph if typegraph in {"png", "svg"} else "png"
            merged["min_freq"] = max(1, int(self._to_number(merged.get("min_freq"), 3)))
            merged["min_edge"] = max(0.0, float(self._to_number(merged.get("min_edge"), 0)))
            merged["coefficient"] = self._normalize_similarity_coefficient(merged.get("coefficient"), default=0)
            if (
                merged["parity_profile"] == OFFICIAL_PARITY_PROFILE
                and merged["render_profile"] == OFFICIAL_RENDER_PROFILE
                and "width" not in raw
            ):
                merged["width"] = int(_OFFICIAL_SIMILARITY_DEFAULTS.get("width", 1000))
            if (
                merged["parity_profile"] == OFFICIAL_PARITY_PROFILE
                and merged["render_profile"] == OFFICIAL_RENDER_PROFILE
                and "height" not in raw
            ):
                merged["height"] = int(_OFFICIAL_SIMILARITY_DEFAULTS.get("height", 1000))
            merged["width"] = max(300, int(self._to_number(merged.get("width"), _OFFICIAL_SIMILARITY_DEFAULTS.get("width", 1000))))
            merged["height"] = max(300, int(self._to_number(merged.get("height"), _OFFICIAL_SIMILARITY_DEFAULTS.get("height", 1000))))
            selected_words_raw = merged.get("selected_words")
            if isinstance(selected_words_raw, (list, tuple, set)):
                selected_words = [
                    str(word).strip()
                    for word in selected_words_raw
                    if str(word).strip()
                ]
            else:
                selected_words = []
            merged["selected_words_explicit"] = bool(merged.get("selected_words_explicit", False))
            if merged["strict_iramuteq_style"] and not merged["selected_words_explicit"]:
                selected_words = []
            merged["selected_words"] = list(dict.fromkeys(selected_words))
            if not merged["selected_words"]:
                merged["selected_words_explicit"] = False

            if merged["strict_iramuteq_style"]:
                merged["layout"] = str(_OFFICIAL_SIMILARITY_DEFAULTS.get("layout", "frutch"))
                merged["arbremax"] = bool(_OFFICIAL_SIMILARITY_DEFAULTS.get("arbremax", True))
                merged["detect_communities"] = False
                merged["community_method"] = "edge_betweenness"
                merged["show_halo"] = False
                merged["show_edge_labels"] = False
                merged["cexalpha"] = False
                merged["renderer_backend"] = "iramuteq_r"
                merged["vertex_scaling"] = "frequency"

            if merged["show_halo"]:
                merged["detect_communities"] = True
            if not merged["detect_communities"]:
                merged["show_halo"] = False
            return merged

        if key == "chd":
            merged = {
                **self.DEFAULT_ANALYSIS_DEFAULTS.get("chd", {}),
                **dict(params or {}),
            }
            params_dict = dict(params or {})
            if "nb_classes" in merged and "n_classes" not in merged:
                merged["n_classes"] = merged.get("nb_classes")
            if "svdmethod" in merged and "svd_method" not in merged:
                merged["svd_method"] = merged.get("svdmethod")
            if "strict_iramuteq_style" in merged and "strict_iramuteq_clone" not in merged:
                merged["strict_iramuteq_clone"] = bool(merged.get("strict_iramuteq_style"))
            analysis_mode_explicit = "analysis_mode" in params_dict
            strict_flag_explicit = any(
                key_name in params_dict
                for key_name in ("strict_iramuteq_clone", "strict_iramuteq_style")
            )
            mode = str(merged.get("analysis_mode", "") or "").strip().lower()
            if analysis_mode_explicit:
                if mode not in {"strict", "legacy"}:
                    mode = "strict" if bool(merged.get("strict_iramuteq_clone", True)) else "legacy"
            elif strict_flag_explicit:
                mode = "strict" if bool(merged.get("strict_iramuteq_clone", True)) else "legacy"
            elif mode not in {"strict", "legacy"}:
                mode = "strict" if bool(merged.get("strict_iramuteq_clone", True)) else "legacy"
            merged["analysis_mode"] = mode
            merged["strict_iramuteq_clone"] = mode == "strict"

            merged["n_classes"] = max(2, min(20, int(self._to_number(merged.get("n_classes"), 5))))
            # min_classes is a FLOOR (default 2), never raised up to the target.
            # Forcing it to n_classes rejected legitimate native runs that emerge
            # with fewer-than-target classes (root cause of the blank-AFC bug).
            merged["min_classes"] = max(
                2,
                min(merged["n_classes"], int(self._to_number(merged.get("min_classes"), 2))),
            )
            merged["min_freq"] = max(1, int(self._to_number(merged.get("min_freq"), 2)))
            merged["classif_mode"] = max(0, min(2, int(self._to_number(merged.get("classif_mode"), 1))))
            merged["tailleuc1"] = max(5, min(200, int(self._to_number(merged.get("tailleuc1"), 12))))
            merged["tailleuc2"] = max(5, min(250, int(self._to_number(merged.get("tailleuc2"), 14))))
            merged["max_actives"] = max(0, min(30000, int(self._to_number(merged.get("max_actives"), 20000))))
            stopword_policy = str(merged.get("stopword_policy", "aggressive_pt")).strip().lower()
            if stopword_policy not in {"legacy", "aggressive_pt"}:
                stopword_policy = "aggressive_pt"
            merged["stopword_policy"] = stopword_policy
            merged["strict_stopword_filter"] = bool(merged.get("strict_stopword_filter", True))
            # Phase-1 over-segmentation DECOUPLED from the desired final count.
            # Default max(10, 2*target) so the split tree has room to grow; the
            # final class count emerges from terminal pruning, not from nbcl_p1.
            merged["nbcl_p1"] = max(
                2,
                min(50, int(self._to_number(merged.get("nbcl_p1"), max(10, 2 * merged["n_classes"])))),
            )
            merged["use_native_chd"] = bool(merged.get("use_native_chd", True))
            merged["native_fallback_legacy"] = bool(merged.get("native_fallback_legacy", True))
            merged["strict_iramuteq_clone"] = bool(merged.get("strict_iramuteq_clone", True))
            merged["auto_expand_actives"] = bool(merged.get("auto_expand_actives", True))
            merged["min_actives_floor"] = max(100, min(20000, int(self._to_number(merged.get("min_actives_floor"), 300))))
            merged["prefer_readable_afc_profiles"] = bool(merged.get("prefer_readable_afc_profiles", False))
            merged["min_visible_words"] = max(20, min(400, int(self._to_number(merged.get("min_visible_words"), 120))))
            merged["nb_per_class"] = max(10, min(400, int(self._to_number(merged.get("nb_per_class"), 80))))
            merged["max_words"] = max(30, min(1200, int(self._to_number(merged.get("max_words"), 600))))
            svd_method = str(merged.get("svd_method", "irlba")).strip().lower()
            if svd_method not in {"svdr", "irlba", "svdlibc"}:
                svd_method = "irlba"
            if svd_method == "svdr":
                svd_method = "svdR"
            merged["svd_method"] = svd_method
            method = str(merged.get("method", "ward.D2")).strip()
            if method not in {"ward.D2", "ward.D", "complete", "average"}:
                method = "ward.D2"
            merged["method"] = method
            if merged["analysis_mode"] == "strict":
                merged["use_native_chd"] = True
                merged["native_fallback_legacy"] = False
                merged["stopword_policy"] = "aggressive_pt"
                merged["strict_stopword_filter"] = True
            elif "native_fallback_legacy" not in params_dict:
                merged["native_fallback_legacy"] = True
            return merged

        if key == "wordcloud":
            merged = {
                **self.DEFAULT_ANALYSIS_DEFAULTS.get("wordcloud", {}),
                **dict(params or {}),
            }
            merged["max_words"] = max(20, min(2000, int(self._to_number(merged.get("max_words"), 100))))
            merged["min_freq"] = max(1, min(200, int(self._to_number(merged.get("min_freq"), 3))))
            merged["active_only"] = bool(merged.get("active_only", True))
            merged["use_lemmas"] = bool(merged.get("use_lemmas", True))

            allowed_palettes = {"Dark2", "Set1", "Set2", "Paired", "Pastel1"}
            colors = str(merged.get("colors", "Dark2")).strip()
            merged["colors"] = colors if colors in allowed_palettes else "Dark2"

            allowed_shapes = {
                "cardioid",
                "diamond",
                "square",
                "triangle",
                "triangle-forward",
                "triangle-upright",
                "pentagon",
                "star",
            }
            shape_aliases = {
                "circular": "square",
                "circulo": "square",
                "círculo": "square",
                "circle": "square",
                "heart": "cardioid",
                "triangulo": "triangle",
                "triângulo": "triangle",
            }
            shape = str(merged.get("shape", "square")).strip().lower()
            shape = shape_aliases.get(shape, shape)
            merged["shape"] = shape if shape in allowed_shapes else "square"

            sizing_mode = str(merged.get("sizing_mode", "area")).strip().lower()
            merged["sizing_mode"] = sizing_mode if sizing_mode in {"area", "height"} else "area"

            ecc = float(self._to_number(merged.get("eccentricity"), 0.65))
            ecc_candidates = [0.35, 0.65, 1.0]
            merged["eccentricity"] = min(ecc_candidates, key=lambda candidate: abs(candidate - ecc))

            merged["rotation_percentage"] = max(
                0.0,
                min(0.95, float(self._to_number(merged.get("rotation_percentage"), 0.1))),
            )
            merged["scale_max"] = max(12, min(80, int(self._to_number(merged.get("scale_max"), 28))))
            merged["grid_size"] = max(3, min(20, int(self._to_number(merged.get("grid_size"), 4))))
            merged["max_steps"] = max(10, min(200, int(self._to_number(merged.get("max_steps"), 60))))

            typegraph = str(merged.get("typegraph", "png")).strip().lower()
            merged["typegraph"] = typegraph if typegraph in {"png", "svg"} else "png"

            raw_width = merged.get("width")
            if raw_width not in (None, "", "None"):
                merged["width"] = max(900, min(2400, int(self._to_number(raw_width, 1200))))
            else:
                merged["width"] = None

            raw_height = merged.get("height")
            if raw_height not in (None, "", "None"):
                merged["height"] = max(900, min(2400, int(self._to_number(raw_height, 1200))))
            else:
                merged["height"] = None
            return merged

        if key == "word_tree_extra":
            merged = {
                **self.DEFAULT_ANALYSIS_DEFAULTS.get("word_tree_extra", {}),
                **dict(params or {}),
            }
            merged["keyword"] = str(merged.get("keyword", "") or "").strip()
            merged["min_freq"] = max(1, min(60, int(self._to_number(merged.get("min_freq"), 3))))
            merged["max_depth"] = max(1, min(8, int(self._to_number(merged.get("max_depth"), 4))))
            merged["min_branch_freq"] = max(1, min(200, int(self._to_number(merged.get("min_branch_freq"), 2))))
            merged["top_branches"] = max(20, min(500, int(self._to_number(merged.get("top_branches"), 120))))
            merged["use_lemmas"] = bool(merged.get("use_lemmas", True))
            merged["active_only"] = bool(merged.get("active_only", True))
            return merged

        if key == "voyant_suite":
            merged = {
                **self.DEFAULT_ANALYSIS_DEFAULTS.get("voyant_suite", {}),
                **dict(params or {}),
            }
            merged["query"] = str(merged.get("query", "") or "").strip()
            mode = str(merged.get("mode", "top") or "top").strip().lower()
            if mode not in {"top", "mixed", "query"}:
                mode = "top"
            merged["mode"] = mode
            merged["num_initial_terms"] = max(5, min(80, int(self._to_number(merged.get("num_initial_terms"), 20))))
            merged["context"] = max(2, min(20, int(self._to_number(merged.get("context"), 5))))
            merged["bins"] = max(4, min(30, int(self._to_number(merged.get("bins"), 10))))
            merged["max_docs"] = max(5, min(300, int(self._to_number(merged.get("max_docs"), 50))))
            merged["min_freq"] = max(1, min(100, int(self._to_number(merged.get("min_freq"), 2))))
            merged["max_context_rows"] = max(50, min(5000, int(self._to_number(merged.get("max_context_rows"), 800))))
            merged["use_lemmas"] = bool(merged.get("use_lemmas", True))
            merged["active_only"] = bool(merged.get("active_only", True))
            merged["remove_stopwords"] = bool(merged.get("remove_stopwords", True))
            return merged

        if key != "network_text":
            return dict(params or {})

        raw_params = dict(params or {})
        if "label_adjust_enabled" in raw_params:
            raw_params["label_adjust"] = bool(raw_params.get("label_adjust_enabled"))
        raw_params.pop("label_adjust_enabled", None)

        merged: Dict[str, Any] = {
            **self.DEFAULT_ANALYSIS_DEFAULTS.get("network_text", {}),
            **raw_params,
        }

        merged["layout"] = "forceatlas2"
        merged["layout_backend"] = "gephi_java"
        merged["strict_layout_backend"] = bool(merged.get("strict_layout_backend", True))
        merged["auto_tune"] = bool(merged.get("auto_tune", True))
        merged["render_quality_auto"] = bool(merged.get("render_quality_auto", True))
        merged["active_only"] = True
        merged["strict_stopword_filter"] = bool(merged.get("strict_stopword_filter", True))
        merged["noverlap_enabled"] = bool(merged.get("noverlap_enabled", True))
        merged["label_adjust"] = bool(merged.get("label_adjust", True))
        merged["label_hide_overlap"] = bool(merged.get("label_hide_overlap", True))
        merged["show_nodes"] = False
        merged["edge_use_community_color"] = bool(merged.get("edge_use_community_color", True))
        merged["auto_reconnect_components"] = bool(merged.get("auto_reconnect_components", True))
        merged["peripheral_enrichment"] = bool(merged.get("peripheral_enrichment", True))
        merged["label_anchor_lines"] = bool(merged.get("label_anchor_lines", True))
        merged["export_gexf"] = bool(merged.get("export_gexf", True))
        merged["export_csv"] = bool(merged.get("export_csv", True))
        merged["export_net"] = bool(merged.get("export_net", False))

        stopword_policy = str(merged.get("stopword_policy", "aggressive_pt")).strip().lower()
        if stopword_policy not in {"legacy", "aggressive_pt"}:
            stopword_policy = "aggressive_pt"
        merged["stopword_policy"] = stopword_policy

        merged["fa2_iterations"] = max(100, min(5000, int(self._to_number(merged.get("fa2_iterations"), 3000))))
        merged["fa2_scaling"] = max(0.1, min(150.0, float(self._to_number(merged.get("fa2_scaling"), 50.0))))
        merged["fa2_gravity"] = max(0.0, min(20.0, float(self._to_number(merged.get("fa2_gravity"), 0.8))))
        merged["edge_weight_quantile"] = max(
            0.0,
            min(0.99, float(self._to_number(merged.get("edge_weight_quantile"), 0.0))),
        )
        merged["candidate_min_cooc"] = max(
            1.0,
            min(20.0, float(self._to_number(merged.get("candidate_min_cooc"), 1.0))),
        )
        merged["label_density"] = max(
            0.02,
            min(1.0, float(self._to_number(merged.get("label_density"), 0.35))),
        )
        merged["label_max_count"] = max(
            20,
            min(300, int(self._to_number(merged.get("label_max_count"), 80))),
        )
        merged["label_min_keep"] = max(
            4,
            min(100, int(self._to_number(merged.get("label_min_keep"), 8))),
        )
        merged["label_size_gamma"] = max(
            0.6,
            min(2.4, float(self._to_number(merged.get("label_size_gamma"), 1.2))),
        )
        merged["label_size_boost"] = max(
            0.0,
            min(10.0, float(self._to_number(merged.get("label_size_boost"), 3.0))),
        )
        merged["label_overlap_target"] = max(
            0.04,
            min(0.65, float(self._to_number(merged.get("label_overlap_target"), 0.16))),
        )
        merged["label_anchor_line_alpha"] = max(
            0.0,
            min(0.8, float(self._to_number(merged.get("label_anchor_line_alpha"), 0.38))),
        )
        merged["label_anchor_line_width"] = max(
            0.1,
            min(3.0, float(self._to_number(merged.get("label_anchor_line_width"), 0.62))),
        )
        merged["render_quality_passes"] = max(
            1,
            min(4, int(self._to_number(merged.get("render_quality_passes"), 3))),
        )
        merged["edge_min_alpha"] = max(
            0.01,
            min(0.6, float(self._to_number(merged.get("edge_min_alpha"), 0.13))),
        )
        merged["edge_min_width"] = max(
            0.05,
            min(3.0, float(self._to_number(merged.get("edge_min_width"), 0.34))),
        )
        merged["edge_max_width"] = max(
            merged["edge_min_width"],
            min(8.0, float(self._to_number(merged.get("edge_max_width"), 1.4))),
        )
        merged["auto_reconnect_max_bridges"] = max(
            1,
            min(200, int(self._to_number(merged.get("auto_reconnect_max_bridges"), 16))),
        )
        merged["peripheral_min_degree"] = max(
            1,
            min(4, int(self._to_number(merged.get("peripheral_min_degree"), 2))),
        )
        merged["peripheral_quantile"] = max(
            0.2,
            min(0.9, float(self._to_number(merged.get("peripheral_quantile"), 0.55))),
        )
        merged["peripheral_boost_max_added"] = max(
            4,
            min(1000, int(self._to_number(merged.get("peripheral_boost_max_added"), 180))),
        )
        merged["min_freq"] = max(1, int(self._to_number(merged.get("min_freq"), 3)))
        merged["min_cooc"] = max(1, int(self._to_number(merged.get("min_cooc"), 2)))
        merged["window_size"] = max(1, int(self._to_number(merged.get("window_size"), 5)))
        merged["max_nodes"] = max(20, min(3000, int(self._to_number(merged.get("max_nodes"), 300))))
        migrated_width = int(self._to_number(merged.get("width"), 3200))
        if migrated_width < 2800:
            migrated_width = 3200
        merged["width"] = max(1200, min(5000, migrated_width))
        migrated_height = int(self._to_number(merged.get("height"), 2200))
        if migrated_height < 1800:
            migrated_height = 2200
        merged["height"] = max(900, min(5000, migrated_height))
        migrated_dpi = int(self._to_number(merged.get("dpi"), 240))
        if migrated_dpi < 240:
            migrated_dpi = 240
        merged["dpi"] = max(120, min(400, migrated_dpi))
        merged["view_trim_quantile"] = max(
            0.0,
            min(0.2, float(self._to_number(merged.get("view_trim_quantile"), 0.05))),
        )
        merged["view_pad_ratio_initial"] = max(
            0.01,
            min(0.2, float(self._to_number(merged.get("view_pad_ratio_initial"), 0.06))),
        )
        merged["view_pad_ratio_final"] = max(
            0.01,
            min(0.2, float(self._to_number(merged.get("view_pad_ratio_final"), 0.03))),
        )

        return merged

    @staticmethod
    def _normalize_similarity_coefficient(value: Any, default: int = 0) -> int:
        """Normalize similarity coefficient to IRaMuTeQ index [0..27]."""
        if isinstance(value, bool):
            return int(default)
        if isinstance(value, (int, float)):
            idx = int(value)
            return idx if 0 <= idx <= 27 else int(default)

        raw = str(value or "").strip().lower()
        if not raw:
            return int(default)
        if raw.isdigit():
            idx = int(raw)
            return idx if 0 <= idx <= 27 else int(default)

        name_to_idx = {
            "cooccurrence": 0,
            "percentual de coocorrência": 1,
            "pourcentage de cooccurrence": 1,
            "russel": 2,
            "jaccard": 3,
            "kulczynski1": 4,
            "kulczynski2": 5,
            "mountford": 6,
            "fager": 7,
            "simple matching": 8,
            "hamman": 9,
            "faith": 10,
            "tanimoto": 11,
            "dice": 12,
            "phi": 13,
            "stiles": 14,
            "michael": 15,
            "mozley": 16,
            "yule": 17,
            "yule2": 18,
            "ochiai": 19,
            "simpson": 20,
            "braun-blanquet": 21,
            "chi-squared": 22,
            "phi-squared": 23,
            "tschuprow": 24,
            "cramer": 25,
            "pearson": 26,
            "binomial": 27,
        }
        return int(name_to_idx.get(raw, default))

    @staticmethod
    def _normalize_parity_profile(value: Any, default: str = "legacy_current") -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "legacy": "legacy_current",
            "legacy_current": "legacy_current",
            "current": "legacy_current",
            "official": "official_0_8a7",
            "official_0_8a7": "official_0_8a7",
            "iramuteq_0_8a7": "official_0_8a7",
        }
        return aliases.get(raw, default)

    @staticmethod
    def _normalize_render_profile(value: Any, default: str = "publication_polish") -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "native": "native",
            "publication": "publication_polish",
            "publication_polish": "publication_polish",
            "polish": "publication_polish",
        }
        return aliases.get(raw, default)

    @staticmethod
    def _to_number(value: Any, fallback: float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return float(fallback)
