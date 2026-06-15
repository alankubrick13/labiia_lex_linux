"""Official IRaMuTeQ 0.8a7 defaults and clone-mode helpers."""

from __future__ import annotations

from configparser import ConfigParser
from functools import lru_cache
from typing import Any, Dict

from ..utils.paths import PathManager

OFFICIAL_PARITY_PROFILE = "official_0_8a7"
OFFICIAL_RENDER_PROFILE = "native"
LEGACY_PARITY_PROFILE = "legacy_current"
LEGACY_RENDER_PROFILE = "publication_polish"

_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "chd": {
        "analysis_mode": "strict",
        "parity_profile": OFFICIAL_PARITY_PROFILE,
        "render_profile": OFFICIAL_RENDER_PROFILE,
        "nb_classes": 4,
        "min_freq": 2,
        "min_uce": 0,
        "classif_mode": 1,
        "tailleuc1": 12,
        "tailleuc2": 14,
        "max_actives": 20000,
        "nbcl_p1": 10,
        "svd_method": "irlba",
        "mode_patate": False,
        "width": 400,
        "height": 400,
        "typegraph": "png",
        "strict_iramuteq_clone": True,
        "use_native_chd": True,
        "native_fallback_legacy": False,
    },
    "similarity": {
        "analysis_mode": "strict",
        "parity_profile": OFFICIAL_PARITY_PROFILE,
        "render_profile": OFFICIAL_RENDER_PROFILE,
        "layout": "frutch",
        "min_freq": 3,
        "coefficient": 0,
        "arbremax": True,
        "detect_communities": False,
        "show_halo": False,
        "show_edge_labels": False,
        "cexalpha": False,
        "vertex_scaling": "frequency",
        "renderer_backend": "iramuteq_r",
        "coeff_tv": True,
        "tvmin": 5,
        "tvmax": 30,
        "vcex": True,
        "vcexmin": 10,
        "vcexmax": 25,
        "label_v": True,
        "seuil_ok": False,
        "seuil": 1,
        "edge_curved": False,
        "width": 1000,
        "height": 1000,
        "strict_iramuteq_style": True,
        "selected_words": [],
    },
}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return int(default)


@lru_cache(maxsize=1)
def load_official_iramuteq_defaults() -> Dict[str, Dict[str, Any]]:
    """Load official defaults from the vendored/installed IRaMuTeQ configs."""
    resolved = {
        key: dict(values)
        for key, values in _DEFAULTS.items()
    }
    config_dir = PathManager.official_configuration_dir()

    reinert_cfg = config_dir / "reinert.cfg"
    if reinert_cfg.exists():
        parser = ConfigParser()
        parser.optionxform = str
        parser.read(reinert_cfg, encoding="utf-8")
        if parser.has_section("ALCESTE"):
            section = parser["ALCESTE"]
            resolved["chd"].update(
                {
                    "nb_classes": _as_int(section.get("nbcl"), resolved["chd"]["nb_classes"]),
                    "min_uce": _as_int(section.get("mincl"), resolved["chd"]["min_uce"]),
                    "min_freq": _as_int(section.get("minforme"), resolved["chd"]["min_freq"]),
                    "classif_mode": _as_int(section.get("classif_mode"), resolved["chd"]["classif_mode"]),
                    "tailleuc1": _as_int(section.get("tailleuc1"), resolved["chd"]["tailleuc1"]),
                    "tailleuc2": _as_int(section.get("tailleuc2"), resolved["chd"]["tailleuc2"]),
                    "max_actives": _as_int(section.get("max_actives"), resolved["chd"]["max_actives"]),
                    "nbcl_p1": _as_int(section.get("nbcl_p1"), resolved["chd"]["nbcl_p1"]),
                    "svd_method": str(section.get("svdmethod", resolved["chd"]["svd_method"])).strip(),
                    "mode_patate": _as_bool(section.get("mode.patate"), resolved["chd"]["mode_patate"]),
                }
            )
        if parser.has_section("IMAGE"):
            section = parser["IMAGE"]
            resolved["chd"]["width"] = _as_int(section.get("width"), resolved["chd"]["width"])
            resolved["chd"]["height"] = _as_int(section.get("heigth"), resolved["chd"]["height"])

    simi_cfg = config_dir / "simitxt.cfg"
    if simi_cfg.exists():
        parser = ConfigParser()
        parser.optionxform = str
        parser.read(simi_cfg, encoding="utf-8")
        if parser.has_section("simitxt"):
            section = parser["simitxt"]
            layout_code = _as_int(section.get("layout"), 2)
            layout_name = {
                0: "random",
                1: "circle",
                2: "frutch",
                3: "kawa",
                4: "graphopt",
                5: "spirale",
                6: "spirale3D",
            }.get(layout_code, "frutch")
            resolved["similarity"].update(
                {
                    "layout": layout_name,
                    "min_freq": _as_int(section.get("eff_min_forme"), resolved["similarity"]["min_freq"]),
                    "coefficient": _as_int(section.get("coeff"), resolved["similarity"]["coefficient"]),
                    "arbremax": _as_bool(section.get("arbremax"), resolved["similarity"]["arbremax"]),
                    "show_edge_labels": _as_bool(section.get("label_e"), resolved["similarity"]["show_edge_labels"]),
                    "coeff_tv": _as_bool(section.get("coeff_tv"), resolved["similarity"]["coeff_tv"]),
                    "tvmin": _as_int(section.get("tvmin"), resolved["similarity"]["tvmin"]),
                    "tvmax": _as_int(section.get("tvmax"), resolved["similarity"]["tvmax"]),
                    "vcex": _as_bool(section.get("vcex"), resolved["similarity"]["vcex"]),
                    "vcexmin": _as_int(section.get("vcexmin"), resolved["similarity"]["vcexmin"]),
                    "vcexmax": _as_int(section.get("vcexmax"), resolved["similarity"]["vcexmax"]),
                    "label_v": _as_bool(section.get("label_v"), resolved["similarity"]["label_v"]),
                    "seuil_ok": _as_bool(section.get("seuil_ok"), resolved["similarity"]["seuil_ok"]),
                    "seuil": _as_int(section.get("seuil"), resolved["similarity"]["seuil"]),
                    "width": _as_int(section.get("width"), resolved["similarity"]["width"]),
                    "height": _as_int(section.get("height"), resolved["similarity"]["height"]),
                    "edge_curved": _as_bool(section.get("edgecurved"), False),
                }
            )

    return resolved


def official_defaults_for(analysis_type: str) -> Dict[str, Any]:
    """Return a copy of the official IRaMuTeQ defaults for one analysis."""
    key = str(analysis_type or "").strip().lower()
    return dict(load_official_iramuteq_defaults().get(key, {}))
