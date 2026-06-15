"""Fix A — convenção de fase 1 (nbcl_p1) e gate min_classes.

Garante que:
- nbcl_p1 é DESACOPLADO do nº de classes desejado (default max(10, 2*target));
- nbcl_p1 explícito do chamador é respeitado;
- min_classes é um PISO (default 2), nunca elevado até o target;
- o config_manager normaliza CHD com a mesma convenção.

Ver planejamentofable.md, Fase 1.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.chd_reinert import CHDAnalysis


def _normalize(cfg):
    return CHDAnalysis._normalize_class_targets(cfg)


def test_nbcl_p1_decoupled_from_target_5():
    out = _normalize({"nb_classes": 5})
    assert out["nbcl_p1"] == 10, "alvo 5 deve explorar 10 classes na fase 1"


def test_nbcl_p1_scales_with_larger_target():
    out = _normalize({"nb_classes": 8})
    assert out["nbcl_p1"] == 16, "alvo 8 -> 2*8 = 16"


def test_nbcl_p1_floor_is_ten_for_small_targets():
    out = _normalize({"nb_classes": 2})
    assert out["nbcl_p1"] == 10, "piso de 10 mesmo para alvo pequeno"


def test_explicit_nbcl_p1_is_respected():
    out = _normalize({"nb_classes": 5, "nbcl_p1": 12})
    assert out["nbcl_p1"] == 12, "nbcl_p1 explícito não pode ser sobrescrito"


def test_min_classes_defaults_to_floor_not_target():
    out = _normalize({"nb_classes": 5})
    assert out["min_classes"] == 2, "min_classes é piso (2), não o alvo"


def test_min_classes_never_exceeds_target():
    # Mesmo pedindo um piso alto, não pode ultrapassar o alvo.
    out = _normalize({"nb_classes": 4, "min_classes": 9})
    assert out["min_classes"] <= 4
    assert out["min_classes"] >= 2


def test_explicit_min_classes_within_range_is_respected():
    out = _normalize({"nb_classes": 6, "min_classes": 3})
    assert out["min_classes"] == 3


def test_default_params_have_corrected_convention():
    assert CHDAnalysis.DEFAULT_PARAMS["nbcl_p1"] == 10
    assert CHDAnalysis.DEFAULT_PARAMS["min_classes"] == 2


def test_config_manager_chd_normalization_matches_convention():
    from src.core.config_manager import ConfigManager

    try:
        cm = ConfigManager()
    except TypeError:
        pytest.skip("ConfigManager requer argumentos de construção neste ambiente")

    normalize = getattr(cm, "_sanitize_analysis_params", None)
    if normalize is None:
        pytest.skip("ConfigManager._sanitize_analysis_params indisponível")

    out = normalize("chd", {"n_classes": 5})
    assert out["nbcl_p1"] == 10
    assert out["min_classes"] == 2
